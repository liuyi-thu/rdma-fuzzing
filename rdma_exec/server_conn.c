// server_conn.c
#include "server_conn.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <unistd.h>
#include <errno.h>
#include <arpa/inet.h>
#include <netinet/in.h>

// ======== 简单的全局连接表（最多支持 128 个 QP） ========

#define MAX_SERVER_CONNS 128

static ServerConn g_conns[MAX_SERVER_CONNS];

void server_conn_global_init(void)
{
    memset(g_conns, 0, sizeof(g_conns));
}

static ServerConn *find_conn_by_qp_name(const char *qp_name)
{
    for (int i = 0; i < MAX_SERVER_CONNS; i++)
    {
        if (g_conns[i].connected &&
            strcmp(g_conns[i].qp_name, qp_name) == 0)
        {
            return &g_conns[i];
        }
    }
    return NULL;
}

static ServerConn *alloc_conn_slot(const char *qp_name)
{
    // 如果已经有这个 qp_name，复用
    ServerConn *c = find_conn_by_qp_name(qp_name);
    if (c)
        return c;

    for (int i = 0; i < MAX_SERVER_CONNS; i++)
    {
        if (!g_conns[i].connected && g_conns[i].sockfd == 0)
        {
            memset(&g_conns[i], 0, sizeof(ServerConn));
            strncpy(g_conns[i].qp_name, qp_name, sizeof(g_conns[i].qp_name) - 1);
            strncpy(g_conns[i].qp_tag, qp_name, sizeof(g_conns[i].qp_tag) - 1);
            return &g_conns[i];
        }
    }
    fprintf(stderr, "[SERVER_CONN] no free slot for qp=%s\n", qp_name);
    return NULL;
}

// ======== 小工具：tcp 连接 + 按行收发 JSON ========

static int tcp_connect_simple(const char *ip, int port)
{
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0)
    {
        perror("[SERVER_CONN] socket");
        return -1;
    }

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons((uint16_t)port);
    if (inet_pton(AF_INET, ip, &addr.sin_addr) <= 0)
    {
        perror("[SERVER_CONN] inet_pton");
        close(fd);
        return -1;
    }

    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0)
    {
        perror("[SERVER_CONN] connect");
        close(fd);
        return -1;
    }
    return fd;
}

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
    ssize_t n = write(fd, s, len);
    return (n == (ssize_t)len) ? 0 : -1;
}

static int send_json_line(int fd, cJSON *obj)
{
    char *s = cJSON_PrintUnformatted(obj);
    if (!s)
        return -1;
    int ret = 0;
    if (write_str(fd, s) || write_str(fd, "\n"))
    {
        ret = -1;
    }
    free(s);
    return ret;
}

static cJSON *recv_json_line(int fd)
{
    char buf[4096];
    int n = read_line(fd, buf, sizeof(buf));
    if (n <= 0)
        return NULL;
    return cJSON_Parse(buf);
}

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

// ======== qp_meta <-> JSON & GID 处理 ========

static void gid_to_str(const uint8_t gid[16], char *buf, size_t len)
{
    snprintf(buf, len,
             "%02x%02x:%02x%02x:%02x%02x:%02x%02x:"
             "%02x%02x:%02x%02x:%02x%02x:%02x%02x",
             gid[0], gid[1], gid[2], gid[3],
             gid[4], gid[5], gid[6], gid[7],
             gid[8], gid[9], gid[10], gid[11],
             gid[12], gid[13], gid[14], gid[15]);
}

static cJSON *qp_meta_to_json(const struct qp_meta *m)
{
    cJSON *obj = cJSON_CreateObject();
    cJSON_AddNumberToObject(obj, "qpn", m->qpn);
    cJSON_AddNumberToObject(obj, "psn", m->psn);
    cJSON_AddNumberToObject(obj, "lid", m->lid);
    cJSON_AddNumberToObject(obj, "port_num", m->port_num);
    cJSON_AddNumberToObject(obj, "gid_index", m->gid_index);

    char gid_str[128];
    gid_to_str(m->gid, gid_str, sizeof(gid_str));
    cJSON_AddStringToObject(obj, "gid", gid_str);
    return obj;
}

static int str_to_gid(const char *s, uint8_t out[16])
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

    if (str_to_gid(gid->valuestring, m_out->gid) != 0)
    {
        fprintf(stderr, "[SERVER_CONN] str_to_gid failed for %s\n", gid->valuestring);
        return -1;
    }
    return 0;
}

