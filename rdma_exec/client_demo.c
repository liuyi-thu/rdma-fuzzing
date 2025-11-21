// client_demo.c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <infiniband/verbs.h>

#include <cjson/cJSON.h>
#include "client_ctrl.h" // 上面实现的 connect_qp_raw

struct client_ctx
{
    struct ibv_context *ctx;
    struct ibv_pd *pd;
    struct ibv_cq *cq;
    uint8_t port_num;
    uint8_t gid_index;
};

static int client_rdma_init(struct client_ctx *c)
{
    int num;
    struct ibv_device **dev_list = ibv_get_device_list(&num);
    if (!dev_list || num == 0)
    {
        fprintf(stderr, "[CLIENT] no RDMA device\n");
        return -1;
    }

    c->ctx = ibv_open_device(dev_list[0]);
    if (!c->ctx)
    {
        fprintf(stderr, "[CLIENT] ibv_open_device failed\n");
        ibv_free_device_list(dev_list);
        return -1;
    }
    ibv_free_device_list(dev_list);

    c->pd = ibv_alloc_pd(c->ctx);
    if (!c->pd)
    {
        fprintf(stderr, "[CLIENT] ibv_alloc_pd failed\n");
        return -1;
    }

    c->cq = ibv_create_cq(c->ctx, 16, NULL, NULL, 0);
    if (!c->cq)
    {
        fprintf(stderr, "[CLIENT] ibv_create_cq failed\n");
        return -1;
    }

    c->port_num = 1;
    c->gid_index = 3;

    fprintf(stderr, "[CLIENT] RDMA init OK\n");
    return 0;
}

static struct ibv_qp *client_create_qp(struct client_ctx *c)
{
    struct ibv_qp_init_attr init_attr = {
        .send_cq = c->cq,
        .recv_cq = c->cq,
        .cap = {
            .max_send_wr = 16,
            .max_recv_wr = 16,
            .max_send_sge = 4,
            .max_recv_sge = 4,
        },
        .qp_type = IBV_QPT_RC,
        .sq_sig_all = 0,
    };

    struct ibv_qp *qp = ibv_create_qp(c->pd, &init_attr);
    if (!qp)
    {
        fprintf(stderr, "[CLIENT] ibv_create_qp failed\n");
        return NULL;
    }

    fprintf(stderr, "[CLIENT] QP created, qpn=%u\n", qp->qp_num);
    return qp;
}

int main(int argc, char **argv)
{
    const char *server_host = "127.0.0.1";
    uint16_t server_port = 18515;

    if (argc >= 2)
        server_host = argv[1];
    if (argc >= 3)
        server_port = (uint16_t)atoi(argv[2]);

    srand((unsigned)time(NULL));

    struct client_ctx c;
    memset(&c, 0, sizeof(c));
    if (client_rdma_init(&c) != 0)
    {
        return 1;
    }

    struct ibv_qp *qp = client_create_qp(&c);
    if (!qp)
        return 1;

    // ==== 控制平面连接（和之前写的 server） ====
    if (connect_qp_raw(c.ctx, qp, "qp0",
                       server_host, server_port,
                       c.port_num, c.gid_index) != 0)
    {
        fprintf(stderr, "[CLIENT] connect_qp_raw failed\n");
        return 1;
    }

    // ==== 注册一块 MR，准备发送 ====
    char *buf = NULL;
    if (posix_memalign((void **)&buf, sysconf(_SC_PAGESIZE), 4096) != 0)
    {
        fprintf(stderr, "[CLIENT] alloc buf failed\n");
        return 1;
    }
    strcpy(buf, "Hello RDMA Server!");

    struct ibv_mr *mr = ibv_reg_mr(c.pd, buf, 4096,
                                   IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_WRITE);
    if (!mr)
    {
        fprintf(stderr, "[CLIENT] ibv_reg_mr failed\n");
        return 1;
    }

    struct ibv_sge sge = {
        .addr = (uintptr_t)buf,
        .length = (uint32_t)strlen(buf) + 1,
        .lkey = mr->lkey,
    };

    struct ibv_send_wr wr;
    memset(&wr, 0, sizeof(wr));
    wr.wr_id = 1;
    wr.sg_list = &sge;
    wr.num_sge = 1;
    wr.opcode = IBV_WR_SEND;
    wr.send_flags = IBV_SEND_SIGNALED;

    struct ibv_send_wr *bad_wr = NULL;
    int ret = ibv_post_send(qp, &wr, &bad_wr);
    if (ret)
    {
        fprintf(stderr, "[CLIENT] ibv_post_send failed, ret=%d\n", ret);
        return 1;
    }
    fprintf(stderr, "[CLIENT] ibv_post_send submitted\n");

    // ==== 等待 send completion ====
    struct ibv_wc wc;
    int ne;
    do
    {
        ne = ibv_poll_cq(c.cq, 1, &wc);
    } while (ne == 0);

    if (ne < 0)
    {
        fprintf(stderr, "[CLIENT] ibv_poll_cq error\n");
        return 1;
    }

    if (wc.status != IBV_WC_SUCCESS)
    {
        fprintf(stderr, "[CLIENT] completion with error, status=%d, opcode=%d\n",
                wc.status, wc.opcode);
        return 1;
    }

    fprintf(stderr, "[CLIENT] send completed: wr_id=%llu, opcode=%d, byte_len=%u\n",
            (unsigned long long)wc.wr_id, wc.opcode, wc.byte_len);

    // 资源释放省略，你后面可以按需要补 Dealloc

    return 0;
}