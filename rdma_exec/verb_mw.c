#include "verb_mw.h"
#include "json_utils.h"

#include <stdio.h>

int handle_AllocMW(cJSON *verb_obj, ResourceEnv *env)
{
    const char *pd_name = json_get_res_name(verb_obj, "pd");
    const char *mw_name = json_get_res_name(verb_obj, "mw");
    if (!pd_name || !mw_name)
    {
        return -1;
    }

    // 解析 EnumValue: IBV_MW_TYPE_1 / IBV_MW_TYPE_2 等
    cJSON *mw_type_spec = obj_get(verb_obj, "mw_type");
    enum ibv_mw_type mw_type = IBV_MW_TYPE_1; // default

    const char *mw_type_str = NULL;
    if (mw_type_spec)
    {
        // 这里假设 EnumValue 的 value 是字符串，比如 "IBV_MW_TYPE_1"
        // 如果你用 IntValue 也可以改成解析整数
        parse_typed_value(mw_type_spec, VAL_KIND_STRING, NULL, &mw_type_str);
    }

    if (mw_type_str)
    {
        if (strcmp(mw_type_str, "IBV_MW_TYPE_1") == 0)
        {
            mw_type = IBV_MW_TYPE_1;
        }
        else if (strcmp(mw_type_str, "IBV_MW_TYPE_2") == 0)
        {
            mw_type = IBV_MW_TYPE_2;
        }
        else
        {
            fprintf(stderr,
                    "[WARN] AllocMW: unknown mw_type '%s', use IBV_MW_TYPE_1\n",
                    mw_type_str);
            mw_type = IBV_MW_TYPE_1;
        }
    }

    if (!env_alloc_mw(env, mw_name, pd_name, mw_type))
    {
        return -1;
    }
    return 0;
}