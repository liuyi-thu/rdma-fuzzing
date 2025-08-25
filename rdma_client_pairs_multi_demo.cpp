// rdma_client_pairs_multi_demo.cpp
// Multi-QP client: claim N pairs, wait BOTH_RTS, push READY, then send on each QP.
// Default: sequential bring-up (safe). Optionally --parallel to stress server pairing.
//
// Build:
//   g++ -O2 -std=c++17 rdma_client_pairs_multi_demo.cpp runtime_resolver.c cJSON.c -libverbs -pthread -o rdma_client_pairs_multi_demo
//
// Run (example):
//   export RDMA_FUZZ_RUNTIME=/path/to/client_view.json
//   ./rdma_client_pairs_multi_demo --pairs 4 --client-update client_update.json --server-ids srv0,srv1
//
// Notes:
// - Uses inotify to hot-reload the BUNDLE file (RDMA_FUZZ_RUNTIME).
// - Writes a single client_update.json containing all local QP/MR/pairs entries (atomic write).
// - Gate sending by pair state = READY.
//
// Requires runtime_resolver.{c,h} with helpers:
//   rr_load_from_env_or_die, rr_has, rr_u32_by_id, rr_try_u32_by_id, rr_try_str_by_id, rr_try_u32, rr_try_str
//
// ©

#include <infiniband/verbs.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/inotify.h>
#include <libgen.h>
#include <errno.h>

#include <string>
#include <vector>
#include <thread>
#include <mutex>
#include <chrono>
#include <sstream>
#include <iostream>
#include <algorithm>

#include <cjson/cJSON.h>

extern "C"
{
#include "runtime_resolver.h"
}

using std::string;
using std::vector;

static const int IB_PORT = 1;
static const int MSG_SIZE = 1024;

