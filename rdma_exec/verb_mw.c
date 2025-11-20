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

static const JsonFlagSpec send_flags_table[] = {
    {"IBV_SEND_SIGNALED", IBV_SEND_SIGNALED},
    {"IBV_SEND_FENCE", IBV_SEND_FENCE},
    {"IBV_SEND_SOLICITED", IBV_SEND_SOLICITED},
    {"IBV_SEND_INLINE", IBV_SEND_INLINE},
    {"IBV_SEND_IP_CSUM", IBV_SEND_IP_CSUM},
};

static const JsonFlagSpec access_flags_table[] = {
    {"IBV_ACCESS_LOCAL_WRITE", IBV_ACCESS_LOCAL_WRITE},
    {"IBV_ACCESS_REMOTE_WRITE", IBV_ACCESS_REMOTE_WRITE},
    {"IBV_ACCESS_REMOTE_READ", IBV_ACCESS_REMOTE_READ},
    {"IBV_ACCESS_REMOTE_ATOMIC", IBV_ACCESS_REMOTE_ATOMIC},
    {"IBV_ACCESS_MW_BIND", IBV_ACCESS_MW_BIND},
    {"IBV_ACCESS_ZERO_BASED", IBV_ACCESS_ZERO_BASED},
    {"IBV_ACCESS_ON_DEMAND", IBV_ACCESS_ON_DEMAND},
    {"IBV_ACCESS_HUGETLB", IBV_ACCESS_HUGETLB},
    {"IBV_ACCESS_FLUSH_GLOBAL", IBV_ACCESS_FLUSH_GLOBAL},
    {"IBV_ACCESS_FLUSH_PERSISTENT", IBV_ACCESS_FLUSH_PERSISTENT},
    {"IBV_ACCESS_RELAXED_ORDERING", IBV_ACCESS_RELAXED_ORDERING}};

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

int handle_BindMW(cJSON *verb_obj, ResourceEnv *env)
{
    const char *mw_name = json_get_res_name(verb_obj, "mw");
    const char *qp_name = json_get_res_name(verb_obj, "qp");
    if (!mw_name || !qp_name)
    {
        fprintf(stderr, "[EXEC] BindMW: missing 'mw' or 'qp' field\n");
        return -1;
    }
    cJSON *mw_bind = obj_get(verb_obj, "mw_bind");
    if (!mw_bind)
    {
        fprintf(stderr, "[EXEC] BindMW: missing 'mw_bind' object\n");
        return -1;
    }
    int wr_id = json_get_int_field(mw_bind, "wr_id", 0);
    int send_flags = json_get_flag_field(
        mw_bind,
        "send_flags",
        send_flags_table,
        sizeof(send_flags_table) / sizeof(send_flags_table[0]),
        0);
    cJSON *bind_info = obj_get(mw_bind, "bind_info");
    if (!bind_info)
    {
        fprintf(stderr, "[EXEC] BindMW: missing 'bind_info' object\n");
        return -1;
    }
    const char *mr = json_get_res_name(bind_info, "mr");
    const char *addr = json_get_res_name(bind_info, "addr");
    int length = json_get_int_field(bind_info, "length", 0);
    int access = json_get_flag_field(
        bind_info,
        "access",
        access_flags_table,
        sizeof(access_flags_table) / sizeof(access_flags_table[0]),
        0);
    env_bind_mw(env,
                mw_name,
                qp_name,
                wr_id,
                send_flags,
                mr,
                addr,
                length,
                access);
    return 0;
}