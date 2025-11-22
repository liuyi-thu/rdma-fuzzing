#include "verb_cq.h"
#include "json_utils.h"
#include <stdio.h>

#include <time.h>

// 可选：放在某个公共 util 里
static uint64_t get_time_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000ULL + ts.tv_nsec / 1000000ULL;
}

// 可选：把 opcode 打印成字符串，方便 debug
static const char *wc_opcode_str(enum ibv_wc_opcode op)
{
    switch (op)
    {
    case IBV_WC_SEND:
        return "SEND";
    case IBV_WC_RDMA_WRITE:
        return "RDMA_WRITE";
    case IBV_WC_RDMA_READ:
        return "RDMA_READ";
    case IBV_WC_COMP_SWAP:
        return "COMP_SWAP";
    case IBV_WC_FETCH_ADD:
        return "FETCH_ADD";
    case IBV_WC_BIND_MW:
        return "BIND_MW";
    case IBV_WC_RECV:
        return "RECV";
    case IBV_WC_RECV_RDMA_WITH_IMM:
        return "RECV_RDMA_IMM";
    default:
        return "UNKNOWN";
    }
}

// 可选：status -> 字符串
static const char *wc_status_str(enum ibv_wc_status st)
{
    switch (st)
    {
    case IBV_WC_SUCCESS:
        return "SUCCESS";
    case IBV_WC_LOC_LEN_ERR:
        return "LOC_LEN_ERR";
    case IBV_WC_LOC_QP_OP_ERR:
        return "LOC_QP_OP_ERR";
    case IBV_WC_LOC_EEC_OP_ERR:
        return "LOC_EEC_OP_ERR";
    case IBV_WC_LOC_PROT_ERR:
        return "LOC_PROT_ERR";
    case IBV_WC_WR_FLUSH_ERR:
        return "WR_FLUSH_ERR";
    case IBV_WC_MW_BIND_ERR:
        return "MW_BIND_ERR";
    case IBV_WC_BAD_RESP_ERR:
        return "BAD_RESP_ERR";
    case IBV_WC_LOC_ACCESS_ERR:
        return "LOC_ACCESS_ERR";
    case IBV_WC_REM_INV_REQ_ERR:
        return "REM_INV_REQ_ERR";
    case IBV_WC_REM_ACCESS_ERR:
        return "REM_ACCESS_ERR";
    case IBV_WC_REM_OP_ERR:
        return "REM_OP_ERR";
    case IBV_WC_RNR_RETRY_EXC_ERR:
        return "RNR_RETRY_EXC_ERR";
    case IBV_WC_LOC_RDD_VIOL_ERR:
        return "LOC_RDD_VIOL_ERR";
    case IBV_WC_REM_INV_RD_REQ_ERR:
        return "REM_INV_RD_REQ_ERR";
    case IBV_WC_REM_ABORT_ERR:
        return "REM_ABORT_ERR";
    case IBV_WC_INV_EECN_ERR:
        return "INV_EECN_ERR";
    case IBV_WC_INV_EEC_STATE_ERR:
        return "INV_EEC_STATE_ERR";
    case IBV_WC_FATAL_ERR:
        return "FATAL_ERR";
    case IBV_WC_RESP_TIMEOUT_ERR:
        return "RESP_TIMEOUT_ERR";
    case IBV_WC_GENERAL_ERR:
        return "GENERAL_ERR";
    case IBV_WC_TM_ERR:
        return "TM_ERR";
    case IBV_WC_TM_RNDV_INCOMPLETE:
        return "TM_RNDV_INCOMPLETE";
    default:
        return "UNKNOWN";
    }
}

