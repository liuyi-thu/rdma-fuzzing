import copy
import json
import logging
import sys
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader

from lib.codegen_context import CodeGenContext
from lib.debug_dump import summarize_verb
from lib.verbs import (
    FreeDeviceList,
    GetDeviceList,
    OpenDevice,
    QueryDeviceAttr,
    QueryGID,
    QueryPortAttr,
    VerbCall,
)

# INITIAL_VERBS = [
#     # GetDeviceList("de8v_list"),
#     # OpenDevice("dev_list"),
#     # FreeDeviceList(),
#     # QueryDeviceAttr(),
#     # QueryPortAttr(),
#     # QueryGID(),
#     AllocPD(pd="pd0"),
#     AllocPD(pd="pd1"),
#     AllocDM(dm="dm0", attr_obj=IbvAllocDmAttr(length=4096, log_align_req=12)),  # --- IGNORE ---
#     AllocDM(dm="dm1", attr_obj=IbvAllocDmAttr(length=4096, log_align_req=12)),  # --- IGNORE ---
#     CreateSRQ(pd="pd0", srq="srq0", srq_init_obj=IbvSrqInitAttr(attr=IbvSrqAttr())),  # --- IGNORE ---
#     CreateCQ(cq="cq0"),
#     CreateCQ(cq="cq1"),
#     ModifyCQ(cq="cq0", attr_obj=IbvModifyCQAttr()),
#     RegMR(
#         pd="pd0",
#         addr="bufs[0]",
#         length=1024,
#         mr="mr0",
#         access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
#     ),
#     RegMR(
#         pd="pd1",
#         addr="bufs[1]",
#         length=1024,
#         mr="mr1",
#         access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
#     ),
#     CreateQP(
#         qp="qp0",
#         pd="pd0",
#         init_attr_obj=IbvQPInitAttr(
#             send_cq="cq0",
#             recv_cq="cq0",
#             cap=IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1),
#             qp_type="IBV_QPT_RC",
#             sq_sig_all=1,
#         ),
#         remote_qp="srv0",
#     ),
#     ModifyQP(
#         qp="qp0",
#         attr_mask="IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS",
#         attr_obj=IbvQPAttr(
#             qp_state="IBV_QPS_INIT",
#             pkey_index=0,
#             port_num=1,
#             qp_access_flags="IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE",
#         ),
#     ),
#     ModifyQP(
#         qp="qp0",
#         attr_mask="IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER",
#         attr_obj=IbvQPAttr(
#             qp_state="IBV_QPS_RTR",
#             path_mtu="IBV_MTU_1024",
#             dest_qp_num="",  # DeferredValue
#             rq_psn=0,
#             max_dest_rd_atomic=1,
#             min_rnr_timer=12,
#             ah_attr=IbvAHAttr(
#                 is_global=1,
#                 dlid="",  # DeferredValue
#                 sl=0,
#                 src_path_bits=0,
#                 port_num=1,
#                 grh=IbvGlobalRoute(
#                     sgid_index=1,
#                     hop_limit=1,
#                     traffic_class=0,
#                     flow_label=0,
#                     dgid="",  # DeferredValue
#                 ),
#             ),
#         ),
#     ),
#     ModifyQP(
#         qp="qp0",
#         attr_mask="IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC",
#         attr_obj=IbvQPAttr(qp_state="IBV_QPS_RTS", timeout=14, retry_cnt=7, rnr_retry=7, sq_psn=0, max_rd_atomic=1),
#     ),
#     ModifySRQ(srq="srq0", attr_obj=IbvSrqAttr(max_wr=1024, max_sge=1)),
#     # 这里可以添加更多的操作，比如发送数据等
#     PostSend(
#         qp="qp0",
#         wr_obj=IbvSendWR(
#             wr_id=1,
#             num_sge=1,
#             opcode="IBV_WR_SEND",
#             send_flags="IBV_SEND_SIGNALED",
#             sg_list=[IbvSge(mr="mr0")],
#         ),
#     ),
#     PostRecv(
#         qp="qp0",
#         wr_obj=IbvRecvWR(
#             wr_id=1,
#             num_sge=1,
#             next_wr=IbvRecvWR(wr_id=1, num_sge=1, next_wr=None, sg_list=[IbvSge(mr="mr0"), IbvSge(mr="mr1")]),
#             sg_list=[IbvSge(mr="mr0"), IbvSge(mr="mr1")],
#         ),
#     ),
#     PostSRQRecv(
#         srq="srq0",
#         wr_obj=IbvRecvWR(
#             wr_id=1,
#             num_sge=1,
#             sg_list=[IbvSge(mr="mr0")],
#         ),
#     ),
#     PollCQ(cq="cq0"),
#     DestroyQP(qp="qp0"),
#     # DestroyQP(qp="qp0"),  # --- IGNORE ---
#     DestroyCQ(cq="cq0"),
#     DestroySRQ(srq="srq0"),
#     DeregMR(mr="mr0"),
#     DeallocPD(pd="pd0"),
#     FreeDM(dm="dm0"),  # --- IGNORE ---
# ]

