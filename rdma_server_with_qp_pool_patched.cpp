// rdma_server_with_qp_pool.cpp
// Integrated with runtime_resolver (by-id & path lookups) and bundle export (server_update.json)

#include <infiniband/verbs.h>
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <cjson/cJSON.h> // ensure your include path is correct (e.g., -I/usr/include)
#include <iostream>
#include <string>
#include <vector>

extern "C"
{
#include "runtime_resolver.h" // rr_load_from_env_or_die / rr_* lookups
}

using std::string;
using std::vector;

static const int IB_PORT = 1;
static const int QP_POOL_SIZE = 2;
static const int RECV_POOL_SIZE = 8;
static const int MSG_SIZE = 4096;

struct RecvSlot
{
    void *buf;
    ibv_mr *mr;
};

struct RecvBufferPool
{
    RecvSlot slots[RECV_POOL_SIZE];
    ibv_pd *pd;
};

struct QPWithBufferPool
{
    ibv_qp *qp;
    RecvBufferPool recv_pool;
};

static void die(const char *msg)
{
    perror(msg);
    exit(1);
}

// Simple parser for colon-separated 16-byte GID string: "xx:xx:...:xx"
static int parse_gid_str_colon(const char *s, uint8_t out[16])
{
    unsigned int b[16];
    if (!s)
        return -1;
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

static ibv_qp *create_qp(ibv_pd *pd, ibv_cq *cq)
{
    ibv_qp_init_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.qp_context = nullptr;
    attr.send_cq = cq;
    attr.recv_cq = cq;
    attr.cap.max_send_wr = 128;
    attr.cap.max_recv_wr = 128;
    attr.cap.max_send_sge = 4;
    attr.cap.max_recv_sge = 4;
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
    int flags = IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT |
                IBV_QP_ACCESS_FLAGS;
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

    // dlid may be 0 for RoCE; that's ok if is_global=1 and GRH present
    attr.ah_attr.dlid = dlid;

    attr.ah_attr.grh.hop_limit = 1;
    attr.ah_attr.grh.traffic_class = 0;
    attr.ah_attr.grh.flow_label = 0;
    attr.ah_attr.grh.sgid_index = 0; // set as needed
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
    }
}

static int dump_server_update(const char *path,
                              QPWithBufferPool *pool, int nq,
                              uint16_t lid,
                              const uint8_t gid[16],
                              uint8_t port_num)
{
    cJSON *root = cJSON_CreateObject();
    cJSON *local = cJSON_AddObjectToObject(root, "local");
    cJSON *arr_qp = cJSON_AddArrayToObject(local, "QP");
    cJSON *arr_mr = cJSON_AddArrayToObject(local, "MR");

    char gid_str[64];
    snprintf(gid_str, sizeof(gid_str),
             "%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x",
             gid[0], gid[1], gid[2], gid[3],
             gid[4], gid[5], gid[6], gid[7],
             gid[8], gid[9], gid[10], gid[11],
             gid[12], gid[13], gid[14], gid[15]);

    for (int i = 0; i < nq; ++i)
    {
        // QP entry
        char qpid[32];
        snprintf(qpid, sizeof(qpid), "srv%d", i);
        cJSON *q = cJSON_CreateObject();
        cJSON_AddStringToObject(q, "id", qpid);
        cJSON_AddNumberToObject(q, "qpn", pool[i].qp->qp_num);
        cJSON_AddNumberToObject(q, "psn", 0);
        cJSON_AddNumberToObject(q, "port", port_num);
        cJSON_AddNumberToObject(q, "lid", lid);
        cJSON_AddStringToObject(q, "gid", gid_str);
        cJSON_AddItemToArray(arr_qp, q);

        // MR entries (expose recv buffers so client can RDMA WRITE if needed)
        for (int j = 0; j < RECV_POOL_SIZE; ++j)
        {
            char mrid[32];
            snprintf(mrid, sizeof(mrid), "lbuf%d_%d", i, j);
            cJSON *m = cJSON_CreateObject();
            cJSON_AddStringToObject(m, "id", mrid);
            cJSON_AddNumberToObject(m, "addr", (double)(uintptr_t)pool[i].recv_pool.slots[j].buf);
            cJSON_AddNumberToObject(m, "length", MSG_SIZE);
            cJSON_AddNumberToObject(m, "lkey", pool[i].recv_pool.slots[j].mr->lkey);
            cJSON_AddItemToArray(arr_mr, m);
        }
    }

    FILE *f = fopen(path, "w");
    if (!f)
    {
        cJSON_Delete(root);
        return -1;
    }
    char *txt = cJSON_PrintBuffered(root, 1 << 20, 1);
    fputs(txt, f);
    fclose(f);
    free(txt);
    cJSON_Delete(root);
    return 0;
}

