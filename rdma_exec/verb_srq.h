#pragma once
#include <cjson/cJSON.h>
#include "resource_env.h"

int handle_CreateSRQ(cJSON *verb_obj, ResourceEnv *env);  // struct ibv_srq * ibv_create_srq(struct ibv_pd * pd, struct ibv_srq_init_attr * srq_init_attr);
int handle_DestroySRQ(cJSON *verb_obj, ResourceEnv *env); // int ibv_destroy_srq(struct ibv_srq * srq);