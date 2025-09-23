// rdma_server_with_qp_pool_pairs.cpp
// Dynamic multi-QP pairing with bundle hot-reload (inotify) and pairs state export.
// Build:
//   g++ -O2 -std=c++17 rdma_server_with_qp_pool_pairs.cpp runtime_resolver.c cJSON.c -libverbs -o rdma_server_pairs
// Run:
//   export RDMA_FUZZ_RUNTIME=/path/to/server_view.json
//   ./rdma_server_pairs

#include <infiniband/verbs.h>
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/inotify.h>
#include <libgen.h>

#include <chrono>
#include <string>
#include <vector>
#include <unordered_set>
#include <iostream>

#include <cjson/cJSON.h>

extern "C"
{
#include "runtime_resolver.h"
}

using std::string;
using std::vector;

static const int IB_PORT = 1;
static const int QP_POOL_SIZE = 100;
static const int RECV_POOL_SIZE = 16;
static const int MSG_SIZE = 4096;

static const uint64_t IDLE_TIMEOUT_MS = 15000;
static const int TICK_INTERVAL_MS = 100;
static const int DUMP_INTERVAL_MS = 1000;

// -------------------- inotify helper --------------------
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
            struct inotify_event *ev = (struct inotify_event *)(buf + i);
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

// -------------------- utils --------------------
static void die(const char *msg)
{
    perror(msg);
    exit(1);
}

static int parse_gid_str_colon(const char *s, uint8_t out[16])
{
    if (!s)
        return -1;
    unsigned int b[16];
    int n = sscanf(s,
                   "%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x",
                   &b[0], &b[1], &b[2], &b[3], &b[4], &b[5], &b[6], &b[7],
                   &b[8], &b[9], &b[10], &b[11], &b[12], &b[13], &b[14], &b[15]);
    if (n != 16)
        return -1;
    for (int i = 0; i < 16; ++i)
        out[i] = (uint8_t)b[i];
    return 0;
}

static void *alloc_aligned(size_t size)
{
    void *p = nullptr;
    if (posix_memalign(&p, sysconf(_SC_PAGESIZE), size))
        return nullptr;
    memset(p, 0, size);
    return p;
}

static uint64_t now_ms()
{
    using namespace std::chrono;
    return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}

// -------------------- verbs helpers --------------------
struct RecvSlot
{
    void *buf = nullptr;
    ibv_mr *mr = nullptr;
};
struct RecvBufferPool
{
    RecvSlot slots[RECV_POOL_SIZE];
    ibv_pd *pd = nullptr;
};
struct QPWithBufferPool
{
    ibv_qp *qp = nullptr;
    RecvBufferPool recv_pool;
};

static ibv_qp *create_qp(ibv_pd *pd, ibv_cq *cq)
{
    ibv_qp_init_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.send_cq = cq;
    attr.recv_cq = cq;
    attr.cap = {.max_send_wr = 256, .max_recv_wr = 256, .max_send_sge = 8, .max_recv_sge = 8, .max_inline_data = 0};
    attr.qp_type = IBV_QPT_RC;
    attr.sq_sig_all = 1;
    ibv_qp *qp = ibv_create_qp(pd, &attr);
    if (!qp)
        die("ibv_create_qp");
    return qp;
}

static int modify_qp_to_init(ibv_qp *qp, uint8_t port_num)
{
    ibv_qp_attr a;
    memset(&a, 0, sizeof(a));
    a.qp_state = IBV_QPS_INIT;
    a.pkey_index = 0;
    a.port_num = port_num;
    a.qp_access_flags = IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE;
    int flags = IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS;
    return ibv_modify_qp(qp, &a, flags);
}

static int modify_qp_to_rtr(ibv_qp *qp, uint32_t dest_qpn, uint16_t dlid, const uint8_t dgid[16], uint8_t port_num, uint32_t rq_psn = 0)
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
    a.ah_attr.port_num = port_num;
    a.ah_attr.dlid = dlid;
    a.ah_attr.grh.hop_limit = 1;
    a.ah_attr.grh.traffic_class = 0;
    a.ah_attr.grh.flow_label = 0;
    a.ah_attr.grh.sgid_index = 1;
    memcpy(a.ah_attr.grh.dgid.raw, dgid, 16);
    int flags = IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER;
    return ibv_modify_qp(qp, &a, flags);
}

