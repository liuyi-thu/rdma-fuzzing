#include "verb_qp.h"
#include "json_utils.h"

#include <stdio.h>
#include <infiniband/verbs.h>

static const JsonEnumSpec qp_type_table[] = {
    {"IBV_QPT_RC", IBV_QPT_RC},
    {"IBV_QPT_UC", IBV_QPT_UC},
    {"IBV_QPT_UD", IBV_QPT_UD},
    {"IBV_QPT_RAW_PACKET", IBV_QPT_RAW_PACKET},
#ifdef IBV_QPT_XRC_SEND
    {"IBV_QPT_XRC_SEND", IBV_QPT_XRC_SEND},
#endif
#ifdef IBV_QPT_XRC_RECV
    {"IBV_QPT_XRC_RECV", IBV_QPT_XRC_RECV},
#endif
#ifdef IBV_QPT_DRIVER
    {"IBV_QPT_DRIVER", IBV_QPT_DRIVER},
#endif
};

static const JsonFlagSpec qp_init_attr_mask_table[] = {
    {"IBV_QP_INIT_ATTR_PD", IBV_QP_INIT_ATTR_PD},
    {"IBV_QP_INIT_ATTR_XRCD", IBV_QP_INIT_ATTR_XRCD},
    {"IBV_QP_INIT_ATTR_CREATE_FLAGS", IBV_QP_INIT_ATTR_CREATE_FLAGS},
    {"IBV_QP_INIT_ATTR_MAX_TSO_HEADER", IBV_QP_INIT_ATTR_MAX_TSO_HEADER},
    {"IBV_QP_INIT_ATTR_IND_TABLE", IBV_QP_INIT_ATTR_IND_TABLE},
    {"IBV_QP_INIT_ATTR_RX_HASH", IBV_QP_INIT_ATTR_RX_HASH},
    {"IBV_QP_INIT_ATTR_SEND_OPS_FLAGS", IBV_QP_INIT_ATTR_SEND_OPS_FLAGS},
};

static const JsonFlagSpec qp_create_flags_table[] = {
    {"IBV_QP_CREATE_BLOCK_SELF_MCAST_LB", IBV_QP_CREATE_BLOCK_SELF_MCAST_LB},
    {"IBV_QP_CREATE_SCATTER_FCS", IBV_QP_CREATE_SCATTER_FCS},
    {"IBV_QP_CREATE_CVLAN_STRIPPING", IBV_QP_CREATE_CVLAN_STRIPPING},
    {"IBV_QP_CREATE_SOURCE_QPN", IBV_QP_CREATE_SOURCE_QPN},
    {"IBV_QP_CREATE_PCI_WRITE_END_PADDING", IBV_QP_CREATE_PCI_WRITE_END_PADDING},
};

static const JsonFlagSpec qp_create_send_ops_flags_table[] = {
    {"IBV_QP_EX_WITH_RDMA_WRITE", IBV_QP_EX_WITH_RDMA_WRITE},
    {"IBV_QP_EX_WITH_RDMA_WRITE_WITH_IMM", IBV_QP_EX_WITH_RDMA_WRITE_WITH_IMM},
    {"IBV_QP_EX_WITH_SEND", IBV_QP_EX_WITH_SEND},
    {"IBV_QP_EX_WITH_SEND_WITH_IMM", IBV_QP_EX_WITH_SEND_WITH_IMM},
    {"IBV_QP_EX_WITH_RDMA_READ", IBV_QP_EX_WITH_RDMA_READ},
    {"IBV_QP_EX_WITH_ATOMIC_CMP_AND_SWP", IBV_QP_EX_WITH_ATOMIC_CMP_AND_SWP},
    {"IBV_QP_EX_WITH_ATOMIC_FETCH_AND_ADD", IBV_QP_EX_WITH_ATOMIC_FETCH_AND_ADD},
    {"IBV_QP_EX_WITH_LOCAL_INV", IBV_QP_EX_WITH_LOCAL_INV},
    {"IBV_QP_EX_WITH_BIND_MW", IBV_QP_EX_WITH_BIND_MW},
    {"IBV_QP_EX_WITH_SEND_WITH_INV", IBV_QP_EX_WITH_SEND_WITH_INV},
    {"IBV_QP_EX_WITH_TSO", IBV_QP_EX_WITH_TSO},
    {"IBV_QP_EX_WITH_FLUSH", IBV_QP_EX_WITH_FLUSH},
    {"IBV_QP_EX_WITH_ATOMIC_WRITE", IBV_QP_EX_WITH_ATOMIC_WRITE}};

