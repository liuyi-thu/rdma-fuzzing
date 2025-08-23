// runtime_resolver.h
#pragma once
#include <stdint.h>
#include <infiniband/verbs.h>

#ifdef __cplusplus
extern "C" {
#endif

// 加载：从环境变量指定的 JSON 路径读取（如 RDMA_FUZZ_RUNTIME=/path/to/runtime.json）
void rr_load_from_env_or_die(const char *envkey);
// 或者直接加载某个路径
void rr_load_json_or_die(const char *path);

// 取值 API：key 形如 "remote.QP[0].qpn" / "local.MR[0].lkey"
// 也支持对象名："remote.QP0.qpn"
uint32_t rr_u32(const char *key);
uint64_t rr_u64(const char *key);
const char* rr_str(const char *key);     // 返回内部指针，请及时复制
int rr_has(const char *key);             // 存在性判断（1/0）

// --- by-id lookup API ---
// 使用：rr_u32_by_id("remote.QP", "peer0", "qpn")
uint32_t rr_u32_by_id(const char *arr_key, const char *id, const char *field);
uint64_t rr_u64_by_id(const char *arr_key, const char *id, const char *field);
const char* rr_str_by_id(const char *arr_key, const char *id, const char *field);

int parse_gid_str(const char *s, union ibv_gid *out); // 解析 GID 字符串为 union ibv_gid

// 调试：打印 JSON 树（可选）
void rr_dump(void);

#ifdef __cplusplus
}
#endif
