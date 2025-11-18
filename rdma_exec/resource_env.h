#pragma once
#include <infiniband/verbs.h>

typedef struct
{
    char name[64];
    struct ibv_pd *pd;
} PdResource;

typedef struct
{
    char name[64];
    int length;
    int log_align_req;
    int comp_mask;
    struct ibv_dm *dm;
} DmResource;

typedef struct
{
    char name[64];
    struct ibv_qp *qp;
    // 将来可以加 qp_state、关联的 pd/cq 等元数据
} QpResource;

typedef struct
{
    PdResource pd[128];
    int pd_count;

    DmResource dm[128];
    int dm_count;

    QpResource qp[128];
    int qp_count;

    char trace_id[128]; // 从 meta 里读出来的可选信息
} ResourceEnv;

void env_init(ResourceEnv *env);

PdResource *env_alloc_pd(ResourceEnv *env, const char *name);
DmResource *env_alloc_dm(ResourceEnv *env,
                         const char *name,
                         int length,
                         int log_align_req,
                         int comp_mask);
QpResource *env_alloc_qp(ResourceEnv *env,
                         const char *name
                         /* 这里将来可以补齐 qp_init_attr 等 */
);

PdResource *env_find_pd(ResourceEnv *env, const char *name);
DmResource *env_find_dm(ResourceEnv *env, const char *name);
QpResource *env_find_qp(ResourceEnv *env, const char *name);

int rdma_init_context(const char *preferred_name);
void rdma_teardown_context(void);