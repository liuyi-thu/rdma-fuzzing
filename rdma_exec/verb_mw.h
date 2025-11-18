#pragma once
#include <cjson/cJSON.h>
#include "resource_env.h"

int handle_AllocMW(cJSON *verb_obj, ResourceEnv *env);
int handle_DeallocMW(cJSON *verb_obj, ResourceEnv *env);