int handle_CreateCQ(cJSON *verb_obj, ResourceEnv *env)
{
    const char *cq_name = json_get_res_name(verb_obj, "cq");
    if (!cq_name)
    {
        fprintf(stderr, "[EXEC] CreateCQ: missing 'cq' field\n");
        return -1;
    }

    int cqe = json_get_int_field(verb_obj, "cqe", 16);
    // 这里可以扩展读取 cq_context、channel、comp_vector 等参数
    const char *cq_context_str = obj_get_string(verb_obj, "cq_context");
    void *cq_context = NULL; // disabled
    const char *channel_str = obj_get_string(verb_obj, "channel");
    struct ibv_comp_channel *channel = NULL; // disabled
    int comp_vector = json_get_int_field(verb_obj, "comp_vector", 0);

    env_create_cq(env, cq_name, cqe, cq_context, channel, comp_vector);
    return 0;
}

int handle_CreateCQEx(cJSON *verb_obj, ResourceEnv *env)
{
    const char *cq_ex_name = json_get_res_name(verb_obj, "cq_ex");
    if (!cq_ex_name)
    {
        fprintf(stderr, "[EXEC] CreateCQ: missing 'cq_ex' field\n");
        return -1;
    }

    cJSON *attr_obj = obj_get(verb_obj, "cq_attr_obj");
    if (!attr_obj || !cJSON_IsObject(attr_obj))
    {
        fprintf(stderr, "[WARN] CreateCQEx missing 'cq_attr_obj'\n");
        return -1;
    }
    int cqe = json_get_int_field(attr_obj, "cqe", 0);
    // 这里可以扩展读取 cq_context、channel、comp_vector 等参数
    const char *cq_context_str = obj_get_string(attr_obj, "cq_context");
    void *cq_context = NULL; // disabled
    const char *channel_str = obj_get_string(attr_obj, "channel");
    struct ibv_comp_channel *channel = NULL; // disabled
    int comp_vector = json_get_int_field(attr_obj, "comp_vector", 0);
    int wc_flags = json_get_int_field(attr_obj, "wc_flags", 0);
    int comp_mask = json_get_int_field(attr_obj, "comp_mask", 0);
    int flags = json_get_int_field(attr_obj, "flags", 0);
    const char *parent_domain_str = obj_get_string(attr_obj, "parent_domain");
    struct ibv_pd *parent_domain = NULL; // disabled

    env_create_cq_ex(env, cq_ex_name, cqe, cq_context, channel,
                     comp_vector, wc_flags, comp_mask, flags, parent_domain);
    return 0;
}

int handle_ModifyCQ(cJSON *verb_obj, ResourceEnv *env)
{
    const char *cq_name = json_get_res_name(verb_obj, "cq");
    if (!cq_name)
    {
        fprintf(stderr, "[EXEC] ModifyCQ: missing 'cq' field\n");
        return -1;
    }
    cJSON *attr_obj = obj_get(verb_obj, "attr_obj");
    if (!attr_obj || !cJSON_IsObject(attr_obj))
    {
        fprintf(stderr, "[WARN] ModifyCQ missing 'attr_obj'\n");
        return -1;
    }
    // 这里可以扩展读取 attr_obj 中的字段
    int attr_mask = json_get_int_field(attr_obj, "attr_mask", 0);
    // TODO: mask 应该支持 str 和 int 两类，不需要检查 str 合法性（由 fuzz tool 保证）
    cJSON *moderate = obj_get(attr_obj, "moderate");
    int cq_count = json_get_int_field(moderate, "cq_count", 0);
    int cq_period = json_get_int_field(moderate, "cq_period", 0);
    env_modify_cq(env, cq_name, attr_mask, cq_count, cq_period);
    return 0;
}

int handle_DestroyCQ(cJSON *verb_obj, ResourceEnv *env)
{
    const char *cq_name = json_get_res_name(verb_obj, "cq");
    if (!cq_name)
    {
        fprintf(stderr, "[EXEC] DestroyCQ: missing 'cq' field\n");
        return -1;
    }
    env_destroy_cq(env, cq_name);
    return 0;
}

