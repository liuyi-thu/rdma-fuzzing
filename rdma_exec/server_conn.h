// server_conn.h
#pragma once

#include <stdint.h>
#include <infiniband/verbs.h>
#include <cjson/cJSON.h>

#include "resource_env.h" // 里面有 ResourceEnv / QpResource / MrResource 等

#ifdef __cplusplus
extern "C"
{
#endif

    // 和 rdma_server 端保持一致的 meta 结构
    struct qp_meta
    {
        uint32_t qpn;
        uint32_t psn;
        uint16_t lid;
        uint8_t port_num;
        uint8_t gid[16];
        uint8_t gid_index;
    };

    // 一条 client<->server 控制连接，对应一个 QP
    typedef struct ServerConn
    {
        int sockfd;
        char qp_name[64]; // 本地 QP 名（qp0 / qp1...）用于查表
        char qp_tag[64];  // 发送给 server 的 tag，一般和 qp_name 相同

        struct qp_meta local_meta;  // client 本地 QP 元数据
        struct qp_meta remote_meta; // server 返回的元数据

        int connected; // 是否已经完成 READY
    } ServerConn;

    /**
     * 初始化内部连接表（如果需要）。目前是静态数组，简单实现。
     * 你可以在 rdma_executor.c 里，在创建 ResourceEnv 后调用一次。
     */
    void server_conn_global_init(void);

    /**
     * 对给定 env + QP 名称，执行完整的 client 侧握手：
     *  - 从 env 中找到 QP 以及 RDMA ctx (需要你在实现中填充)
     *  - 构造 local_meta（qpn/psn/gid 等）
     *  - 和 server 交互：REQ_CONNECT / RESP_CONNECT / CLIENT_META / READY
     * 成功时在内部为该 QP 记录一个 ServerConn。
     *
     * 返回 0 表示成功，<0 表示失败。
     */
    int server_handshake_for_qp(ResourceEnv *env,
                                const char *qp_name,
                                const char *server_ip,
                                int server_port);

    /**
     * 在 ModifyQP 之前调用：
     *   - 根据 qp_name 找到对应的 ServerConn
     *   - 如果即将进入 RTR，则覆盖 qp_attr 中的 dest_qp_num / rq_psn / dgid 等
     *   - 如果即将进入 RTS，则覆盖 sq_psn
     *   - 同时把需要的 IBV_QP_* 位 OR 到 *attr_mask_io 中
     *
     * 参数：
     *   env        : ResourceEnv
     *   qp_name    : JSON 中的 "qp"
     *   qp_attr    : 你在 handle_ModifyQP 里构造好的 attr（会在本函数中被 override 一些字段）
     *   attr_mask_io: 你准备传给 ibv_modify_qp 的 attr_mask（会被 OR 一些位）
     *   new_state  : 目标状态（通常是 qp_attr.qp_state）
     *
     * 返回 0 表示已成功填充（或不需要填），<0 表示失败（比如找不到 ServerConn）
     */
    int server_fill_qp_attr_from_remote(ResourceEnv *env,
                                        const char *qp_name,
                                        struct ibv_qp_attr *qp_attr,
                                        int *attr_mask_io,
                                        enum ibv_qp_state new_state);

#ifdef __cplusplus
}
#endif
