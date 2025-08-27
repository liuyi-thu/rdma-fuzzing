// rdma_client_pairs_multi_demo.cpp  (runtime-dependent, simplified)
// Build:
//   g++ -O2 -std=c++17 rdma_client_pairs_multi_demo.cpp \
//       pair_runtime.cpp runtime_resolver.c cJSON.c \
//       -libverbs -pthread -o rdma_client_pairs_multi_demo
//
// Run:
//   export RDMA_FUZZ_RUNTIME=/path/to/client_view.json
//   ./rdma_client_pairs_multi_demo --pairs 4 --client-update client_update.json --server-ids srv0,srv1 --parallel
//
// This version delegates coordination, hot-reload and by-id lookups to pair_runtime.*.

#include <infiniband/verbs.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <thread>
#include <vector>
#include <string>
#include <sstream>
#include <algorithm>
#include <unistd.h>
#include <iostream>

#include "pair_runtime.h" // our runtime helpers

using std::string;
using std::vector;

static const int IB_PORT = 1;
static const int MSG_SIZE = 1024;

static void die(const char *m)
{
    perror(m);
    exit(1);
}

static vector<string> split_csv(const string &s)
{
    vector<string> out;
    std::stringstream ss(s);
    string item;
    while (std::getline(ss, item, ','))
    {
        if (!item.empty())
            out.push_back(item);
    }
    return out;
}

// -------------------- verbs helpers --------------------
static ibv_qp *create_qp(ibv_pd *pd, ibv_cq *cq)
{
    ibv_qp_init_attr a;
    memset(&a, 0, sizeof(a));
    a.send_cq = cq;
    a.recv_cq = cq;
    a.cap = {.max_send_wr = 64, .max_recv_wr = 64, .max_send_sge = 4, .max_recv_sge = 4, .max_inline_data = 0};
    a.qp_type = IBV_QPT_RC;
    a.sq_sig_all = 0;
    ibv_qp *qp = ibv_create_qp(pd, &a);
    if (!qp)
        die("ibv_create_qp");
    return qp;
}
static int to_init(ibv_qp *qp, uint8_t port)
{
    ibv_qp_attr a;
    memset(&a, 0, sizeof(a));
    a.qp_state = IBV_QPS_INIT;
    a.pkey_index = 0;
    a.port_num = port;
    a.qp_access_flags = IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE;
    int flags = IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS;
    return ibv_modify_qp(qp, &a, flags);
}
static int to_rtr(ibv_qp *qp, uint32_t dest_qpn, uint16_t dlid, const uint8_t dgid[16], uint8_t port, uint32_t rq_psn)
{
    ibv_qp_attr a;
    memset(&a, 0, sizeof(a));
    a.qp_state = IBV_QPS_RTR;
    a.path_mtu = IBV_MTU_1024;
    a.dest_qp_num = dest_qpn;
    a.rq_psn = rq_psn;
    a.max_dest_rd_atomic = 1;
    a.min_rnr_timer = 12;
    a.ah_attr.is_global = 1;
    a.ah_attr.sl = 0;
    a.ah_attr.src_path_bits = 0;
    a.ah_attr.port_num = port;
    a.ah_attr.dlid = dlid;
    a.ah_attr.grh.hop_limit = 1;
    a.ah_attr.grh.traffic_class = 0;
    a.ah_attr.grh.flow_label = 0;
    a.ah_attr.grh.sgid_index = 1;
    memcpy(a.ah_attr.grh.dgid.raw, dgid, 16);
    int flags = IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER;
    return ibv_modify_qp(qp, &a, flags);
}
static int to_rts(ibv_qp *qp, uint32_t sq_psn)
{
    ibv_qp_attr a;
    memset(&a, 0, sizeof(a));
    a.qp_state = IBV_QPS_RTS;
    a.timeout = 14;
    a.retry_cnt = 7;
    a.rnr_retry = 7;
    a.sq_psn = sq_psn;
    a.max_rd_atomic = 1;
    int flags = IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC;
    return ibv_modify_qp(qp, &a, flags);
}

struct PairCtx
{
    string cli_id, srv_id, pair_id;
    ibv_qp *qp = nullptr;
    ibv_mr *mr = nullptr;
    void *sbuf = nullptr;
    bool ready = false;
};

