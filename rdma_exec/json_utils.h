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