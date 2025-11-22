// rdma_server_main.c
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <ctype.h>
#include <pthread.h>

#include <infiniband/verbs.h>
#include <cjson/cJSON.h>

// -------- signal handlers --------
#include <signal.h>

volatile sig_atomic_t g_stop = 0;

static void handle_signal(int signo)
{
    if (signo == SIGINT || signo == SIGTERM)
    {
        g_stop = 1;
    }
}

// -------- 控制平面配置 --------
#define CTRL_PORT 18515
#define CTRL_LISTEN_BACKLOG 16
// 每次 poll 的最大完成数
#define MAX_WC 16

// -------- QP meta 结构 --------
struct qp_meta
{
    uint32_t qpn;
    uint32_t psn;
    uint16_t lid;
    uint8_t port_num;
    uint8_t gid[16];
    uint8_t gid_index;
};

struct server_ctx
{
    struct ibv_context *ctx;
    struct ibv_pd *pd;
    struct ibv_cq *cq;
    uint8_t port_num;
    uint8_t gid_index;

    // QP 表
    struct server_qp_entry *qp_table;
    int qp_table_size;
};

struct server_qp
{
    struct ibv_qp *qp;
    struct qp_meta local_meta;
    struct qp_meta remote_meta;
};

// 每个 QP 的完整信息
struct server_qp_entry
{
    int in_use;
    int ready;            // QP 是否已经连好 (RTR->RTS 并完成 Recv 注册)
    char qp_tag[64];      // "qp0", "qp1", ...
    struct server_qp sqp; // RDMA QP + local/remote meta

    // 为了简单，把接收 buffer 和 MR 也挂在这里
    char *recv_buf;
    struct ibv_mr *recv_mr;
};

// ========= 一些小工具函数 =========

// 简单生成一个 PSN
static uint32_t gen_psn(void)
{
    return (uint32_t)(rand() & 0xffffff);
}

// 把 gid 转为字符串（简单版本）
static void gid_to_str(union ibv_gid *gid, char *buf, size_t len)
{
    // snprintf(buf, len,
    //          "%04x:%04x:%04x:%04x:%04x:%04x:%04x:%04x",
    //          ntohs(gid->raw[0] << 8 | gid->raw[1]),
    //          ntohs(gid->raw[2] << 8 | gid->raw[3]),
    //          ntohs(gid->raw[4] << 8 | gid->raw[5]),
    //          ntohs(gid->raw[6] << 8 | gid->raw[7]),
    //          ntohs(gid->raw[8] << 8 | gid->raw[9]),
    //          ntohs(gid->raw[10] << 8 | gid->raw[11]),
    //          ntohs(gid->raw[12] << 8 | gid->raw[13]),
    //          ntohs(gid->raw[14] << 8 | gid->raw[15]));
    const uint8_t *r = gid->raw;

    // 形式：fe80:0000:0000:0000:1270:fdff:fe2f:b908
    snprintf(buf, len,
             "%02x%02x:%02x%02x:%02x%02x:%02x%02x:"
             "%02x%02x:%02x%02x:%02x%02x:%02x%02x",
             r[0], r[1], r[2], r[3],
             r[4], r[5], r[6], r[7],
             r[8], r[9], r[10], r[11],
             r[12], r[13], r[14], r[15]);
}

// // 这里简单 parse 成 raw gid（你可以以后换成更严谨的）
// static int str_to_gid(const char *s, uint8_t out[16])
// {
//     // 为了简单：先 memset 0，不解析也能跑
//     memset(out, 0, 16);
//     // TODO: 可以按冒号拆分，每段 16bit
//     (void)s;
//     return 0;
// }

static int hex_char_to_val(char c)
{
    if ('0' <= c && c <= '9')
        return c - '0';
    if ('a' <= c && c <= 'f')
        return c - 'a' + 10;
    if ('A' <= c && c <= 'F')
        return c - 'A' + 10;
    return -1;
}

static int parse_hex_byte(const char *p)
{
    int hi = hex_char_to_val(p[0]);
    int lo = hex_char_to_val(p[1]);
    if (hi < 0 || lo < 0)
        return -1;
    return (hi << 4) | lo;
}

/*
 * 支持格式：
 *   1. Full hex with colons:
 *      "00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff"
 *
 *   2. IPv6 style GID:
 *      "fe80::1234:5678:abcd:ef12"
 *
 *   3. Plain 32 hex chars:
 *      "fe8012345678abcd0000000000001234"
 */
