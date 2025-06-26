// 修改后的 rdma_client_with_qp_pool.c
// 支持通过 socket 向控制器发送每个 QP 和其 MR 的信息（QPN, addr, rkey）

#include <infiniband/verbs.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <cjson/cJSON.h>
#include <iostream>
#include <map>
#include <sys/time.h>

using namespace std;

#define QP_POOL_SIZE 4
#define RECV_POOL_SIZE 16
#define MSG_SIZE 128
#define CTRL_PORT 12345
#define MR_POOL_SIZE 1000
#define REMOTE_QP_POOL_SIZE 1000
#define IB_PORT 1
#define GID_INDEX 1
#define MAX_POLL_CQ_TIMEOUT 2000

typedef struct
{
    uint64_t wr_id;
    char *buf;
    struct ibv_mr *mr;
    int in_use;
} recv_slot_t;

typedef struct
{
    recv_slot_t slots[RECV_POOL_SIZE];
    struct ibv_pd *pd;
} RecvBufferPool;

typedef struct
{
    struct ibv_qp *qp;
    RecvBufferPool recv_pool;
} QPWithBufferPool;

void init_recv_pool(RecvBufferPool *pool, struct ibv_pd *pd)
{
    pool->pd = pd;
    for (int i = 0; i < RECV_POOL_SIZE; ++i)
    {
        pool->slots[i].buf = static_cast<char *>(malloc(MSG_SIZE));
        pool->slots[i].mr = ibv_reg_mr(pd, pool->slots[i].buf, MSG_SIZE, IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_REMOTE_READ);
        pool->slots[i].wr_id = (uint64_t)i;
        pool->slots[i].in_use = 0;
    }
}

void post_all_recvs(RecvBufferPool *pool, struct ibv_qp *qp)
{
    for (int i = 0; i < RECV_POOL_SIZE; ++i)
    {
        struct ibv_sge sge = {
            .addr = (uintptr_t)pool->slots[i].buf,
            .length = MSG_SIZE,
            .lkey = pool->slots[i].mr->lkey};
        struct ibv_recv_wr wr = {
            .wr_id = pool->slots[i].wr_id,
            .sg_list = &sge,
            .num_sge = 1};
        struct ibv_recv_wr *bad_wr;
        if (ibv_post_recv(qp, &wr, &bad_wr) == 0)
            pool->slots[i].in_use = 1;
    }
}

struct metadata_global
{
    uint16_t lid;
    uint8_t gid[16];
};

struct metadata_qp
{
    uint32_t qpn;
    uintptr_t addr;
    uint32_t rkey;
};

struct metadata_mr
{
    uintptr_t addr;
    uint32_t rkey;
};

struct metadata_pair
{
    uint32_t remote_qpn;
    uint32_t local_qpn;
};

struct pair_request
{
    uint32_t remote_qp_index;
    uint32_t local_qpn;
};

// struct pair_response {
//     uint32_t remote_qpn;
//     uint32_t local_qpn;
// };

struct metadata_mr MRPool[MR_POOL_SIZE];
int mr_pool_size = 0;

struct metadata_global remote_info;

map<int, int> local_remote_qp_map; // 用于存储本地 QP 和远程 QP 的映射关系
map<int, int> qpn_to_index_map;    // 用于存储 QPN 到索引的映射

QPWithBufferPool qp_pool[QP_POOL_SIZE];

char *serialize_metadata_global(struct metadata_global *meta)
{
    cJSON *json = cJSON_CreateObject();
    cJSON_AddStringToObject(json, "type", "global_metadata");
    cJSON_AddStringToObject(json, "role", "client");
    cJSON_AddNumberToObject(json, "lid", meta->lid);
    char gid_str[48];
    snprintf(gid_str, sizeof(gid_str), "%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x",
             meta->gid[0], meta->gid[1], meta->gid[2], meta->gid[3],
             meta->gid[4], meta->gid[5], meta->gid[6], meta->gid[7],
             meta->gid[8], meta->gid[9], meta->gid[10], meta->gid[11],
             meta->gid[12], meta->gid[13], meta->gid[14], meta->gid[15]);
    cJSON_AddStringToObject(json, "gid", gid_str);
    char *string = cJSON_PrintUnformatted(json);
    cJSON_Delete(json);
    return string;
}