static const JsonFlagSpec rx_hash_fields_table[] = {
    {"IBV_RX_HASH_SRC_IPV4", IBV_RX_HASH_SRC_IPV4},
    {"IBV_RX_HASH_DST_IPV4", IBV_RX_HASH_DST_IPV4},
    {"IBV_RX_HASH_SRC_IPV6", IBV_RX_HASH_SRC_IPV6},
    {"IBV_RX_HASH_DST_IPV6", IBV_RX_HASH_DST_IPV6},
    {"IBV_RX_HASH_SRC_PORT_TCP", IBV_RX_HASH_SRC_PORT_TCP},
    {"IBV_RX_HASH_DST_PORT_TCP", IBV_RX_HASH_DST_PORT_TCP},
    {"IBV_RX_HASH_SRC_PORT_UDP", IBV_RX_HASH_SRC_PORT_UDP},
    {"IBV_RX_HASH_DST_PORT_UDP", IBV_RX_HASH_DST_PORT_UDP},
    {"IBV_RX_HASH_IPSEC_SPI", IBV_RX_HASH_IPSEC_SPI},
    {"IBV_RX_HASH_INNER", IBV_RX_HASH_INNER}};

static const JsonEnumSpec qp_state_table[] = {
    {"IBV_QPS_RESET", IBV_QPS_RESET},
    {"IBV_QPS_INIT", IBV_QPS_INIT},
    {"IBV_QPS_RTR", IBV_QPS_RTR},
    {"IBV_QPS_RTS", IBV_QPS_RTS},
    {"IBV_QPS_SQD", IBV_QPS_SQD},
    {"IBV_QPS_SQE", IBV_QPS_SQE},
    {"IBV_QPS_ERR", IBV_QPS_ERR},
    {"IBV_QPS_UNKNOWN", IBV_QPS_UNKNOWN},
};

static const JsonEnumSpec mig_state_table[] = {
    {"IBV_MIG_MIGRATED", IBV_MIG_MIGRATED},
    {"IBV_MIG_REARM", IBV_MIG_REARM},
    {"IBV_MIG_ARMED", IBV_MIG_ARMED},
};

static const JsonEnumSpec mtu_table[] = {
    {"IBV_MTU_256", IBV_MTU_256},
    {"IBV_MTU_512", IBV_MTU_512},
    {"IBV_MTU_1024", IBV_MTU_1024},
    {"IBV_MTU_2048", IBV_MTU_2048},
    {"IBV_MTU_4096", IBV_MTU_4096},
};

static const JsonFlagSpec access_flags_table[] = {
    {"IBV_ACCESS_LOCAL_WRITE", IBV_ACCESS_LOCAL_WRITE},
    {"IBV_ACCESS_REMOTE_WRITE", IBV_ACCESS_REMOTE_WRITE},
    {"IBV_ACCESS_REMOTE_READ", IBV_ACCESS_REMOTE_READ},
    {"IBV_ACCESS_REMOTE_ATOMIC", IBV_ACCESS_REMOTE_ATOMIC},
    {"IBV_ACCESS_MW_BIND", IBV_ACCESS_MW_BIND},
    {"IBV_ACCESS_ZERO_BASED", IBV_ACCESS_ZERO_BASED},
    {"IBV_ACCESS_ON_DEMAND", IBV_ACCESS_ON_DEMAND},
    {"IBV_ACCESS_HUGETLB", IBV_ACCESS_HUGETLB},
    {"IBV_ACCESS_FLUSH_GLOBAL", IBV_ACCESS_FLUSH_GLOBAL},
    {"IBV_ACCESS_FLUSH_PERSISTENT", IBV_ACCESS_FLUSH_PERSISTENT},
    {"IBV_ACCESS_RELAXED_ORDERING", IBV_ACCESS_RELAXED_ORDERING}};

