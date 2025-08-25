// rdma_server_with_qp_pool_dynamic.cpp
// Dynamic multi-QP pairing server: supports incremental client QP creation,
// runtime bundle hot-reload (path or by-id), and periodic pairing/recycling.
// Requires: libibverbs, runtime_resolver.{c,h}, cJSON.{c,h}
//
// Build example:
//   g++ -O2 -std=c++17 rdma_server_with_qp_pool_dynamic.cpp runtime_resolver.c cJSON.c -libverbs -o rdma_server_dynamic
//
// Run example:
//   export RDMA_FUZZ_RUNTIME=/path/to/server_view.json
//   ./rdma_server_dynamic

#include <infiniband/verbs.h>
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <chrono>
#include <string>
#include <vector>
#include <unordered_set>
#include <iostream>

// Adjust include path as needed for cJSON
#include <cjson/cJSON.h>

extern "C"
{
#include "runtime_resolver.h" // rr_load_from_env_or_die / rr_* lookups
}

using std::string;
using std::vector;

static const int IB_PORT = 1;
static const int QP_POOL_SIZE = 4;    // can be tuned
static const int RECV_POOL_SIZE = 16; // can be tuned
static const int MSG_SIZE = 4096;

static const uint64_t IDLE_TIMEOUT_MS = 15000; // unpair if remote not seen for this long
static const int TICK_INTERVAL_MS = 100;       // pairing tick period
static const int DUMP_INTERVAL_MS = 1000;      // write server_update.json every N ms

// -------------------- helpers & types --------------------

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

struct PairSlot
{
    bool in_use = false; // whether this server slot is paired
    std::string peer_id; // id of remote.QP
    uint32_t peer_qpn = 0;
    uint64_t last_seen_ts = 0; // last timestamp reported by peer (or local now)
    std::string lease;         // optional lease token
};

struct ServerState
{
    vector<QPWithBufferPool> pool; // server QP pool
    vector<PairSlot> pairs;        // pairing table (1-1 with pool)
};

static void die(const char *msg)
{
    perror(msg);
    exit(1);
}