char *serialize_metadata_qp(struct metadata_qp *meta)
{
    cJSON *json = cJSON_CreateObject();
    cJSON_AddStringToObject(json, "type", "qp_metadata");
    cJSON_AddNumberToObject(json, "qpn", meta->qpn);
    cJSON_AddNumberToObject(json, "addr", meta->addr);
    cJSON_AddNumberToObject(json, "rkey", meta->rkey);
    char *string = cJSON_PrintUnformatted(json);
    cJSON_Delete(json);
    return string;
}

char *serialize_pair_request(struct pair_request *req)
{
    cJSON *json = cJSON_CreateObject();
    cJSON_AddStringToObject(json, "type", "pair_request");
    cJSON_AddNumberToObject(json, "remote_qp_index", req->remote_qp_index);
    cJSON_AddNumberToObject(json, "local_qpn", req->local_qpn);
    char *string = cJSON_PrintUnformatted(json);
    cJSON_Delete(json);
    return string;
}

const char *deserialize_metadata_global(const char *json_str, struct metadata_global *meta)
{
    cJSON *json = cJSON_Parse(json_str);
    if (!json)
    {
        fprintf(stderr, "Failed to parse JSON: %s\n", cJSON_GetErrorPtr());
        return NULL;
    }
    meta->lid = (uint16_t)cJSON_GetObjectItem(json, "lid")->valueint;
    const char *gid_str = cJSON_GetObjectItem(json, "gid")->valuestring;
    sscanf(gid_str, "%2hhx:%2hhx:%2hhx:%2hhx:%2hhx:%2hhx:%2hhx:%2hhx:%2hhx:%2hhx:%2hhx:%2hhx:%2hhx:%2hhx:%2hhx:%2hhx",
           &meta->gid[0], &meta->gid[1], &meta->gid[2], &meta->gid[3],
           &meta->gid[4], &meta->gid[5], &meta->gid[6], &meta->gid[7],
           &meta->gid[8], &meta->gid[9], &meta->gid[10], &meta->gid[11],
           &meta->gid[12], &meta->gid[13], &meta->gid[14], &meta->gid[15]);
    cJSON_Delete(json);
    return json_str; // 返回原始 JSON 字符串
}

const char *deserialize_metadata_qp(const char *json_str, struct metadata_qp *meta)
{
    cJSON *json = cJSON_Parse(json_str);
    if (!json)
    {
        fprintf(stderr, "Failed to parse JSON: %s\n", cJSON_GetErrorPtr());
        return NULL;
    }
    meta->qpn = cJSON_GetObjectItem(json, "qpn")->valueint;
    meta->addr = (uintptr_t)cJSON_GetObjectItem(json, "addr")->valuedouble;
    meta->rkey = cJSON_GetObjectItem(json, "rkey")->valueint;
    cJSON_Delete(json);
    return json_str;
}

const char *deserialize_metadata_mr(const char *json_str, struct metadata_mr *meta)
{
    cJSON *json = cJSON_Parse(json_str);
    if (!json)
    {
        fprintf(stderr, "Failed to parse JSON: %s\n", cJSON_GetErrorPtr());
        return NULL;
    }
    meta->addr = (uintptr_t)cJSON_GetObjectItem(json, "addr")->valuedouble;
    meta->rkey = cJSON_GetObjectItem(json, "rkey")->valueint;
    cJSON_Delete(json);
    return json_str;
}

const char *deserialize_pair(const char *json_str, struct metadata_pair *meta)
{
    cJSON *json = cJSON_Parse(json_str);
    if (!json)
    {
        fprintf(stderr, "Failed to parse JSON: %s\n", cJSON_GetErrorPtr());
        return NULL;
    }
    meta->remote_qpn = cJSON_GetObjectItem(json, "remote_qpn")->valueint;
    meta->local_qpn = cJSON_GetObjectItem(json, "local_qpn")->valueint;
    cJSON_Delete(json);
    return json_str;
}