static const JsonFlagSpec qp_attr_mask_table[] = {
    {"IBV_QP_STATE", IBV_QP_STATE},
    {"IBV_QP_CUR_STATE", IBV_QP_CUR_STATE},
    {"IBV_QP_EN_SQD_ASYNC_NOTIFY", IBV_QP_EN_SQD_ASYNC_NOTIFY},
    {"IBV_QP_ACCESS_FLAGS", IBV_QP_ACCESS_FLAGS},
    {"IBV_QP_PKEY_INDEX", IBV_QP_PKEY_INDEX},
    {"IBV_QP_PORT", IBV_QP_PORT},
    {"IBV_QP_QKEY", IBV_QP_QKEY},
    {"IBV_QP_AV", IBV_QP_AV},
    {"IBV_QP_PATH_MTU", IBV_QP_PATH_MTU},
    {"IBV_QP_TIMEOUT", IBV_QP_TIMEOUT},
    {"IBV_QP_RETRY_CNT", IBV_QP_RETRY_CNT},
    {"IBV_QP_RNR_RETRY", IBV_QP_RNR_RETRY},
    {"IBV_QP_RQ_PSN", IBV_QP_RQ_PSN},
    {"IBV_QP_MAX_QP_RD_ATOMIC", IBV_QP_MAX_QP_RD_ATOMIC},
    {"IBV_QP_ALT_PATH", IBV_QP_ALT_PATH},
    {"IBV_QP_MIN_RNR_TIMER", IBV_QP_MIN_RNR_TIMER},
    {"IBV_QP_SQ_PSN", IBV_QP_SQ_PSN},
    {"IBV_QP_MAX_DEST_RD_ATOMIC", IBV_QP_MAX_DEST_RD_ATOMIC},
    {"IBV_QP_PATH_MIG_STATE", IBV_QP_PATH_MIG_STATE},
    {"IBV_QP_CAP", IBV_QP_CAP},
    {"IBV_QP_DEST_QPN", IBV_QP_DEST_QPN},
    {"IBV_QP_RATE_LIMIT", IBV_QP_RATE_LIMIT},
};

int handle_CreateQP(cJSON *verb_obj, ResourceEnv *env)
{
    const char *pd_name = json_get_res_name(verb_obj, "pd");
    const char *qp_name = json_get_res_name(verb_obj, "qp");
    if (!pd_name || !qp_name)
    {
        fprintf(stderr, "[EXEC] CreateQP: missing pd or qp name\n");
        return -1;
    }

    cJSON *attr_obj = obj_get(verb_obj, "init_attr_obj");
    if (!attr_obj)
    {
        fprintf(stderr, "[EXEC] CreateQP: missing init_attr_obj\n");
        return -1;
    }
    const char *qp_context_str = json_get_res_name(attr_obj, "qp_context");
    void *qp_context = NULL;
    const char *send_cq_name = json_get_res_name(attr_obj, "send_cq");
    const char *recv_cq_name = json_get_res_name(attr_obj, "recv_cq");
    const char *srq_name = json_get_res_name(attr_obj, "srq");
    cJSON *cap_obj = obj_get(attr_obj, "cap");
    int cap_max_send_wr = json_get_int_field(cap_obj, "max_send_wr", 0);
    int cap_max_recv_wr = json_get_int_field(cap_obj, "max_recv_wr", 0);
    int cap_max_send_sge = json_get_int_field(cap_obj, "max_send_sge", 0);
    int cap_max_recv_sge = json_get_int_field(cap_obj, "max_recv_sge", 0);
    int cap_max_inline_data = json_get_int_field(cap_obj, "max_inline_data", 0);
    int qp_type = json_get_enum_field(attr_obj,
                                      "qp_type",
                                      qp_type_table,
                                      sizeof(qp_type_table) / sizeof(qp_type_table[0]),
                                      IBV_QPT_RC);
    int sq_sig_all = json_get_int_field(attr_obj, "sq_sig_all", 0);
    env_create_qp(env,
                  qp_name,
                  pd_name,
                  send_cq_name,
                  recv_cq_name,
                  srq_name,
                  qp_context,
                  cap_max_send_wr,
                  cap_max_recv_wr,
                  cap_max_send_sge,
                  cap_max_recv_sge,
                  cap_max_inline_data,
                  qp_type,
                  sq_sig_all);
    // TODO: remote_qp
    // fprintf(stderr, "[EXEC] CreateQP: not implemented yet\n");
    return 0;
}

