#pragma once
#include <cjson/cJSON.h>
#include "resource_env.h"

typedef int (*VerbHandler)(cJSON *verb_obj, ResourceEnv *env);

typedef struct
{
    const char *name; // "AllocPD", "AllocDM", "CreateQP", ...
    VerbHandler handler;
} VerbEntry;

// 对外只暴露这个函数
void exec_verb(cJSON *verb_obj, ResourceEnv *env);