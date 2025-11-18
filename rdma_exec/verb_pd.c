#include "verb_pd.h"
#include "json_utils.h"

#include <stdio.h>

int handle_AllocPD(cJSON *verb_obj, ResourceEnv *env)
{
    const char *pd_name = json_get_res_name(verb_obj, "pd");
    if (!pd_name)
        return -1;
    env_alloc_pd(env, pd_name);
    return 0;
}

int handle_DeallocPD(cJSON *verb_obj, ResourceEnv *env)
{
    if (!verb_obj || !env)
    {
        fprintf(stderr, "[WARN] DeallocPD: null verb_obj or env\n");
        return -1;
    }

    const char *pd_name = json_get_res_name(verb_obj, "pd");
    if (!pd_name)
    {
        // json_get_res_name 里面已经打印过 warning 了
        return -1;
    }

    int ret = env_dealloc_pd(env, pd_name);
    if (ret != 0)
    {
        fprintf(stderr,
                "[WARN] DeallocPD: failed to dealloc PD '%s'\n",
                pd_name);
        return -1;
    }

    return 0;
}