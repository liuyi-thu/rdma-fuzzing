// runtime_resolver.c
#include "runtime_resolver.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <cjson/cJSON.h>
#include <arpa/inet.h>
static cJSON *g_root = NULL;


int parse_gid_str(const char *s, union ibv_gid *out) {
    // 尝试 inet_pton(AF_INET6)
    if (inet_pton(AF_INET6, s, out->raw) == 1) return 0;
    // 备用：解析 "xx:xx:..." 形式（可按需扩展）
    unsigned int b[16];
    if (sscanf(s,
        "%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x",
        &b[0],&b[1],&b[2],&b[3],&b[4],&b[5],&b[6],&b[7],&b[8],&b[9],&b[10],&b[11],&b[12],&b[13],&b[14],&b[15]) == 16) {
        for (int i=0;i<16;i++) out->raw[i] = (uint8_t)b[i];
        return 0;
    }
    fprintf(stderr, "bad GID string: %s\n", s);
    return -1;
}

// 读取整个文件
static char *rr_slurp(const char *path, long *out_sz) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = (char*)malloc(n + 1);
    if (!buf) { fclose(f); return NULL; }
    size_t got = fread(buf, 1, n, f);
    fclose(f);
    if ((long)got != n) { free(buf); return NULL; }
    buf[n] = 0;
    if (out_sz) *out_sz = n;
    return buf;
}

void rr_load_json_or_die(const char *path) {
    long sz = 0;
    char *text = rr_slurp(path, &sz);
    if (!text) { fprintf(stderr, "[rr] open failed: %s\n", path); exit(2); }
    g_root = cJSON_Parse(text);
    free(text);
    if (!g_root) {
        const char *ep = cJSON_GetErrorPtr();
        fprintf(stderr, "[rr] bad json at %s\n", ep ? ep : "(unknown)");
        exit(2);
    }
}

void rr_load_from_env_or_die(const char *envkey) {
    const char *p = getenv(envkey);
    if (!p) { fprintf(stderr, "[rr] set %s=/path/to/runtime.json\n", envkey); exit(2); }
    rr_load_json_or_die(p);
}

static cJSON* rr_child_by_name_or_index(cJSON *node, const char *name) {
    if (!node || !cJSON_IsObject(node)) return NULL;
    // 尝试对象名命中（例如 "QP0"）
    cJSON *v = cJSON_GetObjectItemCaseSensitive(node, name);
    if (v) return v;
    // 尝试数组访问表达式：Name[idx] 或纯 [idx]
    // 支持 "QP[0]" 或 "[0]"
    const char *lb = strchr(name, '[');
    if (!lb) return NULL;
    // 提取前缀和下标
    char prefix[128] = {0};
    int idx = -1;
    if (lb == name) {
        // 形如 "[0]"：数组名由上层提供
        if (sscanf(name, "[%d]", &idx) != 1) return NULL;
        // name 不带前缀，这里返回 NULL，交由上层处理
        return NULL;
    } else {
        size_t n = (size_t)(lb - name);
        if (n >= sizeof(prefix)) n = sizeof(prefix)-1;
        memcpy(prefix, name, n);
        const char *rb = strchr(lb, ']');
        if (!rb) return NULL;
        if (sscanf(lb, "[%d]", &idx) != 1) return NULL;
        // 找到 prefix 对象对应的数组
        cJSON *arr = cJSON_GetObjectItemCaseSensitive(node, prefix);
        if (!arr || !cJSON_IsArray(arr)) return NULL;
        return cJSON_GetArrayItem(arr, idx);
    }
}

static int rr_parse_token(const char *seg, char *name, int *opt_index, int *leading_index_only) {
    // 解析一个路径段：
    //   "QP"           => name="QP", index=-1
    //   "QP[0]"        => name="QP", index=0
    //   "[0]"          => name="",   index=0, leading_index_only=1
    *leading_index_only = 0;
    *opt_index = -1;
    const char *lb = strchr(seg, '[');
    if (!lb) { strncpy(name, seg, 127); name[127]=0; return 0; }
    if (lb == seg) {
        // "[0]"
        const char *rb = strchr(lb, ']');
        if (!rb) return -1;
        if (sscanf(lb, "[%d]", opt_index) != 1) return -1;
        name[0] = 0;
        *leading_index_only = 1;
        return 0;
    }
    // "QP[0]"
    size_t n = (size_t)(lb - seg);
    if (n > 127) n = 127;
    memcpy(name, seg, n);
    name[n] = 0;
    if (sscanf(lb, "[%d]", opt_index) != 1) return -1;
    return 0;
}

