import importlib
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from termcolor import colored

import lib.contracts as contracts
import lib.fuzz_mutate as fuzz_mutate
import lib.ibv_all as ibv_all
import lib.verbs as verbs
from lib.debug_dump import diff_verb_snapshots, dump_verbs, snapshot_verbs, summarize_verb, summarize_verb_list

# Allow users to override the module name via env var (default: "verbs").
# VERBS_MODULE = os.environ.get("VERBS_MODULE", "lib.verbs")

# verbs = importlib.import_module(VERBS_MODULE)

State = contracts.State

# --- Test Helpers ---


class FakeTracker:
    def __init__(self):
        self.calls = []  # e.g. ("use","pd","pd0"), ("create","mr","mr0", {...}), ("destroy","qp","qp0")

    def use(self, typ, name):
        self.calls.append(("use", typ, str(name)))

    def create(self, typ, name, **kwargs):
        self.calls.append(("create", typ, str(name), kwargs))

    def destroy(self, typ, name):
        self.calls.append(("destroy", typ, str(name)))


class FakeCtx:
    def __init__(self, ib_ctx="ctx"):
        self.tracker = FakeTracker()
        self.ib_ctx = ib_ctx
        self._vars = []
        self.contracts = contracts.ContractTable()

    def alloc_variable(self, name, ty, init=None):
        self._vars.append((name, ty, init))


@dataclass
class Snapshot:
    # res_states[(rtype, name)] = State or None
    res_states: Dict[Tuple[str, str], Optional[State]]


# simple assert helper
def assert_contains(s, token):
    assert token in s, f"expected to find {token!r} in generated code:\n{s}"


def apply_instantiated_contract(snap: Snapshot, ic) -> Snapshot:
    rs = dict(snap.res_states)
    # produces override/create
    for p in ic.produces:
        rs[(p.rtype, p.name_attr)] = p.state
    # transitions update state
    for t in ic.transitions:
        rs[(t.rtype, t.name_attr)] = t.to_state
    return Snapshot(rs)


def build_prefix_snapshots(verbs_list: List[Any]) -> List[Snapshot]:
    snaps = [Snapshot(res_states={})]
    cur = snaps[0]
    for v in verbs_list:
        ic = v.instantiate_contract()
        cur = apply_instantiated_contract(cur, ic)
        snaps.append(cur)
    return snaps  # length = len(verbs_list)+1, index i = state before inserting at i


def _mk_pd(name="pd0"):
    v = verbs.AllocPD(pd=name)
    return v


def _mk_cq(name="cq0"):
    v = verbs.CreateCQ(cq=name)
    return v


def _mk_mr(pd, buf="buf[0]", length=1024, name="mr0", flags=None):
    if flags is None:
        flags = "IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE"
    v = verbs.RegMR(pd=pd, addr=buf, length=length, mr=name, access=flags)
    return v


def _mk_qp(pd, cq, name="qp0", init_attr_obj=None):
    if init_attr_obj is None:
        init_attr_obj = ibv_all.IbvQPInitAttr(
            send_cq=cq,
            recv_cq=cq,
            cap=ibv_all.IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1),
            qp_type="IBV_QPT_RC",
            sq_sig_all=1,
        )
    v = verbs.CreateQP(qp=name, pd=pd, init_attr_obj=init_attr_obj)
    return v


def _mk_modify_qp(qp, attr_mask, attr_obj):
    v = verbs.ModifyQP(qp=qp, attr_mask=attr_mask, attr_obj=attr_obj)
    return v


def _mk_modify_qp_init(qp):
    attr_mask = "IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS"
    attr_obj = ibv_all.IbvQPAttr(
        qp_state="IBV_QPS_INIT",
        pkey_index=0,
        port_num=1,
        qp_access_flags="IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE",
    )
    return _mk_modify_qp(qp, attr_mask, attr_obj)


def _mk_modify_qp_rtr(qp):
    attr_mask = "IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER"
    attr_obj = ibv_all.IbvQPAttr(
        qp_state="IBV_QPS_RTR",
        path_mtu="IBV_MTU_1024",
        dest_qp_num="local_remote_qp_map[QP0->qp_num]",
        rq_psn=0,
        max_dest_rd_atomic=1,
        min_rnr_timer=12,
        ah_attr=ibv_all.IbvAHAttr(
            is_global=1,
            dlid="remote_info.lid",
            sl=0,
            src_path_bits=0,
            port_num=1,
            grh=ibv_all.IbvGlobalRoute(
                sgid_index=1,
                hop_limit=1,
                traffic_class=0,
                flow_label=0,
                dgid=ibv_all.IbvGID(src_var="remote_info.gid"),
            ),
        ),
    )
    return _mk_modify_qp(qp, attr_mask, attr_obj)


