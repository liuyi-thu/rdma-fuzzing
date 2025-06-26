#include <infiniband/verbs.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define RECV_POOL_SIZE 16
#define MSG_SIZE 128

typedef struct {
    uint64_t wr_id;
    char *buf;
    struct ibv_mr *mr;
    int in_use;
} recv_slot_t;

typedef struct {
    recv_slot_t slots[RECV_POOL_SIZE];
    struct ibv_pd *pd;
} RecvBufferPool;

void init_recv_pool(RecvBufferPool *pool, struct ibv_pd *pd) {
    pool->pd = pd;
    for (int i = 0; i < RECV_POOL_SIZE; ++i) {
        pool->slots[i].buf = malloc(MSG_SIZE);
        pool->slots[i].mr = ibv_reg_mr(pd, pool->slots[i].buf, MSG_SIZE, IBV_ACCESS_LOCAL_WRITE);
        pool->slots[i].wr_id = (uint64_t)i;
        pool->slots[i].in_use = 0;
    }
}

void post_all_recvs(RecvBufferPool *pool, struct ibv_qp *qp) {
    for (int i = 0; i < RECV_POOL_SIZE; ++i) {
        struct ibv_sge sge = {
            .addr = (uintptr_t)pool->slots[i].buf,
            .length = MSG_SIZE,
            .lkey = pool->slots[i].mr->lkey
        };
        struct ibv_recv_wr wr = {
            .wr_id = pool->slots[i].wr_id,
            .sg_list = &sge,
            .num_sge = 1
        };
        struct ibv_recv_wr *bad_wr;
        if (ibv_post_recv(qp, &wr, &bad_wr) == 0)
            pool->slots[i].in_use = 1;
    }
}

char* get_buffer_by_wr_id(RecvBufferPool *pool, uint64_t wr_id) {
    if (wr_id >= RECV_POOL_SIZE) return NULL;
    return pool->slots[wr_id].in_use ? pool->slots[wr_id].buf : NULL;
}

void destroy_recv_pool(RecvBufferPool *pool) {
    for (int i = 0; i < RECV_POOL_SIZE; ++i) {
        ibv_dereg_mr(pool->slots[i].mr);
        free(pool->slots[i].buf);
    }
}

int main() {
    struct ibv_device **dev_list = ibv_get_device_list(NULL);
    struct ibv_context *ctx = ibv_open_device(dev_list[0]);
    struct ibv_pd *pd = ibv_alloc_pd(ctx);
    struct ibv_port_attr port_attr;
    ibv_query_port(ctx, 1, &port_attr);
    struct ibv_cq *cq = ibv_create_cq(ctx, 10, NULL, NULL, 0);

    struct ibv_qp_init_attr qp_attr = {
        .send_cq = cq,
        .recv_cq = cq,
        .qp_type = IBV_QPT_RC,
        .cap = {
            .max_send_wr = 10,
            .max_recv_wr = RECV_POOL_SIZE,
            .max_send_sge = 1,
            .max_recv_sge = 1
        }
    };

    struct ibv_qp *qp1 = ibv_create_qp(pd, &qp_attr);
    struct ibv_qp *qp2 = ibv_create_qp(pd, &qp_attr);

    RecvBufferPool pool;
    init_recv_pool(&pool, pd);
    post_all_recvs(&pool, qp2);

    // 修改 QP 状态略，假设连接已建立

    // 发送方准备 buffer
    char *send_buf = malloc(MSG_SIZE);
    strcpy(send_buf, "Hello, RDMA!");
    struct ibv_mr *send_mr = ibv_reg_mr(pd, send_buf, MSG_SIZE, IBV_ACCESS_LOCAL_WRITE);

    struct ibv_sge sge = {
        .addr = (uintptr_t)send_buf,
        .length = MSG_SIZE,
        .lkey = send_mr->lkey
    };
    struct ibv_send_wr wr = {
        .wr_id = 0x9999,
        .sg_list = &sge,
        .num_sge = 1,
        .opcode = IBV_WR_SEND,
        .send_flags = IBV_SEND_SIGNALED
    };
    struct ibv_send_wr *bad_wr;
    ibv_post_send(qp1, &wr, &bad_wr);

    // poll CQ
    struct ibv_wc wc;
    while (ibv_poll_cq(cq, 1, &wc) == 1) {
        if (wc.status != IBV_WC_SUCCESS) continue;
        if (wc.opcode == IBV_WC_RECV) {
            char *data = get_buffer_by_wr_id(&pool, wc.wr_id);
            printf("[QP %u] Received: %s\n", wc.qp_num, data);
            pool.slots[wc.wr_id].in_use = 0;  // 可重用
        }
    }

    destroy_recv_pool(&pool);
    ibv_dereg_mr(send_mr);
    free(send_buf);
    ibv_destroy_qp(qp1);
    ibv_destroy_qp(qp2);
    ibv_destroy_cq(cq);
    ibv_dealloc_pd(pd);
    ibv_close_device(ctx);
    ibv_free_device_list(dev_list);
    return 0;
}