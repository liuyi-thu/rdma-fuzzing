from codegen_context import CodeGenContext
from verbs import *
import os
from typing import List, Dict
import json

from jinja2 import Environment, FileSystemLoader


def parse_trace(json_path: str, ctx) -> List[VerbCall]:
    """Read trace_output.json and convert to VerbCall list."""
    calls: List[VerbCall] = []
    with open(json_path, "r") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            verb = rec["verb"]
            info = rec["info"]
            ctor = VERB_FACTORY.get(verb)
            if ctor:
                calls.append(ctor(info, ctx))
    return calls


def generate_replay_code_client(buf_size, server_name=None):
    ctx = CodeGenContext()
    # calls = [
    #     GetDeviceList(),
    #     OpenDevice(),
    #     FreeDeviceList(),
    #     QueryDeviceAttr(),
    #     QueryPortAttr(),
    #     QueryGID(),
    #     ReceiveMR(),

    #     AllocPD(pd_addr="PD0", ctx=ctx),
    #     CreateCQ(cq_addr="CQ0", ctx=ctx),
    #     RegMR(pd_addr=f"PD0", buf=f"bufs[0]", length=buf_size, mr_addr=f"MR0",
    #               flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE", ctx=ctx),
    #     CreateQP(pd_addr=f"PD0", qp_addr=f"QP0", cq_addr=f"CQ0", qp_type="IBV_QPT_RC", cap_params={
    #             "max_send_wr": 1,
    #             "max_recv_wr": 1,
    #             "max_send_sge": 1,
    #             "max_recv_sge": 1}, ctx=ctx), # 顺带binding一下QP信息，TBD
    #     ExchangeQPInfo(qp_addr="QP0", remote_qp_index=0),
    #     ModifyQP(qp_addr="QP0", attr_mask = "IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS", attr = {
    #         "qp_state": "IBV_QPS_INIT",
    #         "pkey_index": 0,
    #         "port_num": 1,
    #         "qp_access_flags": "IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE"
    #     }, ctx=ctx),
    #     ModifyQP(qp_addr="QP0", attr_mask = "IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER", attr = {
    #         "qp_state": "IBV_QPS_RTR",
    #         # "ah_attr": {
    #         #     "is_global": 0,
    #         #     "dlid": 0,  # 需要根据GID查询得到
    #         #     "sl": 0,
    #         #     "src_path_bits": 0,
    #         #     "port_num": 1
    #         # },
    #         "path_mtu": "IBV_MTU_1024",
    #         # "dest_qp_num": 0,  # 需要根据QP信息查询得到
    #         "dest_qp_num": "local_remote_qp_map[" + ctx.get_qp("QP0") + "->qp_num]",  # 需要根据QP信息查询得到
    #         "rq_psn": 0,
    #         "max_dest_rd_atomic": 1,
    #         "min_rnr_timer": 12,
    #         "ah_attr.is_global": 1,
    #         "ah_attr.dlid": "remote_info.lid",  # 需要根据GID查询得到
    #         "ah_attr.sl": 0,
    #         "ah_attr.src_path_bits": 0,
    #         "ah_attr.port_num": 1,
    #         "ah_attr.grh.sgid_index": 1,
    #         "ah_attr.grh.hop_limit": 1,
    #         "ah_attr.grh.traffic_class": 0,
    #         "ah_attr.grh.flow_label": 0,
    #         "ah_attr.grh.dgid": "remote_info.gid"
    #     }, ctx=ctx),
    #     ModifyQP(qp_addr="QP0", attr_mask = "IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC", attr = {
    #         "qp_state": "IBV_QPS_RTS",
    #         "timeout": 14,
    #         "retry_cnt": 7,
    #         "rnr_retry": 7,
    #         "sq_psn": 0,
    #         "max_rd_atomic": 1
    #     }, ctx=ctx),
    #     PostSend(qp_addr=f"QP0", mr_addr = f"MR0", wr_id="1", opcode="IBV_WR_SEND"),
    #     PollCQ(cq_addr=f"CQ0"),
    #     # PostSend(qp_addr=f"QP0", mr_addr = f"MR0", wr_id="1", opcode="IBV_WR_SEND"),
    #     # PollCQ(cq_addr=f"CQ0"),
    #     # PostSend(qp_addr=f"QP0", mr_addr = f"MR0", wr_id="1", opcode="IBV_WR_SEND"),
    #     # PollCQ(cq_addr=f"CQ0"),
    #     # PostSend(qp_addr=f"QP0", mr_addr = f"MR0", wr_id="1", opcode="IBV_WR_SEND"),
    #     # PollCQ(cq_addr=f"CQ0"),
    #     DestroyQP(qp_addr=f"QP0"),
    #     DeregMR(mr_addr=f"MR0"),
    #     DestroyCQ(cq_addr=f"CQ0"),
    #     DeallocPD(pd_addr=f"PD0"),

    #     AllocPD(pd_addr="PD1", ctx=ctx),
    #     CreateCQ(cq_addr="CQ1", ctx=ctx),
    #     RegMR(pd_addr=f"PD1", buf=f"bufs[1]", length=buf_size, mr_addr=f"MR1",
    #               flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE", ctx=ctx),
    #     CreateQP(pd_addr=f"PD1", qp_addr=f"QP1", cq_addr=f"CQ1", qp_type="IBV_QPT_RC", cap_params={
    #             "max_send_wr": 1,
    #             "max_recv_wr": 1,
    #             "max_send_sge": 1,
    #             "max_recv_sge": 1}, ctx=ctx), # 顺带binding一下QP信息，TBD
    #     ExchangeQPInfo(qp_addr="QP1", remote_qp_index=1),
    #     ModifyQP(qp_addr="QP1", attr_mask = "IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS", attr = {
    #         "qp_state": "IBV_QPS_INIT",
    #         "pkey_index": 0,
    #         "port_num": 1,
    #         "qp_access_flags": "IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE"
    #     }, ctx=ctx),
    #     ModifyQP(qp_addr="QP1", attr_mask = "IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER", attr = {
    #         "qp_state": "IBV_QPS_RTR",
    #         # "ah_attr": {
    #         #     "is_global": 0,
    #         #     "dlid": 0,  # 需要根据GID查询得到
    #         #     "sl": 0,
    #         #     "src_path_bits": 0,
    #         #     "port_num": 1
    #         # },
    #         "path_mtu": "IBV_MTU_1024",
    #         # "dest_qp_num": 0,  # 需要根据QP信息查询得到
    #         "dest_qp_num": "local_remote_qp_map[" + ctx.get_qp("QP0") + "->qp_num]",  # 需要根据QP信息查询得到
    #         "rq_psn": 0,
    #         "max_dest_rd_atomic": 1,
    #         "min_rnr_timer": 12,
    #         "ah_attr.is_global": 1,
    #         "ah_attr.dlid": "remote_info.lid",  # 需要根据GID查询得到
    #         "ah_attr.sl": 0,
    #         "ah_attr.src_path_bits": 0,
    #         "ah_attr.port_num": 1,
    #         "ah_attr.grh.sgid_index": 1,
    #         "ah_attr.grh.hop_limit": 1,
    #         "ah_attr.grh.traffic_class": 0,
    #         "ah_attr.grh.flow_label": 0,
    #         "ah_attr.grh.dgid": "remote_info.gid"
    #     }, ctx=ctx),
    #     ModifyQP(qp_addr="QP1", attr_mask = "IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC", attr = {
    #         "qp_state": "IBV_QPS_RTS",
    #         "timeout": 14,
    #         "retry_cnt": 7,
    #         "rnr_retry": 7,
    #         "sq_psn": 0,
    #         "max_rd_atomic": 1
    #     }, ctx=ctx),
    #     PostSend(qp_addr=f"QP1", mr_addr = f"MR1", wr_id="1", opcode="IBV_WR_SEND"),
    #     PollCQ(cq_addr=f"CQ1"),
    #     DestroyQP(qp_addr=f"QP1"),
    #     DeregMR(mr_addr=f"MR1"),
    #     DestroyCQ(cq_addr=f"CQ1"),
    #     DeallocPD(pd_addr=f"PD1"),
    #     CloseDevice()

    # ]
    calls = [
        GetDeviceList(), # 返回的变量固定
        OpenDevice(), # 返回的变量固定
        FreeDeviceList(), # 返回的变量固定
        QueryDeviceAttr(), # 返回的变量固定
        QueryPortAttr(), # 返回的变量固定
        QueryGID(), # 返回的变量固定
        ReceiveMR() # 返回的变量固定
    ] # 这些都是建立连接的准备
    for i in range(10):
        calls += [
            AllocPD(pd_addr=f"PD{i}", ctx=ctx),
            CreateCQ(cq_addr=f"CQ{i}", ctx=ctx),
            RegMR(pd_addr=f"PD{i}", buf=f"bufs[{i}]", length=buf_size, mr_addr=f"MR{i}",
                    flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE", ctx=ctx),
            CreateQP(pd_addr=f"PD{i}", qp_addr=f"QP{i}", cq_addr=f"CQ{i}", qp_type="IBV_QPT_RC", cap_params={
                    "max_send_wr": 1,
                    "max_recv_wr": 1,
                    "max_send_sge": 1,
                    "max_recv_sge": 1}, ctx=ctx), # 顺带binding一下QP信息，TBD
            ExchangeQPInfo(qp_addr=f"QP{i}", remote_qp_index=i),
            ModifyQP(qp_addr=f"QP{i}", attr_mask = "IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS", attr = {
                "qp_state": "IBV_QPS_INIT",
                "pkey_index": 0,
                "port_num": 1,
                "qp_access_flags": "IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE"
            }, ctx=ctx),
            ModifyQP(qp_addr=f"QP{i}", attr_mask = "IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER", attr = {
                "qp_state": "IBV_QPS_RTR",
                # "ah_attr": {
                #     "is_global": 0,
                #     "dlid": 0,  # 需要根据GID查询得到
                #     "sl": 0,
                #     "src_path_bits": 0,
                #     "port_num": 1
                # },
                "path_mtu": "IBV_MTU_1024",
                # "dest_qp_num": 0,  # 需要根据QP信息查询得到
                "dest_qp_num": "local_remote_qp_map[" + ctx.get_qp(f"QP{i}") + "->qp_num]",  # 需要根据QP信息查询得到
                "rq_psn": 0,
                "max_dest_rd_atomic": 1,
                "min_rnr_timer": 12,
                "ah_attr.is_global": 1,
                "ah_attr.dlid": "remote_info.lid",  # 需要根据GID查询得到
                "ah_attr.sl": 0,
                "ah_attr.src_path_bits": 0,
                "ah_attr.port_num": 1,
                "ah_attr.grh.sgid_index": 1,
                "ah_attr.grh.hop_limit": 1,
                "ah_attr.grh.traffic_class": 0,
                "ah_attr.grh.flow_label": 0,
                "ah_attr.grh.dgid": "remote_info.gid"
            }, ctx=ctx),
            ModifyQP(qp_addr=f"QP{i}", attr_mask = "IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC", attr = {
                "qp_state": "IBV_QPS_RTS",
                "timeout": 14,
                "retry_cnt": 7,
                "rnr_retry": 7,
                "sq_psn": 0,
                "max_rd_atomic": 1
            }, ctx=ctx),
            PostSend(qp_addr=f"QP{i}", mr_addr = f"MR{i}", wr_id="1", opcode="IBV_WR_SEND"),
            PollCQ(cq_addr=f"CQ{i}"),
            # DestroyQP(qp_addr=f"QP{i}"),
            # DeregMR(mr_addr=f"MR{i}"),
            # DestroyCQ(cq_addr=f"CQ{i}"),
            # DeallocPD(pd_addr=f"PD{i}"),
        ]
    for i in range(10):
        calls += [
            DestroyQP(qp_addr=f"QP{i}"),
            DeregMR(mr_addr=f"MR{i}"),
            DestroyCQ(cq_addr=f"CQ{i}"),
            DeallocPD(pd_addr=f"PD{i}"),
        ]
    calls += [
        CloseDevice()
    ]
    body = "".join(call.generate_c(ctx) for call in calls)
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('rdma_client_with_qp_pool.cpp.j2')
    variable_definitions = ctx.generate_variable_definitions_all()
    rendered = template.render(body=body, ctx = "ctx", dev_list = ctx.dev_list, dev_attr = ctx.dev_attr, port_attr = ctx.port_attr, max_QPs = ctx.max_QPs, variable_definitions=variable_definitions)
    return rendered
    # we don't need socket any more

if __name__ == "__main__":
    rendered = generate_replay_code_client(1024, "localhost")
    with open('test.cpp', 'w') as f:
        f.write(rendered)
    print("Generated test.cpp")
    os.system('g++ -o test test.cpp -lcjson -libverbs')
    exit(0)
    # # Initialize the code generation context
    # context = CodeGenContext()

    # # Load verbs from the JSON file
    # with open('verbs.json', 'r') as file:
    #     verbs_data = json.load(file)

    # # Add verbs to the context
    # for verb in verbs_data:
    #     context.add_verb(verb['name'], verb['description'])

    # # Generate code for each verb
    # for verb in context.verbs:
    #     print(f"Generating code for verb: {verb.name}")
    #     code = verb.generate_code()
    #     print(code)
    #     print("\\n")