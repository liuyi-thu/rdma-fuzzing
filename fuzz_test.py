import copy
import json
import os
import random
import traceback
import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler

from typing import Dict, List

from jinja2 import Environment, FileSystemLoader
from termcolor import colored

from lib import fuzz_mutate
from lib.codegen_context import CodeGenContext
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
    DestroyCQ(cq="cq0"),
    DestroySRQ(srq="srq0"),
    DeregMR(mr="mr0"),
    DeallocPD(pd="pd0"),
    FreeDM(dm="dm0"),  # --- IGNORE ---
]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    p.add_argument("--rounds", type=int, default=1000, help="Number of fuzzing rounds")
    p.add_argument("--out-dir", type=str, default="./out", help="Output directory for generated files")
    return p.parse_args()


def setup_logging(log_file: str, to_console: bool = False, level=logging.INFO):
    # 根 logger
    logger = logging.getLogger()
    logger.setLevel(level)

    # 清理旧的 handler，避免重复添加
    for h in list(logger.handlers):
        logger.removeHandler(h)

    # 文件轮转（50MB * 3份备份）
    fh = RotatingFileHandler(log_file, mode="w", maxBytes=50 * 1024 * 1024, backupCount=3, encoding="utf-8")
    # fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(process)d %(name)s: %(message)s")
    fmt = logging.Formatter("%(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    if to_console:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    # 把 warnings.warn(...) 也导入 logging（归入 WARNING）
    logging.captureWarnings(True)

    # 把“未捕获异常”的 traceback 也写进日志
    def _excepthook(exc_type, exc, tb):
        logging.critical("Uncaught exception", exc_info=(exc_type, exc, tb))
        # 仍然让默认行为继续（可选）。如果不想再打印到stderr，就注释掉下一行
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _excepthook


def run(args):
    # 你的业务逻辑
    logging.info("start fuzzing: seed=%s rounds=%s", args.seed, args.rounds)
    # 示例：手动记录异常堆栈（捕获型）
    try:
        seed = args.seed
        max_rounds = args.rounds

        ctx = CodeGenContext()
        verbs: list[VerbCall] = INITIAL_VERBS
        rng = random.Random(seed)
        logging.info("Initial verbs:\n%s", summarize_verb_list(verbs=verbs, deep=True))
        for _round in range(max_rounds):
            logging.info("=== TEST ROUND %d ===", _round)
            mutator = fuzz_mutate.ContractAwareMutator(rng=rng)
            mutated = mutator.mutate(verbs)

            logging.info("=== VERBS SUMMARY (after) ===")
            logging.info(
                summarize_verb_list(verbs=verbs, deep=True) + "\n"
            )  # 如果想看 before 的一行摘要：传入反序列化前的

        # f.close()

        pass
    except Exception:
        logging.exception("Exception during fuzzing loop")  # 带完整 traceback
        raise  # 继续抛出也行，交给上面的 excepthook 再记一遍


def render(verbs, ctx):
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
    args = parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    log_file = os.path.join(args.out_dir, f"seed_{args.seed if args.seed is not None else 'none'}.log")
    setup_logging(log_file, to_console=False, level=logging.DEBUG)
    run(args)


# if __name__ == "__main__":
#     arg = argparse.ArgumentParser()
#     arg.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
#     arg.add_argument("--rounds", type=int, default=1000, help="Number of fuzzing rounds")
#     arg.add_argument("--out-dir", type=str, default="./out", help="Output directory for generated files")
#     args = arg.parse_args()
