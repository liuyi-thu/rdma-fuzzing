#include "verb_srq.h"
#include "json_utils.h"
#include <stdio.h>

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