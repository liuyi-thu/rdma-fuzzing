#include "verb_mr.h"
#include "json_utils.h"

#include <stdio.h>
#include <infiniband/verbs.h>

static const JsonFlagSpec access_flag_table[] = {
    {"IBV_ACCESS_LOCAL_WRITE", IBV_ACCESS_LOCAL_WRITE},
    {"IBV_ACCESS_REMOTE_WRITE", IBV_ACCESS_REMOTE_WRITE},
    {"IBV_ACCESS_REMOTE_READ", IBV_ACCESS_REMOTE_READ},
#ifdef IBV_ACCESS_REMOTE_ATOMIC
    {"IBV_ACCESS_REMOTE_ATOMIC", IBV_ACCESS_REMOTE_ATOMIC},
#endif
#ifdef IBV_ACCESS_MW_BIND
    {"IBV_ACCESS_MW_BIND", IBV_ACCESS_MW_BIND},
#endif
#ifdef IBV_ACCESS_ZERO_BASED
    {"IBV_ACCESS_ZERO_BASED", IBV_ACCESS_ZERO_BASED},
#endif
#ifdef IBV_ACCESS_ON_DEMAND
    {"IBV_ACCESS_ON_DEMAND", IBV_ACCESS_ON_DEMAND},
#endif
};

int handle_AllocNullMR(cJSON *verb_obj, ResourceEnv *env) // struct ibv_mr * ibv_alloc_null_mr(struct ibv_pd * pd);
{
    const char *mr_name = json_get_res_name(verb_obj, "mr");
    const char *pd_name = json_get_res_name(verb_obj, "pd");
    if (!mr_name || !pd_name)
    {
        fprintf(stderr, "[EXEC] AllocNullMR: missing 'mr' or 'pd' field\n");
        return -1;
    }
    env_alloc_null_mr(env, mr_name, pd_name);
    // fprintf(stderr, "[EXEC] AllocNullMR -> %s\n", mr_name);
    return 0;
}

int handle_RegMR(cJSON *verb_obj, ResourceEnv *env) // struct ibv_mr * ibv_reg_mr(struct ibv_pd * pd, void * addr, size_t length, int access);
{
    const char *mr_name = json_get_res_name(verb_obj, "mr");
    const char *pd_name = json_get_res_name(verb_obj, "pd");
    const char *addr_name = json_get_res_name(verb_obj, "addr");
    if (!mr_name || !pd_name || !addr_name)
    {
        fprintf(stderr, "[EXEC] RegMR: missing 'mr', 'pd' or 'addr' field\n");
        return -1;
    }
    size_t length = (size_t)json_get_int_field(verb_obj, "length", 4096);
    // here we should parse "access" field
    /* access: 既能写成 IntValue，也能写成 FlagValue 字符串 */
    int access = json_get_flag_field(
        verb_obj,
        "access",
        access_flag_table,
        sizeof(access_flag_table) / sizeof(access_flag_table[0]),
        IBV_ACCESS_LOCAL_WRITE // 默认给一个相对安全的值
    );

    // TODO: addr 的处理（LocalResourceValue "bufs[1]" → 实际地址）
    // 比如先留个占位逻辑:
    // void *addr = NULL;

    // 这里可以先写成 env_reg_mr 内部再处理 addr / length / access
    env_reg_mr(env, mr_name, pd_name, addr_name, length, access);

    // fprintf(stderr, "[EXEC] RegMR -> %s\n", mr_name);
    return 0;
}

int handle_DeregMR(cJSON *verb_obj, ResourceEnv *env)
{
    const char *name = json_get_res_name(verb_obj, "mr");
    if (!name)
    {
        fprintf(stderr, "[EXEC] DeregMR: missing 'mr' field\n");
        return -1;
    }
    env_dereg_mr(env, name);
    return 0;
}