int str_to_gid(const char *s, uint8_t out[16])
{
    if (!s || !out)
        return -1;

    memset(out, 0, 16);

    size_t len = strlen(s);

    /* ============================================================
     * Case 1: 32 hex characters (no colon)
     * ============================================================ */
    int hex_count = 0;
    for (size_t i = 0; i < len; i++)
    {
        if (isxdigit((unsigned char)s[i]))
            hex_count++;
    }
    if (hex_count == 32 && (len == 32 || (len > 32 && strchr(s, ':') == NULL)))
    {
        /* Parse each pair */
        for (int i = 0; i < 16; i++)
        {
            int v = parse_hex_byte(s + i * 2);
            if (v < 0)
                return -1;
            out[i] = (uint8_t)v;
        }
        return 0;
    }

    /* ============================================================
     * Case 2: Standard colon-separated 16 bytes:
     *    "aa:bb:cc:dd:ee:ff:..."
     * ============================================================ */
    if (strchr(s, ':'))
    {
        int byte_index = 0;
        const char *p = s;

        char buf[3];
        buf[2] = '\0';

        while (*p && byte_index < 16)
        {
            /* Expect 2 hex digits */
            if (!isxdigit((unsigned char)p[0]) || !isxdigit((unsigned char)p[1]))
                break;

            buf[0] = p[0];
            buf[1] = p[1];

            int v = parse_hex_byte(buf);
            if (v < 0)
                return -1;
            out[byte_index++] = (uint8_t)v;

            p += 2;
            if (*p == ':')
                p++; // skip colon
        }

        if (byte_index == 16)
            return 0;
        /* If less bytes or IPv6 style? Fall through to IPv6 parser */
    }

    /* ============================================================
     * Case 3: IPv6 compressed format (e.g., fe80::1)
     * We'll expand to 16 bytes manually.
     * ============================================================ */
    {
        /* We do a simple IPv6 parser—sufficient for GID usage */
        uint16_t groups[8];
        for (int i = 0; i < 8; i++)
            groups[i] = 0;

        const char *p = s;
        int group_index = 0;
        int double_colon_index = -1;

        while (*p && group_index < 8)
        {
            if (*p == ':')
            {
                /* "::" compression */
                if (p[1] == ':')
                {
                    double_colon_index = group_index;
                    p += 2;
                    if (!*p)
                        break; // ends with "::"
                    continue;
                }
                else
                {
                    p++;
                    continue;
                }
            }

            /* parse group */
            int val = 0;
            int digits = 0;
            while (isxdigit((unsigned char)*p))
            {
                int v = hex_char_to_val(*p);
                if (v < 0)
                    return -1;
                val = (val << 4) | v;
                digits++;
                p++;
            }
            if (digits == 0 || val > 0xffff)
                return -1;

            groups[group_index++] = (uint16_t)val;
        }

        /* handle :: compression */
        if (double_colon_index >= 0)
        {
            int fill = 8 - group_index;
            /* shift tail to the end */
            for (int i = 7; i >= double_colon_index + fill; i--)
            {
                groups[i] = groups[i - fill];
            }
            /* fill zeros */
            for (int i = double_colon_index; i < double_colon_index + fill; i++)
            {
                groups[i] = 0;
            }
        }

        /* Now convert groups[] to bytes */
        for (int i = 0; i < 8; i++)
        {
            out[i * 2] = (uint8_t)((groups[i] >> 8) & 0xFF);
            out[i * 2 + 1] = (uint8_t)(groups[i] & 0xFF);
        }
        return 0;
    }

    return -1; /* invalid format */
}

// 读取一行（\n 结尾），简单 blocking 版本
static int read_line(int fd, char *buf, size_t maxlen)
{
    size_t off = 0;
    while (off + 1 < maxlen)
    {
        char c;
        ssize_t n = read(fd, &c, 1);
        if (n <= 0)
            return -1;
        if (c == '\n')
            break;
        buf[off++] = c;
    }
    buf[off] = '\0';
    return (int)off;
}

static int write_str(int fd, const char *s)
{
    size_t len = strlen(s);
    if (write(fd, s, len) != (ssize_t)len)
        return -1;
    return 0;
}

static const char *wc_opcode_to_str(enum ibv_wc_opcode op)
{
    switch (op)
    {
    case IBV_WC_SEND:
        return "SEND";
    case IBV_WC_RDMA_WRITE:
        return "RDMA_WRITE";
    case IBV_WC_RDMA_READ:
        return "RDMA_READ";
    case IBV_WC_COMP_SWAP:
        return "COMP_SWAP";
    case IBV_WC_FETCH_ADD:
        return "FETCH_ADD";
    case IBV_WC_BIND_MW:
        return "BIND_MW";
    case IBV_WC_LOCAL_INV:
        return "LOCAL_INV";
    case IBV_WC_RECV:
        return "RECV";
    case IBV_WC_RECV_RDMA_WITH_IMM:
        return "RECV_RDMA_WITH_IMM";
    case IBV_WC_TSO:
        return "TSO";
#ifdef IBV_WC_FLUSH
    case IBV_WC_FLUSH:
        return "FLUSH";
#endif
    default:
        return "UNKNOWN";
    }
}

// ========= RDMA 初始化 & QP 创建 =========

