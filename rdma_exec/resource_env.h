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
    struct ibv_cq *send_cq;
    struct ibv_cq *recv_cq;
    struct ibv_srq *srq;
    void *qp_context;
    int cap_max_send_wr;
    int cap_max_recv_wr;
    int cap_max_send_sge;
    int cap_max_recv_sge;
    int cap_max_inline_data;
    int qp_type;
    int sq_sig_all;
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
    char *local_addr;
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
    char name[64];
    struct ibv_cq *cq;
    int cqe;
    void *cq_context;
    struct ibv_comp_channel *channel;
    int comp_vector;
} CqResource;

typedef struct
{
    char name[64];
    struct ibv_cq_ex *cq_ex;
    int cqe;
    void *cq_context;
    struct ibv_comp_channel *channel;
    int comp_vector;
    int wc_flags;
    int comp_mask;
    int flags;
    struct ibv_pd *parent_domain;
} CqExResource;

typedef struct
{
    char name[64];
    char *addr;
    size_t length;
} LocalBufferResource;

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

    CqResource cq[128];
    int cq_count;

    CqExResource cq_ex[128];
    int cq_ex_count;

    LocalBufferResource local_buf[256];
    int local_buf_count;

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
CqResource *env_create_cq(ResourceEnv *env,
                          const char *cq_name,
                          int cqe,
                          void *cq_context,
                          struct ibv_comp_channel *channel,
                          int comp_vector);
CqExResource *env_create_cq_ex(ResourceEnv *env,
                               const char *cq_name,
                               int cqe,
                               void *cq_context,
                               struct ibv_comp_channel *channel,
                               int comp_vector,
                               int wc_flags,
                               int comp_mask,
                               int flags,
                               struct ibv_pd *parent_domain);
MrResource *env_reg_mr(ResourceEnv *env,
                       const char *mr_name,
                       const char *pd_name,
                       const char *addr_name,
                       size_t length,
                       int access);
QpResource *env_create_qp(ResourceEnv *env,
                          const char *qp_name,
                          const char *pd_name,
                          const char *send_cq_name,
                          const char *recv_cq_name,
                          const char *srq_name,
                          void *qp_context,
                          int cap_max_send_wr,
                          int cap_max_recv_wr,
                          int cap_max_send_sge,
                          int cap_max_recv_sge,
                          int cap_max_inline_data,
                          int qp_type,
                          int sq_sig_all);

int env_modify_cq(ResourceEnv *env,
                  const char *cq_name,
                  int attr_mask,
                  int cq_count,
                  int cq_period);
int env_dealloc_pd(ResourceEnv *env, const char *name);
int env_destroy_srq(ResourceEnv *env, const char *name);

LocalBufferResource *env_alloc_local_buffer(ResourceEnv *env,
                                            const char *name,
                                            size_t length);

PdResource *env_find_pd(ResourceEnv *env, const char *name);
DmResource *env_find_dm(ResourceEnv *env, const char *name);
QpResource *env_find_qp(ResourceEnv *env, const char *name);
MwResource *env_find_mw(ResourceEnv *env, const char *name);
CqResource *env_find_cq(ResourceEnv *env, const char *name);
SrqResource *env_find_srq(ResourceEnv *env, const char *name);
int env_find_pd_index(ResourceEnv *env, const char *name);
// int env_pd_in_use(ResourceEnv *env, struct ibv_pd *pd); // should not be made public
int env_find_srq_index(ResourceEnv *env, const char *name);

int rdma_init_context(const char *preferred_name);
void rdma_teardown_context(void);
struct ibv_context *rdma_get_context(void);