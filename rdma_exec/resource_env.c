#include "resource_env.h"
#include <stddef.h>
#include <stdio.h>
static struct ibv_context *g_ctx = NULL;
static struct ibv_device *g_dev = NULL;
static struct ibv_device **g_dev_list = NULL;

void env_init(ResourceEnv *env)
{
    memset(env, 0, sizeof(*env));
}

PdResource *env_alloc_pd(ResourceEnv *env, const char *name)
{
    if (env->pd_count >= (int)(sizeof(env->pd) / sizeof(env->pd[0])))
    {
        fprintf(stderr, "[EXEC] Too many PD resources, ignoring %s\n", name);
        return NULL;
    }
    PdResource *pd = &env->pd[env->pd_count++];
    snprintf(pd->name, sizeof(pd->name), "%s", name);
    // TODO: 替换成真实的 ibv_alloc_pd 调用，并保存 ibv_pd* 句柄
    fprintf(stderr, "[EXEC] AllocPD -> %s\n", pd->name);
    return pd;
}

DmResource *env_alloc_dm(ResourceEnv *env,
                         const char *name,
                         int length,
                         int log_align_req,
                         int comp_mask)
{
    if (env->dm_count >= (int)(sizeof(env->dm) / sizeof(env->dm[0])))
    {
        fprintf(stderr, "[EXEC] Too many DM resources, ignoring %s\n", name);
        return NULL;
    }
    DmResource *dm = &env->dm[env->dm_count++];
    snprintf(dm->name, sizeof(dm->name), "%s", name);
    dm->length = length;
    dm->log_align_req = log_align_req;
    dm->comp_mask = comp_mask;
    // TODO: 替换成真实的 ibv_alloc_dm 调用，并保存 ibv_dm* 句柄
    fprintf(stderr,
            "[EXEC] AllocDM -> %s, length=%d, log_align_req=%d, comp_mask=%d\n",
            dm->name, dm->length, dm->log_align_req, dm->comp_mask);
    return dm;
}

int rdma_init_context(const char *preferred_name)
{
    int num_devices = 0;
    g_dev_list = ibv_get_device_list(&num_devices);
    if (!g_dev_list || num_devices == 0)
    {
        fprintf(stderr, "[RDMA] ibv_get_device_list failed or no devices\n");
        return -1;
    }

    fprintf(stderr, "[RDMA] Found %d RDMA device(s):\n", num_devices);
    for (int i = 0; i < num_devices; i++)
    {
        const char *name = ibv_get_device_name(g_dev_list[i]);
        fprintf(stderr, "        [%d] %s\n", i, name ? name : "(null)");
    }

    // 选择设备：
    // 1) 如果有 preferred_name（比如 "rxe0"），优先匹配
    // 2) 否则，如果名字里包含 "rxe"，选第一个
    // 3) 否则，就选第一个设备
    struct ibv_device *chosen = NULL;

    if (preferred_name)
    {
        for (int i = 0; i < num_devices; i++)
        {
            const char *name = ibv_get_device_name(g_dev_list[i]);
            if (name && strcmp(name, preferred_name) == 0)
            {
                chosen = g_dev_list[i];
                break;
            }
        }
    }

    if (!chosen)
    {
        for (int i = 0; i < num_devices; i++)
        {
            const char *name = ibv_get_device_name(g_dev_list[i]);
            if (name && strstr(name, "rxe") != NULL)
            {
                chosen = g_dev_list[i];
                break;
            }
        }
    }

    if (!chosen)
    {
        chosen = g_dev_list[0];
    }

    const char *chosen_name = ibv_get_device_name(chosen);
    fprintf(stderr, "[RDMA] Using device: %s\n", chosen_name ? chosen_name : "(unknown)");

    g_ctx = ibv_open_device(chosen);
    if (!g_ctx)
    {
        fprintf(stderr, "[RDMA] ibv_open_device failed\n");
        ibv_free_device_list(g_dev_list);
        g_dev_list = NULL;
        return -1;
    }

    g_dev = chosen;

    // 打印一点设备信息
    struct ibv_device_attr dev_attr;
    if (ibv_query_device(g_ctx, &dev_attr) == 0)
    {
        fprintf(stderr,
                "[RDMA] Device attr: fw_ver=%s, max_qp=%u, max_mr=%u, max_sge=%u\n",
                dev_attr.fw_ver,
                dev_attr.max_qp,
                dev_attr.max_mr,
                dev_attr.max_sge);
    }
    else
    {
        fprintf(stderr, "[RDMA] ibv_query_device failed (ignored)\n");
    }

    return 0;
}

void rdma_teardown_context(void)
{
    if (g_ctx)
    {
        ibv_close_device(g_ctx);
        g_ctx = NULL;
    }
    if (g_dev_list)
    {
        ibv_free_device_list(g_dev_list);
        g_dev_list = NULL;
    }
}