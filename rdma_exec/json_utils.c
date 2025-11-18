#include "json_utils.h"
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include <stdlib.h>

char *read_all_text(const char *path, long *out_len)
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

cJSON *obj_get(cJSON *obj, const char *key)
{
    if (!obj || !cJSON_IsObject(obj))
        return NULL;
    return cJSON_GetObjectItemCaseSensitive(obj, key);
}

const char *obj_get_string(cJSON *obj, const char *key)
{
    cJSON *item = obj_get(obj, key);
    if (item && cJSON_IsString(item) && item->valuestring)
    {
        return item->valuestring;
    }
    return NULL;
}

int obj_get_int(cJSON *obj, const char *key, int default_val)
{
    cJSON *item = obj_get(obj, key);
    if (item && cJSON_IsNumber(item))
    {
        return (int)item->valuedouble;
    }
    return default_val;
}

// 简化版解析：我们只按需解析 Int / String 两种情况
int parse_typed_value(cJSON *val_obj,
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

/*
 * json_get_res_name
 *
 * 从 JSON 中解析 ResourceValue 或 ConstantValue 类型的字符串引用。
 * 期望结构：
 *     "pd": { "type": "ResourceValue", "value": "pd0" }
 *
 * 失败时打印 warning 并返回 NULL。
 */
const char *json_get_res_name(cJSON *verb_obj, const char *key)
{
    if (!verb_obj || !key)
    {
        fprintf(stderr, "[WARN] json_get_res_name: null input\n");
        return NULL;
    }

    cJSON *spec = obj_get(verb_obj, key);
    if (!spec)
    {
        fprintf(stderr, "[WARN] json_get_res_name: missing field '%s'\n", key);
        return NULL;
    }

    const char *name = NULL;
    if (parse_typed_value(spec, VAL_KIND_STRING, NULL, &name) != 0 || !name)
    {
        fprintf(stderr,
                "[WARN] json_get_res_name: field '%s' has invalid ResourceValue\n",
                key);
        return NULL;
    }

    return name;
}

/*
 * json_get_int_field
 *
 * 解析 typed integer 字段，例如：
 *    "length":        { "type": "IntValue", "value": 4096 }
 *    "log_align_req": { "type": "IntValue", "value": 0 }
 *    "comp_mask":     { "type": "None", "value": null }
 *
 * 如果字段不存在或解析失败，返回 default_val。
 */
int json_get_int_field(cJSON *obj, const char *key, int default_val)
{
    if (!obj || !key)
    {
        fprintf(stderr, "[WARN] json_get_int_field: null input\n");
        return default_val;
    }

    cJSON *spec = obj_get(obj, key);
    if (!spec)
    {
        // silent fallback，符合你的使用场景
        return default_val;
    }

    int v = default_val;
    if (parse_typed_value(spec, VAL_KIND_INT, &v, NULL) != 0)
    {
        fprintf(stderr,
                "[WARN] json_get_int_field: field '%s' invalid, using default=%d\n",
                key, default_val);
        return default_val;
    }

    return v;
}