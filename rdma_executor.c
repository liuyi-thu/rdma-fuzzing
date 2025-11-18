// rdma_executor.c
// Skeleton: 读取 JSON 程序，解析并执行 AllocPD / AllocDM 等 Verb。
// 依赖 cJSON: https://github.com/DaveGamble/cJSON
//
// 用法:
//   gcc -O2 rdma_executor.c cJSON.c -o rdma_executor
//   ./rdma_executor program.json

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>

#include <cjson/cJSON.h>

// ======================== 资源环境定义 ========================

typedef struct
{
    char name[64];
} PdResource;

typedef struct
{
    char name[64];
    int length;
    int log_align_req;
    int comp_mask;
} DmResource;

typedef struct
{
    PdResource pd[128];
    int pd_count;

    DmResource dm[128];
    int dm_count;

    // 简易 meta：这里只存 trace_id，当示例
    char trace_id[128];
} ResourceEnv;

static void env_init(ResourceEnv *env)
{
    memset(env, 0, sizeof(*env));
}

static void env_alloc_pd(ResourceEnv *env, const char *name)
{
    if (env->pd_count >= (int)(sizeof(env->pd) / sizeof(env->pd[0])))
    {
        fprintf(stderr, "[EXEC] Too many PD resources, ignoring %s\n", name);
        return;
    }
    PdResource *pd = &env->pd[env->pd_count++];
    snprintf(pd->name, sizeof(pd->name), "%s", name);
    // TODO: 替换成真实的 ibv_alloc_pd 调用，并保存 ibv_pd* 句柄
    fprintf(stderr, "[EXEC] AllocPD -> %s\n", pd->name);
}

