import argparse
import copy
import json
import logging
import os
import pickle
import random
import sys
import traceback
from logging.handlers import RotatingFileHandler
from typing import Dict, List

import dill
from jinja2 import Environment, FileSystemLoader
from termcolor import colored

from lib import fuzz_mutate
from lib.codegen_context import CodeGenContext
from lib.contracts import ContractError, ContractTable, State
from lib.debug_dump import diff_verb_snapshots, dump_verbs, snapshot_verbs, summarize_verb, summarize_verb_list
from lib.ibv_all import (
    IbvAHAttr,
    IbvAllocDmAttr,
    IbvGID,
    IbvGlobalRoute,
    IbvModifyCQAttr,
    IbvQPAttr,
    IbvQPCap,
    IbvQPInitAttr,
    IbvRecvWR,
    IbvSendWR,
    IbvSge,
    IbvSrqAttr,
    IbvSrqInitAttr,
)
from lib.verbs import (
    AllocDM,
    AllocPD,
    CreateCQ,
    CreateQP,
    CreateSRQ,
    DeallocPD,
    DeregMR,
    DestroyCQ,
    DestroyQP,
    DestroySRQ,
    FreeDeviceList,
    FreeDM,
    GetDeviceList,
    ModifyCQ,
    ModifyQP,
    ModifySRQ,
    OpenDevice,
    PollCQ,
    PostRecv,
    PostSend,
    PostSRQRecv,
    QueryDeviceAttr,
    QueryGID,
    QueryPortAttr,
    RegMR,
    VerbCall,
)

INITIAL_VERBS = [
    # GetDeviceList("dev_list"),
    # OpenDevice("dev_list"),
    # FreeDeviceList(),
    # QueryDeviceAttr(),
    # QueryPortAttr(),
    # QueryGID(),
    AllocPD(pd="pd0"),
    AllocPD(pd="pd1"),
    AllocDM(dm="dm0", attr_obj=IbvAllocDmAttr(length=4096, log_align_req=12)),  # --- IGNORE ---
    AllocDM(dm="dm1", attr_obj=IbvAllocDmAttr(length=4096, log_align_req=12)),  # --- IGNORE ---
    CreateSRQ(pd="pd0", srq="srq0", srq_init_obj=IbvSrqInitAttr(attr=IbvSrqAttr())),  # --- IGNORE ---
    CreateCQ(cq="cq0"),
    CreateCQ(cq="cq1"),
    ModifyCQ(cq="cq0", attr_obj=IbvModifyCQAttr()),
    RegMR(
        pd="pd0",
        addr="bufs[0]",
        length=1024,
        mr="mr0",
        access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
    ),
    RegMR(
        pd="pd1",
        addr="bufs[0]",
        length=1024,
        mr="mr1",
        access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
    ),
    CreateQP(
        qp="qp0",
        pd="pd0",
        init_attr_obj=IbvQPInitAttr(
            send_cq="cq0",
            recv_cq="cq0",
            cap=IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1),
            qp_type="IBV_QPT_RC",
            sq_sig_all=1,
        ),
    ),
    ModifyQP(
        qp="qp0",
        attr_mask="IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS",
        attr_obj=IbvQPAttr(
            qp_state="IBV_QPS_INIT",
            pkey_index=0,
            port_num=1,
            qp_access_flags="IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE",
        ),
    ),
    ModifyQP(
        qp="qp0",
        attr_mask="IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER",
        attr_obj=IbvQPAttr(
            qp_state="IBV_QPS_RTR",
            path_mtu="IBV_MTU_1024",
            dest_qp_num="",  # DeferredValue
            rq_psn=0,
            max_dest_rd_atomic=1,
            min_rnr_timer=12,
            ah_attr=IbvAHAttr(
                is_global=1,
                dlid="",  # DeferredValue
                sl=0,
                src_path_bits=0,
                port_num=1,
                grh=IbvGlobalRoute(
                    sgid_index=1,
                    hop_limit=1,
                    traffic_class=0,
                    flow_label=0,
                    dgid="",  # DeferredValue
                ),
            ),
        ),
    ),
    ModifyQP(
        qp="qp0",
        attr_mask="IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC",
        attr_obj=IbvQPAttr(qp_state="IBV_QPS_RTS", timeout=14, retry_cnt=7, rnr_retry=7, sq_psn=0, max_rd_atomic=1),
    ),
    ModifySRQ(srq="srq0", attr_obj=IbvSrqAttr(max_wr=1024, max_sge=1)),
    # 这里可以添加更多的操作，比如发送数据等
    PostSend(
        qp="qp0",
        wr_obj=IbvSendWR(
            wr_id=1,
            num_sge=1,
            opcode="IBV_WR_SEND",
            send_flags="IBV_SEND_SIGNALED",
            sg_list=[IbvSge(mr="mr0")],
        ),
    ),
    PostRecv(
        qp="qp0",
        wr_obj=IbvRecvWR(
            wr_id=1,
            num_sge=1,
            next_wr=IbvRecvWR(wr_id=1, num_sge=1, next_wr=None, sg_list=[IbvSge(mr="mr0"), IbvSge(mr="mr1")]),
            sg_list=[IbvSge(mr="mr0"), IbvSge(mr="mr1")],
        ),
    ),
    PostSRQRecv(
        srq="srq0",
        wr_obj=IbvRecvWR(
            wr_id=1,
            num_sge=1,
            sg_list=[IbvSge(addr="mr0", length=1024, lkey="mr0")],
        ),
    ),
    PollCQ(cq="cq0"),
    DestroyQP(qp="qp0"),
    # DestroyQP(qp="qp0"),  # --- IGNORE ---
    DestroyCQ(cq="cq0"),
    DestroySRQ(srq="srq0"),
    DeregMR(mr="mr0"),
    DeallocPD(pd="pd0"),
    FreeDM(dm="dm0"),  # --- IGNORE ---
]