static int rdma_server_init(struct server_ctx *sctx)
{
    int num;
    struct ibv_device **dev_list = ibv_get_device_list(&num);
    if (!dev_list || num == 0)
    {
        fprintf(stderr, "[RDMA] No device found\n");
        return -1;
    }

    // 简单起见：直接用第一个设备
    sctx->ctx = ibv_open_device(dev_list[0]);
    if (!sctx->ctx)
    {
        fprintf(stderr, "[RDMA] ibv_open_device failed\n");
        ibv_free_device_list(dev_list);
        return -1;
    }

    sctx->pd = ibv_alloc_pd(sctx->ctx);
    if (!sctx->pd)
    {
        fprintf(stderr, "[RDMA] ibv_alloc_pd failed\n");
        return -1;
    }

    sctx->cq = ibv_create_cq(sctx->ctx, 1024, NULL, NULL, 0);
    if (!sctx->cq)
    {
        fprintf(stderr, "[RDMA] ibv_create_cq failed\n");
        return -1;
    }

    sctx->port_num = 1;
    sctx->gid_index = 3; // 你可以根据 REQ_CONNECT 里的 gid_index 来设置

    // 初始化 QP 表，先给个固定上限，比如 128 个 QP
    sctx->qp_table_size = 128;
    sctx->qp_table = calloc(sctx->qp_table_size, sizeof(struct server_qp_entry));
    if (!sctx->qp_table)
    {
        fprintf(stderr, "[RDMA] alloc qp_table failed\n");
        return -1;
    }

    fprintf(stderr, "[RDMA] Server RDMA init OK\n");
    ibv_free_device_list(dev_list);
    return 0;
}

// 在 qp_table 中查找已有的 QP entry
static struct server_qp_entry *server_find_qp_entry(struct server_ctx *sctx,
                                                    const char *qp_tag)
{
    for (int i = 0; i < sctx->qp_table_size; i++)
    {
        struct server_qp_entry *e = &sctx->qp_table[i];
        if (e->in_use && strcmp(e->qp_tag, qp_tag) == 0)
        {
            return e;
        }
    }
    return NULL;
}

static struct server_qp_entry *
server_find_qp_by_qp_num(struct server_ctx *sctx, uint32_t qp_num)
{
    for (int i = 0; i < sctx->qp_table_size; i++)
    {
        struct server_qp_entry *e = &sctx->qp_table[i];
        if (!e->in_use || !e->sqp.qp)
            continue;
        if (e->sqp.qp->qp_num == qp_num)
        {
            return e;
        }
    }
    return NULL;
}

// 找到一个空 slot，用这个 qp_tag 新建 entry
static struct server_qp_entry *server_alloc_qp_entry(struct server_ctx *sctx,
                                                     const char *qp_tag)
{
    // 如果已经存在同名，就直接返回（允许 client 重连时复用）
    struct server_qp_entry *exist = server_find_qp_entry(sctx, qp_tag);
    if (exist)
    {
        return exist;
    }

    for (int i = 0; i < sctx->qp_table_size; i++)
    {
        struct server_qp_entry *e = &sctx->qp_table[i];
        if (!e->in_use)
        {
            e->in_use = 1;
            e->ready = 0;
            strncpy(e->qp_tag, qp_tag, sizeof(e->qp_tag) - 1);
            e->qp_tag[sizeof(e->qp_tag) - 1] = '\0';
            // 其他字段先清零
            memset(&e->sqp, 0, sizeof(e->sqp));
            e->recv_buf = NULL;
            e->recv_mr = NULL;
            return e;
        }
    }

    fprintf(stderr, "[RDMA] qp_table full, cannot allocate new QP for tag=%s\n", qp_tag);
    return NULL;
}

static int server_create_qp(struct server_ctx *sctx,
                            struct server_qp *sqp,
                            struct qp_meta *out_meta)
{
    struct ibv_qp_init_attr init_attr = {
        .qp_context = NULL,
        .send_cq = sctx->cq,
        .recv_cq = sctx->cq,
        .cap = {
            .max_send_wr = 128,
            .max_recv_wr = 128,
            .max_send_sge = 4,
            .max_recv_sge = 4,
        },
        .qp_type = IBV_QPT_RC,
        .sq_sig_all = 0,
    };

    struct ibv_qp *qp = ibv_create_qp(sctx->pd, &init_attr);
    if (!qp)
    {
        fprintf(stderr, "[RDMA] ibv_create_qp failed\n");
        return -1;
    }

    sqp->qp = qp;

    // local_meta 填上 qpn / psn / port / gid
    memset(out_meta, 0, sizeof(*out_meta));
    out_meta->qpn = qp->qp_num;
    out_meta->psn = gen_psn();
    out_meta->port_num = sctx->port_num;
    out_meta->gid_index = sctx->gid_index;

    // lid 对 RoCE 可以不用，这里填 0
    out_meta->lid = 0;

