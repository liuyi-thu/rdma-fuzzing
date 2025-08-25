// rdma_client_pairs_demo.cpp
// Minimal client that claims a pair, waits for BOTH_RTS, moves to READY, and sends one message.
// Build:
//   g++ -O2 -std=c++17 rdma_client_pairs_demo.cpp runtime_resolver.c cJSON.c -libverbs -o rdma_client_pairs_demo
// Run:
//   export RDMA_FUZZ_RUNTIME=/path/to/client_view.json
//   ./rdma_client_pairs_demo

#include <infiniband/verbs.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/inotify.h>
#include <libgen.h>

#include <string>
#include <chrono>

#include <cjson/cJSON.h>

extern "C"
{
#include "runtime_resolver.h"
}

using std::string;

static const int IB_PORT = 1;
static const int MSG_SIZE = 1024;

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
            rr_load_from_env_or_die(env_key);
            return true;
        }
        return false;
    }
};

static void die(const char *m)
{
    perror(m);
    exit(1);
}
static uint64_t now_ms()
{
    using namespace std::chrono;
    return duration_cast<milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
static int parse_gid_str_colon(const char *s, uint8_t out[16])
{
    if (!s)
        return -1;
    unsigned int b[16];
    int n = sscanf(s, "%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x",
                   &b[0], &b[1], &b[2], &b[3], &b[4], &b[5], &b[6], &b[7], &b[8], &b[9], &b[10], &b[11], &b[12], &b[13], &b[14], &b[15]);
    if (n != 16)
        return -1;
    for (int i = 0; i < 16; ++i)
        out[i] = (uint8_t)b[i];
    return 0;
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

static void write_client_update(const char *path, const char *cli_id, ibv_qp *qp, ibv_mr *mr, const char *pair_id, const char *srv_hint, const char *state, const uint8_t gid[16])
{
    cJSON *root = cJSON_CreateObject();
    cJSON *local = cJSON_AddObjectToObject(root, "local");
    cJSON *arr_qp = cJSON_AddArrayToObject(local, "QP");
    cJSON *arr_mr = cJSON_AddArrayToObject(local, "MR");
    cJSON *pairs = cJSON_AddArrayToObject(local, "pairs");

    char gid_str[64];
    snprintf(gid_str, sizeof(gid_str),
             "%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x",
             gid[0], gid[1], gid[2], gid[3], gid[4], gid[5], gid[6], gid[7], gid[8], gid[9], gid[10], gid[11], gid[12], gid[13], gid[14], gid[15]);

    // local QP
    cJSON *q = cJSON_CreateObject();
    cJSON_AddStringToObject(q, "id", cli_id);
    cJSON_AddNumberToObject(q, "qpn", qp->qp_num);
    cJSON_AddNumberToObject(q, "psn", 0);
    cJSON_AddNumberToObject(q, "port", IB_PORT);
    cJSON_AddNumberToObject(q, "lid", 0);
    // cJSON_AddStringToObject(q, "gid", "00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00");
    cJSON_AddStringToObject(q, "gid", gid_str);
    cJSON_AddItemToArray(arr_qp, q);

    // local MR
    if (mr)
    {
        cJSON *m = cJSON_CreateObject();
        cJSON_AddStringToObject(m, "id", "sbuf0");
        cJSON_AddNumberToObject(m, "addr", (double)(uintptr_t)mr->addr);
        cJSON_AddNumberToObject(m, "length", MSG_SIZE);
        cJSON_AddNumberToObject(m, "lkey", mr->lkey);
        cJSON_AddItemToArray(arr_mr, m);
    }

    // pair
    cJSON *p = cJSON_CreateObject();
    cJSON_AddStringToObject(p, "id", pair_id);
    cJSON_AddStringToObject(p, "cli_id", cli_id);
    cJSON_AddStringToObject(p, "srv_id", srv_hint); // hint which server slot to pair
    cJSON_AddStringToObject(p, "state", state);
    cJSON_AddNumberToObject(p, "ts", (double)now_ms());
    cJSON_AddItemToArray(pairs, p);

    char tmp[512];
    snprintf(tmp, sizeof(tmp), "%s.tmp", path);
    FILE *f = fopen(tmp, "w");
    if (!f)
    {
        cJSON_Delete(root);
        return;
    }
    char *txt = cJSON_PrintBuffered(root, 1 << 20, 1);
    fputs(txt, f);
    fclose(f);
    free(txt);
    cJSON_Delete(root);
    rename(tmp, path);
}

static bool wait_state(const char *env_key, const char *pair_id, const char *expect_state, int timeout_ms, InotifyReloader *rld)
{
    uint64_t deadline = now_ms() + timeout_ms;
    while ((int)(now_ms() - deadline) < 0)
    {
        if (rld)
            rld->pump_and_reload(env_key);
        else
            rr_load_from_env_or_die(env_key);
        // path or by-id; here we search path pairs[*].id == pair_id
        for (int i = 0;; ++i)
        {
            char k[128];
            snprintf(k, sizeof(k), "pairs[%d].id", i);
            if (!rr_has(k))
                break;
            const char *id = rr_str(k);
            if (id && !strcmp(id, pair_id))
            {
                snprintf(k, sizeof(k), "pairs[%d].state", i);
                const char *st = rr_str(k);
                if (st && !strcmp(st, expect_state))
                    return true;
            }
        }
        usleep(1000); // 1ms
    }
    return false;
}

int main(int argc, char **argv)
{
    const char *BUNDLE_ENV = "RDMA_FUZZ_RUNTIME";
    rr_load_from_env_or_die(BUNDLE_ENV);
    InotifyReloader rld;
    rld.init_from_env(BUNDLE_ENV);

    int num = 0;
    ibv_device **dev_list = ibv_get_device_list(&num);
    if (!dev_list || num <= 0)
        die("ibv_get_device_list");
    ibv_context *ctx = ibv_open_device(dev_list[0]);
    if (!ctx)
        die("ibv_open_device");

    union ibv_gid my_gid;
    memset(&my_gid, 0, sizeof(my_gid));
    (void)ibv_query_gid(ctx, IB_PORT, 1, &my_gid);

    ibv_pd *pd = ibv_alloc_pd(ctx);
    if (!pd)
        die("ibv_alloc_pd");
    ibv_cq *cq = ibv_create_cq(ctx, 256, nullptr, nullptr, 0);
    if (!cq)
        die("ibv_create_cq");

    // send buffer
    void *sbuf = aligned_alloc(4096, MSG_SIZE);
    memset(sbuf, 0, MSG_SIZE);
    ibv_mr *mr = ibv_reg_mr(pd, sbuf, MSG_SIZE, IBV_ACCESS_LOCAL_WRITE);
    if (!mr)
        die("ibv_reg_mr");

    ibv_qp *qp = create_qp(pd, cq);
    if (to_init(qp, IB_PORT))
        die("to_init");

    // (1) claim pair
    const char *cli_id = "cli0";
    const char *pair_id = "pair-cli0-srv0"; // demo: target srv0
    write_client_update("client_update.json", cli_id, qp, mr, pair_id, "srv0", "CLAIMED", my_gid.raw);

    // (2) wait server to expose BOTH_RTS (server_update merged into client_view)
    if (!wait_state(BUNDLE_ENV, pair_id, "BOTH_RTS", /*timeout_ms=*/10000, &rld))
    {
        fprintf(stderr, "[cli] timeout waiting BOTH_RTS\n");
        return 1;
    }

    // (3) read remote (server) QP by-id if available, else fallback [0]
    uint32_t rqpn = 0, rpsn = 0, rport = IB_PORT;
    uint16_t rlid = 0;
    uint8_t rgid[16]{0};
    if (rr_has("remote.ids.QP[0]"))
    {
        // assume server id is "srv0" for demo
        rqpn = rr_u32_by_id("remote.QP", "srv0", "qpn");
        rpsn = rr_try_u32_by_id("remote.QP", "srv0", "psn", 0);
        rport = rr_try_u32_by_id("remote.QP", "srv0", "port", IB_PORT);
        rlid = (uint16_t)rr_try_u32_by_id("remote.QP", "srv0", "lid", 0);
        const char *g = rr_try_str_by_id("remote.QP", "srv0", "gid", "00:00:...:00");
        parse_gid_str_colon(g, rgid);
    }
    else
    {
        rqpn = rr_u32("remote.QP[0].qpn");
        rpsn = rr_try_u32("remote.QP[0].psn", 0);
        rport = rr_try_u32("remote.QP[0].port", IB_PORT);
        rlid = (uint16_t)rr_try_u32("remote.QP[0].lid", 0);
        const char *g = rr_try_str("remote.QP[0].gid", "00:00:...:00");
        parse_gid_str_colon(g, rgid);
    }
    if (to_rtr(qp, rqpn, rlid, rgid, rport, rpsn))
        die("to_rtr");
    if (to_rts(qp, 0))
        die("to_rts");

    // (4) push READY
    write_client_update("client_update.json", cli_id, qp, mr, pair_id, "srv0", "READY", my_gid.raw);

    // (5) only now, send one message
    uint64_t *p64 = (uint64_t *)sbuf;
    p64[0] = 0x1122334455667788ULL;
    ibv_sge sge;
    memset(&sge, 0, sizeof(sge));
    sge.addr = (uintptr_t)sbuf;
    sge.length = 16;
    sge.lkey = mr->lkey;
    ibv_send_wr wr;
    memset(&wr, 0, sizeof(wr));
    wr.sg_list = &sge;
    wr.num_sge = 1;
    wr.opcode = IBV_WR_SEND;
    wr.send_flags = IBV_SEND_SIGNALED;
    ibv_send_wr *bad = nullptr;
    if (ibv_post_send(qp, &wr, &bad))
        die("ibv_post_send");

    // poll for completion
    for (;;)
    {
        ibv_wc wc;
        int n = ibv_poll_cq(cq, 1, &wc);
        if (n < 0)
            die("ibv_poll_cq");
        if (n == 0)
        {
            usleep(1000);
            continue;
        }
        if (wc.status != IBV_WC_SUCCESS)
        {
            fprintf(stderr, "[cli] WC err %d\n", wc.status);
            break;
        }
        fprintf(stdout, "[cli] SEND completed, wr_id=%llu, len=%u\n", (unsigned long long)wc.wr_id, wc.byte_len);
        break;
    }

    ibv_dereg_mr(mr);
    free(sbuf);
    ibv_destroy_qp(qp);
    ibv_destroy_cq(cq);
    ibv_dealloc_pd(pd);
    ibv_close_device(ctx); // simplified
    return 0;
}