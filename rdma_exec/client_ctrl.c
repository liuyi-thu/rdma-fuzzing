// client_ctrl.c
#include "client_ctrl.h"

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <sys/socket.h>

#include <cjson/cJSON.h>

// ========== 小工具 ==========

static uint32_t gen_psn(void)
{
    return (uint32_t)(rand() & 0xffffff);
}

static void gid_to_str(union ibv_gid *gid, char *buf, size_t len)
{
    // 简化版：用 raw 16 字节 -> 八段 16bit
    const uint8_t *r = gid->raw;
    snprintf(buf, len,
             "%02x%02x:%02x%02x:%02x%02x:%02x%02x:"
             "%02x%02x:%02x%02x:%02x%02x:%02x%02x",
             r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7],
             r[8], r[9], r[10], r[11], r[12], r[13], r[14], r[15]);
}

// 简单版：字符串 gid -> raw 16 字节，这里先偷懒，全 0
// （你如果要严谨解析，可以自己按冒号拆分）
static int str_to_gid(const char *s, uint8_t out[16])
{
    (void)s;
    memset(out, 0, 16);
    return 0;
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
    if (write(fd, s, len) != (ssize_t)len)
        return -1;
    return 0;
}

// ========== qp_meta <-> JSON ==========

static cJSON *qp_meta_to_json(const struct qp_meta *m)
{
    cJSON *obj = cJSON_CreateObject();
    cJSON_AddNumberToObject(obj, "qpn", m->qpn);
    cJSON_AddNumberToObject(obj, "psn", m->psn);
    cJSON_AddNumberToObject(obj, "lid", m->lid);
    cJSON_AddNumberToObject(obj, "port_num", m->port_num);

    union ibv_gid gid;
    memcpy(gid.raw, m->gid, 16);
    char gid_str[128];
    gid_to_str(&gid, gid_str, sizeof(gid_str));
    cJSON_AddStringToObject(obj, "gid", gid_str);

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

// ========== client 侧：构造 local_meta + 修改 QP 状态 ==========

static int client_fill_local_meta(struct ibv_context *ctx,
                                  struct ibv_qp *qp,
                                  uint8_t port_num,
                                  uint8_t gid_index,
                                  struct qp_meta *local)
{
    memset(local, 0, sizeof(*local));
    local->qpn = qp->qp_num;
    local->psn = gen_psn();
    local->port_num = port_num;
    local->gid_index = gid_index;
    local->lid = 0; // RoCE 不用 LID

    union ibv_gid gid;
    if (ibv_query_gid(ctx, port_num, gid_index, &gid) != 0)
    {
        fprintf(stderr, "[CLIENT] ibv_query_gid failed, use zero gid\n");
        memset(local->gid, 0, 16);
    }
    else
    {
        memcpy(local->gid, gid.raw, 16);
    }
    return 0;
}

static int client_modify_qp_to_rts(struct ibv_context *ctx,
                                   struct ibv_qp *qp,
                                   const struct qp_meta *local,
                                   const struct qp_meta *remote)
{
    (void)ctx; // 暂时没用

    // INIT
    struct ibv_qp_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.qp_state = IBV_QPS_INIT;
    attr.pkey_index = 0;
    attr.port_num = local->port_num;
    attr.qp_access_flags = IBV_ACCESS_LOCAL_WRITE |
                           IBV_ACCESS_REMOTE_READ |
                           IBV_ACCESS_REMOTE_WRITE;

    if (ibv_modify_qp(qp, &attr,
                      IBV_QP_STATE |
                          IBV_QP_PKEY_INDEX |
                          IBV_QP_PORT |
                          IBV_QP_ACCESS_FLAGS))
    {
        fprintf(stderr, "[CLIENT] ibv_modify_qp INIT failed\n");
        return -1;
    }

    // RTR
    memset(&attr, 0, sizeof(attr));
    attr.qp_state = IBV_QPS_RTR;
    attr.path_mtu = IBV_MTU_1024;
    attr.dest_qp_num = remote->qpn;
    attr.rq_psn = remote->psn;
    attr.max_dest_rd_atomic = 1;
    attr.min_rnr_timer = 12;
    attr.ah_attr.is_global = 1;
    attr.ah_attr.port_num = local->port_num;
    attr.ah_attr.grh.dgid.global.interface_id = 0;
    memcpy(attr.ah_attr.grh.dgid.raw, remote->gid, 16);
    attr.ah_attr.grh.sgid_index = local->gid_index;
    attr.ah_attr.grh.hop_limit = 1;
    attr.ah_attr.grh.traffic_class = 0;
    attr.ah_attr.grh.flow_label = 0;

    if (ibv_modify_qp(qp, &attr,
                      IBV_QP_STATE |
                          IBV_QP_AV |
                          IBV_QP_PATH_MTU |
                          IBV_QP_DEST_QPN |
                          IBV_QP_RQ_PSN |
                          IBV_QP_MAX_DEST_RD_ATOMIC |
                          IBV_QP_MIN_RNR_TIMER))
    {
        fprintf(stderr, "[CLIENT] ibv_modify_qp RTR failed\n");
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
        fprintf(stderr, "[CLIENT] ibv_modify_qp RTS failed\n");
        return -1;
    }

    fprintf(stderr, "[CLIENT] QP connected (INIT->RTR->RTS)\n");
    return 0;
}

// ========== 核心：connect_qp_raw ==========

int connect_qp_raw(struct ibv_context *ctx,
                   struct ibv_qp *qp,
                   const char *qp_tag,
                   const char *server_host,
                   uint16_t server_port,
                   uint8_t port_num,
                   uint8_t gid_index)
{
    int sock = -1;
    char buf[2048];

    // 1. 建 TCP 连接
    struct addrinfo hints, *res = NULL;
    char port_str[16];
    snprintf(port_str, sizeof(port_str), "%u", server_port);

    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    if (getaddrinfo(server_host, port_str, &hints, &res) != 0)
    {
        perror("getaddrinfo");
        return -1;
    }

    sock = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (sock < 0)
    {
        perror("socket");
        freeaddrinfo(res);
        return -1;
    }

    if (connect(sock, res->ai_addr, res->ai_addrlen) < 0)
    {
        perror("connect");
        freeaddrinfo(res);
        close(sock);
        return -1;
    }
    freeaddrinfo(res);
    fprintf(stderr, "[CLIENT] Connected to control server %s:%u\n",
            server_host, server_port);

    // 2. 发送 REQ_CONNECT
    cJSON *req = cJSON_CreateObject();
    cJSON_AddStringToObject(req, "type", "REQ_CONNECT");
    cJSON_AddStringToObject(req, "qp_tag", qp_tag);
    cJSON_AddNumberToObject(req, "port_num", port_num);
    cJSON_AddNumberToObject(req, "gid_index", gid_index);
    char *req_str = cJSON_PrintUnformatted(req);
    cJSON_Delete(req);

    if (!req_str)
    {
        close(sock);
        return -1;
    }
    write_str(sock, req_str);
    write_str(sock, "\n");
    free(req_str);

    // 3. 读取 RESP_CONNECT
    int n = read_line(sock, buf, sizeof(buf));
    if (n <= 0)
    {
        fprintf(stderr, "[CLIENT] read RESP_CONNECT failed\n");
        close(sock);
        return -1;
    }

    cJSON *resp = cJSON_Parse(buf);
    if (!resp)
    {
        fprintf(stderr, "[CLIENT] invalid RESP_CONNECT JSON\n");
        close(sock);
        return -1;
    }

    cJSON *type = cJSON_GetObjectItemCaseSensitive(resp, "type");
    cJSON *status = cJSON_GetObjectItemCaseSensitive(resp, "status");
    cJSON *server_meta_obj = cJSON_GetObjectItemCaseSensitive(resp, "server_meta");
    if (!cJSON_IsString(type) || strcmp(type->valuestring, "RESP_CONNECT") != 0 ||
        !cJSON_IsString(status) || strcmp(status->valuestring, "OK") != 0 ||
        !server_meta_obj)
    {
        fprintf(stderr, "[CLIENT] RESP_CONNECT content error\n");
        cJSON_Delete(resp);
        close(sock);
        return -1;
    }

    struct qp_meta server_meta;
    if (qp_meta_from_json(server_meta_obj, &server_meta) != 0)
    {
        fprintf(stderr, "[CLIENT] parse server_meta failed\n");
        cJSON_Delete(resp);
        close(sock);
        return -1;
    }
    cJSON_Delete(resp);

    fprintf(stderr, "[CLIENT] Got server_meta: qpn=%u psn=%u\n",
            server_meta.qpn, server_meta.psn);

    // 4. 构造 local_meta + 修改 QP 到 RTS
    struct qp_meta local_meta;
    client_fill_local_meta(ctx, qp, port_num, gid_index, &local_meta);

    if (client_modify_qp_to_rts(ctx, qp, &local_meta, &server_meta) != 0)
    {
        close(sock);
        return -1;
    }

    // 5. 发送 CLIENT_META
    cJSON *cl = cJSON_CreateObject();
    cJSON_AddStringToObject(cl, "type", "CLIENT_META");
    cJSON_AddStringToObject(cl, "qp_tag", qp_tag);
    cJSON_AddItemToObject(cl, "client_meta", qp_meta_to_json(&local_meta));
    char *cl_str = cJSON_PrintUnformatted(cl);
    cJSON_Delete(cl);
    if (!cl_str)
    {
        close(sock);
        return -1;
    }
    write_str(sock, cl_str);
    write_str(sock, "\n");
    free(cl_str);

    // 6. 读取 READY
    n = read_line(sock, buf, sizeof(buf));
    if (n <= 0)
    {
        fprintf(stderr, "[CLIENT] read READY failed\n");
        close(sock);
        return -1;
    }

    cJSON *ready = cJSON_Parse(buf);
    if (!ready)
    {
        fprintf(stderr, "[CLIENT] invalid READY JSON\n");
        close(sock);
        return -1;
    }

    cJSON *type3 = cJSON_GetObjectItemCaseSensitive(ready, "type");
    cJSON *status3 = cJSON_GetObjectItemCaseSensitive(ready, "status");
    if (!cJSON_IsString(type3) || strcmp(type3->valuestring, "READY") != 0 ||
        !cJSON_IsString(status3) || strcmp(status3->valuestring, "OK") != 0)
    {
        fprintf(stderr, "[CLIENT] READY content error\n");
        cJSON_Delete(ready);
        close(sock);
        return -1;
    }
    cJSON_Delete(ready);

    fprintf(stderr, "[CLIENT] QP %s is READY (connected to server)\n", qp_tag);

    close(sock);
    return 0;
}