    union ibv_gid gid;
    if (ibv_query_gid(sctx->ctx, sctx->port_num, sctx->gid_index, &gid) != 0)
    {
        fprintf(stderr, "[RDMA] ibv_query_gid failed, use zero gid\n");
        memset(out_meta->gid, 0, 16);
    }
    else
    {
        memcpy(out_meta->gid, gid.raw, 16);
    }
    // printf("out_meta->qpn=%u, psn=%u, port_num=%u, gid_index=%u\n",
    //        out_meta->qpn, out_meta->psn, out_meta->port_num, out_meta->gid_index);
    // printf("out_meta->gid: ");
    // for (int i = 0; i < 16; i++)
    //     printf("%02x", out_meta->gid[i]);
    // printf("\n");

    // 先把 QP 改到 INIT
    struct ibv_qp_attr attr = {
        .qp_state = IBV_QPS_INIT,
        .pkey_index = 0,
        .port_num = sctx->port_num,
        .qp_access_flags = IBV_ACCESS_LOCAL_WRITE |
                           IBV_ACCESS_REMOTE_READ |
                           IBV_ACCESS_REMOTE_WRITE,
    };

    if (ibv_modify_qp(qp, &attr,
                      IBV_QP_STATE |
                          IBV_QP_PKEY_INDEX |
                          IBV_QP_PORT |
                          IBV_QP_ACCESS_FLAGS))
    {
        fprintf(stderr, "[RDMA] ibv_modify_qp INIT failed\n");
        return -1;
    }

    // 存 local_meta
    sqp->local_meta = *out_meta;

    fprintf(stderr, "[RDMA] server QP created: qpn=%u, psn=%u\n",
            out_meta->qpn, out_meta->psn);
    return 0;
}

// 根据 local_meta / remote_meta 把 QP 改到 RTR/RTS
static int server_connect_qp(struct server_ctx *sctx,
                             struct server_qp_entry *entry)
{
    struct ibv_qp *qp = entry->sqp.qp;
    struct qp_meta *local = &entry->sqp.local_meta;
    struct qp_meta *remote = &entry->sqp.remote_meta;

    // RTR
    struct ibv_qp_attr attr = {
        .qp_state = IBV_QPS_RTR,
        .path_mtu = IBV_MTU_1024,
        .dest_qp_num = remote->qpn,
        .rq_psn = remote->psn,
        .max_dest_rd_atomic = 1,
        .min_rnr_timer = 12,
        .ah_attr = {
            .is_global = 1,
            .port_num = sctx->port_num,
            .grh = {
                .dgid = {0},
                .flow_label = 0,
                .sgid_index = local->gid_index,
                .hop_limit = 1,
                .traffic_class = 0,
            },
        },
    };
    // printf("port_num: %u, gid_index=%u\n", attr.ah_attr.port_num, attr.ah_attr.grh.sgid_index);

    memcpy(attr.ah_attr.grh.dgid.raw, remote->gid, 16);
    // printf("remote gid: ");
    // for (int i = 0; i < 16; i++)
    //     printf("%02x", attr.ah_attr.grh.dgid.raw[i]);
    // printf("\n");

    if (ibv_modify_qp(qp, &attr,
                      IBV_QP_STATE |
                          IBV_QP_AV |
                          IBV_QP_PATH_MTU |
                          IBV_QP_DEST_QPN |
                          IBV_QP_RQ_PSN |
                          IBV_QP_MAX_DEST_RD_ATOMIC |
                          IBV_QP_MIN_RNR_TIMER))
    {
        fprintf(stderr, "[RDMA] ibv_modify_qp RTR failed\n");
        return -1;
    }

    // RTS
    memset(&attr, 0, sizeof(attr));
    attr.qp_state = IBV_QPS_RTS;
    attr.timeout = 14;
    attr.retry_cnt = 7;
    attr.rnr_retry = 7;
    attr.sq_psn = local->psn;
    attr.max_rd_atomic = 1;

    if (ibv_modify_qp(qp, &attr,
                      IBV_QP_STATE |
                          IBV_QP_TIMEOUT |
                          IBV_QP_RETRY_CNT |
                          IBV_QP_RNR_RETRY |
                          IBV_QP_SQ_PSN |
                          IBV_QP_MAX_QP_RD_ATOMIC))
    {
        fprintf(stderr, "[RDMA] ibv_modify_qp RTS failed\n");
        return -1;
    }

    // ====== 为这个 QP 准备一个 Recv buffer ======
    entry->recv_buf = calloc(4096, sizeof(char));
    if (!entry->recv_buf)
    {
        fprintf(stderr, "[RDMA] calloc recv_buf failed\n");
        return -1;
    }

    entry->recv_mr = ibv_reg_mr(sctx->pd, entry->recv_buf, 4096,
                                IBV_ACCESS_LOCAL_WRITE);
    if (!entry->recv_mr)
    {
        fprintf(stderr, "[RDMA] ibv_reg_mr failed\n");
        free(entry->recv_buf);
        entry->recv_buf = NULL;
        return -1;
    }

