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
    const char *pd_name = json_get_res_name(verb_obj, "pd");
    const char *xrcd_name = json_get_res_name(verb_obj, "xrcd");
    int create_flags = json_get_flag_field(
        verb_obj,
        "create_flags",
        qp_create_flags_table,
        sizeof(qp_create_flags_table) / sizeof(qp_create_flags_table[0]),
        0);
    return 0;
}

int handle_ModifyQP(cJSON *verb_obj, ResourceEnv *env)
{
    fprintf(stderr, "[EXEC] ModifyQP: not implemented yet\n");
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