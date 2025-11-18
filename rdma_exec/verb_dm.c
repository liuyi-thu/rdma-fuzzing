#include "verb_dm.h"
#include "json_utils.h"
#include <stdio.h>

int handle_AllocDM(cJSON *verb_obj, ResourceEnv *env)
{
    const char *dm_name = json_get_res_name(verb_obj, "dm");
    if (!dm_name)
        return -1;

    cJSON *attr_obj = obj_get(verb_obj, "attr_obj");
    if (!attr_obj || !cJSON_IsObject(attr_obj))
    {
        fprintf(stderr, "[WARN] AllocDM missing 'attr_obj'\n");
        return -1;
    }

    int length = json_get_int_field(attr_obj, "length", 4096);
    int log_align_req = json_get_int_field(attr_obj, "log_align_req", 0);
    int comp_mask = json_get_int_field(attr_obj, "comp_mask", 0);

    env_alloc_dm(env, dm_name, length, log_align_req, comp_mask);
    return 0;
}