int handle_CreateQPEx(cJSON *verb_obj, ResourceEnv *env)
{
    const char *qp_name = json_get_res_name(verb_obj, "qp");
    if (!qp_name)
    {
        fprintf(stderr, "[EXEC] CreateQPEx: missing qp name\n");
        return -1;
    }
    cJSON *attr_obj = obj_get(verb_obj, "qp_attr_obj");
    if (!attr_obj)
    {
        fprintf(stderr, "[EXEC] CreateQPEx: missing qp_attr_obj\n");
        return -1;
    }
    // 解析属性并创建 QP
    const char *qp_context_str = json_get_res_name(attr_obj, "qp_context");
    void *qp_context = NULL;
    // 这里可以继续解析其他属性字段
    const char *send_cq_name = json_get_res_name(attr_obj, "send_cq");
    const char *recv_cq_name = json_get_res_name(attr_obj, "recv_cq");
    const char *srq_name = json_get_res_name(attr_obj, "srq");
    cJSON *cap_obj = obj_get(attr_obj, "cap");
    int cap_max_send_wr = json_get_int_field(cap_obj, "max_send_wr", 0);
    int cap_max_recv_wr = json_get_int_field(cap_obj, "max_recv_wr", 0);
    int cap_max_send_sge = json_get_int_field(cap_obj, "max_send_sge", 0);
    int cap_max_recv_sge = json_get_int_field(cap_obj, "max_recv_sge", 0);
    int cap_max_inline_data = json_get_int_field(cap_obj, "max_inline_data", 0);
    int qp_type = json_get_enum_field(attr_obj,
                                      "qp_type",
                                      qp_type_table,
                                      sizeof(qp_type_table) / sizeof(qp_type_table[0]),
                                      IBV_QPT_RC);
    int sq_sig_all = json_get_int_field(attr_obj, "sq_sig_all", 0);
    int comp_mask = json_get_flag_field(
        attr_obj,
        "comp_mask",
        qp_init_attr_mask_table,
        sizeof(qp_init_attr_mask_table) / sizeof(qp_init_attr_mask_table[0]),
        0);
    const char *pd_name = json_get_res_name(attr_obj, "pd");
    const char *xrcd_name = json_get_res_name(attr_obj, "xrcd");
    int create_flags = json_get_flag_field(
        attr_obj,
        "create_flags",
        qp_create_flags_table,
        sizeof(qp_create_flags_table) / sizeof(qp_create_flags_table[0]),
        0);
    int max_tso_header = json_get_int_field(attr_obj, "max_tso_header", 0);
    const char *rwq_ind_tbl_name = json_get_res_name(attr_obj, "ind_table");
    void *rwq_ind_tbl = NULL;

    cJSON *rx_hash_conf = obj_get(attr_obj, "rx_hash_conf");
    int rx_hash_fields = json_get_int_field(rx_hash_conf, "rx_hash_fields", 0);
    //
    int rx_hash_function = json_get_int_field(rx_hash_conf, "rx_hash_function", 0);
    int rx_hash_key_len = json_get_int_field(rx_hash_conf, "rx_hash_key_len", 0);
    const char *rx_hash_key_str = json_get_res_name(rx_hash_conf, "rx_hash_key");
    uint8_t *rx_hash_key = NULL;
    // TODO: implement rx_hash_key allocation and initialization
    // if (rx_hash_key_len > 0)
    // {
    //     rx_hash_key = (uint8_t *)malloc(rx_hash_key_len);
    //     // Initialize rx_hash_key from rx_hash_key_str if needed
    // }
    int rx_hash_fields_mask = json_get_flag_field(
        rx_hash_conf,
        "rx_hash_fields_mask",
        rx_hash_fields_table,
        sizeof(rx_hash_fields_table) / sizeof(rx_hash_fields_table[0]),
        0);

    int source_qpn = json_get_int_field(attr_obj, "source_qpn", 0);
    int send_ops_flags = json_get_flag_field(
        attr_obj,
        "send_ops_flags",
        qp_create_send_ops_flags_table,
        sizeof(qp_create_send_ops_flags_table) / sizeof(qp_create_send_ops_flags_table[0]),
        0);
    env_create_qp_ex(env,
                     qp_name,
                     pd_name,
                     xrcd_name,
                     qp_context,
                     send_cq_name,
                     recv_cq_name,
                     srq_name,
                     cap_max_send_wr,
                     cap_max_recv_wr,
                     cap_max_send_sge,
                     cap_max_recv_sge,
                     cap_max_inline_data,
                     qp_type,
                     sq_sig_all,
                     comp_mask,
                     create_flags,
                     max_tso_header,
                     rwq_ind_tbl,
                     rx_hash_function,
                     rx_hash_key_len,
                     rx_hash_key,
                     rx_hash_fields_mask,
                     source_qpn,
                     send_ops_flags);
    return 0;
}