static cJSON* rr_walk_path(const char *key) {
    if (!g_root) { fprintf(stderr, "[rr] not loaded\n"); exit(2); }
    // 拆分 '.'，逐段查找。每段可带可选 [idx]
    char buf[512]; strncpy(buf, key, sizeof(buf)-1); buf[sizeof(buf)-1]=0;
    char *save = NULL;
    char *seg = strtok_r(buf, ".", &save);
    cJSON *cur = g_root;
    while (seg) {
        char name[128]; int idx, lead_idx;
        if (rr_parse_token(seg, name, &idx, &lead_idx) != 0) return NULL;

        if (name[0] != 0) {
            // 先按对象名取
            cJSON *next = cJSON_GetObjectItemCaseSensitive(cur, name);
            if (!next) {
                // 也许是 "Name[idx]" 整体在 child_by_name_or_index 里处理
                next = rr_child_by_name_or_index(cur, seg);
                if (!next) return NULL;
                cur = next;
            } else {
                // 如有 [idx]，再从 next 数组里取元素
                if (idx >= 0) {
                    if (!cJSON_IsArray(next)) return NULL;
                    next = cJSON_GetArrayItem(next, idx);
                    if (!next) return NULL;
                }
                cur = next;
            }
        } else {
            // 形如 "[idx]"：当前节点必须是数组
            if (!cJSON_IsArray(cur)) return NULL;
            cJSON *next = cJSON_GetArrayItem(cur, idx);
            if (!next) return NULL;
            cur = next;
        }

        seg = strtok_r(NULL, ".", &save);
    }
    return cur;
}

int rr_has(const char *key) {
    cJSON *n = rr_walk_path(key);
    return n != NULL;
}

uint32_t rr_u32(const char *key) {
    cJSON *n = rr_walk_path(key);
    if (!n || !cJSON_IsNumber(n)) { fprintf(stderr, "[rr] u32 missing: %s\n", key); exit(3); }
    return (uint32_t)n->valuedouble;
}

uint64_t rr_u64(const char *key) {
    cJSON *n = rr_walk_path(key);
    if (!n || !cJSON_IsNumber(n)) { fprintf(stderr, "[rr] u64 missing: %s\n", key); exit(3); }
    // 注意 cJSON number 是 double，足以表达 53bit；更大的数请用字符串/十六进制处理
    return (uint64_t)n->valuedouble;
}

const char* rr_str(const char *key) {
    cJSON *n = rr_walk_path(key);
    if (!n || !cJSON_IsString(n)) { fprintf(stderr, "[rr] str missing: %s\n", key); exit(3); }
    return n->valuestring;
}

void rr_dump(void) {
    if (!g_root) { fprintf(stderr, "[rr] not loaded\n"); return; }
    char *p = cJSON_Print(g_root);
    if (p) { fprintf(stderr, "[rr] JSON:\n%s\n", p); free(p); }
}

// === helpers: find array node by "remote.QP" / "local.MR" ===
static cJSON* rr_get_node(const char *key);   // 你已有 rr_walk_path，复用一下
extern cJSON *g_root;

// 简易封装：从 "remote.QP" 得到数组节点
static cJSON* rr_array_node_from_key(const char *arr_key) {
    // 复用已有路径 walker（把 arr_key 当完整路径）
    // 可直接调用你现有的 rr_walk_path；这里给个声明：
    extern cJSON* rr_walk_path(const char *key);
    cJSON *node = rr_walk_path(arr_key);
    if (!node || !cJSON_IsArray(node)) {
        fprintf(stderr, "[rr] not an array: %s\n", arr_key);
        exit(3);
    }
    return node;
}

static cJSON* rr_obj_by_id(cJSON *arr, const char *id) {
    for (cJSON *e = arr->child; e; e = e->next) {
        if (!cJSON_IsObject(e)) continue;
        cJSON *idv = cJSON_GetObjectItemCaseSensitive(e, "id");
        if (idv && cJSON_IsString(idv) && idv->valuestring && strcmp(idv->valuestring, id) == 0) {
            return e;
        }
    }
    return NULL;
}

static cJSON* rr_field_in_id(const char *arr_key, const char *id, const char *field) {
    cJSON *arr = rr_array_node_from_key(arr_key);
    cJSON *obj = rr_obj_by_id(arr, id);
    if (!obj) {
        fprintf(stderr, "[rr] id not found in %s: %s\n", arr_key, id);
        exit(3);
    }
    cJSON *fv = cJSON_GetObjectItemCaseSensitive(obj, field);
    if (!fv) {
        fprintf(stderr, "[rr] field not found: %s[%s].%s\n", arr_key, id, field);
        exit(3);
    }
    return fv;
}

uint32_t rr_u32_by_id(const char *arr_key, const char *id, const char *field) {
    cJSON *v = rr_field_in_id(arr_key, id, field);
    if (!cJSON_IsNumber(v)) { fprintf(stderr, "[rr] not number: %s[%s].%s\n", arr_key, id, field); exit(3); }
    return (uint32_t)v->valuedouble;
}

uint64_t rr_u64_by_id(const char *arr_key, const char *id, const char *field) {
    cJSON *v = rr_field_in_id(arr_key, id, field);
    if (!cJSON_IsNumber(v)) { fprintf(stderr, "[rr] not number: %s[%s].%s\n", arr_key, id, field); exit(3); }
    return (uint64_t)v->valuedouble;
}

const char* rr_str_by_id(const char *arr_key, const char *id, const char *field) {
    cJSON *v = rr_field_in_id(arr_key, id, field);
    if (!cJSON_IsString(v)) { fprintf(stderr, "[rr] not string: %s[%s].%s\n", arr_key, id, field); exit(3); }
    return v->valuestring;
}