static void env_alloc_dm(ResourceEnv *env,
                         const char *name,
                         int length,
                         int log_align_req,
                         int comp_mask)
{
    if (env->dm_count >= (int)(sizeof(env->dm) / sizeof(env->dm[0])))
    {
        fprintf(stderr, "[EXEC] Too many DM resources, ignoring %s\n", name);
        return;
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
}

// ======================== 工具函数：读文件 ========================

static char *read_all_text(const char *path, long *out_len)
{
    FILE *f = fopen(path, "rb");
    if (!f)
    {
        fprintf(stderr, "[ERR] fopen('%s'): %s\n", path, strerror(errno));
        return NULL;
    }
    if (fseek(f, 0, SEEK_END) != 0)
    {
        fclose(f);
        return NULL;
    }
    long sz = ftell(f);
    if (sz < 0)
    {
        fclose(f);
        return NULL;
    }
    rewind(f);

    char *buf = (char *)malloc((size_t)sz + 1);
    if (!buf)
    {
        fclose(f);
        return NULL;
    }
    size_t n = fread(buf, 1, (size_t)sz, f);
    fclose(f);
    if (n != (size_t)sz)
    {
        free(buf);
        return NULL;
    }
    buf[sz] = '\0';
    if (out_len)
        *out_len = sz;
    return buf;
}

// ======================== JSON helper 函数 ========================

static cJSON *obj_get(cJSON *obj, const char *key)
{
    if (!obj || !cJSON_IsObject(obj))
        return NULL;
    return cJSON_GetObjectItemCaseSensitive(obj, key);
}

static const char *obj_get_string(cJSON *obj, const char *key)
{
    cJSON *item = obj_get(obj, key);
    if (item && cJSON_IsString(item) && item->valuestring)
    {
        return item->valuestring;
    }
    return NULL;
}

static int obj_get_int(cJSON *obj, const char *key, int default_val)
{
    cJSON *item = obj_get(obj, key);
    if (item && cJSON_IsNumber(item))
    {
        return (int)item->valuedouble;
    }
    return default_val;
}

// typed value: { "type": "...", "value": ... }
typedef enum
{
    VAL_KIND_ANY = 0,
    VAL_KIND_INT,
    VAL_KIND_STRING
} ValueKind;

// 简化版解析：我们只按需解析 Int / String 两种情况
static int parse_typed_value(cJSON *val_obj,
                             ValueKind kind,
                             int *out_int,
                             const char **out_str)
{
    if (!val_obj || !cJSON_IsObject(val_obj))
        return -1;
    cJSON *type_item = obj_get(val_obj, "type");
    cJSON *value_item = obj_get(val_obj, "value");
    if (!type_item || !cJSON_IsString(type_item) || !value_item)
    {
        return -1;
    }
    const char *t = type_item->valuestring;
    if (!t)
        return -1;

    if (kind == VAL_KIND_INT)
    {
        // IntValue 或 ConstantValue (数字)
        if (strcmp(t, "IntValue") == 0 && cJSON_IsNumber(value_item))
        {
            if (out_int)
                *out_int = (int)value_item->valuedouble;
            return 0;
        }
        // 如果以后你支持 ConstantValue(number) 也可以允许
        if (strcmp(t, "ConstantValue") == 0 && cJSON_IsNumber(value_item))
        {
            if (out_int)
                *out_int = (int)value_item->valuedouble;
            return 0;
        }
        // None -> 返回 0（或你自定义）
        if (strcmp(t, "None") == 0)
        {
            if (out_int)
                *out_int = 0;
            return 0;
        }
        return -1;
    }
    else if (kind == VAL_KIND_STRING)
    {
        // ResourceValue / ConstantValue (string)
        if ((strcmp(t, "ResourceValue") == 0 || strcmp(t, "ConstantValue") == 0) && cJSON_IsString(value_item) && value_item->valuestring)
        {
            if (out_str)
                *out_str = value_item->valuestring;
            return 0;
        }
        // None -> 返回 NULL
        if (strcmp(t, "None") == 0)
        {
            if (out_str)
                *out_str = NULL;
            return 0;
        }
        return -1;
    }
    else
    {
        // 任意类型：简单返回 string/int 之一
        if (cJSON_IsString(value_item))
        {
            if (out_str)
                *out_str = value_item->valuestring;
            return 0;
        }
        if (cJSON_IsNumber(value_item))
        {
            if (out_int)
                *out_int = (int)value_item->valuedouble;
            return 0;
        }
        return -1;
    }
}

// ======================== Verb 执行 ========================

static void exec_verb(cJSON *verb_obj, ResourceEnv *env)
{
    if (!verb_obj || !cJSON_IsObject(verb_obj))
    {
        fprintf(stderr, "[WARN] Invalid verb object\n");
        return;
    }

    const char *verb_name = obj_get_string(verb_obj, "verb");
    if (!verb_name)
    {
        fprintf(stderr, "[WARN] Verb missing 'verb' field\n");
        return;
    }

    // -------- GetDeviceGUID 示例 --------
    if (strcmp(verb_name, "GetDeviceGUID") == 0)
    {
        cJSON *device_spec = obj_get(verb_obj, "device");
        cJSON *output_spec = obj_get(verb_obj, "output");
        const char *device_str = NULL;
        const char *output_name = NULL;

        parse_typed_value(device_spec, VAL_KIND_STRING, NULL, &device_str);
        parse_typed_value(output_spec, VAL_KIND_STRING, NULL, &output_name);

        if (!device_str || !output_name)
        {
            fprintf(stderr, "[WARN] GetDeviceGUID missing device/output\n");
            return;
        }

        // TODO: 实际场景：调用 ibv_get_device_list / query GUID
        char guid_buf[128];
        snprintf(guid_buf, sizeof(guid_buf), "fake-guid-for-%s", device_str);

        fprintf(stderr, "[EXEC] GetDeviceGUID device=%s -> %s=%s\n",
                device_str, output_name, guid_buf);

        // 简单示例：把 trace_id 设置为这个 guid（佛系示例）
        snprintf(env->trace_id, sizeof(env->trace_id), "%s", guid_buf);
        return;
    }

    // -------- AllocPD --------
    if (strcmp(verb_name, "AllocPD") == 0)
    {
        cJSON *pd_spec = obj_get(verb_obj, "pd");
        const char *pd_name = NULL;
        if (parse_typed_value(pd_spec, VAL_KIND_STRING, NULL, &pd_name) != 0 || !pd_name)
        {
            fprintf(stderr, "[WARN] AllocPD missing or invalid 'pd'\n");
            return;
        }
        env_alloc_pd(env, pd_name);
        return;
    }

    // -------- AllocDM --------
    if (strcmp(verb_name, "AllocDM") == 0)
    {
        cJSON *dm_spec = obj_get(verb_obj, "dm");
        cJSON *attr_obj = obj_get(verb_obj, "attr_obj");
        const char *dm_name = NULL;
        int length = 0;
        int log_align_req = 0;
        int comp_mask = 0;

        if (parse_typed_value(dm_spec, VAL_KIND_STRING, NULL, &dm_name) != 0 || !dm_name)
        {
            fprintf(stderr, "[WARN] AllocDM missing or invalid 'dm'\n");
            return;
        }

        if (!attr_obj || !cJSON_IsObject(attr_obj))
        {
            fprintf(stderr, "[WARN] AllocDM missing 'attr_obj'\n");
            return;
        }

        // attr_obj: { "verb": "IbvAllocDmAttr", "length": {..}, "log_align_req": {..}, "comp_mask": {..} }
        cJSON *length_spec = obj_get(attr_obj, "length");
        cJSON *log_align_spec = obj_get(attr_obj, "log_align_req");
        cJSON *comp_mask_spec = obj_get(attr_obj, "comp_mask");

        parse_typed_value(length_spec, VAL_KIND_INT, &length, NULL);
        parse_typed_value(log_align_spec, VAL_KIND_INT, &log_align_req, NULL);
        parse_typed_value(comp_mask_spec, VAL_KIND_INT, &comp_mask, NULL);

        env_alloc_dm(env, dm_name, length, log_align_req, comp_mask);
        return;
    }

    // -------- 未实现的 verb --------
    fprintf(stderr, "[WARN] Unsupported verb '%s'\n", verb_name);
}

// ======================== 程序入口 ========================

static int run_program_from_json(const char *json_text)
{
    cJSON *root = cJSON_Parse(json_text);
    if (!root)
    {
        const char *err = cJSON_GetErrorPtr();
        fprintf(stderr, "[ERR] JSON parse error near: %s\n", err ? err : "<unknown>");
        return 1;
    }

    int version = obj_get_int(root, "version", 1);
    if (version != 1)
    {
        fprintf(stderr, "[WARN] Unsupported program version: %d\n", version);
    }

    ResourceEnv env;
    env_init(&env);

    // 解析 meta.trace_id
    cJSON *meta = obj_get(root, "meta");
    if (meta && cJSON_IsObject(meta))
    {
        const char *tid = obj_get_string(meta, "trace_id");
        if (tid)
        {
            snprintf(env.trace_id, sizeof(env.trace_id), "%s", tid);
        }
    }

    // 解析 program 数组
    cJSON *program = obj_get(root, "program");
    if (!program || !cJSON_IsArray(program))
    {
        fprintf(stderr, "[ERR] 'program' must be an array\n");
        cJSON_Delete(root);
        return 1;
    }

    int prog_len = cJSON_GetArraySize(program);
    fprintf(stderr, "[INFO] Running program: %d verbs, trace_id=%s\n",
            prog_len, env.trace_id[0] ? env.trace_id : "(none)");

    for (int i = 0; i < prog_len; i++)
    {
        cJSON *verb_obj = cJSON_GetArrayItem(program, i);
        fprintf(stderr, "[INFO] === Verb #%d ===\n", i);
        exec_verb(verb_obj, &env);
    }

    fprintf(stderr, "[INFO] Program finished. PD count=%d, DM count=%d\n",
            env.pd_count, env.dm_count);

    cJSON_Delete(root);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc < 2)
    {
        fprintf(stderr, "Usage: %s program.json\n", argv[0]);
        return 1;
    }

    const char *path = argv[1];
    long len = 0;
    char *text = read_all_text(path, &len);
    if (!text)
    {
        fprintf(stderr, "[ERR] Failed to read file: %s\n", path);
        return 1;
    }

    int ret = run_program_from_json(text);
    free(text);
    return ret;
}