void print_metadata_global(const struct metadata_global *meta)
{
    printf("Global Metadata:\n");
    printf("  LID: %u\n", meta->lid);
    printf("  GID: ");
    for (int i = 0; i < 16; ++i)
    {
        printf("%02x", meta->gid[i]);
        if (i < 15)
            printf(":");
    }
    printf("\n");
}

void print_metadata_qp(const struct metadata_qp *meta)
{
    printf("QP Metadata:\n");
    printf("  QPN: %u\n", meta->qpn);
    printf("  Address: 0x%lx\n", (unsigned long)meta->addr);
    printf("  RKey: 0x%x\n", meta->rkey);
}

void print_metadata_mr(const struct metadata_mr *meta)
{
    printf("MR Metadata:\n");
    printf("  Address: 0x%lx\n", (unsigned long)meta->addr);
    printf("  RKey: 0x%x\n", meta->rkey);
}

void print_metadata_pair(const struct metadata_pair *meta)
{
    printf("Pair Metadata:\n");
    printf("  Local QPN: %u\n", meta->local_qpn);
    printf("  Remote QPN: %u\n", meta->remote_qpn);
}

const char *deserialize_metadata(const char *json_str)
{
    // to get type
    cJSON *json = cJSON_Parse(json_str);
    if (!json)
    {
        fprintf(stderr, "Failed to parse JSON: %s\n", cJSON_GetErrorPtr());
        return NULL;
    }
    cJSON *type_item = cJSON_GetObjectItem(json, "type");
    if (!cJSON_IsString(type_item))
    {
        fprintf(stderr, "Invalid JSON format: 'type' is not a string\n");
        cJSON_Delete(json);
        return NULL;
    }
    const char *type = type_item->valuestring;
    if (strcmp(type, "global_metadata") == 0)
    {
        struct metadata_global meta;
        const char *result = deserialize_metadata_global(json_str, &meta); // then we have to process 'meta' here
        print_metadata_global(&meta);
        // 将全局信息存储到 remote_info 中
        remote_info.lid = meta.lid;
        memcpy(remote_info.gid, meta.gid, sizeof(remote_info.gid));
        // 这里可以添加更多处理逻辑，例如发送到控制器等
        cJSON_Delete(json);
        return result;
    }
    else if (strcmp(type, "qp_metadata") == 0)
    { // will not trigger
        struct metadata_qp meta;
        const char *result = deserialize_metadata_qp(json_str, &meta);
        cJSON_Delete(json);
        return result;
    }
    else if (strcmp(type, "mr_metadata") == 0)
    {
        struct metadata_mr meta;
        const char *result = deserialize_metadata_mr(json_str, &meta); // then we have to process 'meta' here
        print_metadata_mr(&meta);
        // 将 MR 信息存储到 MRPool 中
        if (mr_pool_size < MR_POOL_SIZE)
        {
            MRPool[mr_pool_size++] = meta;
        }
        else
        {
            fprintf(stderr, "MR pool is full, cannot store more MR metadata.\n");
        }
        // 这里可以添加更多处理逻辑，例如发送到控制器等
        // 目前只是打印 MR 信息
        cJSON_Delete(json);
        return result;
    }
    else if (strcmp(type, "pair") == 0)
    {
        struct metadata_pair meta;
        const char *result = deserialize_pair(json_str, &meta); // then we have to process 'meta' here
        print_metadata_pair(&meta);
        // 将 Pair 信息存储到 Remote_QPPool 中
        if (meta.local_qpn < REMOTE_QP_POOL_SIZE)
        {
            local_remote_qp_map[meta.local_qpn] = meta.remote_qpn; // 存储远程 QPN
            printf("Stored pair metadata: Local QPN %u -> Remote QPN %u\n", meta.local_qpn, meta.remote_qpn);
        }
        else
        {
            fprintf(stderr, "Pair index %u out of bounds for Remote_QPPool\n", meta.local_qpn);
        }
        cJSON_Delete(json);
        return result;
    }
    else
    {
        fprintf(stderr, "Unknown type: %s\n", type);
        cJSON_Delete(json);
        return NULL;
    }
}