// parse colon-separated 16-byte GID string: "xx:xx:...:xx"
static int parse_gid_str_colon(const char *s, uint8_t out[16])
{
    if (!s)
        return -1;
    unsigned int b[16];
    int n = sscanf(s,
                   "%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x",
                   &b[0], &b[1], &b[2], &b[3],
                   &b[4], &b[5], &b[6], &b[7],
                   &b[8], &b[9], &b[10], &b[11],
                   &b[12], &b[13], &b[14], &b[15]);
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

static ibv_qp *create_qp(ibv_pd *pd, ibv_cq *cq)
{
    ibv_qp_init_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.qp_context = nullptr;
    attr.send_cq = cq;
    attr.recv_cq = cq;
    attr.cap.max_send_wr = 256;
    attr.cap.max_recv_wr = 256;
    attr.cap.max_send_sge = 8;
    attr.cap.max_recv_sge = 8;
    attr.qp_type = IBV_QPT_RC;
    attr.sq_sig_all = 0;

    ibv_qp *qp = ibv_create_qp(pd, &attr);
    if (!qp)
        die("ibv_create_qp");
    return qp;
}

static int modify_qp_to_init(ibv_qp *qp, uint8_t port_num)
{
    ibv_qp_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.qp_state = IBV_QPS_INIT;
    attr.pkey_index = 0;
    attr.port_num = port_num;
    attr.qp_access_flags = IBV_ACCESS_LOCAL_WRITE |
                           IBV_ACCESS_REMOTE_READ |
                           IBV_ACCESS_REMOTE_WRITE;
    int flags = IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS;
    if (ibv_modify_qp(qp, &attr, flags))
    {
        perror("ibv_modify_qp INIT");
        return -1;
    }
    return 0;
}

static int modify_qp_to_rtr(ibv_qp *qp,
                            uint32_t dest_qpn,
                            uint16_t dlid,
                            const uint8_t dgid[16],
                            uint8_t port_num,
                            uint32_t rq_psn = 0)
{
    ibv_qp_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.qp_state = IBV_QPS_RTR;
    attr.path_mtu = IBV_MTU_1024;
    attr.dest_qp_num = dest_qpn;
    attr.rq_psn = rq_psn;
    attr.max_dest_rd_atomic = 1;
    attr.min_rnr_timer = 12;

    attr.ah_attr.is_global = 1;
    attr.ah_attr.sl = 0;
    attr.ah_attr.src_path_bits = 0;
    attr.ah_attr.port_num = port_num;
    attr.ah_attr.dlid = dlid; // for RoCE, 0 is acceptable when is_global=1

    attr.ah_attr.grh.hop_limit = 1;
    attr.ah_attr.grh.traffic_class = 0;
    attr.ah_attr.grh.flow_label = 0;
    attr.ah_attr.grh.sgid_index = 0; // tune if needed
    memcpy(attr.ah_attr.grh.dgid.raw, dgid, 16);

    int flags = IBV_QP_STATE |
                IBV_QP_AV |
                IBV_QP_PATH_MTU |
                IBV_QP_DEST_QPN |
                IBV_QP_RQ_PSN |
                IBV_QP_MAX_DEST_RD_ATOMIC |
                IBV_QP_MIN_RNR_TIMER;
    if (ibv_modify_qp(qp, &attr, flags))
    {
        perror("ibv_modify_qp RTR");
        return -1;
    }
    return 0;
}

static int modify_qp_to_rts(ibv_qp *qp, uint32_t sq_psn = 0)
{
    ibv_qp_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.qp_state = IBV_QPS_RTS;
    attr.timeout = 14;
    attr.retry_cnt = 7;
    attr.rnr_retry = 7; // infinite
    attr.sq_psn = sq_psn;
    attr.max_rd_atomic = 1;

    int flags = IBV_QP_STATE |
                IBV_QP_TIMEOUT |
                IBV_QP_RETRY_CNT |
                IBV_QP_RNR_RETRY |
                IBV_QP_SQ_PSN |
                IBV_QP_MAX_QP_RD_ATOMIC;
    if (ibv_modify_qp(qp, &attr, flags))
    {
        perror("ibv_modify_qp RTS");
        return -1;
    }
    return 0;
}

static int setup_recv_pool(RecvBufferPool *pool, ibv_pd *pd)
{
    pool->pd = pd;
    for (int i = 0; i < RECV_POOL_SIZE; ++i)
    {
        void *buf = alloc_aligned(MSG_SIZE);
        if (!buf)
            return -1;
        ibv_mr *mr = ibv_reg_mr(pd, buf, MSG_SIZE,
                                IBV_ACCESS_LOCAL_WRITE |
                                    IBV_ACCESS_REMOTE_WRITE |
                                    IBV_ACCESS_REMOTE_READ);
        if (!mr)
            return -1;
        pool->slots[i].buf = buf;
        pool->slots[i].mr = mr;
    }
    return 0;
}

static int post_all_recvs(RecvBufferPool *pool, ibv_qp *qp)
{
    for (int i = 0; i < RECV_POOL_SIZE; ++i)
    {
        ibv_sge sge;
        memset(&sge, 0, sizeof(sge));
        sge.addr = (uintptr_t)pool->slots[i].buf;
        sge.length = MSG_SIZE;
        sge.lkey = pool->slots[i].mr->lkey;

        ibv_recv_wr wr;
        memset(&wr, 0, sizeof(wr));
        wr.wr_id = (uintptr_t)&pool->slots[i];
        wr.sg_list = &sge;
        wr.num_sge = 1;

        ibv_recv_wr *bad = nullptr;
        if (ibv_post_recv(qp, &wr, &bad))
        {
            perror("ibv_post_recv");
            return -1;
        }
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
        pool->slots[i].mr = nullptr;
        pool->slots[i].buf = nullptr;
    }
}

// -------------------- bundle I/O --------------------

// You can optimize this by checking mtime; simple reload here.
static inline void rr_reload_if_changed(const char *env_key)
{
    rr_load_from_env_or_die(env_key);
}

struct RemoteQP
{
    std::string id;
    uint32_t qpn = 0, psn = 0, port = 1;
    uint16_t lid = 0;
    uint8_t dgid[16]{0};
    uint64_t ts = 0;   // optional
    std::string lease; // optional
};

static vector<RemoteQP> snapshot_remote_qps()
{
    vector<RemoteQP> out;

    // Prefer by-id if remote.ids.QP exists
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
            const char *gid_s = rr_try_str_by_id("remote.QP", id, "gid",
                                                 "00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00");
            parse_gid_str_colon(gid_s, r.dgid);
            r.ts = rr_try_u64_by_id("remote.QP", id, "ts", 0);
            const char *lease = rr_try_str_by_id("remote.QP", id, "lease", "");
            if (lease)
                r.lease = lease;
            out.push_back(std::move(r));
        }
        return out;
    }

    // Fallback: path style remote.QP[N]
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
        const char *gid_s = rr_try_str(k,
                                       "00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00");
        parse_gid_str_colon(gid_s, r.dgid);
        r.ts = now_ms(); // no ts provided; use local now
        out.push_back(std::move(r));
    }
    return out;
}

