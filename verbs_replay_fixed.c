#include <stdio.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdint.h>
#include <inttypes.h>
#include <endian.h>
#include <byteswap.h>
#include <getopt.h>
#include <sys/time.h>
#include <arpa/inet.h>
#include <infiniband/verbs.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netdb.h>


#define MAX_POLL_CQ_TIMEOUT 2000
#define MSG_S "SEND operation from server"
#define MSG_C "SEND operation from client"
#define RDMAMSGR "RDMA read operation "
#define RDMAMSGW "RDMA write operation"
#define MSG_SIZE 64
#if __BYTE_ORDER == __LITTLE_ENDIAN
static inline uint64_t htonll(uint64_t x)
{
    return bswap_64(x);
}
static inline uint64_t ntohll(uint64_t x)
{
    return bswap_64(x);
}
#elif __BYTE_ORDER == __BIG_ENDIAN
static inline uint64_t htonll(uint64_t x)
{
    return x;
}
static inline uint64_t ntohll(uint64_t x)
{
    return x;
}
#else
#error __BYTE_ORDER is neither __LITTLE_ENDIAN nor __BIG_ENDIAN
#endif

struct ibv_context *ctx;
struct ibv_pd *pd_table[10];
struct ibv_cq *cq_table[10];
struct ibv_qp *qp_table[10];
struct ibv_mr *mr_table[10];
struct ibv_device **dev_list;
struct ibv_device_attr dev_attr;
struct ibv_port_attr port_attr;
struct cm_con_data_t local_con_data;
struct cm_con_data_t remote_con_data;
struct cm_con_data_t tmp_con_data;
struct cm_con_data_t remote_props;
union ibv_gid my_gid;

int sock;
char temp_char;
char buf[4096];


struct cm_con_data_t
{
    uint64_t addr;        /* Buffer address */
    uint32_t rkey;        /* Remote key */
    uint32_t qp_num;      /* QP number */
    uint16_t lid;         /* LID of the IB port */
    uint8_t gid[16];      /* gid */
} __attribute__((packed));

static int sock_connect(const char *servername, int port)
{
    struct addrinfo *resolved_addr = NULL;
    struct addrinfo *iterator;
    char service[6];
    int sockfd = -1;
    int listenfd = 0;
    int tmp;
    struct addrinfo hints =
    {
        .ai_flags    = AI_PASSIVE,
        .ai_family   = AF_INET,
        .ai_socktype = SOCK_STREAM
    };

    if(sprintf(service, "%d", port) < 0)
    {
        goto sock_connect_exit;
    }

    /* Resolve DNS address, use sockfd as temp storage */
    sockfd = getaddrinfo(servername, service, &hints, &resolved_addr);
    if(sockfd < 0)
    {
        fprintf(stderr, "%s for %s:%d\n", gai_strerror(sockfd), servername, port);
        goto sock_connect_exit;
    }

    /* Search through results and find the one we want */
    for(iterator = resolved_addr; iterator ; iterator = iterator->ai_next)
    {
        sockfd = socket(iterator->ai_family, iterator->ai_socktype, iterator->ai_protocol);
        if(sockfd >= 0)
        {
            if(servername)
            {
                /* Client mode. Initiate connection to remote */
                if((tmp=connect(sockfd, iterator->ai_addr, iterator->ai_addrlen)))
                {
                    fprintf(stdout, "failed connect \n");
                    close(sockfd);
                    sockfd = -1;
                }
            }
            else
            {
                /* Server mode. Set up listening socket an accept a connection */
                listenfd = sockfd;
                sockfd = -1;
                if(bind(listenfd, iterator->ai_addr, iterator->ai_addrlen))
                {
                    goto sock_connect_exit;
                }
                listen(listenfd, 1);
                sockfd = accept(listenfd, NULL, 0);
            }
        }
    }

sock_connect_exit:
    if(listenfd)
    {
        close(listenfd);
    }

    if(resolved_addr)
    {
        freeaddrinfo(resolved_addr);
    }

    if(sockfd < 0)
    {
        if(servername)
        {
            fprintf(stderr, "Couldn't connect to %s:%d\n", servername, port);
        }
        else
        {
            perror("server accept");
            fprintf(stderr, "accept() failed\n");
        }
    }

    return sockfd;
}
int sock_sync_data(int sock, int xfer_size, char *local_data, char *remote_data)
{
    int rc;
    int read_bytes = 0;
    int total_read_bytes = 0;
    rc = write(sock, local_data, xfer_size);

    if(rc < xfer_size)
    {
        fprintf(stderr, "Failed writing data during sock_sync_data\n");
    }
    else
    {
        rc = 0;
    }

    while(!rc && total_read_bytes < xfer_size)
    {
        read_bytes = read(sock, remote_data, xfer_size);
        if(read_bytes > 0)
        {
            total_read_bytes += read_bytes;
        }
        else
        {
            rc = read_bytes;
        }
    }
    return rc;
}

