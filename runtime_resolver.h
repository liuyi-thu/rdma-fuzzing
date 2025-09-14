// runtime_resolver.h
#pragma once
#include <stdint.h>
#include <infiniband/verbs.h>

#ifdef __cplusplus
extern "C"
{
#endif

    // 加载：从环境变量指定的 JSON 路径读取（如 RDMA_FUZZ_RUNTIME=/path/to/runtime.json）
    void rr_load_from_env_or_die(const char *envkey);
    // 或者直接加载某个路径
    void rr_load_json_or_die(const char *path);

    // 取值 API：key 形如 "remote.QP[0].qpn" / "local.MR[0].lkey"
    // 也支持对象名："remote.QP0.qpn"
    uint32_t rr_u32(const char *key);
    uint64_t rr_u64(const char *key);
    const char *rr_str(const char *key); // 返回内部指针，请及时复制
    int rr_has(const char *key);         // 存在性判断（1/0）

    // --- by-id lookup API ---
    // 使用：rr_u32_by_id("remote.QP", "peer0", "qpn")
    uint32_t rr_u32_by_id(const char *arr_key, const char *id, const char *field);
    uint64_t rr_u64_by_id(const char *arr_key, const char *id, const char *field);
    const char *rr_str_by_id(const char *arr_key, const char *id, const char *field);

    int parse_gid_str(const char *s, union ibv_gid *out); // 解析 GID 字符串为 union ibv_gid

    // 调试：打印 JSON 树（可选）
    void rr_dump(void);

    // runtime_resolver.h 追加
    int rr_has_by_id(const char *arr_key, const char *id, const char *field);

    uint32_t rr_try_u32_by_id(const char *arr_key, const char *id, const char *field, uint32_t def);
    uint64_t rr_try_u64_by_id(const char *arr_key, const char *id, const char *field, uint64_t def);
    const char *rr_try_str_by_id(const char *arr_key, const char *id, const char *field, const char *def);
    uint32_t rr_try_u32(const char *key, uint32_t default_val);
    const char *rr_try_str(const char *key, const char *default_val);
    void rr_free(void); // 释放当前 JSON 树

// runtime_resolver.h
#define RR_U32_ID(kind, id, field) rr_u32_by_id((kind), (id), (field))
#define RR_U64_ID(kind, id, field) rr_u64_by_id((kind), (id), (field))
#define RR_STR_ID(kind, id, field) rr_str_by_id((kind), (id), (field))

#define RR_TRY_U32_ID(kind, id, field, def) rr_try_u32_by_id((kind), (id), (field), (def))
#define RR_TRY_U64_ID(kind, id, field, def) rr_try_u64_by_id((kind), (id), (field), (def))
#define RR_TRY_STR_ID(kind, id, field, def) rr_try_str_by_id((kind), (id), (field), (def))
#ifdef __cplusplus
}
#endif
