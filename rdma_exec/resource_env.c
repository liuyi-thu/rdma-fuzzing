#include "resource_env.h"
#include <stddef.h>
#include <stdio.h>
static struct ibv_context *g_ctx = NULL;
static struct ibv_device *g_dev = NULL;
static struct ibv_device **g_dev_list = NULL;

static int env_pd_in_use(ResourceEnv *env, struct ibv_pd *pd);

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
    if (!(pd->pd = ibv_alloc_pd(g_ctx)))
    {
        fprintf(stderr, "[EXEC] ibv_alloc_pd failed for %s\n", name);
        return NULL;
    }
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
    struct ibv_alloc_dm_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.length = length;
    attr.log_align_req = log_align_req;
    attr.comp_mask = comp_mask;
    if (!(dm->dm = ibv_alloc_dm(g_ctx, &attr)))
    {
        fprintf(stderr, "[EXEC] ibv_alloc_dm failed for %s\n", name);
        return NULL;
    }
    fprintf(stderr,
            "[EXEC] AllocDM -> %s, length=%d, log_align_req=%d, comp_mask=%d\n",
            dm->name, dm->length, dm->log_align_req, dm->comp_mask);
    return dm;
}

MwResource *env_alloc_mw(ResourceEnv *env,
                         const char *mw_name,
                         const char *pd_name,
                         enum ibv_mw_type type)
{
    if (!env || !mw_name || !pd_name)
    {
        fprintf(stderr, "[EXEC] env_alloc_mw: null argument\n");
        return NULL;
    }
    if (!rdma_get_context())
    {
        fprintf(stderr, "[EXEC] env_alloc_mw: RDMA context is NULL\n");
        return NULL;
    }
    if (env->mw_count >= (int)(sizeof(env->mw) / sizeof(env->mw[0])))
    {
        fprintf(stderr, "[EXEC] env_alloc_mw: too many MW resources, ignore %s\n",
                mw_name);
        return NULL;
    }

    // 1. 先在资源表中找到 PD
    PdResource *pd_res = env_find_pd(env, pd_name);
    if (!pd_res || !pd_res->pd)
    {
        fprintf(stderr,
                "[EXEC] env_alloc_mw: PD '%s' not found or invalid\n",
                pd_name);
        return NULL;
    }

    struct ibv_mw *mw = ibv_alloc_mw(pd_res->pd, type);
    if (!mw)
    {
        fprintf(stderr,
                "[EXEC] env_alloc_mw: ibv_alloc_mw failed for mw=%s (pd=%s)\n",
                mw_name, pd_name);
        return NULL;
    }

    MwResource *slot = &env->mw[env->mw_count++];
    memset(slot, 0, sizeof(*slot));
    snprintf(slot->name, sizeof(slot->name), "%s", mw_name);
    slot->mw = mw;
    slot->type = type;
    slot->pd = pd_res->pd;

    fprintf(stderr,
            "[EXEC] AllocMW OK -> %s (mw=%p, pd=%s, type=%d)\n",
            slot->name, (void *)mw, pd_name, (int)type);
    return slot;
}

