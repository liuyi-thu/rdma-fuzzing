#include "verb_mw.h"
#include "json_utils.h"

#include <stdio.h>
#include <infiniband/verbs.h>

static const JsonEnumSpec mw_type_table[] = {
    {"IBV_MW_TYPE_1", IBV_MW_TYPE_1},
#ifdef IBV_MW_TYPE_2
    {"IBV_MW_TYPE_2", IBV_MW_TYPE_2},
#endif
};

int handle_AllocMW(cJSON *verb_obj, ResourceEnv *env)
{
    const char *pd_name = json_get_res_name(verb_obj, "pd");
    const char *mw_name = json_get_res_name(verb_obj, "mw");
    if (!pd_name || !mw_name)
    {
        return -1;
    }

    // 解析 EnumValue: IBV_MW_TYPE_1 / IBV_MW_TYPE_2 等
    // cJSON *mw_type_spec = obj_get(verb_obj, "mw_type");
    // enum ibv_mw_type mw_type = IBV_MW_TYPE_1; // default

    // const char *mw_type_str = NULL;
    // if (mw_type_spec)
    // {
    //     // 这里假设 EnumValue 的 value 是字符串，比如 "IBV_MW_TYPE_1"
    //     // 如果你用 IntValue 也可以改成解析整数
    //     parse_typed_value(mw_type_spec, VAL_KIND_STRING, NULL, &mw_type_str);
    // }

    // if (mw_type_str)
    // {
    //     if (strcmp(mw_type_str, "IBV_MW_TYPE_1") == 0)
    //     {
    //         mw_type = IBV_MW_TYPE_1;
    //     }
    //     else if (strcmp(mw_type_str, "IBV_MW_TYPE_2") == 0)
    //     {
    //         mw_type = IBV_MW_TYPE_2;
    //     }
    //     else
    //     {
    //         fprintf(stderr,
    //                 "[WARN] AllocMW: unknown mw_type '%s', use IBV_MW_TYPE_1\n",
    //                 mw_type_str);
    //         mw_type = IBV_MW_TYPE_1;
    //     }
    // }

    enum ibv_mw_type mw_type = (enum ibv_mw_type)json_get_enum_field(
        verb_obj,
        "mw_type",
        mw_type_table,
        sizeof(mw_type_table) / sizeof(mw_type_table[0]),
        IBV_MW_TYPE_1 // 默认值
    );

    if (!env_alloc_mw(env, mw_name, pd_name, mw_type))
    {
        return -1;
    }
    return 0;
}

int handle_DeallocMW(cJSON *verb_obj, ResourceEnv *env)
{
    const char *name = json_get_res_name(verb_obj, "mw");
    if (!name)
    {
        return -1;
    }

    MwResource *mw_res = env_find_mw(env, name);
    if (!mw_res)
    {
        fprintf(stderr, "[EXEC] DeallocMW: MW '%s' not found\n", name);
        return -1;
    }

    if (ibv_dealloc_mw(mw_res->mw) != 0)
    {
        fprintf(stderr,
                "[EXEC] DeallocMW: ibv_dealloc_mw failed for '%s'\n",
                name);
        return -1;
    }

    fprintf(stderr, "[EXEC] DeallocMW OK -> %s\n", name);

    // 从数组中移除：用最后一个元素覆盖当前，再减计数，保持数组紧凑
    int idx = -1;
    for (int i = 0; i < env->mw_count; i++)
    {
        if (strcmp(env->mw[i].name, name) == 0)
        {
            idx = i;
            break;
        }
    }
    if (idx >= 0)
    {
        int last = env->mw_count - 1;
        if (idx != last)
        {
            env->mw[idx] = env->mw[last];
        }
        env->mw_count--;
    }

    return 0;
}