static int modify_qp_to_rts(ibv_qp *qp, uint32_t sq_psn = 0)
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

static int setup_recv_pool(RecvBufferPool *pool, ibv_pd *pd)
{
    pool->pd = pd;
    for (int i = 0; i < RECV_POOL_SIZE; ++i)
    {
        void *buf = alloc_aligned(MSG_SIZE);
        if (!buf)
            return -1;
        ibv_mr *mr = ibv_reg_mr(pd, buf, MSG_SIZE, IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_REMOTE_READ);
        if (!mr)
            return -1;
        pool->slots[i].buf = buf;
        pool->slots[i].mr = mr;
    }
    return 0;
}

static int post_all_recvs(RecvBufferPool *pool, ibv_qp *qp, int slot_id)
{
    printf("[srv] post_all_recvs slot_id=%d\n", slot_id);
    for (int i = 0; i < RECV_POOL_SIZE; ++i)
    {
        ibv_sge sge;
        memset(&sge, 0, sizeof(sge));
        sge.addr = (uintptr_t)pool->slots[i].buf;
        sge.length = MSG_SIZE;
        sge.lkey = pool->slots[i].mr->lkey;
        ibv_recv_wr wr;
        memset(&wr, 0, sizeof(wr));
        wr.wr_id = slot_id * 100 + i;
        wr.sg_list = &sge;
        wr.num_sge = 1;
        ibv_recv_wr *bad = nullptr;
        if (ibv_post_recv(qp, &wr, &bad))
            return -1;
    }
    return 0;
}

static void destroy_recv_pool(RecvBufferPool *pool)
{
    for (int i = 0; i < RECV_POOL_SIZE; ++i)
    {
        if (pool->slots[i].mr)
            ibv_dereg_mr(pool->slots[i].mr);
        if (pool->slots[i].buf)
            free(pool->slots[i].buf);
    }
}

// -------------------- pairing & state --------------------
struct PairSlot
{
    bool in_use = false;
    string peer_id;
    uint32_t peer_qpn = 0;
    uint64_t last_seen_ts = 0;
    string lease;
};
struct ServerState
{
    vector<QPWithBufferPool> pool;
    vector<PairSlot> pairs;
};

struct RemoteQP
{
    string id;
    uint32_t qpn = 0, psn = 0, port = 1;
    uint16_t lid = 0;
    uint8_t dgid[16]{0};
    uint64_t ts = 0;
    string lease;
};

struct RemotePair
{
    string id;
    string cli_id;
    string srv_id;
    string state;
    int ts;
};

static vector<RemoteQP> snapshot_remote_qps()
{
    vector<RemoteQP> out;
    if (rr_has("remote.ids.QP[0]"))
    {
        for (int i = 0;; ++i)
        {
            char key[64];
            snprintf(key, sizeof(key), "remote.ids.QP[%d]", i);
            if (!rr_has(key))
                break;
            const char *id = rr_str(key);
            RemoteQP r;
            r.id = id;
            r.qpn = rr_u32_by_id("remote.QP", id, "qpn");
            r.psn = rr_try_u32_by_id("remote.QP", id, "psn", 0);
            r.port = rr_try_u32_by_id("remote.QP", id, "port", 1);
            r.lid = (uint16_t)rr_try_u32_by_id("remote.QP", id, "lid", 0);
            const char *gid_s = rr_try_str_by_id("remote.QP", id, "gid", "00:00:00:...:00");
            parse_gid_str_colon(gid_s, r.dgid);
            r.ts = rr_try_u64_by_id("remote.QP", id, "ts", 0);
            const char *lease = rr_try_str_by_id("remote.QP", id, "lease", "");
            if (lease)
                r.lease = lease;
            out.push_back(std::move(r));
        }
        return out;
    }
    for (int i = 0;; ++i)
    {
        char k[64];
        snprintf(k, sizeof(k), "remote.QP[%d].qpn", i);
        if (!rr_has(k))
            break;
        RemoteQP r;
        r.id = "qpidx" + std::to_string(i);
        snprintf(k, sizeof(k), "remote.QP[%d].qpn", i);
        r.qpn = rr_u32(k);
        snprintf(k, sizeof(k), "remote.QP[%d].psn", i);
        r.psn = rr_try_u32(k, 0);
        snprintf(k, sizeof(k), "remote.QP[%d].port", i);
        r.port = rr_try_u32(k, 1);
        snprintf(k, sizeof(k), "remote.QP[%d].lid", i);
        r.lid = (uint16_t)rr_try_u32(k, 0);
        snprintf(k, sizeof(k), "remote.QP[%d].gid", i);
        const char *gid_s = rr_try_str(k, "00:00:00:...:00");
        parse_gid_str_colon(gid_s, r.dgid);
        r.ts = now_ms();
        out.push_back(std::move(r));
    }
    return out;
}

