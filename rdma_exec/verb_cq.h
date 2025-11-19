#pragma once
#include <cjson/cJSON.h>
#include "resource_env.h"

int handle_CreateCQ(cJSON *verb_obj, ResourceEnv *env);
// struct ibv_cq * ibv_create_cq(struct ibv_context * context, int cqe, void * cq_context, struct ibv_comp_channel * channel, int comp_vector);
int handle_CreateCQEx(cJSON *verb_obj, ResourceEnv *env);
// struct ibv_cq_ex * ibv_create_cq_ex(struct ibv_context * context, struct ibv_cq_init_attr_ex * cq_attr)
int handle_ModifyCQ(cJSON *verb_obj, ResourceEnv *env);
// int ibv_modify_cq(struct ibv_cq * cq, struct ibv_modify_cq_attr * attr);
int handle_DestroyCQ(cJSON *verb_obj, ResourceEnv *env);
// int ibv_destroy_cq(struct ibv_cq * cq);