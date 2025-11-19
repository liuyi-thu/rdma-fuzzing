#pragma once
#include <cjson/cJSON.h>
#include "resource_env.h"

int handle_AllocTD(cJSON *verb_obj, ResourceEnv *env); // struct ibv_td * ibv_alloc_td(struct ibv_context * context, struct ibv_td_init_attr * init_attr);