static int find_free_slot(const ServerState &S)
{
    for (int i = 0; i < (int)S.pairs.size(); ++i)
    {
        if (!S.pairs[i].in_use)
            return i;
    }
    return -1;
}

static bool claim_and_pair(ServerState &S, int slot, const RemoteQP &R, uint8_t local_port)
{
    auto &pr = S.pairs[slot];
    auto &qp = S.pool[slot].qp;

    // Drive to RTR/RTS and post recvs
    if (modify_qp_to_rtr(qp, R.qpn, R.lid, R.dgid, local_port, R.psn))
    {
        fprintf(stderr, "[server] RTR failed on srv slot %d\n", slot);
        return false;
    }
    if (modify_qp_to_rts(qp, 0))
    {
        fprintf(stderr, "[server] RTS failed on srv slot %d\n", slot);
        return false;
    }
    if (post_all_recvs(&S.pool[slot].recv_pool, qp))
    {
        fprintf(stderr, "[server] post recv failed on srv slot %d\n", slot);
        return false;
    }

    pr.in_use = true;
    pr.peer_id = R.id;
    pr.peer_qpn = R.qpn;
    pr.last_seen_ts = (R.ts ? R.ts : now_ms());
    pr.lease = R.lease;
    fprintf(stdout, "[server] paired slot %d with remote '%s' (qpn=%u)\n",
            slot, pr.peer_id.c_str(), pr.peer_qpn);
    return true;
}

static void unclaim_slot(ServerState &S, int slot)
{
    if (slot < 0 || slot >= (int)S.pairs.size())
        return;
    auto &pr = S.pairs[slot];
    if (!pr.in_use)
        return;
    fprintf(stdout, "[server] unpair slot %d (remote '%s')\n", slot, pr.peer_id.c_str());
    pr = PairSlot{};
    // Optionally revert QP to INIT here if you want clean re-pairing:
    // modify_qp_to_init(S.pool[slot].qp, IB_PORT);
}

static void dump_server_update(const char *path,
                               const ServerState &S,
                               uint16_t lid,
                               const uint8_t gid[16],
                               uint8_t port_num)
{
    cJSON *root = cJSON_CreateObject();
    cJSON *local = cJSON_AddObjectToObject(root, "local");
    cJSON *arr_qp = cJSON_AddArrayToObject(local, "QP");
    cJSON *arr_mr = cJSON_AddArrayToObject(local, "MR");
    cJSON *pairs = cJSON_AddArrayToObject(local, "pairs"); // optional pairing view

    char gid_str[64];
    snprintf(gid_str, sizeof(gid_str),
             "%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x",
             gid[0], gid[1], gid[2], gid[3],
             gid[4], gid[5], gid[6], gid[7],
             gid[8], gid[9], gid[10], gid[11],
             gid[12], gid[13], gid[14], gid[15]);

    for (int i = 0; i < (int)S.pool.size(); ++i)
    {
        // QP entry
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

        // MR entries (recv buffers)
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

        // pairing view
        cJSON *p = cJSON_CreateObject();
        cJSON_AddStringToObject(p, "srv_id", qpid);
        if (S.pairs[i].in_use)
        {
            cJSON_AddStringToObject(p, "peer_id", S.pairs[i].peer_id.c_str());
            cJSON_AddNumberToObject(p, "peer_qpn", S.pairs[i].peer_qpn);
            cJSON_AddNumberToObject(p, "last_seen_ts", (double)S.pairs[i].last_seen_ts);
            if (!S.pairs[i].lease.empty())
            {
                cJSON_AddStringToObject(p, "lease", S.pairs[i].lease.c_str());
            }
        }
        else
        {
            cJSON_AddStringToObject(p, "peer_id", "");
            cJSON_AddNumberToObject(p, "peer_qpn", 0);
            cJSON_AddNumberToObject(p, "last_seen_ts", 0);
        }
        cJSON_AddItemToArray(pairs, p);
    }

    // atomic write: write to tmp then rename
    char tmp_path[512];
    snprintf(tmp_path, sizeof(tmp_path), "%s.tmp", path);
    FILE *f = fopen(tmp_path, "w");
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
    rename(tmp_path, path);
}

