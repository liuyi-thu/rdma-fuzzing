#include "verb_td.h"
#include "json_utils.h"
#include <stdio.h>

int handle_AllocTD(cJSON *verb_obj, ResourceEnv *env)
{
    const char *td_name = json_get_res_name(verb_obj, "td");
    if (!td_name)
        return -1;
    cJSON *attr_obj = obj_get(verb_obj, "attr_obj");
    if (!attr_obj || !cJSON_IsObject(attr_obj))
    {
        fprintf(stderr, "[WARN] AllocTD missing 'attr_obj'\n");
        return -1;
    }
    int comp_mask = json_get_int_field(attr_obj, "comp_mask", 0);
    env_alloc_td(env, td_name, comp_mask);
    return 0;
}