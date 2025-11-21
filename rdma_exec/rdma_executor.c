#include <stdio.h>
#include <stdlib.h>
#include <cjson/cJSON.h>

#include "json_utils.h"
#include "resource_env.h"
#include "verb_dispatch.h"

static int run_program_from_json(const char *json_text)
{
    cJSON *root = cJSON_Parse(json_text);
    if (!root)
    {
        const char *err = cJSON_GetErrorPtr();
        fprintf(stderr, "[ERR] JSON parse error near: %s\n", err ? err : "<unknown>");
        return 1;
    }

    ResourceEnv env;
    env_init(&env);

    // 读取 meta.trace_id（可选）
    cJSON *meta = obj_get(root, "meta");
    if (meta && cJSON_IsObject(meta))
    {
        const char *tid = obj_get_string(meta, "trace_id");
        if (tid)
            snprintf(env.trace_id, sizeof(env.trace_id), "%s", tid);
        int port_num = obj_get_int(meta, "port_num", 0);
        env_set_port_num(&env, port_num);
        int gid_index = obj_get_int(meta, "gid_index", 0);
        env_set_gid_index(&env, gid_index);
        env_set_default_ctx(&env);
    }

    // 程序数组
    cJSON *program = obj_get(root, "program");
    if (!program || !cJSON_IsArray(program))
    {
        fprintf(stderr, "[ERR] 'program' must be an array\n");
        cJSON_Delete(root);
        return 1;
    }

    int prog_len = cJSON_GetArraySize(program);
    fprintf(stderr, "[INFO] Running program: %d verbs, trace_id=%s, port_num=%d, gid_index=%d\n",
            prog_len, env.trace_id[0] ? env.trace_id : "(none)", env.port_num, env.gid_index);

    for (int i = 0; i < prog_len; i++)
    {
        cJSON *verb_obj = cJSON_GetArrayItem(program, i);
        fprintf(stderr, "[INFO] === Verb #%d ===\n", i);
        exec_verb(verb_obj, &env);
    }

    cJSON_Delete(root);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc < 2)
    {
        fprintf(stderr, "Usage: %s program.json [device_name]\n", argv[0]);
        return 1;
    }
    const char *json_path = argv[1];
    const char *dev_name = (argc >= 3) ? argv[2] : NULL;

    if (rdma_init_context(dev_name) != 0)
    {
        fprintf(stderr, "[ERR] Failed to init RDMA context\n");
        return 1;
    }

    long len = 0;
    char *text = read_all_text(json_path, &len);
    if (!text)
    {
        fprintf(stderr, "[ERR] Failed to read file: %s\n", json_path);
        rdma_teardown_context();
        return 1;
    }

    int ret = run_program_from_json(text);
    free(text);

    rdma_teardown_context();
    return ret;
}