int create_socket()
{
    int sockfd = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in ctrl_addr;
    memset(&ctrl_addr, 0, sizeof(ctrl_addr));
    ctrl_addr.sin_family = AF_INET;
    ctrl_addr.sin_port = htons(CTRL_PORT);
    ctrl_addr.sin_addr.s_addr = inet_addr("192.168.56.1");

    connect(sockfd, (struct sockaddr *)&ctrl_addr, sizeof(ctrl_addr));
    printf("[Controller] Connected to controller at %s:%d\n", inet_ntoa(ctrl_addr.sin_addr), ntohs(ctrl_addr.sin_port));
    return sockfd;
}

int close_socket(int sockfd)
{
    if (close(sockfd) < 0)
    {
        perror("Failed to close socket");
        return -1;
    }
    return 0;
}

void send_metadata_to_controller(QPWithBufferPool *qp_pool, int num_qp, int sockfd)
{
    for (int i = 0; i < num_qp; ++i)
    {
        uint32_t qpn = qp_pool[i].qp->qp_num;
        for (int j = 0; j < RECV_POOL_SIZE; ++j)
        {
            struct ibv_mr *mr = qp_pool[i].recv_pool.slots[j].mr;
            uintptr_t addr = (uintptr_t)(qp_pool[i].recv_pool.slots[j].buf);
            uint32_t rkey = mr->rkey;
            char buf[256];
            struct metadata_qp meta = {qpn, addr, rkey};
            char *json_str = serialize_metadata_qp(&meta);
            snprintf(buf, sizeof(buf), "%s\n", json_str);
            free(json_str);
            // snprintf(buf, sizeof(buf), "QPN %u ADDR 0x%lx RKEY 0x%x\n", qpn, addr, rkey);
            send(sockfd, buf, strlen(buf), 0);
        }
    }
    send(sockfd, "END\n", 4, 0); // 发送结束标志
}

void send_pair_request_to_controller(struct pair_request req, int sockfd)
{
    char buf[256];
    char *json_str = serialize_pair_request(&req);
    snprintf(buf, sizeof(buf), "%s\n", json_str);
    free(json_str);
    // snprintf(buf, sizeof(buf), "QPN %u ADDR 0x%lx RKEY 0x%x\n", qpn, addr, rkey);
    send(sockfd, buf, strlen(buf), 0);
}

void receive_metadata_from_controller(int sockfd)
{
    char buffer[4096];
    char line_buffer[4096];
    int line_pos = 0;

    while (1)
    {
        int bytes_received = recv(sockfd, buffer, sizeof(buffer) - 1, 0);
        if (bytes_received <= 0)
        {
            if (bytes_received < 0)
                perror("recv error");
            break;
        }
        buffer[bytes_received] = '\0';

        for (int i = 0; i < bytes_received; ++i)
        {
            if (buffer[i] == '\n')
            {
                line_buffer[line_pos] = '\0'; // null-terminate
                if (strcmp(line_buffer, "END") == 0)
                {
                    printf("[Controller] Received END marker\n");
                    return;
                }
                printf("[Controller] Received JSON: %s\n", line_buffer);
                // TODO: parse and handle each JSON line here (optional)
                deserialize_metadata(line_buffer); // 解析 JSON 并处理

                line_pos = 0; // reset buffer
            }
            else
            {
                if (line_pos < sizeof(line_buffer) - 1)
                {
                    line_buffer[line_pos++] = buffer[i];
                }
            }
        }
    }
}

void send_pair_request_to_controller_from_pool(QPWithBufferPool *qp_pool, int num_qp, int sockfd)
{
    // 查找远程 QP 的索引
    for (int i = 0; i < num_qp; ++i)
    {
        uint32_t qpn = qp_pool[i].qp->qp_num;
        char buf[256];
        struct pair_request req;
        req.local_qpn = qpn;
        req.remote_qp_index = i;
        send_pair_request_to_controller(req, sockfd);
        receive_metadata_from_controller(sockfd); // is that correct? 接收配对信息
    }
}

static int modify_qp_to_init(struct ibv_qp *qp)
{
    struct ibv_qp_attr attr;
    int flags;
    int rc;
    memset(&attr, 0, sizeof(attr));
    attr.qp_state = IBV_QPS_INIT;
    attr.port_num = IB_PORT; // hardcoded port number, should be set to the actual port number
    attr.pkey_index = 0;
    attr.qp_access_flags = IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE;
    flags = IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS;
    rc = ibv_modify_qp(qp, &attr, flags);
    if (rc)
    {
        fprintf(stderr, "failed to modify QP state to INIT\n");
    }
    return rc;
}