INITIAL_VERBS: List[VerbCall] = []


def escape_c_string(s: str) -> str:
    """
    转义字符串为合法的 C 字符串常量内容。
    会转义双引号、反斜杠、换行等特殊字符。
    """
    # json.dumps 会自动做 C 风格转义
    escaped = json.dumps(s)
    # 去掉最外层的引号
    return escaped[1:-1]


def render(verbs: List[VerbCall]) -> str:
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
    body = ""
    for i, v in enumerate(verbs):
        summary = escape_c_string(summarize_verb(v, deep=True, max_items=1000))
        body += f'    printf("[{i + 1}] {summary} start.\\n");\n'
        body += v.generate_c(ctx)
        body += f'    printf("[{i + 1}] done.\\n");\n\n'
    # body = "".join(v.generate_c(ctx) for v in verbs)
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


def next_seed_index() -> str:
    """Generate next seed index based on existing files in repo directory"""
    repo_dir = Path("./repo")
    repo_dir.mkdir(parents=True, exist_ok=True)

    existing = []
    for p in repo_dir.iterdir():
        if p.is_file() and p.name.endswith("_seed.log"):
            digits = ""
            for c in p.name:
                if c.isdigit():
                    digits += c
                else:
                    break
            if digits:
                existing.append(int(digits))
    n = max(existing) + 1 if existing else 1
    return f"{n:06d}"


def setup_seed_logging(seed_index: str) -> logging.Logger:
    """Setup logging for a specific seed with dedicated log file"""
    repo_dir = Path("./repo")
    log_file = repo_dir / f"{seed_index}_seed.log"

    logger = logging.getLogger(f"seed_{seed_index}")
    logger.setLevel(logging.DEBUG)

    # Clear existing handlers
    for h in list(logger.handlers):
        logger.removeHandler(h)

    # File handler for seed-specific log
    fh = logging.FileHandler(str(log_file), mode="w", encoding="utf-8")
    fmt = logging.Formatter("[%(asctime)s] %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler for immediate feedback
    ch = logging.StreamHandler(sys.stdout)
    ch_fmt = logging.Formatter(f"[SEED_{seed_index}] %(message)s")
    ch.setFormatter(ch_fmt)
    logger.addHandler(ch)

    return logger

import importlib
import random

if __name__ == "__main__":
    print("This is gen_code_from_scaffold.py - generates C code from scaffolded verbs.")

    scaffolds_pkg = "lib.scaffolds"
    scaffold_name = "atomic_pair"  # Change this to use different scaffolds
    fqmn = f"{scaffolds_pkg}.{scaffold_name}"
    mod = importlib.import_module(fqmn)
    build_fn = getattr(mod, "build", None)

    verbs = copy.deepcopy(INITIAL_VERBS)
    ctx = CodeGenContext()
    for v in verbs:  # initial check
        v.apply(ctx)
    snap = global_snapshot = ctx.contracts.snapshot()
    ret = build_fn(snap, global_snapshot, random.Random(42))
    verbs, hotspots = ret if ret else ([], [])
    verbs = INITIAL_VERBS + verbs

    ctx = CodeGenContext()
    for v in verbs:
        print(summarize_verb(v, deep=False))
    for v in verbs:
        v.apply(ctx)

    rendered = render(verbs)
    with open("client.cpp", "w", encoding="utf-8") as f:
        f.write(rendered)

