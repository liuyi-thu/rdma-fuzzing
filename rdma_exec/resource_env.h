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
    struct ibv_pd *pd;
    // 将来可以加 qp_state、关联的 pd/cq 等元数据
} QpResource;
typedef struct
{
    char name[64];
    struct ibv_mw *mw;
    enum ibv_mw_type type;
    struct ibv_pd *pd; // 持有指向 PD 的指针（可选，但挺有用）
} MwResource;

typedef struct
{
    char name[64];
    struct ibv_mr *mr;
    struct ibv_pd *pd;
    size_t length;
    int access;
    // 将来可以加更多 MR 相关的元数据
} MrResource;

typedef struct
{
    char name[64];
    struct ibv_td *td;
    int comp_mask;
} TdResource;

typedef struct
{
    char name[64];
    struct ibv_srq *srq;
    struct ibv_pd *pd;
    int max_wr;
    int max_sge;
    int srq_limit;
} SrqResource;

typedef struct
{
    PdResource pd[128];
    int pd_count;

    DmResource dm[128];
    int dm_count;

    QpResource qp[128];
    int qp_count;

    MwResource mw[128];
    int mw_count;

    MrResource mr[128];
    int mr_count;

    TdResource td[64];
    int td_count;

    SrqResource srq[64];
    int srq_count;

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
MwResource *env_alloc_mw(ResourceEnv *env,
                         const char *mw_name,
                         const char *pd_name,
                         enum ibv_mw_type type);
MrResource *env_alloc_null_mr(ResourceEnv *env,
                              const char *mr_name,
                              const char *pd_name);
TdResource *env_alloc_td(ResourceEnv *env,
                         const char *td_name,
                         int comp_mask);
SrqResource *env_create_srq(ResourceEnv *env,
                            const char *srq_name,
                            const char *pd_name,
                            int max_wr,
                            int max_sge,
                            int srq_limit);

int env_dealloc_pd(ResourceEnv *env, const char *name);
int env_destroy_srq(ResourceEnv *env, const char *name);

PdResource *env_find_pd(ResourceEnv *env, const char *name);
DmResource *env_find_dm(ResourceEnv *env, const char *name);
QpResource *env_find_qp(ResourceEnv *env, const char *name);
MwResource *env_find_mw(ResourceEnv *env, const char *name);
int env_find_pd_index(ResourceEnv *env, const char *name);
// int env_pd_in_use(ResourceEnv *env, struct ibv_pd *pd); // should not be made public
int env_find_srq_index(ResourceEnv *env, const char *name);

int rdma_init_context(const char *preferred_name);
void rdma_teardown_context(void);
struct ibv_context *rdma_get_context(void);