static int modify_qp_to_rtr(struct ibv_qp *qp, uint32_t remote_qpn, uint16_t dlid, uint8_t *dgid)
{
    struct ibv_qp_attr attr;
    int flags;
    int rc;
    int udp_sport = 0;
    int gid_idx = 1; // hardcoded GID index, should be set to the actual GID index

    memset(&attr, 0, sizeof(attr));
    attr.qp_state = IBV_QPS_RTR;
    attr.path_mtu = IBV_MTU_256; /* this field specifies the MTU from source code*/
    attr.dest_qp_num = remote_qpn;
    attr.rq_psn = 0;
    attr.max_dest_rd_atomic = 1;
    attr.min_rnr_timer = 0x12;
    attr.ah_attr.is_global = 0;
    attr.ah_attr.dlid = dlid;
    attr.ah_attr.sl = 0;
    attr.ah_attr.src_path_bits = 0;
    attr.ah_attr.port_num = IB_PORT; // hardcoded port number, should be set to the actual port number
    if (gid_idx >= 0)
    {
        attr.ah_attr.is_global = 1;
        attr.ah_attr.port_num = 1;
        memcpy(&attr.ah_attr.grh.dgid, dgid, 16);
        /* this field specify the UDP source port. if the target UDP source port is expected to be X, the value of flow_label = X ^ 0xC000 */
        if (udp_sport == 0)
        {
            attr.ah_attr.grh.flow_label = 0;
        }
        else
        {
            attr.ah_attr.grh.flow_label = udp_sport ^ 0xC000;
        }
        attr.ah_attr.grh.hop_limit = 1;
        attr.ah_attr.grh.sgid_index = gid_idx;
        attr.ah_attr.grh.traffic_class = 0;
    }

    flags = IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN |
            IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER;
    rc = ibv_modify_qp(qp, &attr, flags);
    if (rc)
    {
        fprintf(stderr, "failed to modify QP state to RTR\n");
    }
    return rc;
}

static int modify_qp_to_rts(struct ibv_qp *qp)
{
    struct ibv_qp_attr attr;
    int flags;
    int rc;
    memset(&attr, 0, sizeof(attr));
    attr.qp_state = IBV_QPS_RTS;
    attr.timeout = 0x12;
    attr.retry_cnt = 6;
    attr.rnr_retry = 0;
    attr.sq_psn = 0;
    attr.max_rd_atomic = 1;
    flags = IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT |
            IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC;
    rc = ibv_modify_qp(qp, &attr, flags);
    if (rc)
    {
        fprintf(stderr, "failed to modify QP state to RTS\n");
    }
    return rc;
}

static int poll_completion(ibv_cq *cq)
{
    struct ibv_wc wc;
    unsigned long start_time_msec;
    unsigned long cur_time_msec;
    struct timeval cur_time;
    int poll_result;
    int rc = 0;
    /* poll the completion for a while before giving up of doing it .. */
    gettimeofday(&cur_time, NULL);
    start_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    do
    {
        poll_result = ibv_poll_cq(cq, 1, &wc);
        gettimeofday(&cur_time, NULL);
        cur_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    } while ((poll_result == 0) && ((cur_time_msec - start_time_msec) < MAX_POLL_CQ_TIMEOUT));

    if (poll_result < 0)
    {
        /* poll CQ failed */
        fprintf(stderr, "poll CQ failed\n");
        rc = 1;
    }
    else if (poll_result == 0)
    {
        /* the CQ is empty */
        fprintf(stderr, "completion wasn't found in the CQ after timeout\n");
        rc = 1;
    }
    else
    {
        /* CQE found */
        fprintf(stdout, "completion was found in CQ with status 0x%x\n", wc.status);
        /* check the completion status (here we don't care about the completion opcode */
        if (wc.status != IBV_WC_SUCCESS)
        {
            fprintf(stderr, "got bad completion with status: 0x%x, vendor syndrome: 0x%x\n",
                    wc.status, wc.vendor_err);
            rc = 1;
        }
    }
    return rc;
}