def render(verbs):
    ctx = CodeGenContext()
    verbs = [
        GetDeviceList("dev_list"),
        OpenDevice("dev_list"),
        FreeDeviceList(),
        QueryDeviceAttr(),
        QueryPortAttr(),
        QueryGID(),
    ] + verbs
    for v in verbs:
        v.apply(ctx)
    print(verbs)
    body = "".join(v.generate_c(ctx) for v in verbs)
    template_dir = "./templates"
    template_name = "client.cpp.j2"
    env = Environment(loader=FileSystemLoader(template_dir), trim_blocks=True, lstrip_blocks=True)
    tpl = env.get_template(template_name)
    rendered = tpl.render(
        compile_units="pair_runtime.cpp runtime_resolver.c -lcjson",
        output_name="rdma_client_autogen",
        ib_port=1,
        msg_size=1024,
        bundle_env="RDMA_FUZZ_RUNTIME",
        client_update="client_update.json",
        length=1000,
        setup_region="/* setup generated by verbs (alloc/reg/create) moved here if你把这些也用 generate_c 产出 */",
        early_verbs_region="".join([]),
        verbs_region="".join(body),
        epilog_region="/* optional CQ polling & cleanup */",
        prolog_extra=ctx.generate_variable_definitions_all(),  # 如果你想注入额外 helper，这里填
    )
    return rendered


if __name__ == "__main__":
    print("This is my_fuzz_test.py")
    logging.basicConfig(level=logging.DEBUG)
    verbs = copy.deepcopy(INITIAL_VERBS)
    mutator = fuzz_mutate.ContractAwareMutator()
    for _ in range(100):
        mutator.mutate(verbs)
    print(summarize_verb_list(verbs, deep=True))
    # print("\n\nGenerated C++ Code:\n")
    rendered = render(verbs)
    with open("client.cpp", "w") as f:
        f.write(rendered)
    # for v in verbs:
    #     print(summarize_verb(v))
    # ctx = CodeGenContext()
    # for i in range(len(verbs)):
    #     print(i, summarize_verb(verbs[i], deep=True, max_items=100))
    #     verbs[i].apply(ctx)
    #     print()
    # mutator = fuzz_mutate.ContractAwareMutator()
    # print(mutator.find_dependent_verbs_stateful(verbs, ("mr", "mr0", State.ALLOCATED)))

    # for k in range(len(verbs)):
    #     verbs = copy.deepcopy(INITIAL_VERBS)
    #     print(f"=== Deleting verb {k} ===")
    #     # for i in range(len(verbs)):
    #     #     print(i, summarize_verb(verbs[i], deep=True, max_items=100))
    #     #     verbs[i].apply(ctx)
    #     print(summarize_verb_list(verbs, highlight=k, deep=True))
    #     print("----- After Deletion -----")
    #     mutator.mutate_param(verbs, idx=k)
    #     print(summarize_verb_list(verbs, deep=True))
    #     ctx = CodeGenContext()
    #     for i in range(len(verbs)):
    #         # print(i, summarize_verb(verbs[i], deep=True, max_items=100))
    #         verbs[i].apply(ctx)

    #     # print()
    #     print()

    # mutator.mutate_param(verbs, 21)
    # # verbs[21].wr_obj.sg_list.mutate()
    # print(i, summarize_verb(verbs[21], deep=True, max_items=100))
    # print(ctx.contracts)
    # mutator = fuzz_mutate.ContractAwareMutator()
    # # target = ("qp", "qp0")
    # # dependent_verbs = mutator.find_dependent_verbs(verbs, target)
    # # print(f"Dependent verbs for {target}:")
    # # for i in dependent_verbs:
    # #     print("  ", summarize_verb(verbs[i], deep=True, max_items=100))

    # target_stateful = ("qp", "qp0", State.ALLOCATED)
    # dependent_verbs = fuzz_mutate.find_dependent_verbs_stateful(verbs, target_stateful)
    # print(dependent_verbs)
    # print(dependent_verbs[:-1])
    # print(f"Dependent verbs for {target_stateful}:")
    # for i in dependent_verbs:
    #     print("  ", summarize_verb(verbs[i], deep=True, max_items=100))

    # # for i in range(len(verbs)):
    # #     print(f"[{i}]", summarize_verb(verbs[i], deep=True, max_items=100))
    # #     # print()
    # # for i in range(len(verbs)):
    # #     mutator.mutate_move(verbs, i, None)

    # # print(mutator.enumerate_mutable_paths(verbs[16]))
