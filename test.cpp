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

#define QP_POOL_SIZE 10
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


// ----- GLOBAL VARIABLES -----
struct metadata_mr MRPool[MR_POOL_SIZE];
int mr_pool_size = 0;

struct metadata_global remote_info;

map<int, int> local_remote_qp_map; // 用于存储本地 QP 和远程 QP 的映射关系
map<int, int> qpn_to_index_map;    // 用于存储 QPN 到索引的映射

QPWithBufferPool qp_pool[QP_POOL_SIZE];

struct ibv_context *ctx;
struct ibv_device **dev_list;
struct ibv_device_attr dev_attr;
struct ibv_port_attr port_attr;
struct ibv_pd *pd[100];
struct ibv_cq *cq[100];
struct ibv_qp *qp[100];
struct ibv_mr *mr[100];
struct ibv_srq *srq[100]; // SRQ 数组

char bufs[100][1024];
struct pair_request req;

struct ibv_qp_attr qp_attr;

struct ibv_wc wc;
unsigned long start_time_msec;
unsigned long cur_time_msec;
struct timeval cur_time;
int poll_result;
int rc = 0;

// ----- FUNCTION DECLARATIONS -----

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
    // --- VARIABLES BEGIN ---

    struct ibv_qp_init_attr attr_init_QP0;
    struct ibv_qp_cap attr_init_QP0_cap;
    struct ibv_qp_attr qp_attr_QP0;
    struct ibv_ah_attr qp_attr_QP0_ah;
    struct ibv_global_route qp_attr_QP0_ah_grh;
    union ibv_gid qp_attr_QP0_ah_grh_dgid;
    struct ibv_send_wr wr_QP0;
    struct ibv_sge wr_QP0_sge_0;
    struct ibv_send_wr * bad_wr_QP0 = NULL;
    struct ibv_qp_init_attr attr_init_QP1;
    struct ibv_qp_cap attr_init_QP1_cap;
    struct ibv_qp_attr qp_attr_QP1;
    struct ibv_ah_attr qp_attr_QP1_ah;
    struct ibv_global_route qp_attr_QP1_ah_grh;
    union ibv_gid qp_attr_QP1_ah_grh_dgid;
    struct ibv_send_wr wr_QP1;
    struct ibv_sge wr_QP1_sge_0;
    struct ibv_send_wr * bad_wr_QP1 = NULL;
    struct ibv_qp_init_attr attr_init_QP2;
    struct ibv_qp_cap attr_init_QP2_cap;
    struct ibv_qp_attr qp_attr_QP2;
    struct ibv_ah_attr qp_attr_QP2_ah;
    struct ibv_global_route qp_attr_QP2_ah_grh;
    union ibv_gid qp_attr_QP2_ah_grh_dgid;
    struct ibv_send_wr wr_QP2;
    struct ibv_sge wr_QP2_sge_0;
    struct ibv_send_wr * bad_wr_QP2 = NULL;
    struct ibv_qp_init_attr attr_init_QP3;
    struct ibv_qp_cap attr_init_QP3_cap;
    struct ibv_qp_attr qp_attr_QP3;
    struct ibv_ah_attr qp_attr_QP3_ah;
    struct ibv_global_route qp_attr_QP3_ah_grh;
    union ibv_gid qp_attr_QP3_ah_grh_dgid;
    struct ibv_send_wr wr_QP3;
    struct ibv_sge wr_QP3_sge_0;
    struct ibv_send_wr * bad_wr_QP3 = NULL;
    struct ibv_qp_init_attr attr_init_QP4;
    struct ibv_qp_cap attr_init_QP4_cap;
    struct ibv_qp_attr qp_attr_QP4;
    struct ibv_ah_attr qp_attr_QP4_ah;
    struct ibv_global_route qp_attr_QP4_ah_grh;
    union ibv_gid qp_attr_QP4_ah_grh_dgid;
    struct ibv_send_wr wr_QP4;
    struct ibv_sge wr_QP4_sge_0;
    struct ibv_send_wr * bad_wr_QP4 = NULL;
    struct ibv_qp_init_attr attr_init_QP5;
    struct ibv_qp_cap attr_init_QP5_cap;
    struct ibv_qp_attr qp_attr_QP5;
    struct ibv_ah_attr qp_attr_QP5_ah;
    struct ibv_global_route qp_attr_QP5_ah_grh;
    union ibv_gid qp_attr_QP5_ah_grh_dgid;
    struct ibv_send_wr wr_QP5;
    struct ibv_sge wr_QP5_sge_0;
    struct ibv_send_wr * bad_wr_QP5 = NULL;
    struct ibv_qp_init_attr attr_init_QP6;
    struct ibv_qp_cap attr_init_QP6_cap;
    struct ibv_qp_attr qp_attr_QP6;
    struct ibv_ah_attr qp_attr_QP6_ah;
    struct ibv_global_route qp_attr_QP6_ah_grh;
    union ibv_gid qp_attr_QP6_ah_grh_dgid;
    struct ibv_send_wr wr_QP6;
    struct ibv_sge wr_QP6_sge_0;
    struct ibv_send_wr * bad_wr_QP6 = NULL;
    struct ibv_qp_init_attr attr_init_QP7;
    struct ibv_qp_cap attr_init_QP7_cap;
    struct ibv_qp_attr qp_attr_QP7;
    struct ibv_ah_attr qp_attr_QP7_ah;
    struct ibv_global_route qp_attr_QP7_ah_grh;
    union ibv_gid qp_attr_QP7_ah_grh_dgid;
    struct ibv_send_wr wr_QP7;
    struct ibv_sge wr_QP7_sge_0;
    struct ibv_send_wr * bad_wr_QP7 = NULL;
    struct ibv_qp_init_attr attr_init_QP8;
    struct ibv_qp_cap attr_init_QP8_cap;
    struct ibv_qp_attr qp_attr_QP8;
    struct ibv_ah_attr qp_attr_QP8_ah;
    struct ibv_global_route qp_attr_QP8_ah_grh;
    union ibv_gid qp_attr_QP8_ah_grh_dgid;
    struct ibv_send_wr wr_QP8;
    struct ibv_sge wr_QP8_sge_0;
    struct ibv_send_wr * bad_wr_QP8 = NULL;
    struct ibv_qp_init_attr attr_init_QP9;
    struct ibv_qp_cap attr_init_QP9_cap;
    struct ibv_qp_attr qp_attr_QP9;
    struct ibv_ah_attr qp_attr_QP9_ah;
    struct ibv_global_route qp_attr_QP9_ah_grh;
    union ibv_gid qp_attr_QP9_ah_grh_dgid;
    struct ibv_send_wr wr_QP9;
    struct ibv_sge wr_QP9_sge_0;
    struct ibv_send_wr * bad_wr_QP9 = NULL;
    struct ibv_pd* PD0;
    struct ibv_pd* PD1;
    struct ibv_pd* PD2;
    struct ibv_pd* PD3;
    struct ibv_pd* PD4;
    struct ibv_pd* PD5;
    struct ibv_pd* PD6;
    struct ibv_pd* PD7;
    struct ibv_pd* PD8;
    struct ibv_pd* PD9;
    struct ibv_cq* CQ0;
    struct ibv_cq* CQ1;
    struct ibv_cq* CQ2;
    struct ibv_cq* CQ3;
    struct ibv_cq* CQ4;
    struct ibv_cq* CQ5;
    struct ibv_cq* CQ6;
    struct ibv_cq* CQ7;
    struct ibv_cq* CQ8;
    struct ibv_cq* CQ9;
    struct ibv_qp* QP0;
    struct ibv_qp* QP1;
    struct ibv_qp* QP2;
    struct ibv_qp* QP3;
    struct ibv_qp* QP4;
    struct ibv_qp* QP5;
    struct ibv_qp* QP6;
    struct ibv_qp* QP7;
    struct ibv_qp* QP8;
    struct ibv_qp* QP9;
    struct ibv_mr* MR0;
    struct ibv_mr* MR1;
    struct ibv_mr* MR2;
    struct ibv_mr* MR3;
    struct ibv_mr* MR4;
    struct ibv_mr* MR5;
    struct ibv_mr* MR6;
    struct ibv_mr* MR7;
    struct ibv_mr* MR8;
    struct ibv_mr* MR9;

    // ---- VARIABLES END ----
    int sockfd = create_socket();
    if (sockfd < 0)
    {
        fprintf(stderr, "Failed to create socket\n");
        return 1;
    }

    // ---- BODY BEGIN ----
    
    /* ibv_get_device_list */
    dev_list = ibv_get_device_list(NULL);
    if (!dev_list) {
        fprintf(stderr, "Failed to get device list: %s\n", strerror(errno));
        return -1;
    }

    /* ibv_open_device */
    ctx = ibv_open_device(dev_list[0]);
    if (!ctx) {
        fprintf(stderr, "Failed to open device\n");
        return -1;
    }

    /* ibv_free_device_list */
    ibv_free_device_list(dev_list);

    /* ibv_query_device */
    if (ibv_query_device(ctx, &dev_attr)) {
        fprintf(stderr, "Failed to query device attributes\n");
        return -1;
    }

    /* ibv_query_port */
    if (ibv_query_port(ctx, 1, &port_attr)) {
        fprintf(stderr, "Failed to query port attributes\n");
        return -1;
    }

    /* ibv_query_gid */
    union ibv_gid my_gid;
    if (ibv_query_gid(ctx, 1, 1, &my_gid)) {
        fprintf(stderr, "Failed to query GID\n");
        return -1;
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

    receive_metadata_from_controller(sockfd); // get remote MRs, and remote GID

    /* ibv_alloc_pd */
    PD0 = ibv_alloc_pd(ctx);
    if (!PD0) {
        fprintf(stderr, "Failed to allocate protection domain\n");
        return -1;
    }

    /* ibv_create_cq */
    CQ0 = ibv_create_cq(ctx, 32, 
                              NULL, NULL, 
                              0);
    if (!CQ0) {
        fprintf(stderr, "Failed to create completion queue\n");
        return -1;
    }

    /* ibv_reg_mr */
    MR0 = ibv_reg_mr(PD0, bufs[0], 1024, IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE);
    if (!MR0) {
        fprintf(stderr, "Failed to register memory region\n");
        return -1;
    }

    /* ibv_create_qp */
    
    memset(&attr_init_QP0, 0, sizeof(attr_init_QP0));
    attr_init_QP0.send_cq = CQ0;
    attr_init_QP0.recv_cq = CQ0;

    memset(&attr_init_QP0_cap, 0, sizeof(attr_init_QP0_cap));
    attr_init_QP0_cap.max_send_wr = 1;
    attr_init_QP0_cap.max_recv_wr = 1;
    attr_init_QP0_cap.max_send_sge = 1;
    attr_init_QP0_cap.max_recv_sge = 1;
    attr_init_QP0.cap = attr_init_QP0_cap;
    attr_init_QP0.qp_type = IBV_QPT_RC;
    attr_init_QP0.sq_sig_all = 1;

    QP0 = ibv_create_qp(PD0, &attr_init_QP0);
    if (!QP0) {
        fprintf(stderr, "Failed to create QP\n");
        return -1;
    }

    /* Export connection data */
    req.local_qpn = QP0->qp_num;
    req.remote_qp_index = 0;
    send_pair_request_to_controller(req, sockfd);
    receive_metadata_from_controller(sockfd); // is that correct? 接收配对信息

    memset(&qp_attr_QP0, 0, sizeof(qp_attr_QP0));
    
    memset(&qp_attr_QP0, 0, sizeof(qp_attr_QP0));
    qp_attr_QP0.qp_state = IBV_QPS_INIT;
    qp_attr_QP0.qp_access_flags = IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE;
    qp_attr_QP0.pkey_index = 0;
    qp_attr_QP0.port_num = 1;

    ibv_modify_qp(QP0, &qp_attr_QP0, IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS);
        
    memset(&qp_attr_QP0, 0, sizeof(qp_attr_QP0));
    
    memset(&qp_attr_QP0, 0, sizeof(qp_attr_QP0));
    qp_attr_QP0.qp_state = IBV_QPS_RTR;
    qp_attr_QP0.path_mtu = IBV_MTU_1024;
    qp_attr_QP0.rq_psn = 0;
    qp_attr_QP0.dest_qp_num = local_remote_qp_map[QP0->qp_num];

    memset(&qp_attr_QP0_ah, 0, sizeof(qp_attr_QP0_ah));

    memset(&qp_attr_QP0_ah_grh, 0, sizeof(qp_attr_QP0_ah_grh));

    memset(&qp_attr_QP0_ah_grh_dgid, 0, sizeof(qp_attr_QP0_ah_grh_dgid));
    memcpy(&qp_attr_QP0_ah_grh_dgid, &remote_info.gid, sizeof(qp_attr_QP0_ah_grh_dgid));
    qp_attr_QP0_ah_grh.dgid = qp_attr_QP0_ah_grh_dgid;
    qp_attr_QP0_ah_grh.flow_label = 0;
    qp_attr_QP0_ah_grh.sgid_index = 1;
    qp_attr_QP0_ah_grh.hop_limit = 1;
    qp_attr_QP0_ah_grh.traffic_class = 0;
    qp_attr_QP0_ah.grh = qp_attr_QP0_ah_grh;
    qp_attr_QP0_ah.dlid = remote_info.lid;
    qp_attr_QP0_ah.sl = 0;
    qp_attr_QP0_ah.src_path_bits = 0;
    qp_attr_QP0_ah.is_global = 1;
    qp_attr_QP0_ah.port_num = 1;
    qp_attr_QP0.ah_attr = qp_attr_QP0_ah;
    qp_attr_QP0.max_dest_rd_atomic = 1;
    qp_attr_QP0.min_rnr_timer = 12;

    ibv_modify_qp(QP0, &qp_attr_QP0, IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER);
        
    memset(&qp_attr_QP0, 0, sizeof(qp_attr_QP0));
    
    memset(&qp_attr_QP0, 0, sizeof(qp_attr_QP0));
    qp_attr_QP0.qp_state = IBV_QPS_RTS;
    qp_attr_QP0.sq_psn = 0;
    qp_attr_QP0.max_rd_atomic = 1;
    qp_attr_QP0.timeout = 14;
    qp_attr_QP0.retry_cnt = 7;
    qp_attr_QP0.rnr_retry = 7;

    ibv_modify_qp(QP0, &qp_attr_QP0, IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC);
        
    /* ibv_post_send */
    
    memset(&wr_QP0, 0, sizeof(wr_QP0));
    wr_QP0.wr_id = 1;

    memset(&wr_QP0_sge_0, 0, sizeof(wr_QP0_sge_0));
    wr_QP0_sge_0.addr = (uintptr_t)bufs[0];
    wr_QP0_sge_0.length = MSG_SIZE;
    wr_QP0_sge_0.lkey = MR0->lkey;
    wr_QP0.sg_list = &wr_QP0_sge_0;
    wr_QP0.num_sge = 1;
    wr_QP0.opcode = IBV_WR_SEND;
    wr_QP0.send_flags = IBV_SEND_SIGNALED;

    
    if (ibv_post_send(QP0, &wr_QP0, &bad_wr_QP0) != 0) {
        fprintf(stderr, "Failed to post send work request\n");
        return -1;
    }
    
    /* Poll completion queue */

    /* poll the completion for a while before giving up of doing it .. */
    gettimeofday(&cur_time, NULL);
    start_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    do
    {
        poll_result = ibv_poll_cq(CQ0, 1, &wc);
        gettimeofday(&cur_time, NULL);
        cur_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    }
    while((poll_result == 0) && ((cur_time_msec - start_time_msec) < MAX_POLL_CQ_TIMEOUT));

    if(poll_result < 0)
    {
        /* poll CQ failed */
        fprintf(stderr, "poll CQ failed\n");
        rc = 1;
    }
    else if(poll_result == 0)
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
        if(wc.status != IBV_WC_SUCCESS)
        {
            fprintf(stderr, "got bad completion with status: 0x%x, vendor syndrome: 0x%x\n", 
                    wc.status, wc.vendor_err);
            rc = 1;
        }
    }

    /* ibv_alloc_pd */
    PD1 = ibv_alloc_pd(ctx);
    if (!PD1) {
        fprintf(stderr, "Failed to allocate protection domain\n");
        return -1;
    }

    /* ibv_create_cq */
    CQ1 = ibv_create_cq(ctx, 32, 
                              NULL, NULL, 
                              0);
    if (!CQ1) {
        fprintf(stderr, "Failed to create completion queue\n");
        return -1;
    }

    /* ibv_reg_mr */
    MR1 = ibv_reg_mr(PD1, bufs[1], 1024, IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE);
    if (!MR1) {
        fprintf(stderr, "Failed to register memory region\n");
        return -1;
    }

    /* ibv_create_qp */
    
    memset(&attr_init_QP1, 0, sizeof(attr_init_QP1));
    attr_init_QP1.send_cq = CQ1;
    attr_init_QP1.recv_cq = CQ1;

    memset(&attr_init_QP1_cap, 0, sizeof(attr_init_QP1_cap));
    attr_init_QP1_cap.max_send_wr = 1;
    attr_init_QP1_cap.max_recv_wr = 1;
    attr_init_QP1_cap.max_send_sge = 1;
    attr_init_QP1_cap.max_recv_sge = 1;
    attr_init_QP1.cap = attr_init_QP1_cap;
    attr_init_QP1.qp_type = IBV_QPT_RC;
    attr_init_QP1.sq_sig_all = 1;

    QP1 = ibv_create_qp(PD1, &attr_init_QP1);
    if (!QP1) {
        fprintf(stderr, "Failed to create QP\n");
        return -1;
    }

    /* Export connection data */
    req.local_qpn = QP1->qp_num;
    req.remote_qp_index = 1;
    send_pair_request_to_controller(req, sockfd);
    receive_metadata_from_controller(sockfd); // is that correct? 接收配对信息

    memset(&qp_attr_QP1, 0, sizeof(qp_attr_QP1));
    
    memset(&qp_attr_QP1, 0, sizeof(qp_attr_QP1));
    qp_attr_QP1.qp_state = IBV_QPS_INIT;
    qp_attr_QP1.qp_access_flags = IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE;
    qp_attr_QP1.pkey_index = 0;
    qp_attr_QP1.port_num = 1;

    ibv_modify_qp(QP1, &qp_attr_QP1, IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS);
        
    memset(&qp_attr_QP1, 0, sizeof(qp_attr_QP1));
    
    memset(&qp_attr_QP1, 0, sizeof(qp_attr_QP1));
    qp_attr_QP1.qp_state = IBV_QPS_RTR;
    qp_attr_QP1.path_mtu = IBV_MTU_1024;
    qp_attr_QP1.rq_psn = 0;
    qp_attr_QP1.dest_qp_num = local_remote_qp_map[QP1->qp_num];

    memset(&qp_attr_QP1_ah, 0, sizeof(qp_attr_QP1_ah));

    memset(&qp_attr_QP1_ah_grh, 0, sizeof(qp_attr_QP1_ah_grh));

    memset(&qp_attr_QP1_ah_grh_dgid, 0, sizeof(qp_attr_QP1_ah_grh_dgid));
    memcpy(&qp_attr_QP1_ah_grh_dgid, &remote_info.gid, sizeof(qp_attr_QP1_ah_grh_dgid));
    qp_attr_QP1_ah_grh.dgid = qp_attr_QP1_ah_grh_dgid;
    qp_attr_QP1_ah_grh.flow_label = 0;
    qp_attr_QP1_ah_grh.sgid_index = 1;
    qp_attr_QP1_ah_grh.hop_limit = 1;
    qp_attr_QP1_ah_grh.traffic_class = 0;
    qp_attr_QP1_ah.grh = qp_attr_QP1_ah_grh;
    qp_attr_QP1_ah.dlid = remote_info.lid;
    qp_attr_QP1_ah.sl = 0;
    qp_attr_QP1_ah.src_path_bits = 0;
    qp_attr_QP1_ah.is_global = 1;
    qp_attr_QP1_ah.port_num = 1;
    qp_attr_QP1.ah_attr = qp_attr_QP1_ah;
    qp_attr_QP1.max_dest_rd_atomic = 1;
    qp_attr_QP1.min_rnr_timer = 12;

    ibv_modify_qp(QP1, &qp_attr_QP1, IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER);
        
    memset(&qp_attr_QP1, 0, sizeof(qp_attr_QP1));
    
    memset(&qp_attr_QP1, 0, sizeof(qp_attr_QP1));
    qp_attr_QP1.qp_state = IBV_QPS_RTS;
    qp_attr_QP1.sq_psn = 0;
    qp_attr_QP1.max_rd_atomic = 1;
    qp_attr_QP1.timeout = 14;
    qp_attr_QP1.retry_cnt = 7;
    qp_attr_QP1.rnr_retry = 7;

    ibv_modify_qp(QP1, &qp_attr_QP1, IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC);
        
    /* ibv_post_send */
    
    memset(&wr_QP1, 0, sizeof(wr_QP1));
    wr_QP1.wr_id = 1;

    memset(&wr_QP1_sge_0, 0, sizeof(wr_QP1_sge_0));
    wr_QP1_sge_0.addr = (uintptr_t)bufs[1];
    wr_QP1_sge_0.length = MSG_SIZE;
    wr_QP1_sge_0.lkey = MR1->lkey;
    wr_QP1.sg_list = &wr_QP1_sge_0;
    wr_QP1.num_sge = 1;
    wr_QP1.opcode = IBV_WR_SEND;
    wr_QP1.send_flags = IBV_SEND_SIGNALED;

    
    if (ibv_post_send(QP1, &wr_QP1, &bad_wr_QP1) != 0) {
        fprintf(stderr, "Failed to post send work request\n");
        return -1;
    }
    
    /* Poll completion queue */

    /* poll the completion for a while before giving up of doing it .. */
    gettimeofday(&cur_time, NULL);
    start_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    do
    {
        poll_result = ibv_poll_cq(CQ1, 1, &wc);
        gettimeofday(&cur_time, NULL);
        cur_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    }
    while((poll_result == 0) && ((cur_time_msec - start_time_msec) < MAX_POLL_CQ_TIMEOUT));

    if(poll_result < 0)
    {
        /* poll CQ failed */
        fprintf(stderr, "poll CQ failed\n");
        rc = 1;
    }
    else if(poll_result == 0)
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
        if(wc.status != IBV_WC_SUCCESS)
        {
            fprintf(stderr, "got bad completion with status: 0x%x, vendor syndrome: 0x%x\n", 
                    wc.status, wc.vendor_err);
            rc = 1;
        }
    }

    /* ibv_alloc_pd */
    PD2 = ibv_alloc_pd(ctx);
    if (!PD2) {
        fprintf(stderr, "Failed to allocate protection domain\n");
        return -1;
    }

    /* ibv_create_cq */
    CQ2 = ibv_create_cq(ctx, 32, 
                              NULL, NULL, 
                              0);
    if (!CQ2) {
        fprintf(stderr, "Failed to create completion queue\n");
        return -1;
    }

    /* ibv_reg_mr */
    MR2 = ibv_reg_mr(PD2, bufs[2], 1024, IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE);
    if (!MR2) {
        fprintf(stderr, "Failed to register memory region\n");
        return -1;
    }

    /* ibv_create_qp */
    
    memset(&attr_init_QP2, 0, sizeof(attr_init_QP2));
    attr_init_QP2.send_cq = CQ2;
    attr_init_QP2.recv_cq = CQ2;

    memset(&attr_init_QP2_cap, 0, sizeof(attr_init_QP2_cap));
    attr_init_QP2_cap.max_send_wr = 1;
    attr_init_QP2_cap.max_recv_wr = 1;
    attr_init_QP2_cap.max_send_sge = 1;
    attr_init_QP2_cap.max_recv_sge = 1;
    attr_init_QP2.cap = attr_init_QP2_cap;
    attr_init_QP2.qp_type = IBV_QPT_RC;
    attr_init_QP2.sq_sig_all = 1;

    QP2 = ibv_create_qp(PD2, &attr_init_QP2);
    if (!QP2) {
        fprintf(stderr, "Failed to create QP\n");
        return -1;
    }

    /* Export connection data */
    req.local_qpn = QP2->qp_num;
    req.remote_qp_index = 2;
    send_pair_request_to_controller(req, sockfd);
    receive_metadata_from_controller(sockfd); // is that correct? 接收配对信息

    memset(&qp_attr_QP2, 0, sizeof(qp_attr_QP2));
    
    memset(&qp_attr_QP2, 0, sizeof(qp_attr_QP2));
    qp_attr_QP2.qp_state = IBV_QPS_INIT;
    qp_attr_QP2.qp_access_flags = IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE;
    qp_attr_QP2.pkey_index = 0;
    qp_attr_QP2.port_num = 1;

    ibv_modify_qp(QP2, &qp_attr_QP2, IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS);
        
    memset(&qp_attr_QP2, 0, sizeof(qp_attr_QP2));
    
    memset(&qp_attr_QP2, 0, sizeof(qp_attr_QP2));
    qp_attr_QP2.qp_state = IBV_QPS_RTR;
    qp_attr_QP2.path_mtu = IBV_MTU_1024;
    qp_attr_QP2.rq_psn = 0;
    qp_attr_QP2.dest_qp_num = local_remote_qp_map[QP2->qp_num];

    memset(&qp_attr_QP2_ah, 0, sizeof(qp_attr_QP2_ah));

    memset(&qp_attr_QP2_ah_grh, 0, sizeof(qp_attr_QP2_ah_grh));

    memset(&qp_attr_QP2_ah_grh_dgid, 0, sizeof(qp_attr_QP2_ah_grh_dgid));
    memcpy(&qp_attr_QP2_ah_grh_dgid, &remote_info.gid, sizeof(qp_attr_QP2_ah_grh_dgid));
    qp_attr_QP2_ah_grh.dgid = qp_attr_QP2_ah_grh_dgid;
    qp_attr_QP2_ah_grh.flow_label = 0;
    qp_attr_QP2_ah_grh.sgid_index = 1;
    qp_attr_QP2_ah_grh.hop_limit = 1;
    qp_attr_QP2_ah_grh.traffic_class = 0;
    qp_attr_QP2_ah.grh = qp_attr_QP2_ah_grh;
    qp_attr_QP2_ah.dlid = remote_info.lid;
    qp_attr_QP2_ah.sl = 0;
    qp_attr_QP2_ah.src_path_bits = 0;
    qp_attr_QP2_ah.is_global = 1;
    qp_attr_QP2_ah.port_num = 1;
    qp_attr_QP2.ah_attr = qp_attr_QP2_ah;
    qp_attr_QP2.max_dest_rd_atomic = 1;
    qp_attr_QP2.min_rnr_timer = 12;

    ibv_modify_qp(QP2, &qp_attr_QP2, IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER);
        
    memset(&qp_attr_QP2, 0, sizeof(qp_attr_QP2));
    
    memset(&qp_attr_QP2, 0, sizeof(qp_attr_QP2));
    qp_attr_QP2.qp_state = IBV_QPS_RTS;
    qp_attr_QP2.sq_psn = 0;
    qp_attr_QP2.max_rd_atomic = 1;
    qp_attr_QP2.timeout = 14;
    qp_attr_QP2.retry_cnt = 7;
    qp_attr_QP2.rnr_retry = 7;

    ibv_modify_qp(QP2, &qp_attr_QP2, IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC);
        
    /* ibv_post_send */
    
    memset(&wr_QP2, 0, sizeof(wr_QP2));
    wr_QP2.wr_id = 1;

    memset(&wr_QP2_sge_0, 0, sizeof(wr_QP2_sge_0));
    wr_QP2_sge_0.addr = (uintptr_t)bufs[2];
    wr_QP2_sge_0.length = MSG_SIZE;
    wr_QP2_sge_0.lkey = MR2->lkey;
    wr_QP2.sg_list = &wr_QP2_sge_0;
    wr_QP2.num_sge = 1;
    wr_QP2.opcode = IBV_WR_SEND;
    wr_QP2.send_flags = IBV_SEND_SIGNALED;

    
    if (ibv_post_send(QP2, &wr_QP2, &bad_wr_QP2) != 0) {
        fprintf(stderr, "Failed to post send work request\n");
        return -1;
    }
    
    /* Poll completion queue */

    /* poll the completion for a while before giving up of doing it .. */
    gettimeofday(&cur_time, NULL);
    start_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    do
    {
        poll_result = ibv_poll_cq(CQ2, 1, &wc);
        gettimeofday(&cur_time, NULL);
        cur_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    }
    while((poll_result == 0) && ((cur_time_msec - start_time_msec) < MAX_POLL_CQ_TIMEOUT));

    if(poll_result < 0)
    {
        /* poll CQ failed */
        fprintf(stderr, "poll CQ failed\n");
        rc = 1;
    }
    else if(poll_result == 0)
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
        if(wc.status != IBV_WC_SUCCESS)
        {
            fprintf(stderr, "got bad completion with status: 0x%x, vendor syndrome: 0x%x\n", 
                    wc.status, wc.vendor_err);
            rc = 1;
        }
    }

    /* ibv_alloc_pd */
    PD3 = ibv_alloc_pd(ctx);
    if (!PD3) {
        fprintf(stderr, "Failed to allocate protection domain\n");
        return -1;
    }

    /* ibv_create_cq */
    CQ3 = ibv_create_cq(ctx, 32, 
                              NULL, NULL, 
                              0);
    if (!CQ3) {
        fprintf(stderr, "Failed to create completion queue\n");
        return -1;
    }

    /* ibv_reg_mr */
    MR3 = ibv_reg_mr(PD3, bufs[3], 1024, IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE);
    if (!MR3) {
        fprintf(stderr, "Failed to register memory region\n");
        return -1;
    }

    /* ibv_create_qp */
    
    memset(&attr_init_QP3, 0, sizeof(attr_init_QP3));
    attr_init_QP3.send_cq = CQ3;
    attr_init_QP3.recv_cq = CQ3;

    memset(&attr_init_QP3_cap, 0, sizeof(attr_init_QP3_cap));
    attr_init_QP3_cap.max_send_wr = 1;
    attr_init_QP3_cap.max_recv_wr = 1;
    attr_init_QP3_cap.max_send_sge = 1;
    attr_init_QP3_cap.max_recv_sge = 1;
    attr_init_QP3.cap = attr_init_QP3_cap;
    attr_init_QP3.qp_type = IBV_QPT_RC;
    attr_init_QP3.sq_sig_all = 1;

    QP3 = ibv_create_qp(PD3, &attr_init_QP3);
    if (!QP3) {
        fprintf(stderr, "Failed to create QP\n");
        return -1;
    }

    /* Export connection data */
    req.local_qpn = QP3->qp_num;
    req.remote_qp_index = 3;
    send_pair_request_to_controller(req, sockfd);
    receive_metadata_from_controller(sockfd); // is that correct? 接收配对信息

    memset(&qp_attr_QP3, 0, sizeof(qp_attr_QP3));
    
    memset(&qp_attr_QP3, 0, sizeof(qp_attr_QP3));
    qp_attr_QP3.qp_state = IBV_QPS_INIT;
    qp_attr_QP3.qp_access_flags = IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE;
    qp_attr_QP3.pkey_index = 0;
    qp_attr_QP3.port_num = 1;

    ibv_modify_qp(QP3, &qp_attr_QP3, IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS);
        
    memset(&qp_attr_QP3, 0, sizeof(qp_attr_QP3));
    
    memset(&qp_attr_QP3, 0, sizeof(qp_attr_QP3));
    qp_attr_QP3.qp_state = IBV_QPS_RTR;
    qp_attr_QP3.path_mtu = IBV_MTU_1024;
    qp_attr_QP3.rq_psn = 0;
    qp_attr_QP3.dest_qp_num = local_remote_qp_map[QP3->qp_num];

    memset(&qp_attr_QP3_ah, 0, sizeof(qp_attr_QP3_ah));

    memset(&qp_attr_QP3_ah_grh, 0, sizeof(qp_attr_QP3_ah_grh));

    memset(&qp_attr_QP3_ah_grh_dgid, 0, sizeof(qp_attr_QP3_ah_grh_dgid));
    memcpy(&qp_attr_QP3_ah_grh_dgid, &remote_info.gid, sizeof(qp_attr_QP3_ah_grh_dgid));
    qp_attr_QP3_ah_grh.dgid = qp_attr_QP3_ah_grh_dgid;
    qp_attr_QP3_ah_grh.flow_label = 0;
    qp_attr_QP3_ah_grh.sgid_index = 1;
    qp_attr_QP3_ah_grh.hop_limit = 1;
    qp_attr_QP3_ah_grh.traffic_class = 0;
    qp_attr_QP3_ah.grh = qp_attr_QP3_ah_grh;
    qp_attr_QP3_ah.dlid = remote_info.lid;
    qp_attr_QP3_ah.sl = 0;
    qp_attr_QP3_ah.src_path_bits = 0;
    qp_attr_QP3_ah.is_global = 1;
    qp_attr_QP3_ah.port_num = 1;
    qp_attr_QP3.ah_attr = qp_attr_QP3_ah;
    qp_attr_QP3.max_dest_rd_atomic = 1;
    qp_attr_QP3.min_rnr_timer = 12;

    ibv_modify_qp(QP3, &qp_attr_QP3, IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER);
        
    memset(&qp_attr_QP3, 0, sizeof(qp_attr_QP3));
    
    memset(&qp_attr_QP3, 0, sizeof(qp_attr_QP3));
    qp_attr_QP3.qp_state = IBV_QPS_RTS;
    qp_attr_QP3.sq_psn = 0;
    qp_attr_QP3.max_rd_atomic = 1;
    qp_attr_QP3.timeout = 14;
    qp_attr_QP3.retry_cnt = 7;
    qp_attr_QP3.rnr_retry = 7;

    ibv_modify_qp(QP3, &qp_attr_QP3, IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC);
        
    /* ibv_post_send */
    
    memset(&wr_QP3, 0, sizeof(wr_QP3));
    wr_QP3.wr_id = 1;

    memset(&wr_QP3_sge_0, 0, sizeof(wr_QP3_sge_0));
    wr_QP3_sge_0.addr = (uintptr_t)bufs[3];
    wr_QP3_sge_0.length = MSG_SIZE;
    wr_QP3_sge_0.lkey = MR3->lkey;
    wr_QP3.sg_list = &wr_QP3_sge_0;
    wr_QP3.num_sge = 1;
    wr_QP3.opcode = IBV_WR_SEND;
    wr_QP3.send_flags = IBV_SEND_SIGNALED;

    
    if (ibv_post_send(QP3, &wr_QP3, &bad_wr_QP3) != 0) {
        fprintf(stderr, "Failed to post send work request\n");
        return -1;
    }
    
    /* Poll completion queue */

    /* poll the completion for a while before giving up of doing it .. */
    gettimeofday(&cur_time, NULL);
    start_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    do
    {
        poll_result = ibv_poll_cq(CQ3, 1, &wc);
        gettimeofday(&cur_time, NULL);
        cur_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    }
    while((poll_result == 0) && ((cur_time_msec - start_time_msec) < MAX_POLL_CQ_TIMEOUT));

    if(poll_result < 0)
    {
        /* poll CQ failed */
        fprintf(stderr, "poll CQ failed\n");
        rc = 1;
    }
    else if(poll_result == 0)
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
        if(wc.status != IBV_WC_SUCCESS)
        {
            fprintf(stderr, "got bad completion with status: 0x%x, vendor syndrome: 0x%x\n", 
                    wc.status, wc.vendor_err);
            rc = 1;
        }
    }

    /* ibv_alloc_pd */
    PD4 = ibv_alloc_pd(ctx);
    if (!PD4) {
        fprintf(stderr, "Failed to allocate protection domain\n");
        return -1;
    }

    /* ibv_create_cq */
    CQ4 = ibv_create_cq(ctx, 32, 
                              NULL, NULL, 
                              0);
    if (!CQ4) {
        fprintf(stderr, "Failed to create completion queue\n");
        return -1;
    }

    /* ibv_reg_mr */
    MR4 = ibv_reg_mr(PD4, bufs[4], 1024, IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE);
    if (!MR4) {
        fprintf(stderr, "Failed to register memory region\n");
        return -1;
    }

    /* ibv_create_qp */
    
    memset(&attr_init_QP4, 0, sizeof(attr_init_QP4));
    attr_init_QP4.send_cq = CQ2;
    attr_init_QP4.recv_cq = CQ2;

    memset(&attr_init_QP4_cap, 0, sizeof(attr_init_QP4_cap));
    attr_init_QP4_cap.max_send_wr = 1;
    attr_init_QP4_cap.max_recv_wr = 1;
    attr_init_QP4_cap.max_send_sge = 1;
    attr_init_QP4_cap.max_recv_sge = 1;
    attr_init_QP4.cap = attr_init_QP4_cap;
    attr_init_QP4.qp_type = IBV_QPT_RC;
    attr_init_QP4.sq_sig_all = 1;

    QP4 = ibv_create_qp(PD4, &attr_init_QP4);
    if (!QP4) {
        fprintf(stderr, "Failed to create QP\n");
        return -1;
    }

    /* Export connection data */
    req.local_qpn = QP4->qp_num;
    req.remote_qp_index = 4;
    send_pair_request_to_controller(req, sockfd);
    receive_metadata_from_controller(sockfd); // is that correct? 接收配对信息

    memset(&qp_attr_QP4, 0, sizeof(qp_attr_QP4));
    
    memset(&qp_attr_QP4, 0, sizeof(qp_attr_QP4));
    qp_attr_QP4.qp_state = IBV_QPS_INIT;
    qp_attr_QP4.qp_access_flags = IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE;
    qp_attr_QP4.pkey_index = 0;
    qp_attr_QP4.port_num = 1;

    ibv_modify_qp(QP4, &qp_attr_QP4, IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS);
        
    memset(&qp_attr_QP4, 0, sizeof(qp_attr_QP4));
    
    memset(&qp_attr_QP4, 0, sizeof(qp_attr_QP4));
    qp_attr_QP4.qp_state = IBV_QPS_RTR;
    qp_attr_QP4.path_mtu = IBV_MTU_1024;
    qp_attr_QP4.rq_psn = 0;
    qp_attr_QP4.dest_qp_num = local_remote_qp_map[QP4->qp_num];

    memset(&qp_attr_QP4_ah, 0, sizeof(qp_attr_QP4_ah));

    memset(&qp_attr_QP4_ah_grh, 0, sizeof(qp_attr_QP4_ah_grh));

    memset(&qp_attr_QP4_ah_grh_dgid, 0, sizeof(qp_attr_QP4_ah_grh_dgid));
    memcpy(&qp_attr_QP4_ah_grh_dgid, &remote_info.gid, sizeof(qp_attr_QP4_ah_grh_dgid));
    qp_attr_QP4_ah_grh.dgid = qp_attr_QP4_ah_grh_dgid;
    qp_attr_QP4_ah_grh.flow_label = 0;
    qp_attr_QP4_ah_grh.sgid_index = 1;
    qp_attr_QP4_ah_grh.hop_limit = 1;
    qp_attr_QP4_ah_grh.traffic_class = 0;
    qp_attr_QP4_ah.grh = qp_attr_QP4_ah_grh;
    qp_attr_QP4_ah.dlid = remote_info.lid;
    qp_attr_QP4_ah.sl = 0;
    qp_attr_QP4_ah.src_path_bits = 0;
    qp_attr_QP4_ah.is_global = 1;
    qp_attr_QP4_ah.port_num = 1;
    qp_attr_QP4.ah_attr = qp_attr_QP4_ah;
    qp_attr_QP4.max_dest_rd_atomic = 1;
    qp_attr_QP4.min_rnr_timer = 12;

    ibv_modify_qp(QP4, &qp_attr_QP4, IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER);
        
    memset(&qp_attr_QP4, 0, sizeof(qp_attr_QP4));
    
    memset(&qp_attr_QP4, 0, sizeof(qp_attr_QP4));
    qp_attr_QP4.qp_state = IBV_QPS_RTS;
    qp_attr_QP4.sq_psn = 0;
    qp_attr_QP4.max_rd_atomic = 1;
    qp_attr_QP4.timeout = 14;
    qp_attr_QP4.retry_cnt = 7;
    qp_attr_QP4.rnr_retry = 7;

    ibv_modify_qp(QP4, &qp_attr_QP4, IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC);
        
    /* ibv_post_send */
    
    memset(&wr_QP4, 0, sizeof(wr_QP4));
    wr_QP4.wr_id = 1;

    memset(&wr_QP4_sge_0, 0, sizeof(wr_QP4_sge_0));
    wr_QP4_sge_0.addr = (uintptr_t)bufs[4];
    wr_QP4_sge_0.length = MSG_SIZE;
    wr_QP4_sge_0.lkey = MR4->lkey;
    wr_QP4.sg_list = &wr_QP4_sge_0;
    wr_QP4.num_sge = 1;
    wr_QP4.opcode = IBV_WR_SEND;
    wr_QP4.send_flags = IBV_SEND_SIGNALED;

    
    if (ibv_post_send(QP4, &wr_QP4, &bad_wr_QP4) != 0) {
        fprintf(stderr, "Failed to post send work request\n");
        return -1;
    }
    
    /* Poll completion queue */

    /* poll the completion for a while before giving up of doing it .. */
    gettimeofday(&cur_time, NULL);
    start_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    do
    {
        poll_result = ibv_poll_cq(CQ2, 1, &wc);
        gettimeofday(&cur_time, NULL);
        cur_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    }
    while((poll_result == 0) && ((cur_time_msec - start_time_msec) < MAX_POLL_CQ_TIMEOUT));

    if(poll_result < 0)
    {
        /* poll CQ failed */
        fprintf(stderr, "poll CQ failed\n");
        rc = 1;
    }
    else if(poll_result == 0)
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
        if(wc.status != IBV_WC_SUCCESS)
        {
            fprintf(stderr, "got bad completion with status: 0x%x, vendor syndrome: 0x%x\n", 
                    wc.status, wc.vendor_err);
            rc = 1;
        }
    }

    /* ibv_alloc_pd */
    PD5 = ibv_alloc_pd(ctx);
    if (!PD5) {
        fprintf(stderr, "Failed to allocate protection domain\n");
        return -1;
    }

    /* ibv_create_cq */
    CQ5 = ibv_create_cq(ctx, 32, 
                              NULL, NULL, 
                              0);
    if (!CQ5) {
        fprintf(stderr, "Failed to create completion queue\n");
        return -1;
    }

    /* ibv_reg_mr */
    MR5 = ibv_reg_mr(PD5, bufs[5], 1024, IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE);
    if (!MR5) {
        fprintf(stderr, "Failed to register memory region\n");
        return -1;
    }

    /* ibv_create_qp */
    
    memset(&attr_init_QP5, 0, sizeof(attr_init_QP5));
    attr_init_QP5.send_cq = CQ5;
    attr_init_QP5.recv_cq = CQ5;

    memset(&attr_init_QP5_cap, 0, sizeof(attr_init_QP5_cap));
    attr_init_QP5_cap.max_send_wr = 1;
    attr_init_QP5_cap.max_recv_wr = 1;
    attr_init_QP5_cap.max_send_sge = 1;
    attr_init_QP5_cap.max_recv_sge = 1;
    attr_init_QP5.cap = attr_init_QP5_cap;
    attr_init_QP5.qp_type = IBV_QPT_RC;
    attr_init_QP5.sq_sig_all = 1;

    QP5 = ibv_create_qp(PD5, &attr_init_QP5);
    if (!QP5) {
        fprintf(stderr, "Failed to create QP\n");
        return -1;
    }

    /* Export connection data */
    req.local_qpn = QP5->qp_num;
    req.remote_qp_index = 5;
    send_pair_request_to_controller(req, sockfd);
    receive_metadata_from_controller(sockfd); // is that correct? 接收配对信息

    memset(&qp_attr_QP5, 0, sizeof(qp_attr_QP5));
    
    memset(&qp_attr_QP5, 0, sizeof(qp_attr_QP5));
    qp_attr_QP5.qp_state = IBV_QPS_INIT;
    qp_attr_QP5.qp_access_flags = IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE;
    qp_attr_QP5.pkey_index = 0;
    qp_attr_QP5.port_num = 1;

    ibv_modify_qp(QP5, &qp_attr_QP5, IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS);
        
    memset(&qp_attr_QP5, 0, sizeof(qp_attr_QP5));
    
    memset(&qp_attr_QP5, 0, sizeof(qp_attr_QP5));
    qp_attr_QP5.qp_state = IBV_QPS_RTR;
    qp_attr_QP5.path_mtu = IBV_MTU_1024;
    qp_attr_QP5.rq_psn = 0;
    qp_attr_QP5.dest_qp_num = local_remote_qp_map[QP5->qp_num];

    memset(&qp_attr_QP5_ah, 0, sizeof(qp_attr_QP5_ah));

    memset(&qp_attr_QP5_ah_grh, 0, sizeof(qp_attr_QP5_ah_grh));

    memset(&qp_attr_QP5_ah_grh_dgid, 0, sizeof(qp_attr_QP5_ah_grh_dgid));
    memcpy(&qp_attr_QP5_ah_grh_dgid, &remote_info.gid, sizeof(qp_attr_QP5_ah_grh_dgid));
    qp_attr_QP5_ah_grh.dgid = qp_attr_QP5_ah_grh_dgid;
    qp_attr_QP5_ah_grh.flow_label = 0;
    qp_attr_QP5_ah_grh.sgid_index = 1;
    qp_attr_QP5_ah_grh.hop_limit = 1;
    qp_attr_QP5_ah_grh.traffic_class = 0;
    qp_attr_QP5_ah.grh = qp_attr_QP5_ah_grh;
    qp_attr_QP5_ah.dlid = remote_info.lid;
    qp_attr_QP5_ah.sl = 0;
    qp_attr_QP5_ah.src_path_bits = 0;
    qp_attr_QP5_ah.is_global = 1;
    qp_attr_QP5_ah.port_num = 1;
    qp_attr_QP5.ah_attr = qp_attr_QP5_ah;
    qp_attr_QP5.max_dest_rd_atomic = 1;
    qp_attr_QP5.min_rnr_timer = 12;

    ibv_modify_qp(QP5, &qp_attr_QP5, IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER);
        
    memset(&qp_attr_QP5, 0, sizeof(qp_attr_QP5));
    
    memset(&qp_attr_QP5, 0, sizeof(qp_attr_QP5));
    qp_attr_QP5.qp_state = IBV_QPS_RTS;
    qp_attr_QP5.sq_psn = 0;
    qp_attr_QP5.max_rd_atomic = 1;
    qp_attr_QP5.timeout = 14;
    qp_attr_QP5.retry_cnt = 7;
    qp_attr_QP5.rnr_retry = 7;

    ibv_modify_qp(QP5, &qp_attr_QP5, IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC);
        
    /* ibv_post_send */
    
    memset(&wr_QP5, 0, sizeof(wr_QP5));
    wr_QP5.wr_id = 1;

    memset(&wr_QP5_sge_0, 0, sizeof(wr_QP5_sge_0));
    wr_QP5_sge_0.addr = (uintptr_t)bufs[5];
    wr_QP5_sge_0.length = MSG_SIZE;
    wr_QP5_sge_0.lkey = MR5->lkey;
    wr_QP5.sg_list = &wr_QP5_sge_0;
    wr_QP5.num_sge = 1;
    wr_QP5.opcode = IBV_WR_SEND;
    wr_QP5.send_flags = IBV_SEND_SIGNALED;

    
    if (ibv_post_send(QP5, &wr_QP5, &bad_wr_QP5) != 0) {
        fprintf(stderr, "Failed to post send work request\n");
        return -1;
    }
    
    /* Poll completion queue */

    /* poll the completion for a while before giving up of doing it .. */
    gettimeofday(&cur_time, NULL);
    start_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    do
    {
        poll_result = ibv_poll_cq(CQ5, 1, &wc);
        gettimeofday(&cur_time, NULL);
        cur_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    }
    while((poll_result == 0) && ((cur_time_msec - start_time_msec) < MAX_POLL_CQ_TIMEOUT));

    if(poll_result < 0)
    {
        /* poll CQ failed */
        fprintf(stderr, "poll CQ failed\n");
        rc = 1;
    }
    else if(poll_result == 0)
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
        if(wc.status != IBV_WC_SUCCESS)
        {
            fprintf(stderr, "got bad completion with status: 0x%x, vendor syndrome: 0x%x\n", 
                    wc.status, wc.vendor_err);
            rc = 1;
        }
    }

    /* ibv_alloc_pd */
    PD6 = ibv_alloc_pd(ctx);
    if (!PD6) {
        fprintf(stderr, "Failed to allocate protection domain\n");
        return -1;
    }

    /* ibv_create_cq */
    CQ6 = ibv_create_cq(ctx, 32, 
                              NULL, NULL, 
                              0);
    if (!CQ6) {
        fprintf(stderr, "Failed to create completion queue\n");
        return -1;
    }

    /* ibv_reg_mr */
    MR6 = ibv_reg_mr(PD6, bufs[6], 1024, IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE);
    if (!MR6) {
        fprintf(stderr, "Failed to register memory region\n");
        return -1;
    }

    /* ibv_create_qp */
    
    memset(&attr_init_QP6, 0, sizeof(attr_init_QP6));
    attr_init_QP6.send_cq = CQ6;
    attr_init_QP6.recv_cq = CQ6;

    memset(&attr_init_QP6_cap, 0, sizeof(attr_init_QP6_cap));
    attr_init_QP6_cap.max_send_wr = 1;
    attr_init_QP6_cap.max_recv_wr = 1;
    attr_init_QP6_cap.max_send_sge = 1;
    attr_init_QP6_cap.max_recv_sge = 1;
    attr_init_QP6.cap = attr_init_QP6_cap;
    attr_init_QP6.qp_type = IBV_QPT_RC;
    attr_init_QP6.sq_sig_all = 1;

    QP6 = ibv_create_qp(PD6, &attr_init_QP6);
    if (!QP6) {
        fprintf(stderr, "Failed to create QP\n");
        return -1;
    }

    /* Export connection data */
    req.local_qpn = QP6->qp_num;
    req.remote_qp_index = 6;
    send_pair_request_to_controller(req, sockfd);
    receive_metadata_from_controller(sockfd); // is that correct? 接收配对信息

    memset(&qp_attr_QP6, 0, sizeof(qp_attr_QP6));
    
    memset(&qp_attr_QP6, 0, sizeof(qp_attr_QP6));
    qp_attr_QP6.qp_state = IBV_QPS_INIT;
    qp_attr_QP6.qp_access_flags = IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE;
    qp_attr_QP6.pkey_index = 0;
    qp_attr_QP6.port_num = 1;

    ibv_modify_qp(QP6, &qp_attr_QP6, IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS);
        
    memset(&qp_attr_QP6, 0, sizeof(qp_attr_QP6));
    
    memset(&qp_attr_QP6, 0, sizeof(qp_attr_QP6));
    qp_attr_QP6.qp_state = IBV_QPS_RTR;
    qp_attr_QP6.path_mtu = IBV_MTU_1024;
    qp_attr_QP6.rq_psn = 0;
    qp_attr_QP6.dest_qp_num = local_remote_qp_map[QP6->qp_num];

    memset(&qp_attr_QP6_ah, 0, sizeof(qp_attr_QP6_ah));

    memset(&qp_attr_QP6_ah_grh, 0, sizeof(qp_attr_QP6_ah_grh));

    memset(&qp_attr_QP6_ah_grh_dgid, 0, sizeof(qp_attr_QP6_ah_grh_dgid));
    memcpy(&qp_attr_QP6_ah_grh_dgid, &remote_info.gid, sizeof(qp_attr_QP6_ah_grh_dgid));
    qp_attr_QP6_ah_grh.dgid = qp_attr_QP6_ah_grh_dgid;
    qp_attr_QP6_ah_grh.flow_label = 0;
    qp_attr_QP6_ah_grh.sgid_index = 1;
    qp_attr_QP6_ah_grh.hop_limit = 1;
    qp_attr_QP6_ah_grh.traffic_class = 0;
    qp_attr_QP6_ah.grh = qp_attr_QP6_ah_grh;
    qp_attr_QP6_ah.dlid = remote_info.lid;
    qp_attr_QP6_ah.sl = 0;
    qp_attr_QP6_ah.src_path_bits = 0;
    qp_attr_QP6_ah.is_global = 1;
    qp_attr_QP6_ah.port_num = 1;
    qp_attr_QP6.ah_attr = qp_attr_QP6_ah;
    qp_attr_QP6.max_dest_rd_atomic = 1;
    qp_attr_QP6.min_rnr_timer = 12;

    ibv_modify_qp(QP6, &qp_attr_QP6, IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER);
        
    memset(&qp_attr_QP6, 0, sizeof(qp_attr_QP6));
    
    memset(&qp_attr_QP6, 0, sizeof(qp_attr_QP6));
    qp_attr_QP6.qp_state = IBV_QPS_RTS;
    qp_attr_QP6.sq_psn = 0;
    qp_attr_QP6.max_rd_atomic = 1;
    qp_attr_QP6.timeout = 14;
    qp_attr_QP6.retry_cnt = 7;
    qp_attr_QP6.rnr_retry = 7;

    ibv_modify_qp(QP6, &qp_attr_QP6, IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC);
        
    /* ibv_post_send */
    
    memset(&wr_QP6, 0, sizeof(wr_QP6));
    wr_QP6.wr_id = 1;

    memset(&wr_QP6_sge_0, 0, sizeof(wr_QP6_sge_0));
    wr_QP6_sge_0.addr = (uintptr_t)bufs[6];
    wr_QP6_sge_0.length = MSG_SIZE;
    wr_QP6_sge_0.lkey = MR6->lkey;
    wr_QP6.sg_list = &wr_QP6_sge_0;
    wr_QP6.num_sge = 1;
    wr_QP6.opcode = IBV_WR_SEND;
    wr_QP6.send_flags = IBV_SEND_SIGNALED;

    
    if (ibv_post_send(QP6, &wr_QP6, &bad_wr_QP6) != 0) {
        fprintf(stderr, "Failed to post send work request\n");
        return -1;
    }
    
    /* Poll completion queue */

    /* poll the completion for a while before giving up of doing it .. */
    gettimeofday(&cur_time, NULL);
    start_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    do
    {
        poll_result = ibv_poll_cq(CQ6, 1, &wc);
        gettimeofday(&cur_time, NULL);
        cur_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    }
    while((poll_result == 0) && ((cur_time_msec - start_time_msec) < MAX_POLL_CQ_TIMEOUT));

    if(poll_result < 0)
    {
        /* poll CQ failed */
        fprintf(stderr, "poll CQ failed\n");
        rc = 1;
    }
    else if(poll_result == 0)
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
        if(wc.status != IBV_WC_SUCCESS)
        {
            fprintf(stderr, "got bad completion with status: 0x%x, vendor syndrome: 0x%x\n", 
                    wc.status, wc.vendor_err);
            rc = 1;
        }
    }

    /* ibv_alloc_pd */
    PD7 = ibv_alloc_pd(ctx);
    if (!PD7) {
        fprintf(stderr, "Failed to allocate protection domain\n");
        return -1;
    }

    /* ibv_create_cq */
    CQ7 = ibv_create_cq(ctx, 32, 
                              NULL, NULL, 
                              0);
    if (!CQ7) {
        fprintf(stderr, "Failed to create completion queue\n");
        return -1;
    }

    /* ibv_reg_mr */
    MR7 = ibv_reg_mr(PD7, bufs[7], 1024, IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE);
    if (!MR7) {
        fprintf(stderr, "Failed to register memory region\n");
        return -1;
    }

    /* ibv_create_qp */
    
    memset(&attr_init_QP7, 0, sizeof(attr_init_QP7));
    attr_init_QP7.send_cq = CQ7;
    attr_init_QP7.recv_cq = CQ7;

    memset(&attr_init_QP7_cap, 0, sizeof(attr_init_QP7_cap));
    attr_init_QP7_cap.max_send_wr = 1;
    attr_init_QP7_cap.max_recv_wr = 1;
    attr_init_QP7_cap.max_send_sge = 1;
    attr_init_QP7_cap.max_recv_sge = 1;
    attr_init_QP7.cap = attr_init_QP7_cap;
    attr_init_QP7.qp_type = IBV_QPT_RC;
    attr_init_QP7.sq_sig_all = 1;

    QP7 = ibv_create_qp(PD7, &attr_init_QP7);
    if (!QP7) {
        fprintf(stderr, "Failed to create QP\n");
        return -1;
    }

    /* Export connection data */
    req.local_qpn = QP7->qp_num;
    req.remote_qp_index = 7;
    send_pair_request_to_controller(req, sockfd);
    receive_metadata_from_controller(sockfd); // is that correct? 接收配对信息

    memset(&qp_attr_QP7, 0, sizeof(qp_attr_QP7));
    
    memset(&qp_attr_QP7, 0, sizeof(qp_attr_QP7));
    qp_attr_QP7.qp_state = IBV_QPS_INIT;
    qp_attr_QP7.qp_access_flags = IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE;
    qp_attr_QP7.pkey_index = 0;
    qp_attr_QP7.port_num = 1;

    ibv_modify_qp(QP7, &qp_attr_QP7, IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS);
        
    memset(&qp_attr_QP7, 0, sizeof(qp_attr_QP7));
    
    memset(&qp_attr_QP7, 0, sizeof(qp_attr_QP7));
    qp_attr_QP7.qp_state = IBV_QPS_RTR;
    qp_attr_QP7.path_mtu = IBV_MTU_1024;
    qp_attr_QP7.rq_psn = 0;
    qp_attr_QP7.dest_qp_num = local_remote_qp_map[QP7->qp_num];

    memset(&qp_attr_QP7_ah, 0, sizeof(qp_attr_QP7_ah));

    memset(&qp_attr_QP7_ah_grh, 0, sizeof(qp_attr_QP7_ah_grh));

    memset(&qp_attr_QP7_ah_grh_dgid, 0, sizeof(qp_attr_QP7_ah_grh_dgid));
    memcpy(&qp_attr_QP7_ah_grh_dgid, &remote_info.gid, sizeof(qp_attr_QP7_ah_grh_dgid));
    qp_attr_QP7_ah_grh.dgid = qp_attr_QP7_ah_grh_dgid;
    qp_attr_QP7_ah_grh.flow_label = 0;
    qp_attr_QP7_ah_grh.sgid_index = 1;
    qp_attr_QP7_ah_grh.hop_limit = 1;
    qp_attr_QP7_ah_grh.traffic_class = 0;
    qp_attr_QP7_ah.grh = qp_attr_QP7_ah_grh;
    qp_attr_QP7_ah.dlid = remote_info.lid;
    qp_attr_QP7_ah.sl = 0;
    qp_attr_QP7_ah.src_path_bits = 0;
    qp_attr_QP7_ah.is_global = 1;
    qp_attr_QP7_ah.port_num = 1;
    qp_attr_QP7.ah_attr = qp_attr_QP7_ah;
    qp_attr_QP7.max_dest_rd_atomic = 1;
    qp_attr_QP7.min_rnr_timer = 12;

    ibv_modify_qp(QP7, &qp_attr_QP7, IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER);
        
    memset(&qp_attr_QP7, 0, sizeof(qp_attr_QP7));
    
    memset(&qp_attr_QP7, 0, sizeof(qp_attr_QP7));
    qp_attr_QP7.qp_state = IBV_QPS_RTS;
    qp_attr_QP7.sq_psn = 0;
    qp_attr_QP7.max_rd_atomic = 1;
    qp_attr_QP7.timeout = 14;
    qp_attr_QP7.retry_cnt = 7;
    qp_attr_QP7.rnr_retry = 7;

    ibv_modify_qp(QP7, &qp_attr_QP7, IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC);
        
    /* ibv_post_send */
    
    memset(&wr_QP7, 0, sizeof(wr_QP7));
    wr_QP7.wr_id = 1;

    memset(&wr_QP7_sge_0, 0, sizeof(wr_QP7_sge_0));
    wr_QP7_sge_0.addr = (uintptr_t)bufs[7];
    wr_QP7_sge_0.length = MSG_SIZE;
    wr_QP7_sge_0.lkey = MR7->lkey;
    wr_QP7.sg_list = &wr_QP7_sge_0;
    wr_QP7.num_sge = 1;
    wr_QP7.opcode = IBV_WR_SEND;
    wr_QP7.send_flags = IBV_SEND_SIGNALED;

    
    if (ibv_post_send(QP7, &wr_QP7, &bad_wr_QP7) != 0) {
        fprintf(stderr, "Failed to post send work request\n");
        return -1;
    }
    
    /* Poll completion queue */

    /* poll the completion for a while before giving up of doing it .. */
    gettimeofday(&cur_time, NULL);
    start_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    do
    {
        poll_result = ibv_poll_cq(CQ7, 1, &wc);
        gettimeofday(&cur_time, NULL);
        cur_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    }
    while((poll_result == 0) && ((cur_time_msec - start_time_msec) < MAX_POLL_CQ_TIMEOUT));

    if(poll_result < 0)
    {
        /* poll CQ failed */
        fprintf(stderr, "poll CQ failed\n");
        rc = 1;
    }
    else if(poll_result == 0)
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
        if(wc.status != IBV_WC_SUCCESS)
        {
            fprintf(stderr, "got bad completion with status: 0x%x, vendor syndrome: 0x%x\n", 
                    wc.status, wc.vendor_err);
            rc = 1;
        }
    }

    /* ibv_alloc_pd */
    PD8 = ibv_alloc_pd(ctx);
    if (!PD8) {
        fprintf(stderr, "Failed to allocate protection domain\n");
        return -1;
    }

    /* ibv_create_cq */
    CQ8 = ibv_create_cq(ctx, 32, 
                              NULL, NULL, 
                              0);
    if (!CQ8) {
        fprintf(stderr, "Failed to create completion queue\n");
        return -1;
    }

    /* ibv_reg_mr */
    MR8 = ibv_reg_mr(PD8, bufs[8], 1024, IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE);
    if (!MR8) {
        fprintf(stderr, "Failed to register memory region\n");
        return -1;
    }

    /* ibv_create_qp */
    
    memset(&attr_init_QP8, 0, sizeof(attr_init_QP8));
    attr_init_QP8.send_cq = CQ8;
    attr_init_QP8.recv_cq = CQ8;

    memset(&attr_init_QP8_cap, 0, sizeof(attr_init_QP8_cap));
    attr_init_QP8_cap.max_send_wr = 1;
    attr_init_QP8_cap.max_recv_wr = 1;
    attr_init_QP8_cap.max_send_sge = 1;
    attr_init_QP8_cap.max_recv_sge = 1;
    attr_init_QP8.cap = attr_init_QP8_cap;
    attr_init_QP8.qp_type = IBV_QPT_RC;
    attr_init_QP8.sq_sig_all = 1;

    QP8 = ibv_create_qp(PD8, &attr_init_QP8);
    if (!QP8) {
        fprintf(stderr, "Failed to create QP\n");
        return -1;
    }

    /* Export connection data */
    req.local_qpn = QP8->qp_num;
    req.remote_qp_index = 8;
    send_pair_request_to_controller(req, sockfd);
    receive_metadata_from_controller(sockfd); // is that correct? 接收配对信息

    memset(&qp_attr_QP8, 0, sizeof(qp_attr_QP8));
    
    memset(&qp_attr_QP8, 0, sizeof(qp_attr_QP8));
    qp_attr_QP8.qp_state = IBV_QPS_INIT;
    qp_attr_QP8.qp_access_flags = IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE;
    qp_attr_QP8.pkey_index = 0;
    qp_attr_QP8.port_num = 1;

    ibv_modify_qp(QP8, &qp_attr_QP8, IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS);
        
    memset(&qp_attr_QP8, 0, sizeof(qp_attr_QP8));
    
    memset(&qp_attr_QP8, 0, sizeof(qp_attr_QP8));
    qp_attr_QP8.qp_state = IBV_QPS_RTR;
    qp_attr_QP8.path_mtu = IBV_MTU_1024;
    qp_attr_QP8.rq_psn = 0;
    qp_attr_QP8.dest_qp_num = local_remote_qp_map[QP8->qp_num];

    memset(&qp_attr_QP8_ah, 0, sizeof(qp_attr_QP8_ah));

    memset(&qp_attr_QP8_ah_grh, 0, sizeof(qp_attr_QP8_ah_grh));

    memset(&qp_attr_QP8_ah_grh_dgid, 0, sizeof(qp_attr_QP8_ah_grh_dgid));
    memcpy(&qp_attr_QP8_ah_grh_dgid, &remote_info.gid, sizeof(qp_attr_QP8_ah_grh_dgid));
    qp_attr_QP8_ah_grh.dgid = qp_attr_QP8_ah_grh_dgid;
    qp_attr_QP8_ah_grh.flow_label = 0;
    qp_attr_QP8_ah_grh.sgid_index = 1;
    qp_attr_QP8_ah_grh.hop_limit = 1;
    qp_attr_QP8_ah_grh.traffic_class = 0;
    qp_attr_QP8_ah.grh = qp_attr_QP8_ah_grh;
    qp_attr_QP8_ah.dlid = remote_info.lid;
    qp_attr_QP8_ah.sl = 0;
    qp_attr_QP8_ah.src_path_bits = 0;
    qp_attr_QP8_ah.is_global = 1;
    qp_attr_QP8_ah.port_num = 1;
    qp_attr_QP8.ah_attr = qp_attr_QP8_ah;
    qp_attr_QP8.max_dest_rd_atomic = 1;
    qp_attr_QP8.min_rnr_timer = 12;

    ibv_modify_qp(QP8, &qp_attr_QP8, IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER);
        
    memset(&qp_attr_QP8, 0, sizeof(qp_attr_QP8));
    
    memset(&qp_attr_QP8, 0, sizeof(qp_attr_QP8));
    qp_attr_QP8.qp_state = IBV_QPS_RTS;
    qp_attr_QP8.sq_psn = 0;
    qp_attr_QP8.max_rd_atomic = 1;
    qp_attr_QP8.timeout = 14;
    qp_attr_QP8.retry_cnt = 7;
    qp_attr_QP8.rnr_retry = 7;

    ibv_modify_qp(QP8, &qp_attr_QP8, IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC);
        
    /* ibv_post_send */
    
    memset(&wr_QP8, 0, sizeof(wr_QP8));
    wr_QP8.wr_id = 1;

    memset(&wr_QP8_sge_0, 0, sizeof(wr_QP8_sge_0));
    wr_QP8_sge_0.addr = (uintptr_t)bufs[8];
    wr_QP8_sge_0.length = MSG_SIZE;
    wr_QP8_sge_0.lkey = MR8->lkey;
    wr_QP8.sg_list = &wr_QP8_sge_0;
    wr_QP8.num_sge = 1;
    wr_QP8.opcode = IBV_WR_SEND;
    wr_QP8.send_flags = IBV_SEND_SIGNALED;

    
    if (ibv_post_send(QP8, &wr_QP8, &bad_wr_QP8) != 0) {
        fprintf(stderr, "Failed to post send work request\n");
        return -1;
    }
    
    /* Poll completion queue */

    /* poll the completion for a while before giving up of doing it .. */
    gettimeofday(&cur_time, NULL);
    start_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    do
    {
        poll_result = ibv_poll_cq(CQ8, 1, &wc);
        gettimeofday(&cur_time, NULL);
        cur_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    }
    while((poll_result == 0) && ((cur_time_msec - start_time_msec) < MAX_POLL_CQ_TIMEOUT));

    if(poll_result < 0)
    {
        /* poll CQ failed */
        fprintf(stderr, "poll CQ failed\n");
        rc = 1;
    }
    else if(poll_result == 0)
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
        if(wc.status != IBV_WC_SUCCESS)
        {
            fprintf(stderr, "got bad completion with status: 0x%x, vendor syndrome: 0x%x\n", 
                    wc.status, wc.vendor_err);
            rc = 1;
        }
    }

    /* ibv_alloc_pd */
    PD9 = ibv_alloc_pd(ctx);
    if (!PD9) {
        fprintf(stderr, "Failed to allocate protection domain\n");
        return -1;
    }

    /* ibv_create_cq */
    CQ9 = ibv_create_cq(ctx, 32, 
                              NULL, NULL, 
                              0);
    if (!CQ9) {
        fprintf(stderr, "Failed to create completion queue\n");
        return -1;
    }

    /* ibv_reg_mr */
    MR9 = ibv_reg_mr(PD9, bufs[9], 1024, IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE);
    if (!MR9) {
        fprintf(stderr, "Failed to register memory region\n");
        return -1;
    }

    /* ibv_create_qp */
    
    memset(&attr_init_QP9, 0, sizeof(attr_init_QP9));
    attr_init_QP9.send_cq = CQ9;
    attr_init_QP9.recv_cq = CQ9;

    memset(&attr_init_QP9_cap, 0, sizeof(attr_init_QP9_cap));
    attr_init_QP9_cap.max_send_wr = 1;
    attr_init_QP9_cap.max_recv_wr = 1;
    attr_init_QP9_cap.max_send_sge = 1;
    attr_init_QP9_cap.max_recv_sge = 1;
    attr_init_QP9.cap = attr_init_QP9_cap;
    attr_init_QP9.qp_type = IBV_QPT_RC;
    attr_init_QP9.sq_sig_all = 1;

    QP9 = ibv_create_qp(PD9, &attr_init_QP9);
    if (!QP9) {
        fprintf(stderr, "Failed to create QP\n");
        return -1;
    }

    /* Export connection data */
    req.local_qpn = QP9->qp_num;
    req.remote_qp_index = 9;
    send_pair_request_to_controller(req, sockfd);
    receive_metadata_from_controller(sockfd); // is that correct? 接收配对信息

    memset(&qp_attr_QP9, 0, sizeof(qp_attr_QP9));
    
    memset(&qp_attr_QP9, 0, sizeof(qp_attr_QP9));
    qp_attr_QP9.qp_state = IBV_QPS_INIT;
    qp_attr_QP9.qp_access_flags = IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE;
    qp_attr_QP9.pkey_index = 0;
    qp_attr_QP9.port_num = 1;

    ibv_modify_qp(QP9, &qp_attr_QP9, IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS);
        
    memset(&qp_attr_QP9, 0, sizeof(qp_attr_QP9));
    
    memset(&qp_attr_QP9, 0, sizeof(qp_attr_QP9));
    qp_attr_QP9.qp_state = IBV_QPS_RTR;
    qp_attr_QP9.path_mtu = IBV_MTU_1024;
    qp_attr_QP9.rq_psn = 0;
    qp_attr_QP9.dest_qp_num = local_remote_qp_map[QP9->qp_num];

    memset(&qp_attr_QP9_ah, 0, sizeof(qp_attr_QP9_ah));

    memset(&qp_attr_QP9_ah_grh, 0, sizeof(qp_attr_QP9_ah_grh));

    memset(&qp_attr_QP9_ah_grh_dgid, 0, sizeof(qp_attr_QP9_ah_grh_dgid));
    memcpy(&qp_attr_QP9_ah_grh_dgid, &remote_info.gid, sizeof(qp_attr_QP9_ah_grh_dgid));
    qp_attr_QP9_ah_grh.dgid = qp_attr_QP9_ah_grh_dgid;
    qp_attr_QP9_ah_grh.flow_label = 0;
    qp_attr_QP9_ah_grh.sgid_index = 1;
    qp_attr_QP9_ah_grh.hop_limit = 1;
    qp_attr_QP9_ah_grh.traffic_class = 0;
    qp_attr_QP9_ah.grh = qp_attr_QP9_ah_grh;
    qp_attr_QP9_ah.dlid = remote_info.lid;
    qp_attr_QP9_ah.sl = 0;
    qp_attr_QP9_ah.src_path_bits = 0;
    qp_attr_QP9_ah.is_global = 1;
    qp_attr_QP9_ah.port_num = 1;
    qp_attr_QP9.ah_attr = qp_attr_QP9_ah;
    qp_attr_QP9.max_dest_rd_atomic = 1;
    qp_attr_QP9.min_rnr_timer = 12;

    ibv_modify_qp(QP9, &qp_attr_QP9, IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER);
        
    memset(&qp_attr_QP9, 0, sizeof(qp_attr_QP9));
    
    memset(&qp_attr_QP9, 0, sizeof(qp_attr_QP9));
    qp_attr_QP9.qp_state = IBV_QPS_RTS;
    qp_attr_QP9.sq_psn = 0;
    qp_attr_QP9.max_rd_atomic = 1;
    qp_attr_QP9.timeout = 14;
    qp_attr_QP9.retry_cnt = 7;
    qp_attr_QP9.rnr_retry = 7;

    ibv_modify_qp(QP9, &qp_attr_QP9, IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC);
        
    /* ibv_post_send */
    
    memset(&wr_QP9, 0, sizeof(wr_QP9));
    wr_QP9.wr_id = 1;

    memset(&wr_QP9_sge_0, 0, sizeof(wr_QP9_sge_0));
    wr_QP9_sge_0.addr = (uintptr_t)bufs[9];
    wr_QP9_sge_0.length = MSG_SIZE;
    wr_QP9_sge_0.lkey = MR9->lkey;
    wr_QP9.sg_list = &wr_QP9_sge_0;
    wr_QP9.num_sge = 1;
    wr_QP9.opcode = IBV_WR_SEND;
    wr_QP9.send_flags = IBV_SEND_SIGNALED;

    
    if (ibv_post_send(QP9, &wr_QP9, &bad_wr_QP9) != 0) {
        fprintf(stderr, "Failed to post send work request\n");
        return -1;
    }
    
    /* Poll completion queue */

    /* poll the completion for a while before giving up of doing it .. */
    gettimeofday(&cur_time, NULL);
    start_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    do
    {
        poll_result = ibv_poll_cq(CQ9, 1, &wc);
        gettimeofday(&cur_time, NULL);
        cur_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    }
    while((poll_result == 0) && ((cur_time_msec - start_time_msec) < MAX_POLL_CQ_TIMEOUT));

    if(poll_result < 0)
    {
        /* poll CQ failed */
        fprintf(stderr, "poll CQ failed\n");
        rc = 1;
    }
    else if(poll_result == 0)
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
        if(wc.status != IBV_WC_SUCCESS)
        {
            fprintf(stderr, "got bad completion with status: 0x%x, vendor syndrome: 0x%x\n", 
                    wc.status, wc.vendor_err);
            rc = 1;
        }
    }

    /* ibv_destroy_qp */
    if (ibv_destroy_qp(QP0)) {
        fprintf(stderr, "Failed to destroy QP\n");
        return -1;
    }

    /* ibv_dereg_mr */
    if (ibv_dereg_mr(MR0)) {
        fprintf(stderr, "Failed to deregister MR\n");
        return -1;
    }

    /* ibv_destroy_cq */
    if (ibv_destroy_cq(CQ0)) {
        fprintf(stderr, "Failed to destroy CQ\n");
        return -1;
    }

    /* ibv_dealloc_pd */
    if (ibv_dealloc_pd(PD0)) {
        fprintf(stderr, "Failed to deallocate PD \n");
        return -1;
    }

    /* ibv_destroy_qp */
    if (ibv_destroy_qp(QP1)) {
        fprintf(stderr, "Failed to destroy QP\n");
        return -1;
    }

    /* ibv_dereg_mr */
    if (ibv_dereg_mr(MR1)) {
        fprintf(stderr, "Failed to deregister MR\n");
        return -1;
    }

    /* ibv_destroy_cq */
    if (ibv_destroy_cq(CQ1)) {
        fprintf(stderr, "Failed to destroy CQ\n");
        return -1;
    }

    /* ibv_dealloc_pd */
    if (ibv_dealloc_pd(PD1)) {
        fprintf(stderr, "Failed to deallocate PD \n");
        return -1;
    }

    /* ibv_destroy_qp */
    if (ibv_destroy_qp(QP2)) {
        fprintf(stderr, "Failed to destroy QP\n");
        return -1;
    }

    /* ibv_dereg_mr */
    if (ibv_dereg_mr(MR2)) {
        fprintf(stderr, "Failed to deregister MR\n");
        return -1;
    }

    /* ibv_destroy_cq */
    if (ibv_destroy_cq(CQ2)) {
        fprintf(stderr, "Failed to destroy CQ\n");
        return -1;
    }

    /* ibv_dealloc_pd */
    if (ibv_dealloc_pd(PD2)) {
        fprintf(stderr, "Failed to deallocate PD \n");
        return -1;
    }

    /* ibv_destroy_qp */
    if (ibv_destroy_qp(QP3)) {
        fprintf(stderr, "Failed to destroy QP\n");
        return -1;
    }

    /* ibv_dereg_mr */
    if (ibv_dereg_mr(MR3)) {
        fprintf(stderr, "Failed to deregister MR\n");
        return -1;
    }

    /* ibv_destroy_cq */
    if (ibv_destroy_cq(CQ3)) {
        fprintf(stderr, "Failed to destroy CQ\n");
        return -1;
    }

    /* ibv_dealloc_pd */
    if (ibv_dealloc_pd(PD3)) {
        fprintf(stderr, "Failed to deallocate PD \n");
        return -1;
    }

    /* ibv_destroy_qp */
    if (ibv_destroy_qp(QP4)) {
        fprintf(stderr, "Failed to destroy QP\n");
        return -1;
    }

    /* ibv_dereg_mr */
    if (ibv_dereg_mr(MR4)) {
        fprintf(stderr, "Failed to deregister MR\n");
        return -1;
    }

    /* ibv_destroy_cq */
    if (ibv_destroy_cq(CQ5)) {
        fprintf(stderr, "Failed to destroy CQ\n");
        return -1;
    }

    /* ibv_dealloc_pd */
    if (ibv_dealloc_pd(PD4)) {
        fprintf(stderr, "Failed to deallocate PD \n");
        return -1;
    }

    /* ibv_destroy_qp */
    if (ibv_destroy_qp(QP5)) {
        fprintf(stderr, "Failed to destroy QP\n");
        return -1;
    }

    /* ibv_dereg_mr */
    if (ibv_dereg_mr(MR5)) {
        fprintf(stderr, "Failed to deregister MR\n");
        return -1;
    }

    /* ibv_destroy_cq */
    if (ibv_destroy_cq(CQ5)) {
        fprintf(stderr, "Failed to destroy CQ\n");
        return -1;
    }

    /* ibv_dealloc_pd */
    if (ibv_dealloc_pd(PD5)) {
        fprintf(stderr, "Failed to deallocate PD \n");
        return -1;
    }

    /* ibv_destroy_qp */
    if (ibv_destroy_qp(QP6)) {
        fprintf(stderr, "Failed to destroy QP\n");
        return -1;
    }

    /* ibv_dereg_mr */
    if (ibv_dereg_mr(MR6)) {
        fprintf(stderr, "Failed to deregister MR\n");
        return -1;
    }

    /* ibv_destroy_cq */
    if (ibv_destroy_cq(CQ6)) {
        fprintf(stderr, "Failed to destroy CQ\n");
        return -1;
    }

    /* ibv_dealloc_pd */
    if (ibv_dealloc_pd(PD6)) {
        fprintf(stderr, "Failed to deallocate PD \n");
        return -1;
    }

    /* ibv_destroy_qp */
    if (ibv_destroy_qp(QP7)) {
        fprintf(stderr, "Failed to destroy QP\n");
        return -1;
    }

    /* ibv_dereg_mr */
    if (ibv_dereg_mr(MR7)) {
        fprintf(stderr, "Failed to deregister MR\n");
        return -1;
    }

    /* ibv_destroy_cq */
    if (ibv_destroy_cq(CQ7)) {
        fprintf(stderr, "Failed to destroy CQ\n");
        return -1;
    }

    /* ibv_dealloc_pd */
    if (ibv_dealloc_pd(PD7)) {
        fprintf(stderr, "Failed to deallocate PD \n");
        return -1;
    }

    /* ibv_destroy_qp */
    if (ibv_destroy_qp(QP8)) {
        fprintf(stderr, "Failed to destroy QP\n");
        return -1;
    }

    /* ibv_dereg_mr */
    if (ibv_dereg_mr(MR8)) {
        fprintf(stderr, "Failed to deregister MR\n");
        return -1;
    }

    /* ibv_destroy_cq */
    if (ibv_destroy_cq(CQ8)) {
        fprintf(stderr, "Failed to destroy CQ\n");
        return -1;
    }

    /* ibv_dealloc_pd */
    if (ibv_dealloc_pd(PD8)) {
        fprintf(stderr, "Failed to deallocate PD \n");
        return -1;
    }

    /* ibv_destroy_qp */
    if (ibv_destroy_qp(QP9)) {
        fprintf(stderr, "Failed to destroy QP\n");
        return -1;
    }

    /* ibv_dereg_mr */
    if (ibv_dereg_mr(MR9)) {
        fprintf(stderr, "Failed to deregister MR\n");
        return -1;
    }

    /* ibv_destroy_cq */
    if (ibv_destroy_cq(CQ9)) {
        fprintf(stderr, "Failed to destroy CQ\n");
        return -1;
    }

    /* ibv_dealloc_pd */
    if (ibv_dealloc_pd(PD9)) {
        fprintf(stderr, "Failed to deallocate PD \n");
        return -1;
    }

    /* ibv_close_device */
    if (ibv_close_device(ctx)) {
        fprintf(stderr, "Failed to close device\n");
        return -1;
    }

    // ---- BODY END ----

    return 0;
}