MrResource *env_alloc_null_mr(ResourceEnv *env, // struct ibv_mr * ibv_alloc_null_mr(struct ibv_pd * pd);
                              const char *mr_name,
                              const char *pd_name)
{
    if (!env || !mr_name || !pd_name)
    {
        fprintf(stderr, "[EXEC] env_alloc_null_mr: null argument\n");
        return NULL;
    }
    if (!rdma_get_context())
    {
        fprintf(stderr, "[EXEC] env_alloc_null_mr: RDMA context is NULL\n");
    }
    if (env->mr_count >= (int)(sizeof(env->mr) / sizeof(env->mr[0])))
    {
        fprintf(stderr,
                "[EXEC] env_alloc_null_mr: too many MR resources, ignore %s\n",
                mr_name);
        return NULL;
    }
    // 1. 先在资源表中找到 PD
    PdResource *pd_res = env_find_pd(env, pd_name);
    if (!pd_res || !pd_res->pd)
    {
        fprintf(stderr,
                "[EXEC] env_alloc_null_mr: PD '%s' not found or invalid\n",
                pd_name);
        return NULL;
    }
    struct ibv_mr *mr = ibv_alloc_null_mr(pd_res->pd);
    if (!mr)
    {
        fprintf(stderr,
                "[EXEC] env_alloc_null_mr: ibv_alloc_null_mr failed for mr=%s (pd=%s)\n",
                mr_name, pd_name);
        return NULL;
    }
    MrResource *slot = &env->mr[env->mr_count++];
    memset(slot, 0, sizeof(*slot));
    snprintf(slot->name, sizeof(slot->name), "%s", mr_name);
    slot->mr = mr;
    slot->pd = pd_res->pd;
    fprintf(stderr,
            "[EXEC] AllocNullMR OK -> %s (mr=%p, pd=%s)\n",
            slot->name, (void *)mr, pd_name);
    return slot;
}

TdResource *env_alloc_td(ResourceEnv *env,
                         const char *td_name,
                         int comp_mask)
{
    if (!env || !td_name)
    {
        fprintf(stderr, "[EXEC] env_alloc_td: null argument\n");
        return NULL;
    }
    if (!rdma_get_context())
    {
        fprintf(stderr, "[EXEC] env_alloc_td: RDMA context is NULL\n");
    }
    if (env->td_count >= (int)(sizeof(env->td) / sizeof(env->td[0])))
    {
        fprintf(stderr, "[EXEC] env_alloc_td: too many TD resources, ignore %s\n",
                td_name);
        return NULL;
    }
    struct ibv_td_init_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.comp_mask = comp_mask;
    struct ibv_td *td = ibv_alloc_td(g_ctx, &attr);
    if (!td)
    {
        fprintf(stderr,
                "[EXEC] env_alloc_td: ibv_alloc_td failed for td=%s\n",
                td_name);
        return NULL;
    }
    TdResource *slot = &env->td[env->td_count++];
    memset(slot, 0, sizeof(*slot));
    snprintf(slot->name, sizeof(slot->name), "%s", td_name);
    slot->td = td;
    slot->comp_mask = comp_mask;
    fprintf(stderr,
            "[EXEC] AllocTD OK -> %s (td=%p, comp_mask=%d)\n",
            slot->name, (void *)td, comp_mask);
    return slot;
}

SrqResource *env_create_srq(ResourceEnv *env,
                            const char *srq_name,
                            const char *pd_name,
                            int max_wr,
                            int max_sge,
                            int srq_limit)
{
    if (!env || !srq_name || !pd_name)
    {
        fprintf(stderr, "[EXEC] env_create_srq: null argument\n");
        return NULL;
    }
    if (!rdma_get_context())
    {
        fprintf(stderr, "[EXEC] env_create_srq: RDMA context is NULL\n");
    }
    if (env->srq_count >= (int)(sizeof(env->srq) / sizeof(env->srq[0])))
    {
        fprintf(stderr,
                "[EXEC] env_create_srq: too many SRQ resources, ignore %s\n",
                srq_name);
        return NULL;
    }
    // 1. 先在资源表中找到 PD
    PdResource *pd_res = env_find_pd(env, pd_name);
    if (!pd_res || !pd_res->pd)
    {
        fprintf(stderr,
                "[EXEC] env_create_srq: PD '%s' not found or invalid\n",
                pd_name);
        return NULL;
    }
    struct ibv_srq_init_attr srq_init_attr;
    memset(&srq_init_attr, 0, sizeof(srq_init_attr));
    srq_init_attr.attr.max_wr = max_wr;
    srq_init_attr.attr.max_sge = max_sge;
    srq_init_attr.attr.srq_limit = srq_limit;
    struct ibv_srq *srq = ibv_create_srq(pd_res->pd, &srq_init_attr);
    if (!srq)
    {
        fprintf(stderr,
                "[EXEC] env_create_srq: ibv_create_srq failed for srq=%s (pd=%s)\n",
                srq_name, pd_name);
        return NULL;
    }
    SrqResource *slot = &env->srq[env->srq_count++];
    memset(slot, 0, sizeof(*slot));
    snprintf(slot->name, sizeof(slot->name), "%s", srq_name);
    slot->srq = srq;
    slot->pd = pd_res->pd;
    slot->max_wr = max_wr;
    slot->max_sge = max_sge;
    slot->srq_limit = srq_limit;
    fprintf(stderr,
            "[EXEC] CreateSRQ OK -> %s (srq=%p, pd=%s, max_wr=%d, max_sge=%d, srq_limit=%d)\n",
            slot->name, (void *)srq, pd_name, max_wr, max_sge, srq_limit);
    return slot;
}