// 简单生成一个 PSN（和 server 一致）
static uint32_t gen_psn(void)
{
    return (uint32_t)(rand() & 0xffffff);
}

// ======== 填充 local_meta：从 env / QP / ctx 里来 ========

static int fill_local_meta_from_env(ResourceEnv *env,
                                    QpResource *qp_res,
                                    struct qp_meta *m_out)
{
    if (!env || !qp_res || !qp_res->qp)
        return -1;

    memset(m_out, 0, sizeof(*m_out));
    m_out->qpn = qp_res->qp->qp_num;
    m_out->psn = gen_psn();

    // ⚠️ 这里假设 ResourceEnv 里能拿到 ctx / port_num / gid_index
    // 你需要根据自己的实现改一下：
    struct ibv_context *ctx = env->ctx; // TODO: 替换成 env_get_ctx(env)
    uint8_t port_num = env->port_num;   // TODO: 替换成 env_get_port_num(env)
    uint8_t gid_index = env->gid_index; // TODO: 替换成 env_get_gid_index(env)

    m_out->port_num = port_num;
    m_out->gid_index = gid_index;
    m_out->lid = 0; // RoCE 下 LID 用不到，保持 0

    printf("port_num=%u, gid_index=%u\n", port_num, gid_index);

    union ibv_gid gid;
    if (ibv_query_gid(ctx, port_num, gid_index, &gid) != 0)
    {
        fprintf(stderr, "[SERVER_CONN] ibv_query_gid failed, use zero gid\n");
        memset(m_out->gid, 0, 16);
    }
    else
    {
        memcpy(m_out->gid, gid.raw, 16);
    }
    return 0;
}

// ======== 对外 API：握手 & 填充 ModifyQP attr ========

int server_handshake_for_qp(ResourceEnv *env,
                            const char *qp_name,
                            const char *server_ip,
                            int server_port)
{
    if (!env || !qp_name || !server_ip)
        return -1;

    QpResource *qp_res = env_find_qp(env, qp_name);
    if (!qp_res || !qp_res->qp)
    {
        fprintf(stderr, "[SERVER_CONN] handshake: QP '%s' not found\n", qp_name);
        return -1;
    }

    ServerConn *conn = alloc_conn_slot(qp_name);
    if (!conn)
        return -1;

    // 建立 TCP 连接
    int fd = tcp_connect_simple(server_ip, server_port);
    if (fd < 0)
    {
        fprintf(stderr, "[SERVER_CONN] handshake: tcp_connect_simple failed\n");
        return -1;
    }
    conn->sockfd = fd;

    // 填 local_meta
    if (fill_local_meta_from_env(env, qp_res, &conn->local_meta) != 0)
    {
        fprintf(stderr, "[SERVER_CONN] handshake: fill_local_meta_from_env failed\n");
        close(fd);
        conn->sockfd = 0;
        return -1;
    }

    // 1) 发送 REQ_CONNECT
    cJSON *req = cJSON_CreateObject();
    cJSON_AddStringToObject(req, "type", "REQ_CONNECT");
    cJSON_AddStringToObject(req, "qp_tag", conn->qp_tag);
    cJSON_AddNumberToObject(req, "port_num", conn->local_meta.port_num);
    cJSON_AddNumberToObject(req, "gid_index", conn->local_meta.gid_index);

    if (send_json_line(fd, req) != 0)
    {
        fprintf(stderr, "[SERVER_CONN] send REQ_CONNECT failed\n");
        cJSON_Delete(req);
        close(fd);
        conn->sockfd = 0;
        return -1;
    }
    cJSON_Delete(req);

    // 2) 接收 RESP_CONNECT
    cJSON *resp = recv_json_line(fd);
    if (!resp)
    {
        fprintf(stderr, "[SERVER_CONN] recv RESP_CONNECT failed\n");
        close(fd);
        conn->sockfd = 0;
        return -1;
    }

    cJSON *type = cJSON_GetObjectItemCaseSensitive(resp, "type");
    if (!cJSON_IsString(type) || strcmp(type->valuestring, "RESP_CONNECT") != 0)
    {
        fprintf(stderr, "[SERVER_CONN] expect RESP_CONNECT, got something else\n");
        cJSON_Delete(resp);
        close(fd);
        conn->sockfd = 0;
        return -1;
    }

    cJSON *status = cJSON_GetObjectItemCaseSensitive(resp, "status");
    if (!cJSON_IsString(status) || strcmp(status->valuestring, "OK") != 0)
    {
        fprintf(stderr, "[SERVER_CONN] RESP_CONNECT status != OK\n");
        cJSON_Delete(resp);
        close(fd);
        conn->sockfd = 0;
        return -1;
    }

    cJSON *server_meta_obj = cJSON_GetObjectItemCaseSensitive(resp, "server_meta");
    if (!server_meta_obj ||
        qp_meta_from_json(server_meta_obj, &conn->remote_meta) != 0)
    {
        fprintf(stderr, "[SERVER_CONN] parse server_meta failed\n");
        cJSON_Delete(resp);
        close(fd);
        conn->sockfd = 0;
        return -1;
    }
    cJSON_Delete(resp);

    // 3) 发送 CLIENT_META
    cJSON *cli = cJSON_CreateObject();
    cJSON_AddStringToObject(cli, "type", "CLIENT_META");
    cJSON_AddItemToObject(cli, "client_meta", qp_meta_to_json(&conn->local_meta));

    if (send_json_line(fd, cli) != 0)
    {
        fprintf(stderr, "[SERVER_CONN] send CLIENT_META failed\n");
        cJSON_Delete(cli);
        close(fd);
        conn->sockfd = 0;
        return -1;
    }
    cJSON_Delete(cli);

    // 4) 等 READY
    cJSON *ready = recv_json_line(fd);
    if (!ready)
    {
        fprintf(stderr, "[SERVER_CONN] recv READY failed\n");
        close(fd);
        conn->sockfd = 0;
        return -1;
    }

    cJSON *type_r = cJSON_GetObjectItemCaseSensitive(ready, "type");
    cJSON *status_r = cJSON_GetObjectItemCaseSensitive(ready, "status");
    if (!cJSON_IsString(type_r) || strcmp(type_r->valuestring, "READY") != 0 ||
        !cJSON_IsString(status_r) || strcmp(status_r->valuestring, "OK") != 0)
    {
        fprintf(stderr, "[SERVER_CONN] READY not OK\n");
        cJSON_Delete(ready);
        close(fd);
        conn->sockfd = 0;
        return -1;
    }
    cJSON_Delete(ready);

    conn->connected = 1;
    fprintf(stderr,
            "[SERVER_CONN] handshake OK for qp=%s (local_qpn=%u, remote_qpn=%u)\n",
            qp_name,
            conn->local_meta.qpn,
            conn->remote_meta.qpn);
    return 0;
}

