#include "verb_cq.h"
#include "json_utils.h"
#include <stdio.h>

int handle_CreateCQ(cJSON *verb_obj, ResourceEnv *env)
{
    const char *cq_name = json_get_res_name(verb_obj, "cq");
    if (!cq_name)
    {
        fprintf(stderr, "[EXEC] CreateCQ: missing 'cq' field\n");
        return -1;
    }

    int cqe = json_get_int_field(verb_obj, "cqe", 16);
    // 这里可以扩展读取 cq_context、channel、comp_vector 等参数
    const char *cq_context_str = obj_get_string(verb_obj, "cq_context");
    void *cq_context = NULL; // disabled
    const char *channel_str = obj_get_string(verb_obj, "channel");
    struct ibv_comp_channel *channel = NULL; // disabled
    int comp_vector = json_get_int_field(verb_obj, "comp_vector", 0);

    env_create_cq(env, cq_name, cqe, cq_context, channel, comp_vector);
    return 0;
}

int handle_CreateCQEx(cJSON *verb_obj, ResourceEnv *env)
{
    const char *cq_ex_name = json_get_res_name(verb_obj, "cq_ex");
    if (!cq_ex_name)
    {
        fprintf(stderr, "[EXEC] CreateCQ: missing 'cq_ex' field\n");
        return -1;
    }

    cJSON *attr_obj = obj_get(verb_obj, "cq_attr_obj");
    if (!attr_obj || !cJSON_IsObject(attr_obj))
    {
        fprintf(stderr, "[WARN] CreateCQEx missing 'cq_attr_obj'\n");
        return -1;
    }
    int cqe = json_get_int_field(attr_obj, "cqe", 0);
    // 这里可以扩展读取 cq_context、channel、comp_vector 等参数
    const char *cq_context_str = obj_get_string(attr_obj, "cq_context");
    void *cq_context = NULL; // disabled
    const char *channel_str = obj_get_string(attr_obj, "channel");
    struct ibv_comp_channel *channel = NULL; // disabled
    int comp_vector = json_get_int_field(attr_obj, "comp_vector", 0);
    int wc_flags = json_get_int_field(attr_obj, "wc_flags", 0);
    int comp_mask = json_get_int_field(attr_obj, "comp_mask", 0);
    int flags = json_get_int_field(attr_obj, "flags", 0);
    const char *parent_domain_str = obj_get_string(attr_obj, "parent_domain");
    struct ibv_pd *parent_domain = NULL; // disabled

    env_create_cq_ex(env, cq_ex_name, cqe, cq_context, channel,
                     comp_vector, wc_flags, comp_mask, flags, parent_domain);
    return 0;
}

int handle_ModifyCQ(cJSON *verb_obj, ResourceEnv *env)
{
    const char *cq_name = json_get_res_name(verb_obj, "cq");
    if (!cq_name)
    {
        fprintf(stderr, "[EXEC] ModifyCQ: missing 'cq' field\n");
        return -1;
    }
    cJSON *attr_obj = obj_get(verb_obj, "attr_obj");
    if (!attr_obj || !cJSON_IsObject(attr_obj))
    {
        fprintf(stderr, "[WARN] ModifyCQ missing 'attr_obj'\n");
        return -1;
    }
    // 这里可以扩展读取 attr_obj 中的字段
    int attr_mask = json_get_int_field(attr_obj, "attr_mask", 0);
    // TODO: mask 应该支持 str 和 int 两类，不需要检查 str 合法性（由 fuzz tool 保证）
    cJSON *moderate = obj_get(attr_obj, "moderate");
    int cq_count = json_get_int_field(moderate, "cq_count", 0);
    int cq_period = json_get_int_field(moderate, "cq_period", 0);
    env_modify_cq(env, cq_name, attr_mask, cq_count, cq_period);
    return 0;
}

int handle_DestroyCQ(cJSON *verb_obj, ResourceEnv *env)
{
    const char *cq_name = json_get_res_name(verb_obj, "cq");
    if (!cq_name)
    {
        fprintf(stderr, "[EXEC] DestroyCQ: missing 'cq' field\n");
        return -1;
    }
    env_destroy_cq(env, cq_name);
    return 0;
}