    struct ibv_sge sge = {
        .addr = (uintptr_t)entry->recv_buf,
        .length = 4096,
        .lkey = entry->recv_mr->lkey,
    };
    struct ibv_recv_wr wr = {
        .wr_id = 0,
        .sg_list = &sge,
        .num_sge = 1,
    };
    struct ibv_recv_wr *bad_wr = NULL;
    fprintf(stderr, "[RDMA] Posting initial Recv WR for tag=%s\n", entry->qp_tag);
    if (ibv_post_recv(qp, &wr, &bad_wr))
    {
        fprintf(stderr, "[RDMA] ibv_post_recv failed\n");
        // 根据需要决定是否 free MR / buf
        return -1;
    }

    entry->ready = 1;
    fprintf(stderr, "[RDMA] server QP connected (RTR->RTS), tag=%s, qpn=%u\n",
            entry->qp_tag, local->qpn);

    return 0;
}

static void server_cleanup(struct server_ctx *sctx)
{
    if (!sctx)
        return;

    // 1. 清理 QP 表
    if (sctx->qp_table)
    {
        for (int i = 0; i < sctx->qp_table_size; i++)
        {
            struct server_qp_entry *e = &sctx->qp_table[i];
            if (!e->in_use)
                continue;

            // destroy QP
            if (e->sqp.qp)
            {
                ibv_destroy_qp(e->sqp.qp);
                e->sqp.qp = NULL;
            }

            // dereg MR & free buf
            if (e->recv_mr)
            {
                ibv_dereg_mr(e->recv_mr);
                e->recv_mr = NULL;
            }
            if (e->recv_buf)
            {
                free(e->recv_buf);
                e->recv_buf = NULL;
            }

            e->in_use = 0;
            e->ready = 0;
        }
        free(sctx->qp_table);
        sctx->qp_table = NULL;
        sctx->qp_table_size = 0;
    }

    // 2. CQ / PD / ctx
    if (sctx->cq)
    {
        ibv_destroy_cq(sctx->cq);
        sctx->cq = NULL;
    }

    if (sctx->pd)
    {
        ibv_dealloc_pd(sctx->pd);
        sctx->pd = NULL;
    }

    if (sctx->ctx)
    {
        ibv_close_device(sctx->ctx);
        sctx->ctx = NULL;
    }

    fprintf(stderr, "[RDMA] server_cleanup done\n");
}