CqResource *env_create_cq(ResourceEnv *env,
                          const char *cq_name,
                          int cqe,
                          void *cq_context,
                          struct ibv_comp_channel *channel,
                          int comp_vector)
{
    if (!env || !cq_name)
    {
        fprintf(stderr, "[EXEC] env_create_cq: null argument\n");
        return NULL;
    }
    if (!rdma_get_context())
    {
        fprintf(stderr, "[EXEC] env_create_cq: RDMA context is NULL\n");
    }
    if (env->cq_count >= (int)(sizeof(env->cq) / sizeof(env->cq[0])))
    {
        fprintf(stderr, "[EXEC] env_create_cq: too many CQ resources, ignore %s\n",
                cq_name);
        return NULL;
    }
    struct ibv_cq *cq = ibv_create_cq(g_ctx, cqe, cq_context, channel, comp_vector);
    if (!cq)
    {
        fprintf(stderr, "[EXEC] env_create_cq: ibv_create_cq failed for '%s'\n",

                cq_name);
        return NULL;
    }
    CqResource *slot = &env->cq[env->cq_count++];
    memset(slot, 0, sizeof(*slot));
    snprintf(slot->name, sizeof(slot->name), "%s", cq_name);
    slot->cq = cq;
    slot->cqe = cqe;
    slot->cq_context = cq_context;
    slot->channel = channel;
    slot->comp_vector = comp_vector;
    fprintf(stderr,
            "[EXEC] CreateCQ OK -> %s (cq=%p, cqe=%d, cq_context=%p, channel=%p, comp_vector=%d)\n",
            slot->name, (void *)cq, cqe, cq_context, (void *)channel, comp_vector);
    return slot;
}
// 真正做 dealloc + 从数组中移除
int env_dealloc_pd(ResourceEnv *env, const char *name)
{
    if (!env || !name)
    {
        fprintf(stderr, "[EXEC] env_dealloc_pd: null argument\n");
        return -1;
    }

    int idx = env_find_pd_index(env, name);
    if (idx < 0)
    {
        fprintf(stderr, "[EXEC] env_dealloc_pd: PD '%s' not found\n", name);
        return -1;
    }

    PdResource *pd_res = &env->pd[idx];
    if (!pd_res->pd)
    {
        fprintf(stderr, "[EXEC] env_dealloc_pd: PD '%s' has null pointer\n", name);
        return -1;
    }

    // 简单资源占用检查（避免先释放 PD 再释放 QP/MW）
    if (env_pd_in_use(env, pd_res->pd))
    {
        fprintf(stderr,
                "[EXEC] env_dealloc_pd: PD '%s' still in use, skip dealloc\n",
                name);
        return -1;
    }

    if (ibv_dealloc_pd(pd_res->pd) != 0)
    {
        fprintf(stderr,
                "[EXEC] env_dealloc_pd: ibv_dealloc_pd failed for '%s'\n",
                name);
        return -1;
    }

    fprintf(stderr, "[EXEC] DeallocPD OK -> %s\n", name);

    // 从数组中移除：用最后一个元素覆盖当前，再减计数，保持数组紧凑
    int last = env->pd_count - 1;
    if (idx != last)
    {
        env->pd[idx] = env->pd[last];
    }
    env->pd_count--;

    return 0;
}

