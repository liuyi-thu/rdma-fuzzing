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
    int cap_max_send_wr = json_get_int_field(attr_obj, "cap_max_send_wr", 0);
    int cap_max_recv_wr = json_get_int_field(attr_obj, "cap_max_recv_wr", 0);
    int cap_max_send_sge = json_get_int_field(attr_obj, "cap_max_send_sge", 0);
    int cap_max_recv_sge = json_get_int_field(attr_obj, "cap_max_recv_sge", 0);
    int cap_max_inline_data = json_get_int_field(attr_obj, "cap_max_inline_data", 0);
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
    // fprintf(stderr, "[EXEC] CreateQP: not implemented yet\n");
    return 0;
}
int handle_ModifyQP(cJSON *verb_obj, ResourceEnv *env)
{
    fprintf(stderr, "[EXEC] ModifyQP: not implemented yet\n");
    return 0;
}
int handle_DestroyQP(cJSON *verb_obj, ResourceEnv *env)
{
    fprintf(stderr, "[EXEC] DestroyQP: not implemented yet\n");
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