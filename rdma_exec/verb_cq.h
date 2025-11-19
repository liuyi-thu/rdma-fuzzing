#pragma once
#include <cjson/cJSON.h>
#include "resource_env.h"

int handle_CreateCQ(cJSON *verb_obj, ResourceEnv *env);
// struct ibv_cq * ibv_create_cq(struct ibv_context * context, int cqe, void * cq_context, struct ibv_comp_channel * channel, int comp_vector);