static int post_send(RecvBufferPool *pool, struct ibv_qp *qp, enum ibv_wr_opcode opcode)
{
    struct ibv_send_wr sr;
    struct ibv_sge sge;
    struct ibv_send_wr *bad_wr = NULL;
    int rc;

    /* prepare the scatter/gather entry */
    memset(&sge, 0, sizeof(sge));
    sge.addr = (uintptr_t)pool->slots[0].buf; // 使用第一个接收槽的缓冲区
    sge.length = MSG_SIZE;
    sge.lkey = pool->slots[0].mr->lkey; // 使用第一个接收槽的 MR

    /* prepare the send work request */
    memset(&sr, 0, sizeof(sr)); // nested variables
    sr.next = NULL;
    sr.wr_id = 0;
    sr.sg_list = &sge;
    sr.num_sge = 1;
    sr.opcode = opcode;
    sr.send_flags = IBV_SEND_SIGNALED;
    if (opcode != IBV_WR_SEND)
    {
        return -1; // only support IBV_WR_SEND for now
        // sr.wr.rdma.remote_addr = res->remote_props.addr;
        // sr.wr.rdma.rkey = res->remote_props.rkey;
    }

    /* there is a Receive Request in the responder side, so we won't get any into RNR flow */
    rc = ibv_post_send(qp, &sr, &bad_wr);
    if (rc)
    {
        fprintf(stderr, "failed to post SR\n");
    }
    else
    {
        switch (opcode)
        {
        case IBV_WR_SEND:
            fprintf(stdout, "Send Request was posted\n");
            break;
        case IBV_WR_RDMA_READ:
            fprintf(stdout, "RDMA Read Request was posted\n");
            break;
        case IBV_WR_RDMA_WRITE:
            fprintf(stdout, "RDMA Write Request was posted\n");
            break;
        default:
            fprintf(stdout, "Unknown Request was posted\n");
            break;
        }
    }
    return rc;
}