int main(int argc, char **argv)
{
    // 0) Load runtime bundle (server_view.json)
    rr_load_from_env_or_die("RDMA_FUZZ_RUNTIME");

    // 1) Open device
    int num;
    ibv_device **dev_list = ibv_get_device_list(&num);
    if (!dev_list || num <= 0)
        die("ibv_get_device_list");
    ibv_context *ctx = ibv_open_device(dev_list[0]);
    if (!ctx)
        die("ibv_open_device");

    // 2) PD / CQ
    ibv_pd *pd = ibv_alloc_pd(ctx);
    if (!pd)
        die("ibv_alloc_pd");
    ibv_cq *cq = ibv_create_cq(ctx, 1024, nullptr, nullptr, 0);
    if (!cq)
        die("ibv_create_cq");

    // 3) Query port / GID
    ibv_port_attr port_attr;
    if (ibv_query_port(ctx, IB_PORT, &port_attr))
        die("ibv_query_port");
    union ibv_gid my_gid;
    memset(&my_gid, 0, sizeof(my_gid));
    if (ibv_query_gid(ctx, IB_PORT, 0, &my_gid))
    {
        // ignore error; keep zero gid
    }

    // 4) Build QP pool
    vector<QPWithBufferPool> pool(QP_POOL_SIZE);
    for (int i = 0; i < QP_POOL_SIZE; ++i)
    {
        pool[i].qp = create_qp(pd, cq);
        if (setup_recv_pool(&pool[i].recv_pool, pd))
            die("setup_recv_pool");
        if (modify_qp_to_init(pool[i].qp, IB_PORT))
            die("modify_qp_to_init");
    }

    // 5) Read remote peer info from bundle and move to RTR/RTS
    // Try by-id first (e.g., "cli0"); fall back to [0] if not present.
    const char *sel_id = nullptr;
    if (rr_has("remote.QP[0].qpn"))
    {
        // path-style
        // uint32_t r_qpn = rr_u32("remote.QP[0].qpn");
        // uint32_t r_psn = rr_try_u32("remote.QP[0].psn", 0);
        // uint32_t r_port = rr_try_u32("remote.QP[0].port", IB_PORT);
        // uint16_t r_lid = (uint16_t)rr_try_u32("remote.QP[0].lid", 0);
        // const char *r_gid_str = rr_try_str("remote.QP[0].gid", "00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00");
        // uint8_t dgid[16] = {0};
        // parse_gid_str_colon(r_gid_str, dgid);
        uint32_t r_qpn = rr_u32_by_id("remote.QP", "cli0", "qpn");
        uint32_t r_psn = rr_try_u32_by_id("remote.QP", "cli0", "psn", 0);
        uint32_t r_port = rr_try_u32_by_id("remote.QP", "cli0", "port", IB_PORT);
        uint16_t r_lid = (uint16_t)rr_try_u32_by_id("remote.QP", "cli0", "lid", 0);
        const char *r_gid_str = rr_try_str_by_id("remote.QP", "cli0", "gid", "00:...:00");
        uint8_t dgid[16];
        parse_gid_str_colon(r_gid_str, dgid);

        for (int i = 0; i < QP_POOL_SIZE; ++i)
        {
            if (modify_qp_to_rtr(pool[i].qp, r_qpn, r_lid, dgid, (uint8_t)r_port, r_psn))
            {
                fprintf(stderr, "Failed to RTR on qp %u\n", pool[i].qp->qp_num);
                continue;
            }
            if (modify_qp_to_rts(pool[i].qp, 0))
            {
                fprintf(stderr, "Failed to RTS on qp %u\n", pool[i].qp->qp_num);
                continue;
            }
            post_all_recvs(&pool[i].recv_pool, pool[i].qp);
        }
    }
    else
    {
        fprintf(stderr, "[server] remote.QP not found; skip RTR/RTS.\n");
    }

    // 6) Dump local resources for coordinator
    dump_server_update("server_update.json", pool.data(), (int)pool.size(),
                       port_attr.lid, my_gid.raw, IB_PORT);

    // 7) Poll CQ (optional demo)
    fprintf(stdout, "[server] entering a short CQ poll loop ...\n");
    for (int loops = 0; loops < 100; ++loops)
    {
        ibv_wc wc[16];
        int n = ibv_poll_cq(cq, 16, wc);
        if (n < 0)
            die("ibv_poll_cq");
        if (n > 0)
        {
            for (int i = 0; i < n; ++i)
            {
                if (wc[i].status != IBV_WC_SUCCESS)
                {
                    fprintf(stderr, "WC error: %d opcode=%d\n", wc[i].status, wc[i].opcode);
                }
                else
                {
                    fprintf(stdout, "WC ok: wr_id=%llu, opcode=%d, byte_len=%u\n",
                            (unsigned long long)wc[i].wr_id, wc[i].opcode, wc[i].byte_len);
                }
            }
        }
        usleep(10000);
    }

    // 8) Cleanup
    for (int i = 0; i < (int)pool.size(); ++i)
    {
        destroy_recv_pool(&pool[i].recv_pool);
        ibv_destroy_qp(pool[i].qp);
    }
    ibv_destroy_cq(cq);
    ibv_dealloc_pd(pd);
    ibv_close_device(ctx);
    ibv_free_device_list(dev_list);
    return 0;
}