static vector<RemotePair> snapshot_remote_pairs()
{
    vector<RemotePair> out;
    if (rr_has("remote.ids.pairs[0]"))
    {
        for (int i = 0;; ++i)
        {
            char key[64];
            snprintf(key, sizeof(key), "remote.ids.pairs[%d]", i);
            if (!rr_has(key))
                break;
            const char *id = rr_str(key);
            RemotePair p;
            p.id = id;
            p.cli_id = rr_str_by_id("remote.pairs", id, "cli_id");
            p.srv_id = rr_str_by_id("remote.pairs", id, "srv_id");
            p.state = rr_str_by_id("remote.pairs", id, "state");
            p.ts = (int)rr_try_u64_by_id("remote.pairs", id, "ts", 0);
            out.push_back(std::move(p));
        }
        return out;
    }
    for (int i = 0;; ++i)
    {
        char k[64];
        snprintf(k, sizeof(k), "remote.pairs[%d].id", i);
        if (!rr_has(k))
            break;
        RemotePair p;
        snprintf(k, sizeof(k), "remote.pairs[%d].id", i);
        p.id = rr_str(k);
        snprintf(k, sizeof(k), "remote.pairs[%d].cli_id", i);
        p.cli_id = rr_str(k);
        snprintf(k, sizeof(k), "remote.pairs[%d].srv_id", i);
        p.srv_id = rr_str(k);
        snprintf(k, sizeof(k), "remote.pairs[%d].state", i);
        p.state = rr_str(k);
        // snprintf(k, sizeof(k), "remote.pairs[%d].ts", i);
        // p.ts = (int)rr_try_u64(k, 0);
        p.ts = 0;
        out.push_back(std::move(p));
    }
    return out;
}

static int find_free_slot(const ServerState &S)
{
    for (int i = 0; i < (int)S.pairs.size(); ++i)
        if (!S.pairs[i].in_use)
            return i;
    return -1;
}

static bool claim_and_pair(ServerState &S, int slot, const RemoteQP &R, uint8_t local_port)
{
    auto &pr = S.pairs[slot];
    auto &qp = S.pool[slot].qp;
    pr.in_use = true;
    pr.peer_id = R.id;
    pr.peer_qpn = R.qpn;
    pr.last_seen_ts = R.ts ? R.ts : now_ms();
    pr.lease = R.lease;
    // 无论配对成功与否都进行标记，防止重复尝试失败配对（experimental）
    printf("[srv] trying to pair slot %d with '%s' (qpn=%u, lid=%u, gid=%02x...)\n",
           slot, pr.peer_id.c_str(), pr.peer_qpn, R.lid, R.dgid[15]);
    if (modify_qp_to_rtr(qp, R.qpn, R.lid, R.dgid, local_port, R.psn))
    {
        perror("RTR");
        return false;
    }
    if (modify_qp_to_rts(qp, 0))
    {
        perror("RTS");
        return false;
    }
    if (post_all_recvs(&S.pool[slot].recv_pool, qp, slot))
    {
        perror("post_recv");
        return false;
    }
    // pr.in_use = true;
    // pr.peer_id = R.id;
    // pr.peer_qpn = R.qpn;
    // pr.last_seen_ts = R.ts ? R.ts : now_ms();
    // pr.lease = R.lease;
    fprintf(stdout, "[srv] paired slot %d with '%s' (qpn=%u)\n", slot, pr.peer_id.c_str(), pr.peer_qpn);
    return true;
}

