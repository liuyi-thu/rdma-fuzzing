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