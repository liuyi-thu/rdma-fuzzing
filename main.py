from lib.codegen_context import CodeGenContext
from lib.verbs import *
from lib.IbvQPAttr import *
from lib.IbvSendWR import *
from lib.IbvQPInitAttr import *
from lib.IbvSrqAttr import *
from lib.IbvAHAttr import IbvAHAttr
from lib.IbvSrqInitAttr import IbvSrqInitAttr

import os
from typing import List, Dict
import json
from jinja2 import Environment, FileSystemLoader


def parse_trace(json_path: str, ctx: CodeGenContext) -> List[VerbCall]:
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


def generate_replay_code_client(buf_size):
    ctx = CodeGenContext()
    calls = [
        GetDeviceList(),  # 返回的变量固定
        OpenDevice(),  # 返回的变量固定
        FreeDeviceList(),  # 返回的变量固定
        QueryDeviceAttr(),  # 返回的变量固定
        QueryPortAttr(),  # 返回的变量固定
        QueryGID(),  # 返回的变量固定
        ReceiveMR()  # 返回的变量固定
    ]  # 这些都是建立连接的准备
    for i in range(10):
        calls += [
            AllocPD(pd=f"PD{i}", ctx=ctx),
            CreateCQ(cq=f"CQ{i}", ctx=ctx),
            RegMR(pd=f"PD{i}", buf=f"bufs[{i}]", length=buf_size, mr=f"MR{i}",
                  flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE", ctx=ctx),
            # CreateQP(pd=f"PD{i}", qp=f"QP{i}", cq=f"CQ{i}", qp_type="IBV_QPT_RC", cap_params={
            #         "max_send_wr": 1,
            #         "max_recv_wr": 1,
            #         "max_send_sge": 1,
            #         "max_recv_sge": 1}, ctx=ctx), # 顺带binding一下QP信息，TBD
            CreateQP(qp=f"QP{i}", pd=f"PD{i}", init_attr_obj=IbvQpInitAttr(send_cq=f"CQ{i}", recv_cq=
                f"CQ{i}", cap=IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1), qp_type="IBV_QPT_RC", sq_sig_all=1), ctx=ctx),
            ExchangeQPInfo(qp=f"QP{i}", remote_qp_index=i),
            # CreateSRQ(pd=f"PD{i}", srq=f"SRQ{i}",
            #           srq_init_obj=IbvSrqInitAttr(attr = IbvSrqAttr(max_wr=32, max_sge=1, srq_limit=0)), ctx=ctx),
            # ModifyQP(qp
            ModifyQP(
                qp=f"QP{i}",
                attr_mask="IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS",
                attr=IbvQPAttr(qp_state="IBV_QPS_INIT", pkey_index=0, port_num=1,
                               qp_access_flags="IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE"),
                ctx=ctx
            ),
            ModifyQP(
                qp=f"QP{i}",
                attr_mask="IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER",
                attr=IbvQPAttr(
                    qp_state="IBV_QPS_RTR",
                    path_mtu="IBV_MTU_1024",
                    dest_qp_num=f'local_remote_qp_map[QP{i}->qp_num]',
                    rq_psn=0,
                    max_dest_rd_atomic=1,
                    min_rnr_timer=12,
                    ah_attr=IbvAHAttr(
                        is_global=1,
                        dlid="remote_info.lid",
                        sl=0,
                        src_path_bits=0,
                        port_num=1,
                        grh=IbvGlobalRoute(
                            sgid_index=1,
                            hop_limit=1,
                            traffic_class=0,
                            flow_label=0,
                            dgid=IbvGID(src_var="remote_info.gid")
                        )
                    )
                ),
                ctx=ctx
            ),
            ModifyQP(
                qp=f"QP{i}",
                attr_mask="IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC",
                attr=IbvQPAttr(
                    qp_state="IBV_QPS_RTS",
                    timeout=14,
                    retry_cnt=7,
                    rnr_retry=7,
                    sq_psn=0,
                    max_rd_atomic=1
                ),
                ctx=ctx
            ),
            # 这里可以添加更多的操作，比如发送数据等
            PostSend(qp=f"QP{i}",
                     wr_obj=IbvSendWR(wr_id=1, num_sge=1, opcode='IBV_WR_SEND', send_flags='IBV_SEND_SIGNALED', sg_list=[IbvSge(addr=f'(uintptr_t)bufs[{i}]', length='MSG_SIZE', lkey=f'MR{i}->lkey')]), ctx=ctx),
            PollCQ(cq=f"CQ{i}"),
            # DestroyQP(qp=f"QP{i}"),
            # DeregMR(mr=f"MR{i}"),
            # DestroyCQ(cq=f"CQ{i}"),
            # DeallocPD(pd=f"PD{i}"),
        ]
    for i in range(10):
        calls += [
            DestroyQP(qp=f"QP{i}"),
            DeregMR(mr=f"MR{i}"),
            DestroyCQ(cq=f"CQ{i}"),
            DeallocPD(pd=f"PD{i}"),
        ]
    calls += [
        CloseDevice()
    ]
    body = "".join(call.generate_c(ctx) for call in calls)
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('rdma_client_with_qp_pool.cpp.j2')
    ctx.alloc_variables_objtracker()
    variable_definitions = ctx.generate_variable_definitions_all()
    rendered = template.render(body=body, ctx="ctx", dev_list=ctx.dev_list, dev_attr=ctx.dev_attr,
                               port_attr=ctx.port_attr, max_QPs=ctx.max_QPs, variable_definitions=variable_definitions)
    return rendered
    # we don't need socket any more


if __name__ == "__main__":
    rendered = generate_replay_code_client(1024)
    with open('test.cpp', 'w') as f:
        f.write(rendered)
    print("Generated test.cpp")
    os.system('g++ -o test test.cpp -lcjson -libverbs')
    exit(0)