static void unclaim_slot(ServerState &S, int slot)
{
    if (slot < 0 || slot >= (int)S.pairs.size())
        return;
    auto &pr = S.pairs[slot];
    if (!pr.in_use)
        return;
    fprintf(stdout, "[srv] unpair slot %d (peer '%s')\n", slot, pr.peer_id.c_str());
    pr = PairSlot{};
    // Optionally: modify_qp_to_init(S.pool[slot].qp, IB_PORT);
}

// export local view (including pairs with BOTH_RTS when paired)
static void dump_server_update(const char *path, const ServerState &S, uint16_t lid, const uint8_t gid[16], uint8_t port_num)
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

    for (int i = 0; i < (int)S.pool.size(); ++i)
    {
        // QP
        char qpid[32];
        snprintf(qpid, sizeof(qpid), "srv%d", i);
        cJSON *q = cJSON_CreateObject();
        cJSON_AddStringToObject(q, "id", qpid);
        cJSON_AddNumberToObject(q, "qpn", S.pool[i].qp->qp_num);
        cJSON_AddNumberToObject(q, "psn", 0);
        cJSON_AddNumberToObject(q, "port", port_num);
        cJSON_AddNumberToObject(q, "lid", lid);
        cJSON_AddStringToObject(q, "gid", gid_str);
        cJSON_AddItemToArray(arr_qp, q);
        // MR (recv buffers)
        for (int j = 0; j < RECV_POOL_SIZE; ++j)
        {
            char mrid[32];
            snprintf(mrid, sizeof(mrid), "lbuf%d_%d", i, j);
            cJSON *m = cJSON_CreateObject();
            cJSON_AddStringToObject(m, "id", mrid);
            cJSON_AddNumberToObject(m, "addr", (double)(uintptr_t)S.pool[i].recv_pool.slots[j].buf);
            cJSON_AddNumberToObject(m, "length", MSG_SIZE);
            cJSON_AddNumberToObject(m, "lkey", S.pool[i].recv_pool.slots[j].mr->lkey);
            cJSON_AddItemToArray(arr_mr, m);
        }
        // pairs: server已到RTS视为 BOTH_RTS（等待客户端把 READY 提上来）
        cJSON *p = cJSON_CreateObject();
        cJSON_AddStringToObject(p, "id", ("pair-" + (S.pairs[i].in_use ? S.pairs[i].peer_id : "none") + "-" + qpid).c_str());
        cJSON_AddStringToObject(p, "srv_id", qpid);
        if (S.pairs[i].in_use)
        {
            cJSON_AddStringToObject(p, "peer_id", S.pairs[i].peer_id.c_str());
            cJSON_AddStringToObject(p, "state", "BOTH_RTS"); // server侧标注：本端已RTS，配对成功
            cJSON_AddNumberToObject(p, "last_seen_ts", (double)S.pairs[i].last_seen_ts);
            if (!S.pairs[i].lease.empty())
                cJSON_AddStringToObject(p, "lease", S.pairs[i].lease.c_str());
        }
        else
        {
            cJSON_AddStringToObject(p, "peer_id", "");
            cJSON_AddStringToObject(p, "state", "INIT");
            cJSON_AddNumberToObject(p, "last_seen_ts", 0);
        }
        cJSON_AddItemToArray(pairs, p);
    }

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

