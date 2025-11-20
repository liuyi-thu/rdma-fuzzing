#include "verb_srq.h"
#include "json_utils.h"
#include <stdio.h>

static const JsonFlagSpec srq_attr_mask_table[] = {
    {"IBV_SRQ_MAX_WR", IBV_SRQ_MAX_WR},
    {"IBV_SRQ_LIMIT", IBV_SRQ_LIMIT},
};

int handle_CreateSRQ(cJSON *verb_obj, ResourceEnv *env)
{
    const char *srq_name = json_get_res_name(verb_obj, "srq");
    const char *pd_name = json_get_res_name(verb_obj, "pd");
    if (!srq_name || !pd_name)
    {
        return -1;
    }

    cJSON *srq_init_obj = obj_get(verb_obj, "srq_init_obj"); // not "attr_obj"
    if (!srq_init_obj || !cJSON_IsObject(srq_init_obj))
    {
        fprintf(stderr, "[WARN] CreateSRQ missing 'srq_init_obj'\n");
        return -1;
    }
    // note that we ignore the "srq_context field"
    cJSON *attr_obj = obj_get(srq_init_obj, "attr"); // not "attr_obj"
    int max_wr = json_get_int_field(attr_obj, "max_wr", 0);
    int max_sge = json_get_int_field(attr_obj, "max_sge", 0);
    int srq_limit = json_get_int_field(attr_obj, "srq_limit", 0);

    env_create_srq(env, srq_name, pd_name, max_wr, max_sge, srq_limit);
    return 0;
}

int handle_DestroySRQ(cJSON *verb_obj, ResourceEnv *env)
{
    const char *name = json_get_res_name(verb_obj, "srq");
    if (!name)
    {
        return -1;
    }
    env_destroy_srq(env, name);
    return 0;
}

int handle_ModifySRQ(cJSON *verb_obj, ResourceEnv *env)
{
    const char *name = json_get_res_name(verb_obj, "srq");
    if (!name)
    {
        fprintf(stderr, "[EXEC] ModifySRQ: missing 'srq' field\n");
        return -1;
    }
    cJSON *attr_obj = obj_get(verb_obj, "attr_obj");
    if (!attr_obj)
    {
        fprintf(stderr, "[EXEC] ModifySRQ: missing 'attr_obj'\n");
        return -1;
    }
    // struct ibv_srq_attr srq_attr;
    // memset(&srq_attr, 0, sizeof(srq_attr));
    // int attr_mask = 0;

    // parse srq_attr fields from attr_obj
    // srq_attr.max_wr = json_get_int_field(attr_obj, "max_wr", 0);
    // srq_attr.max_sge = json_get_int_field(attr_obj, "max_sge", 0);
    // srq_attr.srq_limit = json_get_int_field(attr_obj, "srq_limit", 0);
    // // set attr_mask accordingly
    // if (srq_attr.max_wr > 0)
    //     attr_mask |= IBV_SRQ_ATTR_MAX_WR;
    // if (srq_attr.max_sge > 0)
    //     attr_mask |= IBV_SRQ_ATTR_MAX_SGE;
    // if (srq_attr.srq_limit > 0)
    //     attr_mask |= IBV_SRQ_ATTR_SRQ_LIMIT;
    int max_wr = json_get_int_field(attr_obj, "max_wr", 0);
    int max_sge = json_get_int_field(attr_obj, "max_sge", 0);
    int srq_limit = json_get_int_field(attr_obj, "srq_limit", 0);
    int attr_mask = json_get_flag_field(
        verb_obj,
        "attr_mask",
        srq_attr_mask_table,
        sizeof(srq_attr_mask_table) / sizeof(srq_attr_mask_table[0]),
        0);

    // call env_modify_srq with parsed parameters
    env_modify_srq(env, name, max_wr, max_sge, srq_limit, attr_mask);
    return 0;
}