int server_fill_qp_attr_from_remote(ResourceEnv *env,
                                    const char *qp_name,
                                    struct ibv_qp_attr *qp_attr,
                                    int *attr_mask_io,
                                    enum ibv_qp_state new_state)
{
    (void)env; // 当前没直接用到 env，但保留以便以后扩展
    if (!qp_name || !qp_attr || !attr_mask_io)
        return -1;

    ServerConn *conn = find_conn_by_qp_name(qp_name);
    if (!conn || !conn->connected)
    {
        // 没有建立 server 连接，直接不动
        return -1;
    }

    int attr_mask = *attr_mask_io;

    if (new_state == IBV_QPS_RTR)
    {
        // 用 remote_meta 覆盖：dest_qp_num / rq_psn / dgid 等
        qp_attr->dest_qp_num = conn->remote_meta.qpn;
        qp_attr->rq_psn = conn->remote_meta.psn;
        qp_attr->ah_attr.is_global = 1;
        qp_attr->ah_attr.port_num = conn->local_meta.port_num;
        qp_attr->ah_attr.grh.sgid_index = conn->local_meta.gid_index;
        memcpy(qp_attr->ah_attr.grh.dgid.raw,
               conn->remote_meta.gid, 16);
        // 这些字段需要在 attr_mask 中开启
        attr_mask |= IBV_QP_DEST_QPN |
                     IBV_QP_RQ_PSN |
                     IBV_QP_AV |
                     IBV_QP_PATH_MTU |
                     IBV_QP_MAX_DEST_RD_ATOMIC |
                     IBV_QP_MIN_RNR_TIMER;
    }

    if (new_state == IBV_QPS_RTS)
    {
        // 用 local_meta 填 sq_psn
        qp_attr->sq_psn = conn->local_meta.psn;
        attr_mask |= IBV_QP_SQ_PSN |
                     IBV_QP_TIMEOUT |
                     IBV_QP_RETRY_CNT |
                     IBV_QP_RNR_RETRY |
                     IBV_QP_MAX_QP_RD_ATOMIC;
    }

    *attr_mask_io = attr_mask;
    return 0;
}
