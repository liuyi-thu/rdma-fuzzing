#include "verb_flow.h"
#include "json_utils.h"
#include <stdio.h>

static const JsonEnumSpec flow_attr_type_table[] = {
    {"IBV_FLOW_ATTR_NORMAL", IBV_FLOW_ATTR_NORMAL},
    {"IBV_FLOW_ATTR_ALL_DEFAULT", IBV_FLOW_ATTR_ALL_DEFAULT},
    {"IBV_FLOW_ATTR_MC_DEFAULT", IBV_FLOW_ATTR_MC_DEFAULT},
    {"IBV_FLOW_ATTR_SNIFFER", IBV_FLOW_ATTR_SNIFFER},
};

static const JsonFlagSpec flow_flags_table[] = {
    {"IBV_FLOW_ATTR_FLAGS_DONT_TRAP", IBV_FLOW_ATTR_FLAGS_DONT_TRAP},
    {"IBV_FLOW_ATTR_FLAGS_EGRESS", IBV_FLOW_ATTR_FLAGS_EGRESS},
};

int handle_CreateFlow(cJSON *verb_obj, ResourceEnv *env)
{
    const char *flow_name = json_get_res_name(verb_obj, "flow");
    if (!flow_name)
    {
        fprintf(stderr, "[EXEC] CreateFlow: missing flow name\n");
        return -1;
    }

    const char *qp_name = json_get_res_name(verb_obj, "qp");
    if (!qp_name)
    {
        fprintf(stderr, "[EXEC] CreateFlow: missing qp name in attr_obj\n");
        return -1;
    }

    cJSON *attr_obj = obj_get(verb_obj, "flow_attr_obj");
    if (!attr_obj)
    {
        fprintf(stderr, "[EXEC] CreateFlow: missing attr_obj\n");
        return -1;
    }

    // int comp_mask = json_get_flag_field(
    //     attr_obj,
    //     "comp_mask",
    //     flow_attr_mask_table,
    //     sizeof(flow_attr_mask_table) / sizeof(flow_attr_mask_table[0]),
    //     0);
    int comp_mask = json_get_int_field(attr_obj, "comp_mask", 0); // future extendibility
    // 这里可以继续解析其他属性字段
    int type = json_get_enum_field(attr_obj,
                                   "type",
                                   flow_attr_type_table,
                                   sizeof(flow_attr_type_table) / sizeof(flow_attr_type_table[0]),
                                   IBV_FLOW_ATTR_NORMAL);
    int size = json_get_int_field(attr_obj, "size", 0);
    int priority = json_get_int_field(attr_obj, "priority", 0);
    int num_of_specs = json_get_int_field(attr_obj, "num_of_specs", 0);
    int port = json_get_int_field(attr_obj, "port", 1);
    int flags = json_get_flag_field(
        attr_obj,
        "flags",
        flow_flags_table,
        sizeof(flow_flags_table) / sizeof(flow_flags_table[0]),
        0);
    env_create_flow(env,
                    flow_name,
                    qp_name,
                    comp_mask,
                    type,
                    size,
                    priority,
                    num_of_specs,
                    port,
                    flags);
    return 0;
}