// -------------------- main --------------------
int main(int argc, char **argv)
{
    int pairs = 2;
    string client_update_path = "client_update.json";
    string server_ids_csv = ""; // "srv0,srv1"
    bool parallel = false;

    for (int i = 1; i < argc; ++i)
    {
        string a = argv[i];
        if (a == "--pairs" && i + 1 < argc)
        {
            pairs = atoi(argv[++i]);
        }
        else if (a == "--client-update" && i + 1 < argc)
        {
            client_update_path = argv[++i];
        }
        else if (a == "--server-ids" && i + 1 < argc)
        {
            server_ids_csv = argv[++i];
        }
        else if (a == "--parallel")
        {
            parallel = true;
        }
        else if (a == "-h" || a == "--help")
        {
            fprintf(stderr,
                    "Usage: %s [--pairs N] [--client-update PATH] [--server-ids srv0,srv1,...] [--parallel]\n", argv[0]);
            return 0;
        }
    }

    const char *BUNDLE_ENV = "RDMA_FUZZ_RUNTIME";
    pr_init(BUNDLE_ENV); // inotify + 初次加载视图

    // IB setup
    int num = 0;
    ibv_device **dev_list = ibv_get_device_list(&num);
    if (!dev_list || num <= 0)
        die("ibv_get_device_list");
    ibv_context *ctx = ibv_open_device(dev_list[0]);
    if (!ctx)
        die("ibv_open_device");
    ibv_pd *pd = ibv_alloc_pd(ctx);
    if (!pd)
        die("ibv_alloc_pd");
    ibv_cq *cq = ibv_create_cq(ctx, 512, nullptr, nullptr, 0);
    if (!cq)
        die("ibv_create_cq");

    // get local GID (for simplicity we use a fixed GID string "00:00:...:00" in PR_QP)
    // however, real GID is queried here to ensure the device/port actually has one
    union ibv_gid my_gid;
    memset(&my_gid, 0, sizeof(my_gid));
    (void)ibv_query_gid(ctx, IB_PORT, 1, &my_gid);
    // get local LID if needed (optional)

    vector<string> srv_ids = split_csv(server_ids_csv);
    vector<PairCtx> P;
    P.reserve(pairs);

    // local resource description for pair_runtime writers
    vector<PR_QP> qps;
    vector<PR_MR> mrs;
    vector<PR_Pair> prs;

    // create local pairs
    for (int i = 0; i < pairs; ++i)
    {
        PairCtx pc;
        pc.cli_id = "cli" + std::to_string(i);
        pc.srv_id = srv_ids.empty() ? ("srv" + std::to_string(i)) : srv_ids[i % srv_ids.size()];
        pc.pair_id = "pair-" + pc.cli_id + "-" + pc.srv_id;

        pc.qp = create_qp(pd, cq);
        if (to_init(pc.qp, IB_PORT))
            die("to_init");

        pc.sbuf = aligned_alloc(4096, MSG_SIZE);
        if (!pc.sbuf)
            die("aligned_alloc");
        memset(pc.sbuf, 0, MSG_SIZE);
        pc.mr = ibv_reg_mr(pd, pc.sbuf, MSG_SIZE, IBV_ACCESS_LOCAL_WRITE);
        if (!pc.mr)
            die("ibv_reg_mr");

        // fill PR_* for runtime view writing
        P.push_back(pc);

        PR_QP q{P[i].cli_id.c_str(), P[i].qp->qp_num, 0, (uint8_t)IB_PORT, 0, "00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00"};
        snprintf(q.gid, sizeof(q.gid),
                 "%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x",
                 my_gid.raw[0], my_gid.raw[1], my_gid.raw[2], my_gid.raw[3], my_gid.raw[4], my_gid.raw[5], my_gid.raw[6], my_gid.raw[7], my_gid.raw[8], my_gid.raw[9], my_gid.raw[10], my_gid.raw[11], my_gid.raw[12], my_gid.raw[13], my_gid.raw[14], my_gid.raw[15]);
        // std::cout << q.id << " gid: " << q.gid << " len: " << strlen(q.gid) << std::endl;
        PR_MR m{("sbuf_" + P[i].cli_id).c_str(), (uint64_t)P[i].mr->addr, (uint32_t)MSG_SIZE, P[i].mr->lkey};
        PR_Pair pr{P[i].pair_id.c_str(), P[i].cli_id.c_str(), P[i].srv_id.c_str()};
        std::cout << q.id << " " << m.id << " " << pr.id << " -> " << pr.srv_id << std::endl;

        qps.push_back(q);
        std::cout << qps[i].id << " gid: " << qps[i].gid << " len: " << strlen(qps[i].gid) << std::endl;
        mrs.push_back(m);
        prs.push_back(pr);
        //
    }
    // std::cout << qps[2].id << " gid: " << qps[2].gid << " len: " << strlen(qps[2].gid) << std::endl;
    // initial CLAIMED for all pairs
    pr_write_client_update_claimed(client_update_path.c_str(),
                                   qps.data(), (int)qps.size(),
                                   mrs.data(), (int)mrs.size(),
                                   prs.data(), (int)prs.size());
    // std::cout << qps[2].id << " gid: " << qps[2].gid << " len: " << strlen(qps[2].gid) << std::endl;
    // // exit(0); // DEBUG

    auto bring_up_one = [&](PairCtx &pc)
    {
        // 1) 等待服务端 RTS（BOTH_RTS）
        if (!pr_wait_pair_state(BUNDLE_ENV, pc.pair_id.c_str(), "BOTH_RTS", /*timeout_ms=*/15000))
        {
            fprintf(stderr, "[cli] %s: timeout waiting BOTH_RTS\n", pc.pair_id.c_str());
            return;
        }
        // 2) 解析远端 QP 参数
        uint32_t rqpn = 0, rpsn = 0;
        uint16_t rlid = 0;
        uint8_t rgid[16]{0};
        uint8_t rport = IB_PORT;
        if (!pr_resolve_remote_qp(pc.srv_id.c_str(), &rqpn, &rpsn, &rlid, rgid, &rport))
        {
            fprintf(stderr, "[cli] %s: resolve remote QP failed\n", pc.pair_id.c_str());
            return;
        }
        // 3) 本地 RTR/RTS
        if (to_rtr(pc.qp, rqpn, rlid, rgid, rport, rpsn))
            die("to_rtr");
        if (to_rts(pc.qp, 0))
            die("to_rts");

        // 4) 宣告 READY（注意写入整个数组，包含所有 pair 当前状态）
        pc.ready = true;
        // 更新 prs 中该 pair 的状态 —— 这里简化：ready 标记只用于 gate；写文件调用还是“READY”覆盖全部 pairs（服务端只看 state=READY 的那些 pair）
        pr_write_client_update_ready(client_update_path.c_str(),
                                     qps.data(), (int)qps.size(),
                                     mrs.data(), (int)mrs.size(),
                                     prs.data(), (int)prs.size());

        // 5) 发一条 SEND（可按需扩展 RDMA READ/WRITE/ATOMIC）
        uint64_t *p64 = (uint64_t *)pc.sbuf;
        p64[0] = 0xA5A5A5A500000000ULL | (uint64_t)(pc.qp->qp_num & 0xFFFF);
        ibv_sge sge;
        memset(&sge, 0, sizeof(sge));
        sge.addr = (uintptr_t)pc.sbuf;
        sge.length = 16;
        sge.lkey = pc.mr->lkey;
        ibv_send_wr wr;
        memset(&wr, 0, sizeof(wr));
        wr.sg_list = &sge;
        wr.num_sge = 1;
        wr.opcode = IBV_WR_SEND;
        wr.send_flags = IBV_SEND_SIGNALED;
        ibv_send_wr *bad = nullptr;
        if (ibv_post_send(pc.qp, &wr, &bad))
            die("ibv_post_send");
    };

    if (parallel)
    {
        vector<std::thread> th;
        th.reserve(P.size());
        for (auto &pc : P)
            th.emplace_back([&](PairCtx &ref)
                            { bring_up_one(ref); }, std::ref(pc));
        for (auto &t : th)
            t.join();
    }
    else
    {
        for (auto &pc : P)
            bring_up_one(pc);
    }

    // poll completions briefly（可选）
    ibv_wc wc[32];
    int left = (int)P.size();
    int spins = 10000; // ~10ms
    while (left > 0 && spins-- > 0)
    {
        int n = ibv_poll_cq(cq, 32, wc);
        for (int i = 0; i < n; ++i)
        {
            if (wc[i].status == IBV_WC_SUCCESS)
                --left;
        }
        if (n <= 0)
            usleep(1000);
    }

    // cleanup
    for (auto &pc : P)
    {
        if (pc.mr)
            ibv_dereg_mr(pc.mr);
        if (pc.sbuf)
            free(pc.sbuf);
        if (pc.qp)
            ibv_destroy_qp(pc.qp);
    }
    ibv_destroy_cq(cq);
    ibv_dealloc_pd(pd);
    // close device (skip device_list cleanup for brevity)
    return 0;
}