static void *cq_poll_loop(void *arg)
{
    struct server_ctx *sctx = (struct server_ctx *)arg;
    struct ibv_wc wc[MAX_WC];

    fprintf(stderr, "[POLL] CQ poll loop started\n");

    while (!g_stop)
    {
        int ne = ibv_poll_cq(sctx->cq, MAX_WC, wc);
        if (ne < 0)
        {
            fprintf(stderr, "[POLL] ibv_poll_cq error: %d\n", ne);
            continue;
        }
        if (ne == 0)
        {
            // 没有完成，稍微 sleep 一下防止空转占用太高
            usleep(1000);
            continue;
        }

        for (int i = 0; i < ne; i++)
        {
            struct ibv_wc *w = &wc[i];
            fprintf(stderr, "[POLL] Got completion: wc[%d]: status=%s(%d), opcode=%s(%d), qp_num=%u, wr_id=%llu, byte_len=%u\n",
                    i,
                    ibv_wc_status_str(w->status), w->status,
                    wc_opcode_to_str(w->opcode), w->opcode,
                    w->qp_num,
                    (unsigned long long)w->wr_id,
                    w->byte_len);
            if (w->status != IBV_WC_SUCCESS)
            {
                const char *status_str = ibv_wc_status_str(w->status);
                const char *opcode_str = wc_opcode_to_str(w->opcode);

                // 先尝试找到这个 completion 对应的 QP entry
                struct server_qp_entry *entry =
                    server_find_qp_by_qp_num(sctx, w->qp_num);

                const char *tag = entry ? entry->qp_tag : "?";

                // 粗粒度描述这个 WR 是干嘛的（基于 wr_id + opcode）
                const char *wr_desc = "unknown WR";
                if (w->opcode == IBV_WC_RECV || w->opcode == IBV_WC_RECV_RDMA_WITH_IMM)
                {
                    if (w->wr_id == 0)
                        wr_desc = "server pre-posted RECV (entry->recv_buf / recv_mr)";
                    else
                        wr_desc = "application RECV WR";
                }
                else
                {
                    if (w->wr_id == 1)
                        wr_desc = "server echo SEND WR";
                    else
                        wr_desc = "application SEND/ATOMIC/WRITE WR";
                }

                fprintf(stderr,
                        "[POLL] Completion ERROR on tag=%s\n"
                        "       status=%s(%d), opcode=%s(%d), qp_num=%u, wr_id=%llu\n"
                        "       wr_desc=%s\n",
                        tag,
                        status_str, w->status,
                        opcode_str, w->opcode,
                        w->qp_num,
                        (unsigned long long)w->wr_id,
                        wr_desc);

                // 如果是 RECV 错误，还可以顺便打印一下当前 Recv buffer 的信息
                if (entry && (w->opcode == IBV_WC_RECV || w->opcode == IBV_WC_RECV_RDMA_WITH_IMM))
                {
                    if (entry->recv_mr)
                    {
                        fprintf(stderr,
                                "       RECV buf addr=%p, length=4096, lkey=0x%x\n",
                                (void *)entry->recv_buf,
                                entry->recv_mr->lkey);
                    }
                    else
                    {
                        fprintf(stderr,
                                "       WARNING: entry->recv_mr is NULL, Recv MR not registered?\n");
                    }
                }

                // 你也可以在这里根据错误类型做一些恢复，比如 RDMA_CM_EVENT / QP reset 等
                continue;
            }

            // 找到对应的 QP entry
            struct server_qp_entry *entry =
                server_find_qp_by_qp_num(sctx, w->qp_num);
            if (!entry)
            {
                fprintf(stderr,
                        "[POLL] QP entry not found for qp_num=%u\n",
                        w->qp_num);
                continue;
            }

            switch (w->opcode)
            {
            case IBV_WC_RECV:
            case IBV_WC_RECV_RDMA_WITH_IMM:
            {
                // 收到数据，打印出来
                uint32_t len = w->byte_len;
                fprintf(stderr,
                        "[POLL] RECV: tag=%s, qp_num=%u, len=%u\n",
                        entry->qp_tag, w->qp_num, len);

                // 打印前 64 字节（以字符串形式），避免污染终端
                uint32_t to_print = len < 64 ? len : 64;
                fprintf(stderr, "[POLL] RECV data (first %u bytes): \"", to_print);
                for (uint32_t j = 0; j < to_print; j++)
                {
                    char c = entry->recv_buf[j];
                    if (c >= 32 && c < 127)
                    {
                        fputc(c, stderr);
                    }
                    else
                    {
                        fputc('.', stderr);
                    }
                }
                fprintf(stderr, "\"\n");

                // 简单 echo：把同一块 buffer 原样发回去
                struct ibv_sge sge = {
                    .addr = (uintptr_t)entry->recv_buf,
                    .length = len,
                    .lkey = entry->recv_mr->lkey,
                };
                struct ibv_send_wr send_wr = {
                    .wr_id = 1, // 你也可以用不同 wr_id 做区分
                    .sg_list = &sge,
                    .num_sge = 1,
                    .opcode = IBV_WR_SEND,
                    .send_flags = IBV_SEND_SIGNALED,
                };
                struct ibv_send_wr *bad_wr = NULL;
                int ret = ibv_post_send(entry->sqp.qp, &send_wr, &bad_wr);
                if (ret)
                {
                    fprintf(stderr,
                            "[POLL] ibv_post_send (echo) failed, ret=%d\n",
                            ret);
                }
                else
                {
                    fprintf(stderr,
                            "[POLL] Echo SEND posted for tag=%s, len=%u\n",
                            entry->qp_tag, len);
                }

                // 再 post 一个新的 Recv，保持 pipeline
                struct ibv_sge rsge = {
                    .addr = (uintptr_t)entry->recv_buf,
                    .length = 4096,
                    .lkey = entry->recv_mr->lkey,
                };
                struct ibv_recv_wr recv_wr = {
                    .wr_id = 0,
                    .sg_list = &rsge,
                    .num_sge = 1,
                };
                struct ibv_recv_wr *bad_recv_wr = NULL;
                ret = ibv_post_recv(entry->sqp.qp, &recv_wr, &bad_recv_wr);
                fprintf(stderr, "[POLL] ibv_post_recv (new) posted for tag=%s\n", entry->qp_tag);
                if (ret)
                {
                    fprintf(stderr,
                            "[POLL] ibv_post_recv failed, ret=%d\n", ret);
                }
                else
                {
                    fprintf(stderr,
                            "[POLL] Re-armed RECV for tag=%s\n",
                            entry->qp_tag);
                }

                break;
            }

            case IBV_WC_SEND:
            {
                fprintf(stderr,
                        "[POLL] SEND completed: tag=%s, qp_num=%u, wr_id=%llu\n",
                        entry->qp_tag, w->qp_num,
                        (unsigned long long)w->wr_id);
                break;
            }

            default:
                fprintf(stderr,
                        "[POLL] Other completion: opcode=%d, qp_num=%u, wr_id=%llu\n",
                        w->opcode, w->qp_num,
                        (unsigned long long)w->wr_id);
                break;
            }
        }
    }

    return NULL;
}

// ========= JSON 编解码：qp_meta / 消息 =========