// 真正的 PollCQ handler
int handle_PollCQ(cJSON *verb_obj, ResourceEnv *env)
{
    if (!verb_obj || !env)
    {
        fprintf(stderr, "[EXEC] PollCQ: null verb_obj or env\n");
        return -1;
    }

    // 1) 解析 CQ 名字
    const char *cq_name = json_get_res_name(verb_obj, "cq");
    if (!cq_name)
    {
        fprintf(stderr, "[EXEC] PollCQ: missing 'cq' field\n");
        return -1;
    }

    CqResource *cq_res = env_find_cq(env, cq_name);
    if (!cq_res || !cq_res->cq)
    {
        fprintf(stderr, "[EXEC] PollCQ: CQ '%s' not found\n", cq_name);
        return -1;
    }

    // 2) 解析可选参数
    int max_wc = json_get_int_field(verb_obj, "max_wc", 16);
    int min_wc = json_get_int_field(verb_obj, "min_wc", 2);
    int timeout_ms = json_get_int_field(verb_obj, "timeout_ms", 100);

    if (max_wc <= 0)
        max_wc = 1;
    if (max_wc > 64)
        max_wc = 64;

    if (min_wc < 0)
        min_wc = 0;
    if (min_wc > max_wc)
        min_wc = max_wc;

    struct ibv_wc *wc_array = calloc((size_t)max_wc, sizeof(struct ibv_wc));
    if (!wc_array)
    {
        fprintf(stderr, "[EXEC] PollCQ: calloc wc_array failed\n");
        return -1;
    }

    fprintf(stderr,
            "[EXEC] PollCQ on cq=%s, max_wc=%d, min_wc=%d, timeout_ms=%d\n",
            cq_name, max_wc, min_wc, timeout_ms);

    uint64_t start_ms = get_time_ms();
    int total_polled = 0;
    int ret = 0;

    for (;;)
    {
        int ne = ibv_poll_cq(cq_res->cq, max_wc, wc_array);
        if (ne < 0)
        {
            fprintf(stderr, "[EXEC] PollCQ: ibv_poll_cq returned %d\n", ne);
            ret = -1;
            break;
        }

        if (ne > 0)
        {
            for (int i = 0; i < ne; i++)
            {
                struct ibv_wc *w = &wc_array[i];

                if (w->status != IBV_WC_SUCCESS)
                {
                    fprintf(stderr,
                            "[EXEC] PollCQ: completion ERROR on cq=%s: "
                            "status=%d(%s), opcode=%d(%s), qp_num=%u, wr_id=%llu, byte_len=%u\n",
                            cq_name,
                            w->status, wc_status_str(w->status),
                            w->opcode, wc_opcode_str(w->opcode),
                            w->qp_num,
                            (unsigned long long)w->wr_id,
                            w->byte_len);
                }
                else
                {
                    fprintf(stderr,
                            "[EXEC] PollCQ: completion OK on cq=%s: "
                            "opcode=%d(%s), qp_num=%u, wr_id=%llu, byte_len=%u\n",
                            cq_name,
                            w->opcode, wc_opcode_str(w->opcode),
                            w->qp_num,
                            (unsigned long long)w->wr_id,
                            w->byte_len);
                }

                // 这里也可以做一些环境记录，比如：
                // env_record_completion(env, cq_name, w);
                // 或者根据 qp_num 找到 QP 名字做映射。
            }

            total_polled += ne;
        }

        // 如果我们只想“尝试一次 poll”：
        if (timeout_ms == 0)
            break;

        // 如果已经达到 min_wc，就可以退出
        if (total_polled >= min_wc)
            break;

        // 检查超时
        uint64_t now_ms = get_time_ms();
        if ((int)(now_ms - start_ms) >= timeout_ms)
        {
            fprintf(stderr,
                    "[EXEC] PollCQ: timeout after %d ms, total_polled=%d\n",
                    timeout_ms, total_polled);
            break;
        }

        // 防止忙等
        usleep(1000); // 1ms
    }

    free(wc_array);
    return ret;
}