int env_destroy_srq(ResourceEnv *env, const char *name)
{
    if (!env || !name)
    {
        fprintf(stderr, "[EXEC] env_destroy_srq: null argument\n");
        return -1;
    }

    int idx = env_find_srq_index(env, name);
    if (idx < 0)
    {
        fprintf(stderr, "[EXEC] env_destroy_srq: SRQ '%s' not found\n", name);
        return -1;
    }

    SrqResource *srq_res = &env->srq[idx];
    if (!srq_res->srq)
    {
        fprintf(stderr, "[EXEC] env_destroy_srq: SRQ '%s' has null pointer\n", name);
        return -1;
    }

    if (ibv_destroy_srq(srq_res->srq) != 0)
    {
        fprintf(stderr,
                "[EXEC] env_destroy_srq: ibv_destroy_srq failed for '%s'\n",
                name);
        return -1;
    }

    fprintf(stderr, "[EXEC] DestroySRQ OK -> %s\n", name);

    // 从数组中移除：用最后一个元素覆盖当前，再减计数，保持数组紧凑
    int last = env->srq_count - 1;
    if (idx != last)
    {
        env->srq[idx] = env->srq[last];
    }
    env->srq_count--;

    return 0;
}

// 简单线性扫描查找 PD
PdResource *env_find_pd(ResourceEnv *env, const char *name)
{
    if (!env || !name)
        return NULL;
    for (int i = 0; i < env->pd_count; i++)
    {
        if (strcmp(env->pd[i].name, name) == 0)
        {
            return &env->pd[i];
        }
    }
    return NULL;
}

// 查找 MW（可能后面会用到）
MwResource *env_find_mw(ResourceEnv *env, const char *name)
{
    if (!env || !name)
        return NULL;
    for (int i = 0; i < env->mw_count; i++)
    {
        if (strcmp(env->mw[i].name, name) == 0)
        {
            return &env->mw[i];
        }
    }
    return NULL;
}

// 找到 PD 在 env->pd[] 里的下标，找不到返回 -1
int env_find_pd_index(ResourceEnv *env, const char *name)
{
    if (!env || !name)
        return -1;
    for (int i = 0; i < env->pd_count; i++)
    {
        if (strcmp(env->pd[i].name, name) == 0)
        {
            return i;
        }
    }
    return -1;
}

// 简单检查：是否有资源还在使用这个 pd（可按需增强）
static int env_pd_in_use(ResourceEnv *env, struct ibv_pd *pd)
{
    if (!env || !pd)
        return 0;

    // 1) QP 是否引用这个 PD
    for (int i = 0; i < env->qp_count; i++)
    {
        if (env->qp[i].pd == pd)
        {
            return 1;
        }
    }

    // 2) MW 是否引用这个 PD
    for (int i = 0; i < env->mw_count; i++)
    {
        if (env->mw[i].pd == pd)
        {
            return 1;
        }
    }

    // 3) DM/MR 如果你有 pd 关联，也可以在这里检查

    return 0;
}

int env_find_srq_index(ResourceEnv *env, const char *name)
{
    if (!env || !name)
        return -1;
    for (int i = 0; i < env->srq_count; i++)
    {
        if (strcmp(env->srq[i].name, name) == 0)
        {
            return i;
        }
    }
    return -1;
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
    fprintf(stderr, "[RDMA] Teardown complete\n");
}

struct ibv_context *rdma_get_context(void)
{
    return g_ctx;
}