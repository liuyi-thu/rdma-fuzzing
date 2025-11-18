#pragma once
#include <cjson/cJSON.h>
#include "resource_env.h"

int handle_AllocPD(cJSON *verb_obj, ResourceEnv *env);
int handle_DeallocPD(cJSON *verb_obj, ResourceEnv *env); // 将来可能有
                                                         // 其他 PD 相关 verbs ...