def _mk_modify_qp_rts(qp):
    attr_mask = (
        "IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC"
    )
    attr_obj = ibv_all.IbvQPAttr(
        qp_state="IBV_QPS_RTS", timeout=14, retry_cnt=7, rnr_retry=7, sq_psn=0, max_rd_atomic=1
    )
    return _mk_modify_qp(qp, attr_mask, attr_obj)


def _mk_post_send(qp, wr_id=1, num_sge=1, opcode="IBV_WR_SEND", send_flags="IBV_SEND_SIGNALED", sg_list=None):
    if sg_list is None:
        sg_list = [ibv_all.IbvSge(addr="(uintptr_t)bufs[0]", length="MSG_SIZE", lkey="MR0->lkey")]
    v = verbs.PostSend(
        qp=qp,
        wr_obj=ibv_all.IbvSendWR(
            wr_id=wr_id,
            num_sge=num_sge,
            opcode=opcode,
            send_flags=send_flags,
            sg_list=sg_list,
        ),
    )
    return v


def _mk_poll_cq(cq):
    v = verbs.PollCQ(cq=cq)
    return v


def _mk_destroy_qp(qp):
    v = verbs.DestroyQP(qp=qp)
    return v


def _mk_destroy_cq(cq):
    v = verbs.DestroyCQ(cq=cq)
    return v


def _mk_dealloc_pd(pd):
    v = verbs.DeallocPD(pd=pd)
    return v


def _mk_dereg_mr(mr):
    v = verbs.DeregMR(mr=mr)
    return v


if __name__ == "__main__":
    buf_size = 1024
    original_verb_list = [
        _mk_pd("PD0"),
        _mk_cq("CQ0"),
        _mk_mr("PD0", buf="bufs[0]", length=buf_size, name="MR0"),
        _mk_qp("PD0", "CQ0", name="QP0"),
        _mk_modify_qp_init("QP0"),
        _mk_modify_qp_rtr("QP0"),
        _mk_modify_qp_rts("QP0"),
        _mk_post_send("QP0"),
        _mk_poll_cq("CQ0"),
        _mk_destroy_qp("QP0"),
        _mk_destroy_cq("CQ0"),
        _mk_dealloc_pd("PD0"),
        _mk_dereg_mr("MR0"),
    ]
    random.seed(42)  # for reproducibility
    CHOICES = [
        "destroy_qp",
        "destroy_cq",
        "dealloc_pd",
        "dereg_mr",
    ]
    for choice in CHOICES:
        print(colored(f"=== Mutation Choice: {choice} ===", "red"))
        for i in range(len(original_verb_list)):
            print(colored(f"=== Mutation Iteration {i} ===", "blue"))
            rng = random.Random(42)  # for reproducibility
            ctx = FakeCtx()
            verb_list = list(original_verb_list)  # make a copy
            for v in verb_list:
                v.apply(ctx)
            print(colored("=== VERBS SUMMARY (before) ===", "green"))
            print(
                summarize_verb_list(verbs=verb_list, deep=True, highlight=i)
            )  # 如果想看 before 的一行摘要：传入反序列化前的原 list
            mutator = fuzz_mutate.ContractAwareMutator(rng=rng)
            # mutator.mutate(verb_list, i, "insert")
            flag = mutator.mutate_insert(verb_list, i, choice=choice)

            ctx = FakeCtx()
            print(colored("=== VERBS SUMMARY (after) ===", "green"))
            if flag:
                print(
                    summarize_verb_list(verbs=verb_list, deep=True, highlight=i, color="green")
                )  # 如果想看 before 的一行摘要：传入反序列化前的
            else:
                print(summarize_verb_list(verbs=verb_list, deep=True))

            try:
                for v in verb_list:
                    v.apply(ctx)
            except Exception as e:
                print(colored(f"Error during apply: {e}", "red"))
                print(summarize_verb(v, deep=True))  # 如果想看某个 verb 的一行摘要：传入反序列化前的原 verb
                exit(1)
            print()
