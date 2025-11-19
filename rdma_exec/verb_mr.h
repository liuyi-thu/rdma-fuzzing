#pragma once
#include <cjson/cJSON.h>
#include "resource_env.h"

int handle_AllocNullMR(cJSON *verb_obj, ResourceEnv *env);
int handle_RegMR(cJSON *verb_obj, ResourceEnv *env);