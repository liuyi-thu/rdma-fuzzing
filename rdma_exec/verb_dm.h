#pragma once
#include <cjson/cJSON.h>
#include "resource_env.h"

int handle_AllocDM(cJSON *verb_obj, ResourceEnv *env);
// 将来可能还有 handle_FreeDM 等