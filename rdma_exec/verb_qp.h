#pragma once
#include <cjson/cJSON.h>
#include "resource_env.h"

int handle_CreateQP(cJSON *verb_obj, ResourceEnv *env);
int handle_CreateQPEx(cJSON *verb_obj, ResourceEnv *env);
int handle_ModifyQP(cJSON *verb_obj, ResourceEnv *env);
int handle_DestroyQP(cJSON *verb_obj, ResourceEnv *env);
int handle_PostSend(cJSON *verb_obj, ResourceEnv *env);
int handle_PostRecv(cJSON *verb_obj, ResourceEnv *env);
// ... 其它你需要的