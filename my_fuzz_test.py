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
    GetDeviceList("dev_list"),
    OpenDevice("dev_list"),
    FreeDeviceList(),
    QueryDeviceAttr(),
    QueryPortAttr(),
    QueryGID(),
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
            sg_list=[IbvSge(addr="mr0", length=1024, lkey="mr0")],
        ),
    ),
    PostRecv(
        qp="qp0",
        wr_obj=IbvRecvWR(
            wr_id=1,
            num_sge=1,
            sg_list=[IbvSge(addr="mr0", length=1024, lkey="mr0")],
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

if __name__ == "__main__":
    print("This is my_fuzz_test.py")
    verbs = copy.deepcopy(INITIAL_VERBS)
    # for v in verbs:
    #     print(summarize_verb(v))
    ctx = CodeGenContext()
    for v in verbs:
        v.apply(ctx)
        # print(ctx.contracts)
    mutator = fuzz_mutate.ContractAwareMutator()
    # target = ("qp", "qp0")
    # dependent_verbs = mutator.find_dependent_verbs(verbs, target)
    # print(f"Dependent verbs for {target}:")
    # for i in dependent_verbs:
    #     print("  ", summarize_verb(verbs[i], deep=True, max_items=100))

    target_stateful = ("qp", "qp0", State.ALLOCATED)
    dependent_verbs = mutator.find_dependent_verbs_stateful(verbs, target_stateful)
    print(f"Dependent verbs for {target_stateful}:")
    for i in dependent_verbs:
        print("  ", summarize_verb(verbs[i], deep=True, max_items=100))

    for i in range(len(verbs)):
        print(f"[{i}]", summarize_verb(verbs[i], deep=True, max_items=100))
        # print()
    for i in range(len(verbs)):
        mutator.mutate_move(verbs, i, None)

    # print(mutator.enumerate_mutable_paths(verbs[16]))
