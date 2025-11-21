#include "json_utils.h"
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include <stdlib.h>
#include <ctype.h>

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
        // FlagValue (数字)
        if (strcmp(t, "FlagValue") == 0 && cJSON_IsNumber(value_item))
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
        if ((strcmp(t, "ResourceValue") == 0 || strcmp(t, "ConstantValue") == 0 || strcmp(t, "EnumValue") || strcmp(t, "FlagValue")) && cJSON_IsString(value_item) && value_item->valuestring)
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
        fprintf(stderr, "[WARN] json_get_int_field: field '%s' null input, using default=%d\n", key, default_val);
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

const char *json_get_str_field(cJSON *obj, const char *key, const char *default_val)
{
    if (!obj || !key)
    {
        fprintf(stderr, "[WARN] json_get_str_field: field '%s' null input, using default=%s\n", key, default_val);
        return default_val;
    }

    cJSON *spec = obj_get(obj, key);
    if (!spec)
    {
        // silent fallback，符合你的使用场景
        return default_val;
    }

    const char *v = default_val;
    if (parse_typed_value(spec, VAL_KIND_STRING, NULL, &v) != 0 || v)
    {
        fprintf(stderr,
                "[WARN] json_get_str_field: field '%s' invalid, using default=%s\n",
                key, default_val);
        return default_val;
    }

    return v;
}

// 简单的就地 trim 工具
static char *trim_spaces(char *s)
{
    if (!s)
        return s;
    while (*s && isspace((unsigned char)*s))
        s++;
    char *end = s + strlen(s);
    while (end > s && isspace((unsigned char)end[-1]))
    {
        end--;
    }
    *end = '\0';
    return s;
}

int json_get_flag_field(cJSON *obj,
                        const char *key,
                        const JsonFlagSpec *table,
                        size_t table_len,
                        int default_val)
{
    if (!obj || !key)
    {
        fprintf(stderr, "[WARN] json_get_flag_field: null obj or key\n");
        return default_val;
    }

    cJSON *spec = obj_get(obj, key);
    if (!spec)
    {
        // 字段不存在，直接用默认值
        return default_val;
    }

    int v_int;
    const char *v_str = NULL;

    /* 1. 优先：尝试解析成整数（IntValue / ConstantValue 为数值） */
    if (parse_typed_value(spec, VAL_KIND_INT, &v_int, NULL) == 0)
    {
        return v_int;
    }

    /* 2. 再尝试解析成字符串：FlagValue / ConstantValue 为字符串 */
    cJSON *type_item = cJSON_GetObjectItemCaseSensitive(spec, "type");
    cJSON *value_item = cJSON_GetObjectItemCaseSensitive(spec, "value");

    if (!cJSON_IsString(type_item) || !type_item->valuestring || !value_item)
    {
        fprintf(stderr,
                "[WARN] json_get_flag_field: field '%s' has invalid typed value\n",
                key);
        return default_val;
    }

    const char *type_str = type_item->valuestring;

    // 只在 FlagValue 或字符串 ConstantValue 时当作 flag 表达式
    if (!(strcmp(type_str, "FlagValue") == 0 ||
          strcmp(type_str, "EnumValue") == 0 ||
          (strcmp(type_str, "ConstantValue") == 0 && cJSON_IsString(value_item))))
    {
        fprintf(stderr,
                "[WARN] json_get_flag_field: field '%s' type '%s' not supported for flags\n",
                key, type_str);
        return default_val;
    }

    if (!cJSON_IsString(value_item) || !value_item->valuestring)
    {
        fprintf(stderr,
                "[WARN] json_get_flag_field: field '%s' value is not string\n",
                key);
        return default_val;
    }

    // 拷贝一份字符串做就地切分
    char buf[512];
    strncpy(buf, value_item->valuestring, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';

    int result = 0;
    int matched_any = 0;

    // 按 '|' 切分，如 "A | B | C"
    char *saveptr = NULL;
    for (char *tok = strtok_r(buf, "|", &saveptr);
         tok != NULL;
         tok = strtok_r(NULL, "|", &saveptr))
    {

        char *name = trim_spaces(tok);
        if (*name == '\0')
            continue;

        int found = 0;
        for (size_t i = 0; i < table_len; i++)
        {
            if (strcmp(name, table[i].name) == 0)
            {
                result |= table[i].value;
                found = 1;
                matched_any = 1;
                break;
            }
        }
        if (!found)
        {
            fprintf(stderr,
                    "[WARN] json_get_flag_field: unknown flag token '%s' in field '%s'\n",
                    name, key);
        }
    }

    if (!matched_any)
    {
        fprintf(stderr,
                "[WARN] json_get_flag_field: no valid flags found in field '%s', use default=%d\n",
                key, default_val);
        return default_val;
    }

    return result;
}

int json_get_enum_field(cJSON *obj,
                        const char *key,
                        const JsonEnumSpec *table,
                        size_t table_len,
                        int default_val)
{
    if (!obj || !key)
    {
        fprintf(stderr, "[WARN] json_get_enum_field: null obj or key\n");
        return default_val;
    }

    cJSON *spec = obj_get(obj, key);
    if (!spec)
    {
        // 字段不存在，直接返回默认值
        return default_val;
    }

    int v_int;
    const char *v_str = NULL;

    /* 1) 优先尝试解析成整数：
     *    支持 IntValue / ConstantValue 为整数 的情况，比如：
     *      "mw_type": { "type": "IntValue", "value": 1 }
     */
    if (parse_typed_value(spec, VAL_KIND_INT, &v_int, NULL) == 0)
    {
        return v_int;
    }

    /* 2) 再尝试解析成字符串枚举名：
     *    支持 EnumValue / ConstantValue 为字符串，比如：
     *      "mw_type": { "type": "EnumValue",
     *                   "value": "IBV_MW_TYPE_1" }
     */
    if (parse_typed_value(spec, VAL_KIND_STRING, NULL, &v_str) != 0 || !v_str)
    {
        fprintf(stderr,
                "[WARN] json_get_enum_field: field '%s' is neither int nor string\n",
                key);
        return default_val;
    }

    for (size_t i = 0; i < table_len; i++)
    {
        if (strcmp(v_str, table[i].name) == 0)
        {
            return table[i].value;
        }
    }

    fprintf(stderr,
            "[WARN] json_get_enum_field: unknown enum '%s' in field '%s', use default=%d\n",
            v_str, key, default_val);
    return default_val;
}