int main()
{
    int sockfd = create_socket();
    if (sockfd < 0)
    {
        fprintf(stderr, "Failed to create socket\n");
        return 1;
    }

    struct ibv_device **dev_list = ibv_get_device_list(NULL);
    struct ibv_context *ctx = ibv_open_device(dev_list[0]);
    struct ibv_pd *pd = ibv_alloc_pd(ctx);
    struct ibv_port_attr port_attr;
    ibv_query_port(ctx, IB_PORT, &port_attr);
    struct ibv_cq *cq = ibv_create_cq(ctx, QP_POOL_SIZE * RECV_POOL_SIZE, NULL, NULL, 0);

    union ibv_gid my_gid;
    if (ibv_query_gid(ctx, IB_PORT, GID_INDEX, &my_gid))
    {
        fprintf(stderr, "Failed to query GID\n");
        return 1;
    }
    struct metadata_global meta_global = {
        .lid = port_attr.lid,
        .gid = {my_gid.raw[0], my_gid.raw[1], my_gid.raw[2], my_gid.raw[3],
                my_gid.raw[4], my_gid.raw[5], my_gid.raw[6], my_gid.raw[7],
                my_gid.raw[8], my_gid.raw[9], my_gid.raw[10], my_gid.raw[11],
                my_gid.raw[12], my_gid.raw[13], my_gid.raw[14], my_gid.raw[15]}};

    char *json_str = serialize_metadata_global(&meta_global);
    printf("[Controller] Global Metadata: %s\n", json_str);
    char buf[256];
    snprintf(buf, sizeof(buf), "%s\n", json_str);
    send(sockfd, buf, strlen(buf), 0);
    free(json_str);
    send(sockfd, "END\n", 4, 0); // 发送结束标志

    struct ibv_qp_init_attr qp_attr = {
        .send_cq = cq,
        .recv_cq = cq,
        .cap = {
            .max_send_wr = 10,
            .max_recv_wr = RECV_POOL_SIZE,
            .max_send_sge = 1,
            .max_recv_sge = 1},
        .qp_type = IBV_QPT_RC};

    for (int i = 0; i < QP_POOL_SIZE; ++i)
    {
        qp_pool[i].qp = ibv_create_qp(pd, &qp_attr);
        qpn_to_index_map[qp_pool[i].qp->qp_num] = i; // 存储 QPN 到索引的映射
        init_recv_pool(&qp_pool[i].recv_pool, pd);
        // post_all_recvs(&qp_pool[i].recv_pool, qp_pool[i].qp);
    }

    receive_metadata_from_controller(sockfd);
    // send_metadata_to_controller(qp_pool, QP_POOL_SIZE, sockfd);
    send_pair_request_to_controller_from_pool(qp_pool, QP_POOL_SIZE, sockfd); // 一次性发送所有的，按理说也可以一个一个发送

    // 这里需要写一个收到控制器的消息后，修改 QP 状态的逻辑
    // 例如：修改 QP 状态为 INIT，然后修改为 RTR 和 RTS

    // 可选：进入通信阶段，poll CQ 等（略）
    for (auto iter = local_remote_qp_map.begin(); iter != local_remote_qp_map.end(); ++iter)
    {
        int local_qpn = iter->first;
        int remote_qpn = iter->second;
        int local_index = qpn_to_index_map[local_qpn]; // 获取本地 QPN 的索引

        if (modify_qp_to_init(qp_pool[local_index].qp))
        {
            fprintf(stderr, "Failed to modify QP %d to INIT\n", local_qpn);
            continue;
        }
    }

    for (auto iter = local_remote_qp_map.begin(); iter != local_remote_qp_map.end(); ++iter)
    {
        int local_qpn = iter->first;
        int remote_qpn = iter->second;
        int local_index = qpn_to_index_map[local_qpn]; // 获取本地 QPN 的索引

        // 假设我们有一个远程 QPN 和 LID，这里需要根据实际情况设置
        uint16_t dlid = remote_info.lid;                        // 需要从控制器接收或其他方式获取
        uint8_t dgid[16] = {0};                                 // 如果是全局地址，需要设置 GID
        memcpy(dgid, remote_info.gid, sizeof(remote_info.gid)); // 使用从控制器接收到的 GID

        if (modify_qp_to_rtr(qp_pool[local_index].qp, remote_qpn, dlid, dgid))
        {
            fprintf(stderr, "Failed to modify QP %d to RTR\n", local_qpn);
            continue;
        }
    }

    for (auto iter = local_remote_qp_map.begin(); iter != local_remote_qp_map.end(); ++iter)
    {
        int local_qpn = iter->first;
        int remote_qpn = iter->second;
        int local_index = qpn_to_index_map[local_qpn]; // 获取本地 QPN 的索引

        // 假设我们有一个远程 QPN 和 LID，这里需要根据实际情况设置
        uint16_t dlid = remote_info.lid;                        // 需要从控制器接收或其他方式获取
        uint8_t dgid[16] = {0};                                 // 如果是全局地址，需要设置 GID
        memcpy(dgid, remote_info.gid, sizeof(remote_info.gid)); // 使用从控制器接收到的 GID

        if (modify_qp_to_rts(qp_pool[local_index].qp))
        {
            fprintf(stderr, "Failed to modify QP %d to RTS\n", local_qpn);
            continue;
        }
    }

    for (int i = 0; i < QP_POOL_SIZE; ++i)
    {
        // ibv_post_send(qp_pool[i].qp, NULL, NULL); // 这里可以根据需要发送数据
        post_send(&qp_pool[i].recv_pool, qp_pool[i].qp, IBV_WR_SEND); // 发送一个空的 WR
        fprintf(stdout, "Posted send for QP %d\n", qp_pool[i].qp->qp_num);
        // poll_completion(cq); // 等待发送完成
        poll_completion(cq); // 等待发送完成
    }

    for (int i = 0; i < QP_POOL_SIZE; ++i)
    {
        for (int j = 0; j < RECV_POOL_SIZE; ++j)
        {
            ibv_dereg_mr(qp_pool[i].recv_pool.slots[j].mr);
            free(qp_pool[i].recv_pool.slots[j].buf);
        }
        ibv_destroy_qp(qp_pool[i].qp);
    }
    ibv_destroy_cq(cq);
    ibv_dealloc_pd(pd);
    ibv_close_device(ctx);
    ibv_free_device_list(dev_list);
    return 0;
}
