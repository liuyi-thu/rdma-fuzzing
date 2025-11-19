#pragma once
#include <cjson/cJSON.h>

char *read_all_text(const char *path, long *out_len);

cJSON *obj_get(cJSON *obj, const char *key);
const char *obj_get_string(cJSON *obj, const char *key);
int obj_get_int(cJSON *obj, const char *key, int default_val);

typedef enum
{
    VAL_KIND_ANY = 0,
    VAL_KIND_INT,
    VAL_KIND_STRING
} ValueKind;

int parse_typed_value(cJSON *val_obj,
                      ValueKind kind,
                      int *out_int,
                      const char **out_str);

// 便捷 wrapper，用于 verb handler 里减少样板代码：
const char *json_get_res_name(cJSON *verb_obj, const char *key);
int json_get_int_field(cJSON *obj, const char *key, int default_val);

typedef struct
{
    const char *name; // 比如 "IBV_ACCESS_LOCAL_WRITE"
    int value;        // 比如 IBV_ACCESS_LOCAL_WRITE
} JsonFlagSpec;

/**
 * 解析形如：
 *   "access": { "type": "FlagValue",
 *               "value": "IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ" }
 * 或者直接 IntValue：
 *   "access": { "type": "IntValue",
 *               "value": 7 }
 *
 * 参数：
 *   obj        - 包含该字段的 JSON 对象
 *   key        - 字段名，例如 "access"
 *   table      - 名字到位掩码的映射表
 *   table_len  - 映射表元素个数
 *   default_val- 字段不存在或解析失败时返回的默认值
 */
int json_get_flag_field(cJSON *obj,
                        const char *key,
                        const JsonFlagSpec *table,
                        size_t table_len,
                        int default_val);

typedef struct
{
    const char *name; // 比如 "IBV_MW_TYPE_1"
    int value;        // 比如 IBV_MW_TYPE_1
} JsonEnumSpec;

/**
 * 解析形如：
 *   "mw_type": { "type": "EnumValue",
 *                "value": "IBV_MW_TYPE_1" }
 * 或者直接是整数：
 *   "mw_type": { "type": "IntValue",
 *                "value": 1 }
 *
 * 参数：
 *   obj        - 包含该字段的 JSON 对象
 *   key        - 字段名，例如 "mw_type"
 *   table      - 名字到枚举值的映射表
 *   table_len  - 映射表元素个数
 *   default_val- 字段不存在或解析失败时返回的默认值
 */
int json_get_enum_field(cJSON *obj,
                        const char *key,
                        const JsonEnumSpec *table,
                        size_t table_len,
                        int default_val);