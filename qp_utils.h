#ifndef QP_UTILS_H
#define QP_UTILS_H
#include <infiniband/verbs.h>
#include <stdio.h>
static int modify_qp_to_init(struct ibv_qp *qp);
static int modify_qp_to_rtr(struct ibv_qp *qp, uint32_t remote_qpn, uint16_t dlid, uint8_t *dgid);
static int modify_qp_to_rts(struct ibv_qp *qp);
#endif