static uint64_t now_ms()
{
    using namespace std::chrono;
    return duration_cast<milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

// -------------------- runtime resolver lock (to serialize reload/reads) --------------------
static std::mutex g_rr_mtx;
struct RRLock
{
    RRLock() { g_rr_mtx.lock(); }
    ~RRLock() { g_rr_mtx.unlock(); }
};
static inline void rr_reload_locked(const char *env)
{
    RRLock lk;
    rr_load_from_env_or_die(env);
}

// -------------------- inotify reloader --------------------
struct InotifyReloader
{
    int fd = -1;
    int wd = -1;
    string watch_dir;
    string watch_base;
    bool init_from_env(const char *env_key)
    {
        const char *p = getenv(env_key);
        if (!p)
            return false;
        char buf[1024];
        snprintf(buf, sizeof(buf), "%s", p);
        char *dirc = strdup(buf);
        char *basec = strdup(buf);
        watch_dir = dirname(dirc);
        watch_base = basename(basec);
        free(dirc);
        free(basec);
        fd = inotify_init1(IN_NONBLOCK);
        if (fd < 0)
            return false;
        wd = inotify_add_watch(fd, watch_dir.c_str(), IN_CLOSE_WRITE | IN_MOVED_TO | IN_ATTRIB);
        if (wd < 0)
        {
            close(fd);
            fd = -1;
            return false;
        }
        return true;
    }
    bool pump_and_reload(const char *env_key)
    {
        if (fd < 0)
            return false;
        char buf[4096];
        ssize_t n = read(fd, buf, sizeof(buf));
        if (n <= 0)
            return false;
        size_t i = 0;
        bool reload = false;
        while (i < (size_t)n)
        {
            auto *ev = (struct inotify_event *)(buf + i);
            if (ev->len > 0 && (ev->mask & (IN_CLOSE_WRITE | IN_MOVED_TO | IN_ATTRIB)))
            {
                if (watch_base == ev->name)
                    reload = true;
            }
            i += sizeof(struct inotify_event) + ev->len;
        }
        if (reload)
        {
            rr_reload_locked(env_key);
            return true;
        }
        return false;
    }
};

// -------------------- verbs helpers --------------------
static void die(const char *m)
{
    perror(m);
    exit(1);
}

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

// -------------------- client update I/O --------------------
struct PairCtx
{
    string cli_id;
    string srv_id; // hint which server slot to pair
    string pair_id;
    ibv_qp *qp = nullptr;
    ibv_mr *mr = nullptr;
    void *sbuf = nullptr;
    bool ready = false;
};

static void atomic_write_json(const char *path, cJSON *root)
{
    char tmp[512];
    snprintf(tmp, sizeof(tmp), "%s.tmp", path);
    FILE *f = fopen(tmp, "w");
    if (!f)
    {
        perror("open tmp");
        return;
    }
    char *txt = cJSON_PrintBuffered(root, 1 << 20, 1);
    fputs(txt, f);
    fclose(f);
    free(txt);
    if (rename(tmp, path) != 0)
    {
        printf("%s\n", tmp);
        perror("rename");
    }
}

static void write_client_update_many(const char *path, const vector<PairCtx> &pairs, const uint8_t gid[16])
{
    cJSON *root = cJSON_CreateObject();
    cJSON *local = cJSON_AddObjectToObject(root, "local");
    cJSON *arr_qp = cJSON_AddArrayToObject(local, "QP");
    cJSON *arr_mr = cJSON_AddArrayToObject(local, "MR");
    cJSON *arr_pairs = cJSON_AddArrayToObject(local, "pairs");

    char gid_str[64];
    snprintf(gid_str, sizeof(gid_str),
             "%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x",
             gid[0], gid[1], gid[2], gid[3], gid[4], gid[5], gid[6], gid[7], gid[8], gid[9], gid[10], gid[11], gid[12], gid[13], gid[14], gid[15]);

    for (auto &p : pairs)
    {
        // QP
        if (p.qp)
        {
            cJSON *q = cJSON_CreateObject();
            cJSON_AddStringToObject(q, "id", p.cli_id.c_str());
            cJSON_AddNumberToObject(q, "qpn", p.qp->qp_num);
            cJSON_AddNumberToObject(q, "psn", 0);
            cJSON_AddNumberToObject(q, "port", IB_PORT);
            cJSON_AddNumberToObject(q, "lid", 0);
            cJSON_AddStringToObject(q, "gid", gid_str);
            cJSON_AddItemToArray(arr_qp, q);
        }
        // MR
        if (p.mr)
        {
            cJSON *m = cJSON_CreateObject();
            std::string mid = "sbuf_" + p.cli_id;
            cJSON_AddStringToObject(m, "id", mid.c_str());
            cJSON_AddNumberToObject(m, "addr", (double)(uintptr_t)p.mr->addr);
            cJSON_AddNumberToObject(m, "length", MSG_SIZE);
            cJSON_AddNumberToObject(m, "lkey", p.mr->lkey);
            cJSON_AddItemToArray(arr_mr, m);
        }
        // pair entry
        cJSON *pe = cJSON_CreateObject();
        cJSON_AddStringToObject(pe, "id", p.pair_id.c_str());
        cJSON_AddStringToObject(pe, "cli_id", p.cli_id.c_str());
        cJSON_AddStringToObject(pe, "srv_id", p.srv_id.c_str());
        cJSON_AddStringToObject(pe, "state", p.ready ? "READY" : "CLAIMED");
        cJSON_AddNumberToObject(pe, "ts", (double)now_ms());
        cJSON_AddItemToArray(arr_pairs, pe);
    }
    atomic_write_json(path, root);
    cJSON_Delete(root);
}

// wait until pairs[id].state == expect_state
static bool wait_state(const char *env_key, const string &pair_id, const char *expect_state, int timeout_ms, InotifyReloader *rld)
{
    uint64_t deadline = now_ms() + timeout_ms;
    while ((int)(now_ms() - deadline) < 0)
    {
        if (rld)
            rld->pump_and_reload(env_key);
        else
            rr_reload_locked(env_key);
        {
            RRLock lk;
            for (int i = 0;; ++i)
            {
                char key[128];
                snprintf(key, sizeof(key), "pairs[%d].id", i);
                if (!rr_has(key))
                    break;
                const char *id = rr_str(key);
                if (id && pair_id == id)
                {
                    snprintf(key, sizeof(key), "pairs[%d].state", i);
                    const char *st = rr_str(key);
                    if (st && !strcmp(st, expect_state))
                        return true;
                }
            }
        }
        usleep(1000); // 1ms
    }
    return false;
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

int main(int argc, char **argv)
{
    // Args
    int pairs = 2;
    string client_update_path = "client_update.json";
    string server_ids_csv = ""; // "srv0,srv1"
    bool parallel = false;
    // default arguments

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
    rr_reload_locked(BUNDLE_ENV);
    InotifyReloader rld;
    rld.init_from_env(BUNDLE_ENV);

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
    union ibv_gid my_gid;
    memset(&my_gid, 0, sizeof(my_gid));
    (void)ibv_query_gid(ctx, IB_PORT, 1, &my_gid);

    // Prepare pairs
    vector<string> srv_ids = split_csv(server_ids_csv); // srv0, srv1, ... （对应的都是QP）
    vector<PairCtx> P;
    P.reserve(pairs);
    for (int i = 0; i < pairs; ++i)
    {
        PairCtx pc;
        pc.cli_id = "cli" + std::to_string(i);
        pc.srv_id = srv_ids.empty() ? "srv" + std::to_string(i) : srv_ids[i % srv_ids.size()];
        pc.pair_id = "pair-" + pc.cli_id + "-" + pc.srv_id; // 比如cli0-srv0
        std::cout << "make a pair:" << pc.pair_id << " (cli_id=" << pc.cli_id << ", srv_id=" << pc.srv_id << ")\n";
        // QP貌似必须是一对一的？
        // create QP + MR
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
        P.push_back(pc);
    }

    // Initial CLAIMED for all pairs
    write_client_update_many(client_update_path.c_str(), P, my_gid.raw);

    auto bring_up_one = [&](PairCtx &pc)
    {
        // 1) wait BOTH_RTS from server
        if (!wait_state(BUNDLE_ENV, pc.pair_id, "BOTH_RTS", /*timeout_ms=*/15000, &rld))
        {
            fprintf(stderr, "[cli] %s: timeout waiting BOTH_RTS\n", pc.pair_id.c_str());
            return;
        }
        // 2) read remote QP params
        uint32_t rqpn = 0, rpsn = 0, rport = IB_PORT;
        uint16_t rlid = 0;
        uint8_t rgid[16]{0};
        {
            RRLock lk;
            // prefer by-id
            if (rr_has("remote.ids.QP[0]"))
            {
                rqpn = rr_u32_by_id("remote.QP", pc.srv_id.c_str(), "qpn");
                rpsn = rr_try_u32_by_id("remote.QP", pc.srv_id.c_str(), "psn", 0);
                rport = rr_try_u32_by_id("remote.QP", pc.srv_id.c_str(), "port", IB_PORT);
                rlid = (uint16_t)rr_try_u32_by_id("remote.QP", pc.srv_id.c_str(), "lid", 0);
                const char *g = rr_try_str_by_id("remote.QP", pc.srv_id.c_str(), "gid", "00:...:00");
                // parse gid "xx:..:xx" into 16 bytes
                unsigned int bb[16] = {0};
                if (sscanf(g,
                           "%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x",
                           &bb[0], &bb[1], &bb[2], &bb[3], &bb[4], &bb[5], &bb[6], &bb[7], &bb[8], &bb[9], &bb[10], &bb[11], &bb[12], &bb[13], &bb[14], &bb[15]) == 16)
                {
                    for (int i = 0; i < 16; ++i)
                        rgid[i] = (uint8_t)bb[i];
                }
            }
            else
            {
                // fallback: first remote
                rqpn = rr_u32("remote.QP[0].qpn");
                rpsn = rr_try_u32("remote.QP[0].psn", 0);
                rport = rr_try_u32("remote.QP[0].port", IB_PORT);
                rlid = (uint16_t)rr_try_u32("remote.QP[0].lid", 0);
                const char *g = rr_try_str("remote.QP[0].gid", "00:...:00");
                unsigned int bb[16] = {0};
                if (sscanf(g,
                           "%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x",
                           &bb[0], &bb[1], &bb[2], &bb[3], &bb[4], &bb[5], &bb[6], &bb[7], &bb[8], &bb[9], &bb[10], &bb[11], &bb[12], &bb[13], &bb[14], &bb[15]) == 16)
                {
                    for (int i = 0; i < 16; ++i)
                        rgid[i] = (uint8_t)bb[i];
                }
            }
        }
        // 3) local RTR/RTS
        if (to_rtr(pc.qp, rqpn, rlid, rgid, rport, rpsn))
            die("to_rtr");
        if (to_rts(pc.qp, 0))
            die("to_rts");
        // 4) push READY and write update
        pc.ready = true;
        write_client_update_many(client_update_path.c_str(), P, my_gid.raw);
        // 5) send one message
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
        // parallel bring-up
        vector<std::thread> th;
        for (auto &pc : P)
        {
            th.emplace_back([&](PairCtx &ref)
                            { bring_up_one(ref); }, std::ref(pc));
        }
        for (auto &t : th)
            t.join();
    }
    else
    {
        // sequential bring-up
        for (auto &pc : P)
            bring_up_one(pc);
    }

    // poll CQs until all pairs got a completion (or small timeout)
    int need = pairs;
    uint64_t deadline = now_ms() + 10000;
    while (need > 0 && (int)(now_ms() - deadline) < 0)
    {
        ibv_wc wc[32];
        int n = ibv_poll_cq(cq, 32, wc);
        if (n < 0)
            die("ibv_poll_cq");
        for (int i = 0; i < n; ++i)
        {
            if (wc[i].status == IBV_WC_SUCCESS)
            {
                fprintf(stdout, "[cli] SEND completed, qp=%u wr_id=%llu len=%u\n", wc[i].qp_num,
                        (unsigned long long)wc[i].wr_id, wc[i].byte_len);
                --need;
            }
            else
            {
                fprintf(stderr, "[cli] WC error: status=%d opcode=%d\n", wc[i].status, wc[i].opcode);
            }
        }
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
    ibv_close_device(ctx); // simplified demo
    return 0;
}
