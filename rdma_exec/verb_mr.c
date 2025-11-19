#include "verb_mr.h"
#include "json_utils.h"

#include <stdio.h>

int handle_AllocNullMR(cJSON *verb_obj, ResourceEnv *env) // struct ibv_mr * ibv_alloc_null_mr(struct ibv_pd * pd);
{
    const char *mr_name = json_get_res_name(verb_obj, "mr");
    const char *pd_name = json_get_res_name(verb_obj, "pd");
    if (!mr_name || !pd_name)
    {
        return -1;
    }
    env_alloc_null_mr(env, mr_name, pd_name);
    fprintf(stderr, "[EXEC] AllocNullMR -> %s\n", mr_name);
    return 0;
}