// -------------------- main --------------------
int main(int argc, char **argv)
{
    const char *BUNDLE_ENV = "RDMA_FUZZ_RUNTIME";
    rr_load_from_env_or_die(BUNDLE_ENV);

    InotifyReloader reloader;
    reloader.init_from_env(BUNDLE_ENV);

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
    ibv_cq *cq = ibv_create_cq(ctx, 2048, nullptr, nullptr, 0);
    if (!cq)
        die("ibv_create_cq");

    ibv_port_attr port_attr;
    if (ibv_query_port(ctx, IB_PORT, &port_attr))
        die("ibv_query_port");
    union ibv_gid my_gid;
    memset(&my_gid, 0, sizeof(my_gid));
    (void)ibv_query_gid(ctx, IB_PORT, 1, &my_gid);

    ServerState S;
    S.pool.resize(QP_POOL_SIZE);
    S.pairs.resize(QP_POOL_SIZE);
    for (int i = 0; i < QP_POOL_SIZE; ++i)
    {
        S.pool[i].qp = create_qp(pd, cq);
        if (modify_qp_to_init(S.pool[i].qp, IB_PORT))
            die("modify_qp_to_init");
        if (setup_recv_pool(&S.pool[i].recv_pool, pd))
            die("setup_recv_pool");
    }

    uint64_t last_dump = 0;
    fprintf(stdout, "[srv] pairing loop...\n");
    std::unordered_set<string> paired;
    for (;;)
    {
        // reload on FS event
        reloader.pump_and_reload(BUNDLE_ENV);

        auto remote_pairs = snapshot_remote_pairs();
        auto remote_qps = snapshot_remote_qps();
        for (auto &r : remote_pairs)
        {
            if (paired.count(r.cli_id) > 0)
                continue;
            if (r.state == "BOTH_RTS")
                paired.insert(r.cli_id);
            if (r.state == "CLAIMED")
            {
                for (auto qp = remote_qps.begin(); qp != remote_qps.end(); ++qp)
                {
                    if (qp->id == r.cli_id) // r.srv_id == "srv*"
                    {
                        (void)claim_and_pair(S, std::stoi(r.srv_id.substr(3)), *qp, IB_PORT);
                        paired.insert(r.cli_id);
                    }
                }
            }
        }
        // pairing tick
        // auto remotes = snapshot_remote_qps(); // 远程(client)qp列表快照
        // std::unordered_set<string> alive;
        // for (auto &r : remotes)
        //     alive.insert(r.id);
        // for (auto &r : remotes)
        // {
        //     bool already = false;
        //     for (auto &pr : S.pairs)
        //     {
        //         if (pr.in_use && pr.peer_id == r.id)
        //         {
        //             pr.last_seen_ts = r.ts ? r.ts : now_ms();
        //             already = true;
        //             break;
        //         }
        //     }
        //     if (already)
        //         continue;
        //     int slot = find_free_slot(S); // 找一个本地QP和client的QP做配对
        //     if (slot >= 0)
        //         (void)claim_and_pair(S, slot, r, IB_PORT);
        // }
        // for (int i = 0; i < (int)S.pairs.size(); ++i) // 无所谓吧，应该不会出现unclaim的情况
        // {
        //     auto &pr = S.pairs[i];
        //     if (!pr.in_use)
        //         continue;
        //     bool still = alive.count(pr.peer_id) > 0;
        //     bool idle = (pr.last_seen_ts && (now_ms() > pr.last_seen_ts + IDLE_TIMEOUT_MS));
        //     if (!still || idle)
        //         unclaim_slot(S, i);
        // }

        // poll CQ (optional)
        ibv_wc wc[100];
        int n = ibv_poll_cq(cq, 100, wc);
        if (n > 0)
        {
            for (int i = 0; i < n; ++i)
            {
                if (wc[i].status != IBV_WC_SUCCESS)
                {
                    fprintf(stderr, "[srv] WC err: status=%d opcode=%d wr_id=%d\n", wc[i].status, wc[i].opcode, wc[i].wr_id);
                }
            }
        }

        if (now_ms() - last_dump >= DUMP_INTERVAL_MS)
        {
            dump_server_update("server_update.json", S, port_attr.lid, my_gid.raw, IB_PORT);
            printf("[srv] dump server_update.json\n");
            last_dump = now_ms();
        }
        usleep(TICK_INTERVAL_MS * 1000);
    }

    // cleanup (unreached)
    for (int i = 0; i < (int)S.pool.size(); ++i)
    {
        destroy_recv_pool(&S.pool[i].recv_pool);
        if (S.pool[i].qp)
            ibv_destroy_qp(S.pool[i].qp);
    }
    ibv_destroy_cq(cq);
    ibv_dealloc_pd(pd);
    ibv_close_device(ctx);
    ibv_free_device_list(dev_list);
    return 0;
}