// -------------------- pairing tick --------------------

static void tick_pairing(ServerState &S,
                         uint8_t local_port,
                         uint64_t now,
                         uint64_t idle_timeout_ms)
{
    rr_reload_if_changed("RDMA_FUZZ_RUNTIME");
    auto remotes = snapshot_remote_qps();

    // mark alive
    std::unordered_set<string> alive;
    alive.reserve(remotes.size());
    for (auto &r : remotes)
    {
        alive.insert(r.id);
    }

    // refresh existing & pair new
    for (auto &r : remotes)
    {
        bool already = false;
        for (auto &pr : S.pairs)
        {
            if (pr.in_use && pr.peer_id == r.id)
            {
                pr.last_seen_ts = (r.ts ? r.ts : now);
                already = true;
                break;
            }
        }
        if (already)
            continue;
        int slot = find_free_slot(S);
        if (slot >= 0)
        {
            (void)claim_and_pair(S, slot, r, local_port);
        }
    }

    // recycle disappeared or idle
    for (int i = 0; i < (int)S.pairs.size(); ++i)
    {
        auto &pr = S.pairs[i];
        if (!pr.in_use)
            continue;
        bool still = alive.count(pr.peer_id) > 0;
        bool idle = (pr.last_seen_ts && (now > pr.last_seen_ts + idle_timeout_ms));
        if (!still || idle)
        {
            unclaim_slot(S, i);
        }
    }
}

// -------------------- main --------------------

int main(int argc, char **argv)
{
    // 0) load runtime bundle (server_view.json)
    rr_load_from_env_or_die("RDMA_FUZZ_RUNTIME");

    // 1) open device
    int num = 0;
    ibv_device **dev_list = ibv_get_device_list(&num);
    if (!dev_list || num <= 0)
        die("ibv_get_device_list");
    ibv_context *ctx = ibv_open_device(dev_list[0]);
    if (!ctx)
        die("ibv_open_device");

    // 2) PD/CQ
    ibv_pd *pd = ibv_alloc_pd(ctx);
    if (!pd)
        die("ibv_alloc_pd");
    ibv_cq *cq = ibv_create_cq(ctx, 2048, nullptr, nullptr, 0);
    if (!cq)
        die("ibv_create_cq");

    // 3) query port/gid
    ibv_port_attr port_attr;
    if (ibv_query_port(ctx, IB_PORT, &port_attr))
        die("ibv_query_port");
    union ibv_gid my_gid;
    memset(&my_gid, 0, sizeof(my_gid));
    (void)ibv_query_gid(ctx, IB_PORT, 0, &my_gid); // ignore failure

    // 4) build server pool & INIT
    ServerState S;
    S.pool.resize(QP_POOL_SIZE);
    S.pairs.resize(QP_POOL_SIZE);

    for (int i = 0; i < QP_POOL_SIZE; ++i)
    {
        S.pool[i].qp = create_qp(pd, cq);
        if (setup_recv_pool(&S.pool[i].recv_pool, pd))
            die("setup_recv_pool");
        if (modify_qp_to_init(S.pool[i].qp, IB_PORT))
            die("modify_qp_to_init");
    }

    // 5) main loop: pairing tick + optional CQ polling + periodic dump
    uint64_t last_dump = 0;
    fprintf(stdout, "[server] running pairing loop ...\n");
    for (;;)
    {
        uint64_t t = now_ms();
        tick_pairing(S, IB_PORT, t, IDLE_TIMEOUT_MS);

        // Optional: short CQ poll
        ibv_wc wc[32];
        int n = ibv_poll_cq(cq, 32, wc);
        if (n > 0)
        {
            for (int i = 0; i < n; ++i)
            {
                if (wc[i].status != IBV_WC_SUCCESS)
                {
                    fprintf(stderr, "[server] WC err: status=%d opcode=%d\n", wc[i].status, wc[i].opcode);
                }
                else
                {
                    // You can add data-plane handling here
                    // fprintf(stdout, "[server] WC ok: wr_id=%llu opcode=%d len=%u\n",
                    //         (unsigned long long)wc[i].wr_id, wc[i].opcode, wc[i].byte_len);
                }
            }
        }

        if (t - last_dump >= DUMP_INTERVAL_MS)
        {
            dump_server_update("server_update.json", S, port_attr.lid, my_gid.raw, IB_PORT);
            last_dump = t;
        }

        usleep(TICK_INTERVAL_MS * 1000);
    }

    // 6) cleanup (unreachable in this loop; keep for completeness)
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