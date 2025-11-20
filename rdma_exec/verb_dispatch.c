#include "verb_dispatch.h"
#include "verb_pd.h"
#include "verb_dm.h"
#include "verb_qp.h"
#include "verb_mw.h"
#include "verb_mr.h"
#include "verb_td.h"
#include "verb_srq.h"
#include "verb_cq.h"
#include "verb_flow.h"
// 如果有其他模块，比如 verb_cq.h，也在这里 include

#include <stdio.h>

// 中央路由表
static VerbEntry g_verb_table[] = {
    {"AllocPD", handle_AllocPD},
    {"AllocDM", handle_AllocDM},
    {"CreateQP", handle_CreateQP},
    {"ModifyQP", handle_ModifyQP},
    {"DestroyQP", handle_DestroyQP},
    {"PostSend", handle_PostSend},
    {"PostRecv", handle_PostRecv},
    {"AllocMW", handle_AllocMW},
    {"DeallocPD", handle_DeallocPD},
    {"DeallocMW", handle_DeallocMW},
    {"AllocNullMR", handle_AllocNullMR},
    {"AllocTD", handle_AllocTD},
    {"CreateSRQ", handle_CreateSRQ},
    {"DestroySRQ", handle_DestroySRQ},
    {"CreateCQ", handle_CreateCQ},
    {"CreateCQEx", handle_CreateCQEx},
    {"ModifyCQ", handle_ModifyCQ},
    {"RegMR", handle_RegMR},
    {"CreateQP", handle_CreateQP},
    {"DeregMR", handle_DeregMR},
    {"FreeDM", handle_FreeDM},
    {"DestroyQP", handle_DestroyQP},
    {"DestroyCQ", handle_DestroyCQ},
    {"CreateQPEx", handle_CreateQPEx},
    {"CreateFlow", handle_CreateFlow},
    {"ModifyQP", handle_ModifyQP},
    {"ModifySRQ", handle_ModifySRQ},
    {"BindMW", handle_BindMW},
    {"PostSend", handle_PostSend},
    // ... 后面慢慢加
};

void exec_verb(cJSON *verb_obj, ResourceEnv *env)
{
    if (!verb_obj || !cJSON_IsObject(verb_obj))
        return;

    cJSON *verb_item = cJSON_GetObjectItemCaseSensitive(verb_obj, "verb");
    if (!verb_item || !cJSON_IsString(verb_item) || !verb_item->valuestring)
    {
        fprintf(stderr, "[WARN] Verb missing 'verb' field\n");
        return;
    }
    const char *verb_name = verb_item->valuestring;

    for (size_t i = 0; i < sizeof(g_verb_table) / sizeof(g_verb_table[0]); i++)
    {
        if (strcmp(verb_name, g_verb_table[i].name) == 0)
        {
            g_verb_table[i].handler(verb_obj, env);
            return;
        }
    }

    fprintf(stderr, "[WARN] Unsupported verb '%s'\n", verb_name);
}