int main() {

    /* Connect to server */
    sock = sock_connect("192.168.56.11", 19875);
    if (sock < 0) {
        fprintf(stderr, "Failed to connect to 192.168.56.11:19875\n");
        return -1;
    }

    /* ibv_get_device_list */
    dev_list = ibv_get_device_list(NULL);
    if (!dev_list) {
        fprintf(stderr, "Failed to get device list\n");
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

    /* ibv_alloc_pd */
    pd_table[0] = ibv_alloc_pd(ctx);
    if (!pd_table[0]) {
        fprintf(stderr, "Failed to allocate protection domain\n");
        return -1;
    }

    /* ibv_create_cq */
    cq_table[0] = ibv_create_cq(ctx, 32, NULL, NULL, 0);
    if (!cq_table[0]) {
        fprintf(stderr, "Failed to create completion queue\n");
        return -1;
    }

    /* ibv_reg_mr */
    mr_table[0] = ibv_reg_mr(pd_table[0], buf, 4096, IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE);

    /* ibv_create_qp */
    struct ibv_qp_init_attr attr_init_0 = {0};
    attr_init_0.qp_type = IBV_QPT_RC;
    attr_init_0.send_cq = cq_table[0];
    attr_init_0.recv_cq = cq_table[0];
    attr_init_0.cap.max_send_wr = 1;
    attr_init_0.cap.max_recv_wr = 1;
    attr_init_0.cap.max_send_sge = 1;
    attr_init_0.cap.max_recv_sge = 1;
    qp_table[0] = ibv_create_qp(pd_table[0], &attr_init_0);

    /* ibv_query_gid */
    if (ibv_query_gid(ctx, 1, 1, &my_gid)) {
        fprintf(stderr, "Failed to query GID\n");
        return -1;
    }

    local_con_data.addr = htonll((uintptr_t)buf);
    local_con_data.rkey = htonl(mr_table[0]->rkey);
    local_con_data.qp_num = htonl(qp_table[0]->qp_num);
    local_con_data.lid = htons(port_attr.lid);
    memcpy(local_con_data.gid, &my_gid, 16);
    if(sock_sync_data(sock, sizeof(struct cm_con_data_t), (char *) &local_con_data, (char *) &tmp_con_data) < 0)
    {
        fprintf(stderr, "failed to exchange connection data between sides\n");
        return 1;
    }

    remote_con_data.addr = ntohll(tmp_con_data.addr);
    remote_con_data.rkey = ntohl(tmp_con_data.rkey);
    remote_con_data.qp_num = ntohl(tmp_con_data.qp_num);
    remote_con_data.lid = ntohs(tmp_con_data.lid);
    memcpy(remote_con_data.gid, tmp_con_data.gid, 16);

    /* ibv_modify_qp */
    struct ibv_qp_attr attr_modify_init_0 = {0};
    attr_modify_init_0.qp_state = IBV_QPS_INIT;
    attr_modify_init_0.pkey_index = 0;
    attr_modify_init_0.port_num = 1;
    attr_modify_init_0.qp_access_flags = IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE;
    ibv_modify_qp(qp_table[0], &attr_modify_init_0, IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS);
    
    /* ibv_post_recv */
    struct ibv_recv_wr rr_0;
    struct ibv_sge sge_recv_0;
    struct ibv_recv_wr *bad_wr_recv_0;
    memset(&sge_recv_0, 0, sizeof(sge_recv_0));
    sge_recv_0.addr = (uintptr_t)buf; // HARD-WIRED
    sge_recv_0.length = MSG_SIZE;
    sge_recv_0.lkey = mr_table[0]->lkey; // HARD-WIRED

    /* prepare the receive work request */
    memset(&rr_0, 0, sizeof(rr_0));
    rr_0.next = NULL;
    rr_0.wr_id = 0;  // HARD-WIRED
    rr_0.sg_list = &sge_recv_0;
    rr_0.num_sge = 1;
    ibv_post_recv(qp_table[0], &rr_0, &bad_wr_recv_0);
    
    /* ibv_modify_qp to RTR */
    struct ibv_qp_attr attr_modify_rtr_0 = {0};
    attr_modify_rtr_0.qp_state = IBV_QPS_RTR;
    attr_modify_rtr_0.path_mtu = IBV_MTU_256; /* this field specifies the MTU from source code*/
    attr_modify_rtr_0.dest_qp_num = remote_con_data.qp_num;
    attr_modify_rtr_0.rq_psn = 0;
    attr_modify_rtr_0.max_dest_rd_atomic = 1;
    attr_modify_rtr_0.min_rnr_timer = 0x12;
    attr_modify_rtr_0.ah_attr.is_global = 0;
    attr_modify_rtr_0.ah_attr.dlid = remote_con_data.lid;
    attr_modify_rtr_0.ah_attr.sl = 0;
    attr_modify_rtr_0.ah_attr.src_path_bits = 0;
    attr_modify_rtr_0.ah_attr.port_num = 1;
    if(1 >= 0)
    {
        attr_modify_rtr_0.ah_attr.is_global = 1;
        attr_modify_rtr_0.ah_attr.port_num = 1;
        memcpy(&attr_modify_rtr_0.ah_attr.grh.dgid, remote_con_data.gid, 16);
        /* this field specify the UDP source port. if the target UDP source port is expected to be X, the value of flow_label = X ^ 0xC000 */
        attr_modify_rtr_0.ah_attr.grh.flow_label = 0;
        attr_modify_rtr_0.ah_attr.grh.hop_limit = 1;
        attr_modify_rtr_0.ah_attr.grh.sgid_index = 1;
        attr_modify_rtr_0.ah_attr.grh.traffic_class = 0;
    }
    ibv_modify_qp(qp_table[0], &attr_modify_rtr_0, IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER);

    /* ibv_modify_qp to RTS */
    struct ibv_qp_attr attr_modify_rts_0 = {0};
    attr_modify_rts_0.qp_state = IBV_QPS_RTS;
    attr_modify_rts_0.timeout = 0x12;
    attr_modify_rts_0.retry_cnt = 6;
    attr_modify_rts_0.rnr_retry = 0;
    attr_modify_rts_0.sq_psn = 0;
    attr_modify_rts_0.max_rd_atomic = 1;
    ibv_modify_qp(qp_table[0], &attr_modify_rts_0, IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC);

    /* Dummy sync, no actual data transfer */
    sock_sync_data(sock, 1, "{char}", &temp_char);

    /* ibv_post_send */
    struct ibv_send_wr sr_0;
    struct ibv_sge sge_send_0;
    struct ibv_send_wr *bad_wr_send_0 = NULL;

    memset(&sge_send_0, 0, sizeof(sge_send_0)); // nested variables
    sge_send_0.addr = (uintptr_t)buf; // HARD-WIRED
    sge_send_0.length = MSG_SIZE;
    sge_send_0.lkey = mr_table[0]->lkey; // HARD-WIRED

    /* prepare the send work request */
    memset(&sr_0, 0, sizeof(sr_0)); // nested variables
    sr_0.next = NULL;
    sr_0.wr_id = 1;  // HARD-WIRED
    sr_0.sg_list = &sge_send_0;
    sr_0.num_sge = 1;
    sr_0.opcode = IBV_WR_SEND;
    sr_0.send_flags = IBV_SEND_SIGNALED;

    /*
    if(IBV_WR_SEND != IBV_WR_SEND) // 暂不考虑READ和WRITE？
    {
        sr_0.wr.rdma.remote_addr = res->remote_props.addr; // HARD-WIRED
        sr_0.wr.rdma.rkey = res->remote_props.rkey; // HARD-WIRED
    }
    */

    /* there is a Receive Request in the responder side, so we won't get any into RNR flow */
    ibv_post_send(qp_table[0], &sr_0, &bad_wr_send_0);

    /* Poll completion queue */
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
        poll_result = ibv_poll_cq(cq_table[0], 1, &wc);
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

    /* Dummy sync, no actual data transfer */
    sock_sync_data(sock, 1, "{char}", &temp_char);

    /* ibv_destroy_qp */
    if (ibv_destroy_qp(qp_table[0])) {
        fprintf(stderr, "Failed to destroy QP\n");
        return -1;
    }

    /* ibv_dereg_mr */
    if (ibv_dereg_mr(mr_table[0])) {
        fprintf(stderr, "Failed to deregister MR\n");
        return -1;
    }

    /* ibv_destroy_cq */
    if (ibv_destroy_cq(cq_table[0])) {
        fprintf(stderr, "Failed to destroy CQ\n");
        return -1;
    }

    /* ibv_dealloc_pd */
    if (ibv_dealloc_pd(pd_table[0])) {
        fprintf(stderr, "Failed to deallocate PD\n");
        return -1;
    }

    /* ibv_close_device */
    if (ibv_close_device(ctx)) {
        fprintf(stderr, "Failed to close device\n");
        return -1;
    }

    /* Close socket */
    if (close(sock) < 0) {
        fprintf(stderr, "Failed to close socket\n");
        return -1;
    }

 return 0;
}