int handle_ModifyQP(cJSON *verb_obj, ResourceEnv *env)
// the parameter may be nested json object, so I would like to extract it into structs and pass them to env
{
    const char *name = json_get_res_name(verb_obj, "qp");
    if (!name)
    {
        fprintf(stderr, "[EXEC] ModifyQP: missing 'qp' field\n");
        return -1;
    }
    cJSON *attr_obj = obj_get(verb_obj, "attr_obj");
    if (!attr_obj)
    {
        fprintf(stderr, "[EXEC] ModifyQP: missing 'attr_obj'\n");
        return -1;
    }
    // TODO: parse attr_obj, extract it into structs and call env_modify_qp
    int qp_state = json_get_enum_field(attr_obj,
                                       "qp_state",
                                       qp_state_table,
                                       sizeof(qp_state_table) / sizeof(qp_state_table[0]),
                                       IBV_QPS_RESET);
    int cur_qp_state = json_get_enum_field(attr_obj,
                                           "cur_qp_state",
                                           qp_state_table,
                                           sizeof(qp_state_table) / sizeof(qp_state_table[0]),
                                           IBV_QPS_RESET);
    // Other fields can be parsed similarly
    int path_mtu = json_get_enum_field(attr_obj,
                                       "path_mtu",
                                       mtu_table,
                                       sizeof(mtu_table) / sizeof(mtu_table[0]),
                                       IBV_MTU_256);
    int path_mig_state = json_get_enum_field(attr_obj,
                                             "path_mig_state",
                                             mig_state_table,
                                             sizeof(mig_state_table) / sizeof(mig_state_table[0]),
                                             IBV_MIG_ARMED);
    int qkey = json_get_int_field(attr_obj, "qkey", 0);
    int rq_psn = json_get_int_field(attr_obj, "rq_psn", 0);
    int sq_psn = json_get_int_field(attr_obj, "sq_psn", 0);
    int dest_qp_num = json_get_int_field(attr_obj, "dest_qp_num", 0);
    int qp_access_flags = json_get_flag_field(
        attr_obj,
        "qp_access_flags",
        access_flags_table,
        sizeof(access_flags_table) / sizeof(access_flags_table[0]),
        0);

    cJSON *cap_obj = obj_get(attr_obj, "cap");
    int cap_max_send_wr = json_get_int_field(cap_obj, "max_send_wr", 0);
    int cap_max_recv_wr = json_get_int_field(cap_obj, "max_recv_wr", 0);
    int cap_max_send_sge = json_get_int_field(cap_obj, "max_send_sge", 0);
    int cap_max_recv_sge = json_get_int_field(cap_obj, "max_recv_sge", 0);
    int cap_max_inline_data = json_get_int_field(cap_obj, "max_inline_data", 0);
    // ... parse other fields as needed

    // TODO: parse ah_attr and alt_ah_attr if present
    cJSON *ah_attr_obj = obj_get(attr_obj, "ah_attr");
    // parse ah_attr_obj fields...
    cJSON *ah_attr_grh = obj_get(ah_attr_obj, "grh");
    // parse grh fields...
    // TODO: dgid is a DeferredValue, so we skip it for now; How to parse DeferredValue?
    uint8_t ah_attr_grh_dgid[16];
    memset(ah_attr_grh_dgid, 0, sizeof(ah_attr_grh_dgid));
    int ah_attr_grh_flow_label = json_get_int_field(ah_attr_grh, "flow_label", 0);
    int ah_attr_grh_sgid_index = json_get_int_field(ah_attr_grh, "sgid_index", 0);
    int ah_attr_grh_hop_limit = json_get_int_field(ah_attr_grh, "hop_limit", 0);
    int ah_attr_grh_traffic_class = json_get_int_field(ah_attr_grh, "traffic_class", 0);
    //
    int ah_attr_dlid = json_get_int_field(ah_attr_obj, "dlid", 0);
    int ah_attr_sl = json_get_int_field(ah_attr_obj, "sl", 0);
    int ah_attr_src_path_bits = json_get_int_field(ah_attr_obj, "src_path_bits", 0);
    int ah_attr_static_rate = json_get_int_field(ah_attr_obj, "static_rate", 0);
    int ah_attr_is_global = json_get_int_field(ah_attr_obj, "is_global", 0);
    int ah_attr_port_num = json_get_int_field(ah_attr_obj, "port_num", 0);

    cJSON *alt_ah_attr_obj = obj_get(attr_obj, "alt_ah_attr");
    // parse alt_ah_attr_obj fields...
    cJSON *alt_ah_attr_grh = obj_get(alt_ah_attr_obj, "grh");
    // parse grh fields...
    uint8_t alt_ah_attr_grh_dgid[16];
    memset(alt_ah_attr_grh_dgid, 0, sizeof(alt_ah_attr_grh_dgid));
    int alt_ah_attr_grh_flow_label = json_get_int_field(alt_ah_attr_grh, "flow_label", 0);
    int alt_ah_attr_grh_sgid_index = json_get_int_field(alt_ah_attr_grh, "sgid_index", 0);
    int alt_ah_attr_grh_hop_limit = json_get_int_field(alt_ah_attr_grh, "hop_limit", 0);
    int alt_ah_attr_grh_traffic_class = json_get_int_field(alt_ah_attr_grh, "traffic_class", 0);
    //
    int alt_ah_attr_dlid = json_get_int_field(alt_ah_attr_obj, "dlid", 0);
    int alt_ah_attr_sl = json_get_int_field(alt_ah_attr_obj, "sl", 0);
    int alt_ah_attr_src_path_bits = json_get_int_field(alt_ah_attr_obj, "src_path_bits", 0);
    int alt_ah_attr_static_rate = json_get_int_field(alt_ah_attr_obj, "static_rate", 0);
    int alt_ah_attr_is_global = json_get_int_field(alt_ah_attr_obj, "is_global", 0);
    int alt_ah_attr_port_num = json_get_int_field(alt_ah_attr_obj, "port_num", 0);

    int pkey_index = json_get_int_field(attr_obj, "pkey_index", 0);
    int alt_pkey_index = json_get_int_field(attr_obj, "alt_pkey_index", 0);
    int en_sqd_async_notify = json_get_int_field(attr_obj, "en_sqd_async_notify", 0);
    int sq_draining = json_get_int_field(attr_obj, "sq_draining", 0);
    int max_rd_atomic = json_get_int_field(attr_obj, "max_rd_atomic", 0);
    int max_dest_rd_atomic = json_get_int_field(attr_obj, "max_dest_rd_atomic", 0);
    int min_rnr_timer = json_get_int_field(attr_obj, "min_rnr_timer", 0);
    int port_num = json_get_int_field(attr_obj, "port_num", 0);
    int timeout = json_get_int_field(attr_obj, "timeout", 0);
    int retry_cnt = json_get_int_field(attr_obj, "retry_cnt", 0);
    int rnr_retry = json_get_int_field(attr_obj, "rnr_retry", 0);
    int alt_port_num = json_get_int_field(attr_obj, "alt_port_num", 0);
    int alt_timeout = json_get_int_field(attr_obj, "alt_timeout", 0);
    int rate_limit = json_get_int_field(attr_obj, "rate_limit", 0);

    int attr_mask = json_get_flag_field(
        verb_obj,
        "attr_mask",
        qp_attr_mask_table,
        sizeof(qp_attr_mask_table) / sizeof(qp_attr_mask_table[0]),
        0);
    // Now, we should write parsed parameters into a struct and pass to env_modify_qp

    struct ibv_qp_attr qp_attr;
    struct ibv_qp_init_attr init_attr;
    // Fill qp_attr and init_attr with parsed values
    memset(&qp_attr, 0, sizeof(qp_attr));
    qp_attr.qp_state = qp_state;
    qp_attr.cur_qp_state = cur_qp_state;
    qp_attr.path_mtu = path_mtu;
    qp_attr.path_mig_state = path_mig_state;
    qp_attr.qkey = qkey;
    qp_attr.rq_psn = rq_psn;
    qp_attr.sq_psn = sq_psn;
    qp_attr.dest_qp_num = dest_qp_num;
    qp_attr.qp_access_flags = qp_access_flags;
    qp_attr.cap.max_send_wr = cap_max_send_wr;
    qp_attr.cap.max_recv_wr = cap_max_recv_wr;
    qp_attr.cap.max_send_sge = cap_max_send_sge;
    qp_attr.cap.max_recv_sge = cap_max_recv_sge;
    qp_attr.cap.max_inline_data = cap_max_inline_data;
    // ... fill other fields similarly
    memcpy(qp_attr.ah_attr.grh.dgid.raw, ah_attr_grh_dgid, 16);
    qp_attr.ah_attr.grh.flow_label = ah_attr_grh_flow_label;
    qp_attr.ah_attr.grh.sgid_index = ah_attr_grh_sgid_index;
    qp_attr.ah_attr.grh.hop_limit = ah_attr_grh_hop_limit;
    qp_attr.ah_attr.grh.traffic_class = ah_attr_grh_traffic_class;
    //
    qp_attr.ah_attr.dlid = ah_attr_dlid;
    qp_attr.ah_attr.sl = ah_attr_sl;
    qp_attr.ah_attr.src_path_bits = ah_attr_src_path_bits;
    qp_attr.ah_attr.static_rate = ah_attr_static_rate;
    qp_attr.ah_attr.is_global = ah_attr_is_global;
    qp_attr.ah_attr.port_num = ah_attr_port_num;
    // alt_ah_attr
    memcpy(qp_attr.alt_ah_attr.grh.dgid.raw, alt_ah_attr_grh_dgid, 16);
    qp_attr.alt_ah_attr.grh.flow_label = alt_ah_attr_grh_flow_label;
    qp_attr.alt_ah_attr.grh.sgid_index = alt_ah_attr_grh_sgid_index;
    qp_attr.alt_ah_attr.grh.hop_limit = alt_ah_attr_grh_hop_limit;
    qp_attr.alt_ah_attr.grh.traffic_class = alt_ah_attr_grh_traffic_class;
    //
    qp_attr.alt_ah_attr.dlid = alt_ah_attr_dlid;
    qp_attr.alt_ah_attr.sl = alt_ah_attr_sl;
    qp_attr.alt_ah_attr.src_path_bits = alt_ah_attr_src_path_bits;
    qp_attr.alt_ah_attr.static_rate = alt_ah_attr_static_rate;
    qp_attr.alt_ah_attr.is_global = alt_ah_attr_is_global;
    qp_attr.alt_ah_attr.port_num = alt_ah_attr_port_num;

    qp_attr.pkey_index = pkey_index;
    qp_attr.alt_pkey_index = alt_pkey_index;
    qp_attr.en_sqd_async_notify = en_sqd_async_notify;
    qp_attr.sq_draining = sq_draining;
    qp_attr.max_rd_atomic = max_rd_atomic;
    qp_attr.max_dest_rd_atomic = max_dest_rd_atomic;
    qp_attr.min_rnr_timer = min_rnr_timer;
    qp_attr.port_num = port_num;
    qp_attr.timeout = timeout;
    qp_attr.retry_cnt = retry_cnt;
    qp_attr.rnr_retry = rnr_retry;
    qp_attr.alt_port_num = alt_port_num;
    qp_attr.alt_timeout = alt_timeout;
    qp_attr.rate_limit = rate_limit;

    // Finally, call env_modify_qp with parsed parameters
    env_modify_qp(env, name, &qp_attr, attr_mask);
    return 0;
}
int handle_DestroyQP(cJSON *verb_obj, ResourceEnv *env)
{
    const char *name = json_get_res_name(verb_obj, "qp");
    if (!name)
    {
        fprintf(stderr, "[EXEC] DestroyQP: missing 'qp' field\n");
        return -1;
    }
    env_destroy_qp(env, name);
    return 0;
}
int handle_PostSend(cJSON *verb_obj, ResourceEnv *env)
{
    fprintf(stderr, "[EXEC] PostSend: not implemented yet\n");
    return 0;
}
int handle_PostRecv(cJSON *verb_obj, ResourceEnv *env)
{
    fprintf(stderr, "[EXEC] PostRecv: not implemented yet\n");
    return 0;
}