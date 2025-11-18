#include "verb_pd.h"
#include "json_utils.h"

int handle_AllocPD(cJSON *verb_obj, ResourceEnv *env)
{
    const char *pd_name = json_get_res_name(verb_obj, "pd");
    if (!pd_name)
        return -1;
    env_alloc_pd(env, pd_name);
    return 0;
}