static cJSON *qp_meta_to_json(const struct qp_meta *m)
{
    cJSON *obj = cJSON_CreateObject();
    cJSON_AddNumberToObject(obj, "qpn", m->qpn);
    cJSON_AddNumberToObject(obj, "psn", m->psn);
    cJSON_AddNumberToObject(obj, "lid", m->lid);
    cJSON_AddNumberToObject(obj, "port_num", m->port_num);

    char gid_str[128];
    union ibv_gid gid;
    memcpy(gid.raw, m->gid, 16);
    gid_to_str(&gid, gid_str, sizeof(gid_str));
    cJSON_AddStringToObject(obj, "gid", gid_str);
    // printf("gid_str=%s\n", gid_str);

    cJSON_AddNumberToObject(obj, "gid_index", m->gid_index);
    return obj;
}

static int qp_meta_from_json(cJSON *obj, struct qp_meta *m_out)
{
    if (!cJSON_IsObject(obj))
        return -1;
    memset(m_out, 0, sizeof(*m_out));

    cJSON *qpn = cJSON_GetObjectItemCaseSensitive(obj, "qpn");
    cJSON *psn = cJSON_GetObjectItemCaseSensitive(obj, "psn");
    cJSON *lid = cJSON_GetObjectItemCaseSensitive(obj, "lid");
    cJSON *port = cJSON_GetObjectItemCaseSensitive(obj, "port_num");
    cJSON *gid = cJSON_GetObjectItemCaseSensitive(obj, "gid");
    cJSON *gix = cJSON_GetObjectItemCaseSensitive(obj, "gid_index");

    if (!cJSON_IsNumber(qpn) || !cJSON_IsNumber(psn) ||
        !cJSON_IsNumber(port) || !cJSON_IsString(gid))
    {
        return -1;
    }

    m_out->qpn = (uint32_t)qpn->valuedouble;
    m_out->psn = (uint32_t)psn->valuedouble;
    m_out->lid = cJSON_IsNumber(lid) ? (uint16_t)lid->valuedouble : 0;
    m_out->port_num = (uint8_t)port->valuedouble;
    m_out->gid_index = cJSON_IsNumber(gix) ? (uint8_t)gix->valuedouble : 0;

    str_to_gid(gid->valuestring, m_out->gid);

    return 0;
}

// ========= 核心：处理一次连接（一个 client） =========

static int handle_client(int conn_fd, struct server_ctx *sctx)
{
    char buf[2048];

    // 1) 读 REQ_CONNECT
    int n = read_line(conn_fd, buf, sizeof(buf));
    if (n <= 0)
        return -1;

    cJSON *root = cJSON_Parse(buf);
    if (!root)
    {
        fprintf(stderr, "[CTRL] invalid JSON from client\n");
        return -1;
    }

    cJSON *type = cJSON_GetObjectItemCaseSensitive(root, "type");
    if (!cJSON_IsString(type) || strcmp(type->valuestring, "REQ_CONNECT") != 0)
    {
        fprintf(stderr, "[CTRL] expected REQ_CONNECT\n");
        cJSON_Delete(root);
        return -1;
    }

    cJSON *qp_tag = cJSON_GetObjectItemCaseSensitive(root, "qp_tag");
    cJSON *port = cJSON_GetObjectItemCaseSensitive(root, "port_num");
    cJSON *gix = cJSON_GetObjectItemCaseSensitive(root, "gid_index");
    if (cJSON_IsNumber(port))
        sctx->port_num = (uint8_t)port->valuedouble;
    if (cJSON_IsNumber(gix))
        sctx->gid_index = (uint8_t)gix->valuedouble;

    const char *qp_tag_str = cJSON_IsString(qp_tag) ? qp_tag->valuestring : "qp0";
    // 在栈上留一个本地 buffer
    char qp_tag_buf[64];
    if (cJSON_IsString(qp_tag) && qp_tag->valuestring)
    {
        // 拷贝一份，保证以 '\0' 结尾
        strncpy(qp_tag_buf, qp_tag->valuestring, sizeof(qp_tag_buf) - 1);
        qp_tag_buf[sizeof(qp_tag_buf) - 1] = '\0';
    }
    else
    {
        strcpy(qp_tag_buf, "qp0");
    }

    fprintf(stderr, "[CTRL] REQ_CONNECT for %s\n", qp_tag_buf);
    cJSON_Delete(root);

    // 2) 创建 server QP 并返回 RESP_CONNECT
    // 2) 为这个 qp_tag 分配 / 查找一个 QP entry
    struct server_qp_entry *entry = server_alloc_qp_entry(sctx, qp_tag_buf);
    if (!entry)
    {
        fprintf(stderr, "[CTRL] server_alloc_qp_entry failed for %s\n", qp_tag_buf);
        return -1;
    }

    if (server_create_qp(sctx, &entry->sqp, &entry->sqp.local_meta) != 0)
    {
        fprintf(stderr, "[CTRL] server_create_qp failed\n");
        return -1;
    }

    cJSON *resp = cJSON_CreateObject();
    cJSON_AddStringToObject(resp, "type", "RESP_CONNECT");
    cJSON_AddStringToObject(resp, "qp_tag", qp_tag_buf);
    cJSON_AddStringToObject(resp, "status", "OK");
    cJSON_AddItemToObject(resp, "server_meta",
                          qp_meta_to_json(&entry->sqp.local_meta));

    char *resp_str = cJSON_PrintUnformatted(resp);
    cJSON_Delete(resp);

    if (!resp_str)
        return -1;
    // 以 '\n' 结尾方便 client 按行读取
    write_str(conn_fd, resp_str);
    write_str(conn_fd, "\n");
    free(resp_str);

    // 3) 等待 CLIENT_META
    n = read_line(conn_fd, buf, sizeof(buf));
    if (n <= 0)
        return -1;

    cJSON *root2 = cJSON_Parse(buf);
    if (!root2)
    {
        fprintf(stderr, "[CTRL] invalid JSON CLIENT_META\n");
        return -1;
    }

    cJSON *type2 = cJSON_GetObjectItemCaseSensitive(root2, "type");
    if (!cJSON_IsString(type2) || strcmp(type2->valuestring, "CLIENT_META") != 0)
    {
        fprintf(stderr, "[CTRL] expected CLIENT_META\n");
        cJSON_Delete(root2);
        return -1;
    }

    cJSON *client_meta_obj = cJSON_GetObjectItemCaseSensitive(root2, "client_meta");
    if (!client_meta_obj)
    {
        fprintf(stderr, "[CTRL] CLIENT_META missing client_meta\n");
        cJSON_Delete(root2);
        return -1;
    }

    if (qp_meta_from_json(client_meta_obj, &entry->sqp.remote_meta) != 0)
    {
        fprintf(stderr, "[CTRL] failed to parse client_meta\n");
        cJSON_Delete(root2);
        return -1;
    }
    cJSON_Delete(root2);

    // 4) 把 server QP 改到 RTR/RTS
    if (server_connect_qp(sctx, entry) != 0)
    {
        fprintf(stderr, "[CTRL] server_connect_qp failed\n");
        return -1;
    }

    // 5) 回 READY
    cJSON *ready = cJSON_CreateObject();
    cJSON_AddStringToObject(ready, "type", "READY");
    cJSON_AddStringToObject(ready, "qp_tag", qp_tag_buf);
    cJSON_AddStringToObject(ready, "status", "OK");
    char *ready_str = cJSON_PrintUnformatted(ready);
    cJSON_Delete(ready);

    if (ready_str)
    {
        write_str(conn_fd, ready_str);
        write_str(conn_fd, "\n");
        free(ready_str);
    }

    fprintf(stderr, "[CTRL] QP %s connected and READY\n", qp_tag_buf);

    // 后续你可以在这里：
    // - 为 sqp 关联一个 Worker 线程
    // - 或加入一个全局 QP 表，交给 CQ poll loop 使用
    return 0;
}

