// client_ctrl.h
#pragma once
#include <infiniband/verbs.h>
#include <cjson/cJSON.h>

struct qp_meta
{
    uint32_t qpn;
    uint32_t psn;
    uint16_t lid;
    uint8_t port_num;
    uint8_t gid[16];
    uint8_t gid_index;
};

// 原始的 QP 连接函数（不依赖 ResourceEnv）：
// ctx       : ibv_context（用来 query_gid）
// qp        : 已创建好的 QP（一般在 RESET/INIT）
// qp_tag    : 字符串标识（比如 "qp0"，和 server 那边 REQ_CONNECT/RESP_CONNECT 的 qp_tag 对应）
// server_host: 控制平面服务器 IP/hostname（比如 "127.0.0.1"）
// server_port: 控制平面端口（前面 server 写的是 18515）
// port_num  : RDMA 物理端口号
// gid_index : sgid_index
int connect_qp_raw(struct ibv_context *ctx,
                   struct ibv_qp *qp,
                   const char *qp_tag,
                   const char *server_host,
                   uint16_t server_port,
                   uint8_t port_num,
                   uint8_t gid_index);