int main(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    srand((unsigned)time(NULL));

    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = handle_signal;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGTERM, &sa, NULL);

    struct server_ctx sctx;
    memset(&sctx, 0, sizeof(sctx));
    if (rdma_server_init(&sctx) != 0)
    {
        return 1;
    }

    // 启动一个独立线程轮询 CQ
    pthread_t poll_tid;
    if (pthread_create(&poll_tid, NULL, cq_poll_loop, &sctx) != 0)
    {
        perror("pthread_create cq_poll_loop");
        return 1;
    }

    int listen_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (listen_fd < 0)
    {
        perror("socket");
        return 1;
    }

    int opt = 1;
    setsockopt(listen_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(CTRL_PORT);

    if (bind(listen_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0)
    {
        perror("bind");
        return 1;
    }

    if (listen(listen_fd, CTRL_LISTEN_BACKLOG) < 0)
    {
        perror("listen");
        return 1;
    }

    fprintf(stderr, "[CTRL] RDMA server listening on port %d\n", CTRL_PORT);

    while (!g_stop)
    {
        struct sockaddr_in cli;
        socklen_t clilen = sizeof(cli);
        int conn_fd = accept(listen_fd, (struct sockaddr *)&cli, &clilen);
        if (conn_fd < 0)
        {
            if (errno == EINTR && g_stop)
            {
                // 被信号打断，且我们准备退出了
                break;
            }
            perror("accept");
            continue;
        }

        fprintf(stderr, "[CTRL] client connected\n");
        // 简化：一个连接里只处理一次 REQ_CONNECT/CLIENT_META
        handle_client(conn_fd, &sctx);
        close(conn_fd);
        fprintf(stderr, "[CTRL] client disconnected\n");
    }
    // 跳出循环后继续做清理
    fprintf(stderr, "[CTRL] main loop exiting\n");

    // 停止 CQ poll 线程
    g_stop = 1; // 再保险设置一次
    pthread_join(poll_tid, NULL);

    // 关闭 listening socket
    close(listen_fd);

    // 清理 RDMA 资源
    server_cleanup(&sctx);

    return 0;
}