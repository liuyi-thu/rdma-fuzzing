# lib/fuzz_mutate.py (refactored)
from __future__ import annotations

import logging
import random
import re
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple, Callable

from termcolor import colored

from lib.debug_dump import diff_verb_snapshots, dump_verbs, snapshot_verbs, summarize_verb, summarize_verb_list

from .value import Value
from .verbs import ModifyQP, VerbCall

try:
    from .contracts import ContractError, ContractTable, State
except Exception:
    ContractTable = None

    class ContractError(Exception): ...

    class State:
        ALLOCATED = "ALLOCATED"
        RESET = "RESET"
        INIT = "INIT"
        RTR = "RTR"
        RTS = "RTS"
        DESTROYED = "DESTROYED"


# ========================= Config =========================
@dataclass
class MutatorConfig:
    repair: bool = True
    dryrun_contract: bool = True
    pass_through_fail_prob: float = 0.0
    verbose: bool = False  # 控制调试输出


# ========================= Ctx (dry-run) =========================
class _FakeTracker:
    def __init__(self):
        self.calls = []

    def use(self, typ, name):
        self.calls.append(("use", typ, str(name)))

    def create(self, typ, name, **kw):
        self.calls.append(("create", typ, str(name), kw))

    def destroy(self, typ, name):
        self.calls.append(("destroy", typ, str(name)))


class FakeCtx:
    def __init__(self, ib_ctx="ctx"):
        self.tracker = _FakeTracker()
        self.ib_ctx = ib_ctx
        self.variables = {}
        self.bindings = {}
        # 统一的 contracts：如果 ContractTable 不可用，则注入一个 dummy
        if ContractTable is not None:
            self.contracts = ContractTable()
        else:

            class _DummyContracts:
                def apply_contract(self, verb, contract):
                    pass

                def snapshot(self):
                    return {}

            self.contracts = _DummyContracts()

    def alloc_variable(self, name, type, init_value=None, array_size=None):
        name = str(name)
        if name in self.variables and type != self.variables[name][0]:
            raise ValueError(f"Variable '{name}' already allocated, but with a different type {self.variables[name]}.")
        else:
            if name in self.variables:
                # raise ValueError(f"Variable '{name}' already allocated.")
                # support reuse
                return False
            else:
                self.variables[name] = [type, init_value, array_size]
                return True

    def gen_var_name(self, prefix="var", sep="_"):
        idx = 0
        while True:
            name = f"{prefix}{sep}{idx}"
            if name not in self.variables:
                return name
            idx += 1

    def make_qp_binding(self, local_qp: str, remote_qp: str):
        self.bindings[local_qp] = remote_qp

    def get_peer_qp_num(self, local_qp: str) -> str:
        if local_qp not in self.bindings:
            raise ValueError(f"No binding found for local QP '{local_qp}'")
        return self.bindings[local_qp]


# ========================= Helpers (unwrap/dotted) =========================
def _get_dotted(obj: Any, dotted: str) -> Any:
    cur = obj
    for p in dotted.split("."):
        if cur is None:
            return None
        cur = _unwrap_value(cur)
        cur = getattr(cur, p, None)
    return cur


def _unwrap(x):
    """统一解包 OptionalValue/ResourceValue/ConstantValue 等。"""
    if x is None:
        return None
    inner = getattr(x, "inner", None)
    if inner is not None:  # OptionalValue
        return _unwrap(inner)
    name = getattr(x, "name", None)
    rty = getattr(x, "resource_type", None)
    if name is not None and rty is not None:  # ResourceValue
        return str(name)
    val = getattr(x, "value", None)
    if val is not None:
        return _unwrap(val)
    return x


def listify(x) -> List[Any]:
    x = _unwrap(x)
    if x is None:
        return []
    if isinstance(x, (list, tuple)):
        return list(x)
    return [x]


# ---- 位置选择策略：best / append / prepend / random ----


def _choose_insert_pos(
    feasible: list[tuple[int, list[VerbCall]]], rng: random.Random, *, place: str = "best"
) -> tuple[int, list[VerbCall]] | None:
    """在一组 (pos, ins_list) 中选择一个，返回 (pos, ins_list) 或 None。"""
    if not feasible:
        return None
    place = (place or "best").lower()
    if place == "append":
        return max(feasible, key=lambda x: x[0])
    if place == "prepend":
        return min(feasible, key=lambda x: x[0])
    if place == "random":
        return rng.choice(feasible)
    # "best": 偏向靠后，最后 2~3 个位置里随机一个，避免过度偏置同一点
    m = max(p for p, _ in feasible)
    tail = [pair for pair in feasible if pair[0] >= m - 2]
    # logging.debug("tail: %s", tail)
    return rng.choice(tail) if tail else max(feasible, key=lambda x: x[0])


# ========================= Error classification =========================
class ErrKind:
    MISSING_RESOURCE = "missing_resource"
    ILLEGAL_TRANSITION = "illegal_transition"
    DANGLING_DESTROY = "dangling_destroy"
    DOUBLE_DESTROY = "double_destroy"
    UNKNOWN = "unknown"


_missing_re = re.compile(r"required resource not found:\s*(\w+)\s+([^\s]+)", re.I)
_illegal_re = re.compile(
    r"illegal transition for\s+(\w+)\s+([^\s]+):\s*([A-Z_]+)\s*->\s*([A-Z_]+),\s*expected from\s*([A-Z_]+)", re.I
)


def classify_contract_error(msg: str) -> Tuple[str, dict]:
    m = _missing_re.search(msg or "")
    if m:
        return ErrKind.MISSING_RESOURCE, {"rtype": m.group(1), "name": m.group(2)}
    m = _illegal_re.search(msg or "")
    if m:
        return ErrKind.ILLEGAL_TRANSITION, {
            "rtype": m.group(1),
            "name": m.group(2),
            "cur": m.group(3),
            "to": m.group(4),
            "expect_from": m.group(5),
        }
    if "destroy before create" in (msg or ""):
        return ErrKind.DANGLING_DESTROY, {}
    if "destroy twice" in (msg or ""):
        return ErrKind.DOUBLE_DESTROY, {}
    return ErrKind.UNKNOWN, {}


# ========================= Resource/SG invariants =========================
RESOURCE_TYPES = {"pd", "cq", "qp", "mr", "mw", "wq", "srq", "flow", "ah", "channel", "table", "dm"}


def is_resource_field(name: str) -> bool:
    return name.split(".")[-1] in RESOURCE_TYPES


def fix_sg_invariants(obj: Any) -> None:
    """保持 (sg_list|sge|sgl) 和 (num_sge|num_sges) 一致。"""
    sgl_name = next((n for n in ("sg_list", "sge", "sgl") if hasattr(obj, n)), None)
    n_name = next((n for n in ("num_sge", "num_sges") if hasattr(obj, n)), None)
    if not sgl_name or not n_name:
        return
    n = len(listify(getattr(obj, sgl_name)))
    cur = getattr(obj, n_name)
    if hasattr(cur, "value"):
        cur.value = n
    else:
        setattr(obj, n_name, n)


# ========================= QP FSM =========================
_QP_ORDER = ["RESET", "INIT", "RTR", "RTS", "SQD", "ERR"]
_QP_NEXT = {"RESET": ["INIT"], "INIT": ["RTR"], "RTR": ["RTS"], "RTS": ["RTS"]}


def _qp_path(from_state: str, to_state: str):
    """返回最短路径（不含起点，含终点）；不可达 None。"""
    if from_state == to_state:
        return []
    cur, path, seen = from_state, [], set()
    while cur != to_state:
        if cur in seen:
            return None
        seen.add(cur)
        nxts = _QP_NEXT.get(cur, [])
        if not nxts:
            return None
        cur = nxts[0]
        path.append(cur)
        if len(path) > 16:
            return None
    return path


def _state_leq(a: str, b: str) -> bool:
    try:
        return _QP_ORDER.index(a) <= _QP_ORDER.index(b)
    except ValueError:
        return False


def _qp_state_before(snap, qp_name: str) -> str:
    return snap.get(("qp", qp_name)) or "RESET"


def _make_snapshot(verbs, i: int):
    ctx = FakeCtx()
    for j in range(0, i):
        verbs[j].apply(ctx)
    snap = ctx.contracts.snapshot() if hasattr(ctx, "contracts") else {}
    return snap


def _first_successor_target_after(verbs, i: int, qp_name: str):
    for k in range(i, len(verbs)):
        v = verbs[k]
        if v.__class__.__name__ != "ModifyQP":
            continue
        name = _unwrap(_get_dotted(v, "qp"))
        if str(name) != str(qp_name):
            continue
        target = _unwrap(_get_dotted(getattr(v, "attr_obj", None), "qp_state"))
        if target and str(target).startswith("IBV_QPS_"):
            return str(target).replace("IBV_QPS_", "")
    return None


# ========================= Contract graph edges =========================
def _is_optional_none(x):
    return hasattr(x, "is_none") and x.is_none()


def _unwrap_value(x):
    if x is None:
        return None
    if hasattr(x, "inner"):
        return _unwrap_value(getattr(x, "inner"))
    if hasattr(x, "name") and hasattr(x, "resource_type"):
        return getattr(x, "name")
    if hasattr(x, "value"):
        return _unwrap_value(getattr(x, "value"))
    return x


# ========================= Minimal builders =========================
def mk_min_qp_cap():
    from lib.ibv_all import IbvQPCap

    return IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1, max_inline_data=0)


def mk_min_gid():
    from lib.ibv_all import IbvGID

    return IbvGID.zero()


def mk_min_grh():
    from lib.ibv_all import IbvGlobalRoute

    return IbvGlobalRoute(dgid=mk_min_gid(), flow_label=0, sgid_index=0, hop_limit=0, traffic_class=0)


def mk_min_ah_attr(*, use_grh=False):
    from lib.ibv_all import IbvAHAttr

    if not use_grh:
        return IbvAHAttr(grh=None, dlid=1, sl=None, src_path_bits=None, static_rate=None, is_global=False, port_num=1)
    else:
        return IbvAHAttr(
            grh=mk_min_grh(), dlid=1, sl=None, src_path_bits=None, static_rate=None, is_global=True, port_num=1
        )


# ==== 新增：最小 WR/SGE 构造 ====
def _mk_min_recv_wr():
    from lib.ibv_all import IbvRecvWR, IbvSge

    sge = IbvSge(addr=0x2000, length=32, lkey=0x5678)
    return IbvRecvWR(num_sge=1, sg_list=[sge])


def _mk_min_send_wr():
    from lib.ibv_all import IbvSendWR, IbvSge

    sge = IbvSge(addr=0x1000, length=16, lkey=0x1234)
    return IbvSendWR(opcode="IBV_WR_SEND", num_sge=1, sg_list=[sge])


# ==== 新版：最小 WR/SGE 构造（传入 mr 名称） ====
def _mk_min_recv_wr_with_mr(mr_name: str):
    from lib.ibv_all import IbvRecvWR, IbvSge

    sge = IbvSge(mr=mr_name)
    return IbvRecvWR(num_sge=1, sg_list=[sge])


def _mk_min_send_wr_with_mr(mr_name: str):
    from lib.ibv_all import IbvSendWR, IbvSge

    sge = IbvSge(mr=mr_name)
    # 最小可行：SEND + 1 SGE
    return IbvSendWR(opcode="IBV_WR_SEND", num_sge=1, sg_list=[sge])


def _mk_min_mw_bind_with_mr(mr_name: str):
    """
    返回 (mw_bind_obj, mr_name)。若现场没有 MR，则生成一个占位名并交给 requires-filler 去补链。
    """
    from lib.ibv_all import IbvMwBind, IbvMwBindInfo

    bind_info = IbvMwBindInfo(mr=mr_name, addr=0x0, length=0x1000, mw_access_flags=0)  # 最小配置
    return IbvMwBind(bind_info=bind_info)


# ==== Minimal builders (复用你已有的 ibv_all 聚合) ====
def _mk_min_srq_init():
    from lib.ibv_all import IbvSrqAttr, IbvSrqInitAttr

    # 你的 CreateSRQ 里要求 IbvSrqInitAttr(srq_context, attr=IbvSrqAttr(...))
    return IbvSrqInitAttr(srq_context=None, attr=IbvSrqAttr(max_wr=1, max_sge=1, srq_limit=0))


def _mk_min_wq_init(pd_name: str, cq_name: str):
    from lib.ibv_all import IbvWQInitAttr

    # 你在 verbs.CreateWQ.CONTRACT 里会追溯 wq_attr_obj.pd / cq
    return IbvWQInitAttr(pd=pd_name, cq=cq_name, wq_type="IBV_WQT_RQ", max_wr=1, max_sge=1)


def _mk_min_ah_attr():
    from lib.ibv_all import IbvAHAttr

    # 不带 GRH，走本地 lid 路线（更稳）
    return IbvAHAttr(is_global=0, port_num=1, dlid=1)


def _mk_min_flow_attr():
    from lib.ibv_all import IbvFlowAttr

    # 用最小规则，驱动支持不同；这里给一个保守模板（你那边 IbvFlowAttr 已实现 to_cxx）
    return IbvFlowAttr()  # 若需要，可在 ibv_all 里加 random/minimal 填充


# ---- QP init（CreateQP 用）----
def _mk_min_qp_init(send_cq: str, recv_cq: str):
    from lib.ibv_all import IbvQPCap, IbvQPInitAttr

    return IbvQPInitAttr(
        qp_type="IBV_QPT_RC",
        send_cq=send_cq,
        recv_cq=recv_cq,
        cap=IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1),
    )


# ---- CQ attr（ModifyCQ 用）----
def _mk_min_cq_attr():
    from lib.ibv_all import (
        IbvModerateCQ,
        IbvModifyCQAttr,  # 若你的聚合模块里类名不同，改这里
    )

    # 常见最低变更：只改 cqe/cq_cap 或 moderation（按你的 IbvCQAttr 定义来）
    return IbvModifyCQAttr(
        attr_mask=0, moderate=IbvModerateCQ(cq_count=1, cq_period=1)
    )  # 示例：moderation 1 event/0 usec


# ---- MW alloc 的最小形态 ----
def _mk_min_alloc_mw(pd_name: str, mw_name: str):
    from .verbs import AllocMW

    # 若你的 AllocMW 需要 mw_type，按 verbs.py 调整
    return AllocMW(pd=pd_name, mw=mw_name, mw_type="IBV_MW_TYPE_1")


# ---- DM alloc 的最小形态 ----
def _mk_min_alloc_dm(dm_name: str):
    from lib.ibv_all import IbvAllocDmAttr  # 若你的 IbvAllocDmAttr 有不同字段，按需调整

    from .verbs import AllocDM

    # 视你的 verbs.py 签名而定：很多实现是 ctx_name + length + align
    return AllocDM(ctx_name="ctx", dm=dm_name, attr_obj=IbvAllocDmAttr(length=0x2000, log_align_req=64))


# ========================= ModifyQP builders =========================
# 字段名 → attr_mask 位名
_QP_FIELD2MASK = {
    "cur_qp_state": "IBV_QP_CUR_STATE",
    "en_sqd_async_notify": "IBV_QP_EN_SQD_ASYNC_NOTIFY",
    "qp_access_flags": "IBV_QP_ACCESS_FLAGS",
    "pkey_index": "IBV_QP_PKEY_INDEX",
    "port_num": "IBV_QP_PORT",
    "qkey": "IBV_QP_QKEY",
    "ah_attr": "IBV_QP_AV",
    "path_mtu": "IBV_QP_PATH_MTU",
    "timeout": "IBV_QP_TIMEOUT",
    "retry_cnt": "IBV_QP_RETRY_CNT",
    "rnr_retry": "IBV_QP_RNR_RETRY",
    "rq_psn": "IBV_QP_RQ_PSN",
    "max_rd_atomic": "IBV_QP_MAX_QP_RD_ATOMIC",
    "min_rnr_timer": "IBV_QP_MIN_RNR_TIMER",
    "sq_psn": "IBV_QP_SQ_PSN",
    "max_dest_rd_atomic": "IBV_QP_MAX_DEST_RD_ATOMIC",
    "path_mig_state": "IBV_QP_PATH_MIG_STATE",
    "cap": "IBV_QP_CAP",
    "dest_qp_num": "IBV_QP_DEST_QPN",
    "rate_limit": "IBV_QP_RATE_LIMIT",
}

ALLOW_ATTRS_BY_STATE = {
    "RESET": [],
    "INIT": [
        "path_mtu",
        "qp_access_flags",
        "pkey_index",
        "port_num",
        "rq_psn",
        "sq_psn",
        "dest_qp_num",
        "cap",
        "ah_attr",
    ],
    "RTR": ["path_mtu", "min_rnr_timer", "max_dest_rd_atomic", "ah_attr", "timeout", "retry_cnt", "rnr_retry"],
    "RTS": ["timeout", "retry_cnt", "rnr_retry", "max_rd_atomic", "rate_limit", "path_mtu"],
}


def build_modify_qp_out(verbs, i: int, snap, qp_name: str, rng):
    if rng.random() < 0.5:
        res = build_modify_qp_safe_chain(verbs, i, snap, qp_name, rng)
        if res:
            return res
        else:
            return build_modify_qp_stateless(snap, qp_name, rng)
    else:
        return build_modify_qp_stateless(snap, qp_name, rng)


def build_modify_qp_safe_chain(verbs, i: int, snap, qp_name: str, rng) -> List[VerbCall]:
    from lib.ibv_all import IbvQPAttr

    cur = _qp_state_before(snap, qp_name)  # 也可从 snapshot 里取
    succ = _first_successor_target_after(verbs, i, qp_name)  # 真的要用到完整verbs了

    def _rand_target_from(s, rng):
        idx = _QP_ORDER.index(s) if s in _QP_ORDER else 0
        end = min(idx + 2, len(_QP_ORDER) - 1)
        return _QP_ORDER[rng.randint(idx + 1, end)]

    target = succ if succ is not None and _state_leq(cur, succ) else _rand_target_from(cur, rng)
    path = _qp_path(cur, target)
    if not path:
        return []
    L = rng.randrange(1, len(path) + 1)
    prefix = path[:L]
    return [
        ModifyQP(qp=qp_name, attr_obj=IbvQPAttr(qp_state=f"IBV_QPS_{st}"), attr_mask="IBV_QP_STATE") for st in prefix
    ]


def build_modify_qp_stateless(snap, qp_name: str, rng) -> Optional[VerbCall]:
    from lib.ibv_all import IbvQPAttr

    cur = _qp_state_before(snap, qp_name)
    cand = ALLOW_ATTRS_BY_STATE.get(cur, [])
    if not cand:
        return None
    field = rng.choice(cand)
    kwargs, masks = {"qp_state": None}, []
    if field == "path_mtu":
        kwargs["path_mtu"] = rng.choice(["IBV_MTU_512", "IBV_MTU_1024", "IBV_MTU_2048"])
    elif field == "qp_access_flags":
        kwargs["qp_access_flags"] = rng.choice([0, 1, 7])
    elif field == "pkey_index":
        kwargs["pkey_index"] = rng.randint(0, 128)
    elif field == "port_num":
        kwargs["port_num"] = rng.choice([1, 2])
    elif field == "rq_psn":
        kwargs["rq_psn"] = rng.randint(0, (1 << 24) - 1)
    elif field == "sq_psn":
        kwargs["sq_psn"] = rng.randint(0, (1 << 24) - 1)
    elif field == "dest_qp_num":
        kwargs["dest_qp_num"] = rng.randint(0, (1 << 24) - 1)
    elif field == "cap":
        kwargs["cap"] = mk_min_qp_cap()
    elif field == "ah_attr":
        kwargs["ah_attr"] = mk_min_ah_attr(use_grh=False)
    elif field == "min_rnr_timer":
        kwargs["min_rnr_timer"] = rng.randint(0, 31)
    elif field == "max_dest_rd_atomic":
        kwargs["max_dest_rd_atomic"] = rng.choice([1, 4, 8])
    elif field == "timeout":
        kwargs["timeout"] = rng.choice([0, 14, 20, 30])
    elif field == "retry_cnt":
        kwargs["retry_cnt"] = rng.choice([0, 3, 7])
    elif field == "rnr_retry":
        kwargs["rnr_retry"] = rng.choice([0, 3, 7])
    elif field == "max_rd_atomic":
        kwargs["max_rd_atomic"] = rng.choice([1, 4, 8])
    elif field == "rate_limit":
        kwargs["rate_limit"] = rng.randint(0, 0xFFFFF)
    else:
        return None
    masks.append(_QP_FIELD2MASK.get(field, ""))
    attr_mask = "|".join([m for m in masks if m])
    return ModifyQP(qp=qp_name, attr_obj=IbvQPAttr(**kwargs), attr_mask=attr_mask)


# ---- 判断是否为 Destroy verb，并提取 DESTROYED 目标 ----
def is_destroy_verb(v) -> bool:
    tr = getattr(v.__class__, "CONTRACT", None)
    if not tr:
        return v.__class__.__name__.startswith(("Destroy", "Dealloc", "Dereg"))
    for t in getattr(tr, "transitions", []) or []:
        # to_state = str(getattr(t, "to_state", "")).upper()
        # if to_state == "DESTROYED":
        to_state = getattr(t, "to_state", None)
        if to_state == State.DESTROYED:
            return True
    return False


def destroyed_targets(v) -> set[tuple[str, str]]:
    """
    返回本 verb 将置为 DESTROYED 的 {(rtype, name)} 集合。
    优先用 CONTRACT.transitions；否则按类名猜测（兜底）。
    """
    outs = set()
    tr = getattr(v.__class__, "CONTRACT", None)
    # print("tr:", tr)
    if tr:
        for t in getattr(tr, "transitions", []) or []:
            to_state = getattr(t, "to_state", None)
            if to_state == State.DESTROYED:
                rtype = getattr(t, "rtype", None)
                name_attr = getattr(t, "name_attr", None)
                if rtype and name_attr:
                    name = _unwrap(_get_dotted(v, name_attr))
                    if name:
                        outs.add((str(rtype), str(name)))
    if outs:
        return outs

    # 兜底：依据类名映射推断
    name = v.__class__.__name__
    if name == "DestroyQP":
        outs.add(("qp", str(_unwrap(getattr(v, "qp", None)))))
    elif name == "DestroyCQ":
        outs.add(("cq", str(_unwrap(getattr(v, "cq", None)))))
    elif name == "DeallocPD":
        outs.add(("pd", str(_unwrap(getattr(v, "pd", None)))))
    elif name == "DeregMR":
        outs.add(("mr", str(_unwrap(getattr(v, "mr", None)))))
    elif name == "DeallocMW":
        outs.add(("mw", str(_unwrap(getattr(v, "mw", None)))))
    elif name == "DestroyAH":
        outs.add(("ah", str(_unwrap(getattr(v, "ah", None)))))
    elif name == "DestroyFlow":
        outs.add(("flow", str(_unwrap(getattr(v, "flow", None)))))
    elif name == "DestroyWQ":
        outs.add(("wq", str(_unwrap(getattr(v, "wq", None)))))
    elif name == "DestroySRQ":
        outs.add(("srq", str(_unwrap(getattr(v, "srq", None)))))
    elif name == "DestroyCompChannel":
        outs.add(("channel", str(_unwrap(getattr(v, "channel", None)))))
    elif name == "DeallocTD":
        outs.add(("td", str(_unwrap(getattr(v, "td", None)))))
    return {(t, n) for (t, n) in outs if t and n}


# ---- Destroy 插入模板 ----
def _build_destroy_of_type(snap, rtype, rng):
    """
    从 live 集合里挑选一个 rtype 资源，构造相应 Destroy verb。
    若该类型在现场没有实例，返回 None。
    """
    name = _pick_live_from_snap(snap, rtype, rng)

    # 映射：rtype -> (Class, param_name)
    from .verbs import (
        DeallocMW,
        DeallocPD,
        DeallocTD,
        DeregMR,
        DestroyAH,
        DestroyCompChannel,
        DestroyCQ,
        DestroyFlow,
        DestroyQP,
        DestroySRQ,
        DestroyWQ,
    )

    mapping = {
        "qp": (DestroyQP, "qp"),
        "cq": (DestroyCQ, "cq"),
        "pd": (DeallocPD, "pd"),
        "mr": (DeregMR, "mr"),
        "mw": (DeallocMW, "mw"),
        "ah": (DestroyAH, "ah"),
        "flow": (DestroyFlow, "flow"),
        "wq": (DestroyWQ, "wq"),
        "srq": (DestroySRQ, "srq"),
        "channel": (DestroyCompChannel, "channel"),
        "td": (DeallocTD, "td"),
    }
    if rtype not in mapping:
        return None

    cls, param = mapping[rtype]
    kwargs = {param: name}
    return cls(**kwargs)


def build_destroy_generic(snap, rng):
    """
    优先销毁“叶子资源”，减少大范围连锁影响；
    若无叶子，就退化为销毁任一 live 资源（不包括 device 等全局）。
    """
    # 优先级从“叶子”到“根”：
    order = [
        "mw",
        "mr",
        "ah",
        "flow",
        "wq",
        "srq",  # 叶子优先
        "qp",
        "cq",
        "channel",
        "td",
        "pd",  # 最后考虑 PD（破坏力最大）
    ]
    rng.shuffle(order)

    for rt in order:
        v = _build_destroy_of_type(snap, rt, rng)
        if v is not None:
            return v
    return None


def _pick_live_from_snap(snap: dict, rtype: str, rng: random.Random) -> str | None:
    cands = []
    for (rt, nm), st in (snap or {}).items():
        if rt == rtype and st not in (State.DESTROYED,):
            cands.append(nm)
    return rng.choice(cands) if cands else None


# ========================= Insertion templates =========================
def _pick_insertion_template(
    rng: random.Random, verbs: List[VerbCall], i: int, choice: str = None, global_snapshot=None
) -> Optional[Callable]:
    from lib.ibv_all import IbvQPAttr  # 你已聚合的话

    from .verbs import (
        AllocDM,
        AllocMW,
        AllocPD,
        AttachMcast,
        BindMW,
        CreateAH,
        CreateCQ,
        CreateFlow,
        CreateQP,
        CreateSRQ,
        CreateWQ,
        DestroyAH,
        DestroyFlow,
        DestroySRQ,
        DestroyWQ,
        FreeDM,
        ModifyCQ,
        ModifySRQ,
        PollCQ,
        PostRecv,
        PostSend,
        PostSRQRecv,
        QueryQP,
        QuerySRQ,
        RegDmaBufMR,  # 注意类名大小写
        RegMR,  # 如需补链
        ReqNotifyCQ,
        ReRegMR,
    )

    def gen_new_name(kind, snap, rng):
        # existing = {n for (t, n) in snap.keys() if t == kind}
        # global_snapshot = _make_snapshot(verbs, len(verbs))
        existing = {n for (t, n) in global_snapshot.keys() if t == kind}
        for _ in range(1000):
            name = f"{kind}_{rng.randrange(1 << 16)}"
            if name not in existing:
                return name
        return None

    # 1) ModifyQP：复用你已有的有/无状态策略
    def build_modify_qp(ctx, rng, snap):
        qp = _pick_live_from_snap(snap, "qp", rng)
        if not qp:
            return None
        return build_modify_qp_out(verbs, i, snap, qp, rng)  # 你现有的包装

    # 2) PostSend：最小 WR（1 SGE）

    def build_post_send(ctx, rng, snap):
        qp = _pick_live_from_snap(snap, "qp", rng)
        if not qp:
            return None

        # 先找活着的 MR；没有就插入 RegMR（要有 PD）
        mr_name = _pick_live_from_snap(snap, "mr", rng)
        ins_list = []
        if mr_name is None:
            pd = _pick_live_from_snap(snap, "pd", rng)
            if pd is None:
                return None  # 现场既没 MR 也没 PD，无法自举
            mr_name = gen_new_name("mr", snap, rng)
            ins_list.append(RegMR(pd=pd, mr=mr_name, addr="buf0", length=4096, access="IBV_ACCESS_LOCAL_WRITE"))

        wr = _mk_min_send_wr_with_mr(mr_name)
        ins_list.append(PostSend(qp=qp, wr_obj=wr))
        return ins_list

    # 3) PollCQ
    def build_poll_cq(ctx, rng, snap):
        cq = _pick_live_from_snap(snap, "cq", rng)
        return None if not cq else PollCQ(cq=cq)

    # 4) RegMR（绑定已有 PD）
    def build_reg_mr(ctx, rng, snap):
        pd = _pick_live_from_snap(snap, "pd", rng)
        if not pd:
            return None
        mr_name = gen_new_name("mr", snap, rng)
        return RegMR(pd=pd, mr=mr_name, addr="buf0", length=4096, access="IBV_ACCESS_LOCAL_WRITE")

    # 5) CreateCQ（纯创建）
    def build_create_cq(ctx, rng, snap):
        cq_name = gen_new_name("cq", snap, rng)
        return CreateCQ(cq=cq_name, cqe=16, comp_vector=0, channel="NULL")

    # 6) **PostRecv**（最小 WR：1 SGE）
    def build_post_recv(ctx, rng, snap):
        qp = _pick_live_from_snap(snap, "qp", rng)
        if not qp:
            return None
        mr_name = _pick_live_from_snap(snap, "mr", rng)
        ins_list = []
        if mr_name is None:
            pd = _pick_live_from_snap(snap, "pd", rng)
            if pd is None:
                return None
            mr_name = gen_new_name("mr", snap, rng)
            ins_list.append(RegMR(pd=pd, mr=mr_name, addr="buf0", length=4096, access="IBV_ACCESS_LOCAL_WRITE"))

        wr = _mk_min_recv_wr_with_mr(mr_name)
        ins_list.append(PostRecv(qp=qp, wr_obj=wr))
        return ins_list

    # 7) **BindMW**（绑定已有 MR，产出 MW）
    def build_bind_mw(ctx, rng, snap):
        qp = _pick_live_from_snap(snap, "qp", rng)
        if not qp:
            return None
        mw = _pick_live_from_snap(snap, "mw", rng)
        if not mw:
            return None
        mr = _pick_live_from_snap(snap, "mr", rng)
        mw_bind_obj = _mk_min_mw_bind_with_mr(mr)
        # BindMW 的 CONTRACT: 需要 qp 和 mw_bind_obj.bind_info.mr；产出 mw
        # （没有 MR 时，_ensure_requires_before 会补建 RegMR）
        return BindMW(qp=qp, mw=mw, mw_bind_obj=mw_bind_obj)

    # 8) **AttachMcast**（最小 gid/lid）
    def build_attach_mcast(ctx, rng, snap):
        qp = _pick_live_from_snap(snap, "qp", rng)
        if not qp:
            return None
        # 用最小 GID 变量名（假设你的 ctx 里会有 gid 变量，或者后续你可以在 factories 里补一个定义 GID 的 helper）
        gid_var = "gid0"
        return AttachMcast(qp=qp, gid=gid_var, lid=0)

    # 9) （可选）**RegDmaBufMR**（需要 pd）
    def build_reg_dmabuf_mr(ctx, rng, snap):
        pd = _pick_live_from_snap(snap, "pd", rng)
        if not pd:
            return None
        # mr_name = f"mr_{rng.randrange(1 << 16)}"
        mr_name = gen_new_name("mr", snap, rng)
        # 随便给一个小范围
        return RegDmaBufMR(pd=pd, mr=mr_name, offset=0, length=0x2000, iova=0, fd=3, access="IBV_ACCESS_LOCAL_WRITE")

    # 新增：销毁类模板（支持点名 destroy_XXX，也支持 generic）
    def build_destroy(ctx, rng, snap):
        return build_destroy_generic(snap, rng)

    def build_destroy_qp(ctx, rng, snap):
        return _build_destroy_of_type(snap, "qp", rng)

    def build_destroy_cq(ctx, rng, snap):
        return _build_destroy_of_type(snap, "cq", rng)

    def build_dealloc_pd(ctx, rng, snap):
        return _build_destroy_of_type(snap, "pd", rng)

    def build_dereg_mr(ctx, rng, snap):
        return _build_destroy_of_type(snap, "mr", rng)

    def build_dealloc_mw(ctx, rng, snap):
        return _build_destroy_of_type(snap, "mw", rng)

    # ---------- SRQ ----------
    def build_create_srq(ctx, rng, snap):
        pd = _pick_live_from_snap(snap, "pd", rng)
        if not pd:
            return None
        # srq_name = f"srq_{rng.randrange(1 << 16)}"
        srq_name = gen_new_name("srq", snap, rng)
        return CreateSRQ(pd=pd, srq=srq_name, srq_init_obj=_mk_min_srq_init())

    def build_post_srq_recv(ctx, rng, snap):
        srq = _pick_live_from_snap(snap, "srq", rng)
        from lib.ibv_all import IbvRecvWR

        return PostSRQRecv(srq=rng.choice(srq), wr_obj=_mk_min_recv_wr())

    def build_modify_srq(ctx, rng, snap):
        srq = _pick_live_from_snap(snap, "srq", rng)
        # 你的 ModifySRQ 支持 IbvSrqAttr + mask（verbs 里定义了 attr_mask: IBV_SRQ_ATTR_*）
        from lib.ibv_all import IbvSrqAttr

        return ModifySRQ(
            srq=rng.choice(srq), attr_obj=IbvSrqAttr(max_wr=1, srq_limit=0), attr_mask="IBV_SRQ_MAX_WR | IBV_SRQ_LIMIT"
        )

    # ---------- WQ ----------
    def build_create_wq(ctx, rng, snap):
        pd = _pick_live_from_snap(snap, "pd", rng)
        cq = _pick_live_from_snap(snap, "cq", rng)
        if not (pd and cq):
            return None
        # wq_name = f"wq_{rng.randrange(1 << 16)}"
        wq_name = gen_new_name("wq", snap, rng)
        return CreateWQ(ctx_name="ctx", wq=wq_name, wq_attr_obj=_mk_min_wq_init(pd, cq))

    # ---------- AH ----------
    def build_create_ah(ctx, rng, snap):
        pd = _pick_live_from_snap(snap, "pd", rng)
        if not pd:
            return None
        ah_name = gen_new_name("ah", snap, rng)
        return CreateAH(pd=pd, ah=ah_name, attr_obj=_mk_min_ah_attr())

    # ---------- Flow ----------
    def build_create_flow(ctx, rng, snap):
        qp = _pick_live_from_snap(snap, "qp", rng)
        if not qp:
            return None
        flow_name = gen_new_name("flow", snap, rng)
        return CreateFlow(qp=qp, flow=flow_name, flow_attr_obj=_mk_min_flow_attr())

    # ---------- CQ notify ----------
    def build_req_notify_cq(ctx, rng, snap):
        cq = _pick_live_from_snap(snap, "cq", rng)
        if not cq:
            return None
        return ReqNotifyCQ(cq=cq, solicited_only=rng.choice([0, 1]))

    # ---------- 查询类 ----------
    def build_query_qp(ctx, rng, snap):
        qp = _pick_live_from_snap(snap, "qp", rng)
        if not qp:
            return None
        return QueryQP(qp=qp, attr_mask="IBV_QP_STATE | IBV_QP_PORT | IBV_QP_PKEY_INDEX")

    def build_query_srq(ctx, rng, snap):
        srq = _pick_live_from_snap(snap, "srq", rng)
        if not srq:
            return None
        return QuerySRQ(srq=srq)

    # --- AllocPD: 直接产一个 PD ---
    def build_alloc_pd(ctx, rng, snap):
        # pd_name = f"pd_{rng.randrange(1 << 16)}"
        pd_name = gen_new_name("pd", snap, rng)
        return AllocPD(pd=pd_name)

    # --- CreateQP: 需要 pd/cq，init_attr_obj 引用已有 cq（缺就补链）---
    def build_create_qp(ctx, rng, snap):
        pd = _pick_live_from_snap(snap, "pd", rng)
        if not pd:
            return None
        send_cq = _pick_live_from_snap(snap, "cq", rng)
        recv_cq = _pick_live_from_snap(snap, "cq", rng)
        init = _mk_min_qp_init(send_cq, recv_cq)
        qp_name = gen_new_name("qp", snap, rng)
        return CreateQP(pd=pd, qp=qp_name, init_attr_obj=init)

    # --- ModifyCQ: 改调度/容量等（按你的 IbvCQAttr 定义）---
    def build_modify_cq(ctx, rng, snap):
        cq = _pick_live_from_snap(snap, "cq", rng)
        if not cq:
            return None
        # return ModifyCQ(cq=cq, attr_obj=_mk_min_cq_attr(), attr_mask="IBV_CQ_MODERATION")
        return ModifyCQ(cq=cq, attr_obj=_mk_min_cq_attr())

    # --- AllocMW: 需要 pd，产出 mw ---
    def build_alloc_mw(ctx, rng, snap):
        pd = _pick_live_from_snap(snap, "pd", rng)
        if not pd:
            return None
        return _mk_min_alloc_mw(pd, mw_name=gen_new_name("mw", snap, rng))

    # --- AllocDM / FreeDM: 产出/释放 dm ---
    def build_alloc_dm(ctx, rng, snap):
        return _mk_min_alloc_dm(dm_name=gen_new_name("dm", snap, rng))

    def build_free_dm(ctx, rng, snap):
        dm = _pick_live_from_snap(snap, "dm", rng)
        if not dm:
            return None
        return FreeDM(dm=dm)

    # --- ReRegMR: 需要已存在 mr & pd（flags 简化一版）---
    def build_rereg_mr(ctx, rng, snap):
        mr = _pick_live_from_snap(snap, "mr", rng)
        pd = _pick_live_from_snap(snap, "pd", rng)
        if not (mr and pd):
            return None
        # 例：只变更 access/length；flags 视你的 verbs.py 定义
        length = rng.choice([1024, 4096, 8192])
        return ReRegMR(
            mr=mr,
            pd=pd,
            addr="buf0",
            length=length,
            access="IBV_ACCESS_LOCAL_WRITE",
            flags="IBV_REREG_MR_CHANGE_TRANSLATION | IBV_REREG_MR_CHANGE_ACCESS",
        )

    # ------ choice 精确选择（便于脚本/调试） ------
    dispatch = {
        # 你已有的：
        "modify_qp": build_modify_qp,
        "post_send": build_post_send,
        "poll_cq": build_poll_cq,
        "reg_mr": build_reg_mr,
        "create_cq": build_create_cq,
        "post_recv": build_post_recv,
        "bind_mw": build_bind_mw,
        "attach_mcast": build_attach_mcast,
        "reg_dmabuf_mr": build_reg_dmabuf_mr,
        "destroy": build_destroy,
        "destroy_qp": build_destroy_qp,
        "destroy_cq": build_destroy_cq,
        "dealloc_pd": build_dealloc_pd,
        "dereg_mr": build_dereg_mr,
        "dealloc_mw": build_dealloc_mw,
        # 新增：
        "create_srq": build_create_srq,
        "post_srq_recv": build_post_srq_recv,
        "modify_srq": build_modify_srq,
        "create_wq": build_create_wq,
        "create_ah": build_create_ah,
        "create_flow": build_create_flow,
        "req_notify_cq": build_req_notify_cq,
        "query_qp": build_query_qp,
        "query_srq": build_query_srq,
        "alloc_pd": build_alloc_pd,
        "create_qp": build_create_qp,
        "modify_cq": build_modify_cq,
        "alloc_mw": build_alloc_mw,
        "alloc_dm": build_alloc_dm,
        "free_dm": build_free_dm,
        "rereg_mr": build_rereg_mr,
    }

    if choice:
        if choice not in dispatch:
            raise ValueError(f"Unknown insertion template: {choice}")
        return dispatch[choice]

    # 默认：混合分布（你可根据实验效果调整比例）
    candidates = [
        (build_modify_qp, "qp"),
        (build_post_send, "qp"),
        (build_post_recv, "qp"),
        (build_poll_cq, "cq"),
        (build_reg_mr, "mr"),
        (build_create_cq, "cq"),
        (build_bind_mw, "mw"),
        (build_attach_mcast, "qp"),
        # (build_reg_dmabuf_mr, "mr"),  # 如果想多产出 MR，可以打开
        (build_alloc_pd, "pd"),
        (build_create_qp, "qp"),
        (build_modify_cq, "cq"),
        (build_alloc_mw, "mw"),
        (build_alloc_dm, "dm"),
        (build_free_dm, "dm"),
        (build_rereg_mr, "mr"),
    ]
    return rng.choice(candidates)


# ====== 工具：枚举嵌套可变路径 ======
def _enumerate_mutable_paths(obj, prefix=""):
    """
    返回 [(path_str, leaf_obj)]，path 用点号表示，如 "attr_obj.qp_state"
    规则：
      - 优先使用 Attr/Verb 的 MUTABLE_FIELDS / MUTABLE_FIELD_LIST
      - OptionalValue/ListValue/ResourceValue 等 wrapper 继续深入其 .value / 内部元素
    """
    # 1) 如果是你的 wrapper，递归 value
    from lib.value import ConstantValue, EnumValue, FlagValue, IntValue, ListValue, OptionalValue, ResourceValue, Value

    out = []
    if obj is None or isinstance(obj, Value):  # Value有自己的mutate方法，故不用进一步深入（个人观点）
        return out

    def add(path, leaf):
        out.append((path, leaf))

    # Attr/Verb 带声明的可变字段
    field_names = []
    if hasattr(obj, "MUTABLE_FIELDS"):
        field_names = getattr(obj, "MUTABLE_FIELDS") or []
    elif hasattr(obj, "FIELD_LIST"):
        field_names = getattr(obj, "FIELD_LIST") or []
    elif hasattr(obj, "__dict__"):  # 兜底：无元数据时，把所有非私有属性作为候选
        field_names = [k for k in obj.__dict__.keys() if not k.startswith("_")]

    for fname in field_names:
        if not hasattr(obj, fname):
            continue
        val = getattr(obj, fname)
        path = f"{prefix}.{fname}" if prefix else fname

        # None：可考虑 OptionalValue.factory 构建
        if val is None:
            add(path, None)
            continue

        # OptionalValue：既可以 mutate OptionalValue 本身，也可以深入其内部
        if isinstance(val, OptionalValue):
            add(path, val)  # 让上层有机会 flip present/absent
            inner = val.value
            if inner is not None:
                # 向下挖
                out.extend(_enumerate_mutable_paths(inner, path))
            continue

        # ListValue：可以变长/元素变异
        if isinstance(val, ListValue):
            add(path, val)
            # 尝试深入每个元素
            if isinstance(val.value, list):
                for idx, elem in enumerate(val.value):
                    out.extend(_enumerate_mutable_paths(elem, f"{path}[{idx}]"))
            continue

        # 简单 wrapper：Resource/Int/Enum/Flag/Constant
        if isinstance(val, (ResourceValue, IntValue, EnumValue, FlagValue, ConstantValue)):
            add(path, val)
            continue

        # 复杂 Attr/对象：递归
        if hasattr(val, "__dict__"):
            out.extend(_enumerate_mutable_paths(val, path))
        else:
            add(path, val)

    return out


def _as_str_name(x: Any) -> str:
    if x is None:
        return ""
    if hasattr(x, "value"):
        try:
            return str(x.value)
        except Exception:
            return str(x)
    return str(x)


# --- 递归遍历对象树，收集所有 ResourceValue 出现，返回 {(rtype,name), ...} ---
def _collect_resource_refs(obj: Any) -> Set[Tuple[str, str]]:  # this is a contract-free implementation
    from lib.value import ListValue, OptionalValue, ResourceValue  # 按你的路径调整

    seen: Set[int] = set()
    out: Set[Tuple[str, str]] = set()

    def walk(o: Any):
        if o is None:
            return
        oid = id(o)
        if oid in seen:
            return
        seen.add(oid)

        # 资源引用
        if isinstance(o, ResourceValue):
            rtype = getattr(o, "resource_type", None)
            name = _as_str_name(getattr(o, "value", None))
            if rtype and name:
                out.add((str(rtype), str(name)))
            return

        # OptionalValue: 进入其 .value
        if isinstance(o, OptionalValue):
            walk(getattr(o, "value", None))
            return

        # ListValue: 进入每个元素
        if isinstance(o, ListValue):
            lst = getattr(o, "value", None)
            if isinstance(lst, list):
                for it in lst:
                    walk(it)
            return

        # 常规对象：遍历公开字段
        if hasattr(o, "__dict__"):
            for k, v in o.__dict__.items():
                if k.startswith("_"):
                    continue
                walk(v)
        elif isinstance(o, (list, tuple)):
            for it in o:
                walk(it)
        # 其他原子类型忽略

    walk(obj)
    return out


# --- 收集 verb 的 requires（优先走 get_required_resources_recursively，其次静态扫描） ---
def _requires_of(verb: Any) -> Set[Tuple[str, str]]:
    return _collect_resource_refs(verb)


# --- 收集 verb 的 produces（优先 CONTRACT，然后 allocated_resources，然后静态推断） ---
def _produces_of(verb: VerbCall) -> Set[Tuple[str, str]]:
    prods: Set[Tuple[str, str]] = set()
    # 1) CONTRACT.produces
    contract = verb.get_contract()
    if contract and hasattr(contract, "produces"):
        for spec in getattr(contract, "produces") or []:
            # spec 有 rtype / name_attr / state
            rtype = getattr(spec, "rtype", None)
            name_attr = getattr(spec, "name_attr", None)
            if rtype and name_attr:
                val = _get_dotted(verb, name_attr)
                name = _as_str_name(val)
                if name:
                    prods.add((str(rtype), str(name)))
    return prods


# ---------- 从 CONTRACT 提取 requires / transitions / produces ----------
def _contract_specs(
    verb: VerbCall,
) -> Tuple[Set[Tuple[str, str, Any, Any]], List[Tuple[str, str, Any, Any]], Set[Tuple[str, str, Any]]]:
    """
    返回：
      - reqs: Set[(rtype, name, state_or_None)]
      - transitions: List[(rtype, name, from_state_or_None, to_state)]
      - prods: Set[(rtype, name, state)]
    """

    from .contracts import _as_iter, _get_by_path

    reqs: Set[Tuple[str, str, Any]] = set()
    prods: Set[Tuple[str, str, Any]] = set()
    transitions: List[Tuple[str, str, Any, Any]] = []

    # contract = getattr(verb, "CONTRACT", None)
    contract = verb.get_contract()
    if not contract:
        return reqs, transitions, prods
    for spec in contract.requires:
        try:
            val = _get_by_path(verb, spec.name_attr, missing_ok=True)
        except Exception as e:
            raise ContractError(f"require: cannot resolve '{spec.name_attr}' on {type(verb).__name__}: {e}")
        for name in _as_iter(val):
            reqs.add((str(spec.rtype), str(name), spec.state))
            # reqs.add((str(spec.rtype), str(name), spec.state, spec.exclude_states))

    for spec in contract.transitions:
        try:
            val = _get_by_path(verb, spec.name_attr, missing_ok=True)
        except Exception as e:
            raise ContractError(f"transition: cannot resolve '{spec.name_attr}' on {type(verb).__name__}: {e}")
        for name in _as_iter(val):
            transitions.append((str(spec.rtype), str(name), spec.from_state, spec.to_state))

    for spec in contract.produces:
        try:
            val = _get_by_path(verb, spec.name_attr, missing_ok=True)
        except Exception as e:
            raise ContractError(f"produce: cannot resolve '{spec.name_attr}' on {type(verb).__name__}: {e}")
        for name in _as_iter(val):
            prods.add((str(spec.rtype), str(name), spec.state))

    return reqs, transitions, prods


def destroyed_targets_stateful(verb: Any) -> List[Tuple[str, str, Any]]:
    """
    从一个 verb 的 transitions 中，抽出所有 to=DESTROYED 的目标，作为“种子”：
      返回 [(rtype, name, State.ALLOCATED)]
    说明：
      - 作为 find_dependent_verbs_stateful 的 stateful 种子，它的传播逻辑是“凡是需要该资源存在/特定状态的后继都算依赖”
      - 如果你的 find_dependent... 把 DESTROYED 当作“存在性的负面”，上游可以把目标降格为 (rtype, name, None) 也可。
    """
    _, trans, _ = _contract_specs(verb)
    out = []
    for rt, nm, frm, to in trans:
        if to == State.DESTROYED:
            out.append((rt, nm, State.ALLOCATED))
    return out


def _trim_forward_on_lost_stateful(verbs: List[Any], start_idx: int, lost: List[Tuple[str, str, Any]]) -> None:
    """
    用状态感知依赖分析统一裁剪：
      - lost: [(rtype, name, state|None)] 作为种子
      - 对每个种子调用 find_dependent_verbs_stateful，取并集
      - 仅删除位于 start_idx 之后的依赖 verb
    """
    if not verbs or not lost:
        return
    victim_ids: Set[int] = set()
    for seed in lost:
        deps = find_dependent_verbs_stateful(verbs, seed)
        for i in deps:
            if i > start_idx:
                victim_ids.add(i)
    # 从后往前删
    for i in sorted(victim_ids, reverse=True):
        verbs.pop(i)


# ---------- 判断 require 是“存在性需求”还是“状态需求” ----------
def _is_existence_requirement(state) -> bool:
    """
    state 为 None 或 “ALLOCATED” 视作存在性需求；
    其余（INIT/RTR/RTS/...）为状态需求。
    """
    if state is None:
        return True
    return state == State.ALLOCATED


def _ES_in_of_requires(verb: Any):
    """把 requires 切分成 E_in(存在) 和 S_in(状态) 两类输入。"""
    reqs, _, _ = _contract_specs(verb)
    E_in: Set[Tuple[str, str]] = set()
    S_in: Set[Tuple[str, str, str]] = set()
    for rt, nm, st in reqs:
        if _is_existence_requirement(st):
            E_in.add((rt, nm))
        else:
            E_in.add((rt, nm))
            S_in.add((rt, nm, str(st)))
    return E_in, S_in


def _ES_out_of_verb(verb: Any):
    """
    verb 的输出：
      - E_out: 产生了哪些存在资源 {(rtype,name)}
      - S_out: 产生了哪些“已达成状态” {(rtype,name,state)}；来自 produces(state!=None) 或 transitions(to_state)
    """
    _, trans, prods = _contract_specs(verb)
    E_out: Set[Tuple[str, str]] = set()
    S_out: Set[Tuple[str, str, str]] = set()

    for rt, nm, st in prods:
        E_out.add((rt, nm))
        if st is not None:
            S_out.add((rt, nm, str(st)))

    for rt, nm, frm, to in trans:
        if to is not None:
            S_out.add((rt, nm, str(to)))
    return E_out, S_out


def _kills_resource(verb: Any) -> Set[Tuple[str, str]]:
    """
    返回该 verb 杀伤（使之后不可再用）的资源集合 {(rtype, name)}。
    规则：
      - 若 transitions 里有 to_state == DESTROYED，则该 (rtype,name) 被杀伤；
      - 也可按需扩展：DeallocPD/DeregMR/DestroyCQ/DestroyQP 若用 produces 显式表示“free”，
        也将其加入杀伤集（见注释）。
    """
    killed: Set[Tuple[str, str]] = set()
    reqs, transitions, prods = _contract_specs(verb)

    # A) 通过状态机：to_state == DESTROYED
    for rt, nm, frm, to in transitions:
        if to == State.DESTROYED:
            killed.add((rt, nm))

    # B) （可选）如果你在 Dealloc/Dereg/Destroy 类动词里，用 produces 标记了 State.DESTROYED，
    #    那么这里也把它当做“杀伤”
    for rt, nm, st in prods:
        if st is not None and st == State.DESTROYED:
            killed.add((rt, nm))

    return killed


def consumers_of_resource_any_state(verbs, key: tuple[str, str]) -> list[int]:
    """
    返回所有“引用了这同一资源 (rtype,name) 的 verb 下标”，不关心其 requires 的状态取值。
    用于 Destroy/Dealloc/Dereg 这类 Kill 动词的“最后消费者栅栏”。
    """
    rt0, nm0 = key
    idxs: list[int] = []
    for i, v in enumerate(verbs):
        reqs, _trans, _prods = _contract_specs(v)  # 你已有：把 CONTRACT 实例化为 (reqs, trans, prods)
        # reqs: List[(rtype, name, need_state)]
        for rt, nm, _need_state in reqs:
            if rt == rt0 and nm == nm0:
                idxs.append(i)
                break
    return idxs


def _last_consumer_before_any_state(verbs, key: tuple[str, str], limit_idx: int) -> int | None:
    """
    在 limit_idx 之前，找最后一个“存在性消费者”（不看状态）的下标。
    """
    idxs = [i for i in consumers_of_resource_any_state(verbs, key) if i < limit_idx]
    return max(idxs) if idxs else None


# ==== 单个 verb 的可移动窗口 ====


def find_dependent_verbs_stateful(verbs: List[Any], target: Tuple[str, str, Any]) -> List[int]:
    """
    目标带状态：(rtype, name, state)
    - 若 state 为 None 或 ALLOCATED：以“存在性”种子初始化；
    - 否则：以“状态”种子初始化。
    传播：
    - 命中依赖（根据 require 的类型选择 E 或 S）：将 produces 加入 E，并把（若附带状态）加入 S；
    - transitions 只更新 S（不会影响 E）。
    """

    if not verbs or not target or not target[0] or not target[1]:
        return []

    rtype0, name0, state0 = target[0], target[1], target[2] if len(target) > 2 else None

    # E: 存在性集合 {(rtype, name)}
    E: Set[Tuple[str, str]] = set()
    # S: 状态集合 {(rtype, name) -> set(states)}
    S: Dict[Tuple[str, str], Set[str]] = {}

    def S_add(rt: str, nm: str, st: Any):
        if st is None:
            return
        key = (rt, nm)
        if key not in S:
            S[key] = set()
        S[key].add(str(st))

    # 初始种子
    if _is_existence_requirement(state0):  # State.ALLOCATED
        E.add((str(rtype0), str(name0)))
        # 如果给了具体 RESET 之类的也可以同步到 S
        if state0 not in (None,):
            S_add(str(rtype0), str(name0), state0)
    else:
        # E.add((str(rtype0), str(name0)))
        S_add(str(rtype0), str(name0), state0)
    # 预解析 CONTRACT
    parsed = [_contract_specs(v) for v in verbs]
    # parsed2 = [verb_effect_targets(v) for v in verbs]
    # print(f"parsed contract: {parsed}")
    # print(f"parsed2 contract: {parsed2}")
    dependents: List[int] = []

    for i, (reqs, trans, prods) in enumerate(parsed):
        # 1) 判断是否命中依赖
        # excluded_states 不用管，因为当前序列只要合法，就一定不会触及
        hit = False
        for rt, nm, need_state in reqs:
            if _is_existence_requirement(need_state):
                # 只看 E
                if (rt, nm) in E:
                    hit = True
                    break
            else:
                # 只看 S
                key = (rt, nm)
                if key in S and str(need_state) in S[key]:
                    hit = True
                    break

        if hit:
            dependents.append(i)
            # 2) 命中后：把 produces 的资源加入 E；附带状态也加入 S
            for rt, nm, st in prods:
                E.add((rt, nm))
                if st is not None:
                    S_add(rt, nm, st)
            # 3) 命中后：根据 transitions 推进 S
            for rt, nm, frm, to in trans:
                key = (rt, nm)
                if (frm is None and key in E) or (key in S and str(frm) in S[key]):
                    S_add(rt, nm, to)
        else:
            # 未命中：仅允许 transitions 在“已存在”或“已知状态”上推进 S（不影响 E）
            for rt, nm, frm, to in trans:
                key = (rt, nm)
                if key in E or (key in S and (frm is None or str(frm) in S[key])):
                    S_add(rt, nm, to)
            # 未命中时，不把 produces 纳入 E（避免把与目标无关的创建当作依赖路径）

    return dependents


def compute_move_window(verbs: List[Any], idx: int) -> Tuple[int, int]:
    """
    返回 (lo, hi)：把 verbs[idx] 移动到 [lo, hi] 之间都不破坏基于 CONTRACT 的因果关系。
      - lo：所有输入（E_in / S_in）被满足的“最后一次提供点”之后
      - hi：第一个“依赖此 verb 的输出（E_out / S_out）”的消费者之前
    若无法定位提供点/消费者，则取极端（开头或末尾）。
    """
    n = len(verbs)
    if not (0 <= idx < n):
        return (0, n - 1)

    v = verbs[idx]
    E_in, S_in = _ES_in_of_requires(v)
    E_out, S_out = _ES_out_of_verb(v)

    # 1) 计算 lo：所有输入的“最后提供点” + 1
    lo = 0

    def last_provider_for_E(rt: str, nm: str, before: int) -> Optional[int]:
        # 找 < before 的最大 j，使得 verbs[j] 的 E_out 包含 (rt,nm)
        for j in range(before - 1, -1, -1):
            Ej, _ = _ES_out_of_verb(verbs[j])
            if (rt, nm) in Ej:
                return j
        return None

    def last_provider_for_S(rt: str, nm: str, st: str, before: int) -> Optional[int]:
        # 找 < before 的最大 j，使得 verbs[j] 的 S_out 包含 (rt,nm,st)
        for j in range(before - 1, -1, -1):
            _, Sj = _ES_out_of_verb(verbs[j])
            if (rt, nm, st) in Sj:
                return j
        return None

    for rt, nm in E_in:
        j = last_provider_for_E(rt, nm, idx)
        if j is not None:
            lo = max(lo, j + 1)
        else:
            # 没有提供者：不允许越过开头（保持在原地或之后）
            lo = max(lo, idx)  # 不能提前

    for rt, nm, st in S_in:
        j = last_provider_for_S(rt, nm, st, idx)
        if j is not None:
            lo = max(lo, j + 1)
        else:
            lo = max(lo, idx)  # 不能提前

    # 2) 计算 hi：第一个消费者位置 - 1
    hi = n - 1

    def first_consumer_after(i0: int, Eset: Set[Tuple[str, str]], Sset: Set[Tuple[str, str, str]]) -> Optional[int]:
        for k in range(i0 + 1, n):
            Ein_k, Sin_k = _ES_in_of_requires(verbs[k])
            if (Ein_k & Eset) or (Sin_k & Sset):
                return k
        return None

    # 注意：Modify 类通常只有 S_out；Create/Alloc 同时有 E_out 和 S_out
    if E_out or S_out:
        k = first_consumer_after(idx, E_out, S_out)
        if k is not None:
            hi = min(hi, k - 1)

    # === 新增：根据“杀伤点”进一步限制 hi ===
    # 思想：一旦后续某个 verb 把我们“依赖的资源”（E_in 或 S_in 中的 rtype,name）杀死，
    # 那么当前 verb 必须在这个“杀伤点”之前。
    need_keys: Set[Tuple[str, str]] = set()
    need_keys |= E_in  # {(rt,nm)}
    need_keys |= {(rt, nm) for (rt, nm, _) in S_in}

    for j in range(idx + 1, n):
        killed = _kills_resource(verbs[j])
        # logging.debug("killed at %d: %s", j, killed)
        if killed & need_keys:
            hi = min(hi, j - 1)
            break

    # 如果v本身就是“杀伤”类verb，那么不能移太前，因为有的verb可能会依赖于这个资源

    K = list(_kills_resource(v))
    if K:
        for key in K:
            # dependent_verb_indices = find_dependent_verbs_stateful(verbs, (rtype, name, State.ALLOCATED))[:-1]
            # lo = max(lo, max(dependent_verb_indices) + 1 if dependent_verb_indices else -1)
            # logging.debug(f"{rtype}, {name}, {dependent_verb_indices}")
            last_cons = _last_consumer_before_any_state(verbs, key, idx)
            if last_cons is not None:
                lo = max(lo, last_cons + 1)

    # 避免 (lo > hi) 的退化：把窗口收缩到原位置
    if lo > hi:
        lo = hi = idx
    return (lo, hi)


def _swap_in_place(lst, i, j):
    logging.debug(f"  Swapping positions {i} and {j}")
    lst[i], lst[j] = lst[j], lst[i]


def _dryrun_sequence(verbs: List[VerbCall], ctx=None) -> bool:
    if not ctx:
        ctx = FakeCtx()
    try:
        for v in verbs:
            v.apply(ctx)
    except Exception as e:
        logging.debug(f"Dry-run failed at verb {v}: {e}")
        logging.debug(traceback.format_exc())
        return False
    return True


# ========================= Mutator =========================


class ContractAwareMutator:
    def __init__(self, rng: random.Random | None = None, *, cfg: MutatorConfig | None = None):
        self.rng = rng or random.Random()
        self.cfg = cfg or MutatorConfig()

    def find_dependent_verbs(self, verbs: List[Any], target: Tuple[str, str]) -> List[int]:
        """
        找出所有依赖于 target 资源的 verb 索引（直接或间接依赖）。
        target: (rtype, name)
        规则：顺序扫描，若某 verb 的 requires 命中当前已知依赖资源集合 S，则该 verb 被标记为依赖；
            同时将该 verb 产生的资源（produces）加入 S，形成传递闭包。
        """
        if not verbs or not target or not target[0] or not target[1]:
            return []

        # 预计算每个 verb 的 requires / produces
        reqs_list: List[Set[Tuple[str, str]]] = []
        prods_list: List[Set[Tuple[str, str]]] = []
        for v in verbs:
            reqs_list.append(_requires_of(v))
            prods_list.append(_produces_of(v))

        # 传递式前向传播
        S: Set[Tuple[str, str]] = {(str(target[0]), str(target[1]))}
        deps: List[int] = []

        for i, (reqs, prods) in enumerate(zip(reqs_list, prods_list)):
            # 命中依赖集合即认为该 verb 依赖于 target
            if any((rt, rn) in S for (rt, rn) in reqs):
                deps.append(i)
                # 该 verb 新产出的资源也成为“依赖传递体”
                for p in prods:
                    S.add((str(p[0]), str(p[1])))

        return deps

    def enumerate_mutable_paths(self, verb: VerbCall) -> List[Tuple[List[str], Any]]:
        return _enumerate_mutable_paths(verb)

    def find_dependent_verbs_stateful(self, verbs: List[Any], target: Tuple[str, str, Any]) -> List[int]:
        return find_dependent_verbs_stateful(verbs, target)

    def mutate(
        self, verbs: List[VerbCall], idx: Optional[int] = None, idx2: Optional[int] = None, choice: str = None, rng=None
    ) -> bool:
        if not rng:
            rng = self.rng
        choices = ["insert", "delete", "param", "move", "swap"]
        prob_dist = [0.3, 0.1, 0.2, 0.2, 0.2]
        if not choice:
            # randomly pick one
            choice = rng.choices(choices, weights=prob_dist, k=1)[0]
            # choice = rng.choices(choices, weights=[1, 0, 0, 0, 0], k=1)[0]
        logging.debug("mutation choice:" + choice)
        if choice == "insert":
            return self.mutate_insert(verbs, idx)
        elif choice == "delete":
            return self.mutate_delete(verbs, idx)
        elif choice == "param":
            return self.mutate_param(verbs, idx)
        elif choice == "move":
            return self.mutate_move(verbs, idx)
        elif choice == "swap":
            return self.mutate_swap(verbs, idx, idx2)
        else:
            raise ValueError(f"Unknown mutation choice: {choice}")

    def mutate_delete(self, verbs: List[VerbCall], idx_: Optional[int] = None) -> bool:
        """
        基于 contract 的统一删除策略：
        1) 选中一个 victim；
        2) 取出 victim 的 produces 与 transitions，生成“依赖种子”：
        - 对 produces：加入 (rtype, name, None) 作为存在性种子；若带 state 也加入 (rtype, name, state)
        - 对 transitions：加入 (rtype, name, to_state) 作为状态种子
        3) 在 suffix = verbs[idx+1:] 上，用 find_dependent_verbs_stateful 逐个种子做依赖传播；
        把所有命中的下标偏移回全局并合并；
        4) 反向删除 {victim} ∪ dependents
        """
        if not verbs:
            return False

        # 1) 选择要删除的 verb
        idx = self.rng.randrange(len(verbs)) if idx_ is None else idx_
        victim = verbs[idx]

        # # （可选策略）不删 ModifyQP，避免把状态链打断到不可修复
        # try:
        #     from .verbs import ModifyQP

        #     if isinstance(victim, ModifyQP):
        #         return False
        # except Exception:
        #     pass

        # 2) 解析 victim 的 CONTRACT，提取 produces / transitions
        try:
            reqs, trans, prods = _contract_specs(victim)  # [(rt,nm,state)], [(rt,nm,from,to)], [(rt,nm,state)]
        except Exception:
            # 回退：如果拿不到 CONTRACT，就只删自己
            del verbs[idx]
            return True

        # 3) 生成依赖种子
        seeds = set()
        # produces -> 存在性 +（可选）状态
        for rt, nm, st in prods:
            seeds.add((rt, nm, None))  # 资源“存在性”
            if st is not None:
                seeds.add((rt, nm, st))  # 如果 produce 自带状态（如 RESET），也作为状态种子

        # transitions -> 目标状态
        for rt, nm, frm, to in trans:
            if to is not None:
                seeds.add((rt, nm, to))

        # 特例：如果 victim 什么都不产生、也不迁移（少见），就直接删自己
        if not seeds:
            del verbs[idx]
            return True

        # 4) 在 suffix 上做状态化依赖传播
        suffix = verbs[idx + 1 :]
        all_dep_global_idx = set()
        for seed in seeds:
            try:
                dep_local = find_dependent_verbs_stateful(suffix, seed)  # 返回 suffix 内的局部下标
            except Exception:
                dep_local = []
            for j in dep_local:
                all_dep_global_idx.add(idx + 1 + j)

        # 5) 反向删除：先删 dependents，再删 victim
        #    注意：同一个 verb 可能被多个种子命中，集合去重后统一删除
        delete_idx = sorted(all_dep_global_idx | {idx}, reverse=True)
        for k in delete_idx:
            if 0 <= k < len(verbs):
                verbs.pop(k)

        return True

    def mutate_insert(self, verbs: List[VerbCall], idx: Optional[int] = None, choice: str = None) -> bool:
        """
        先生成候选 ins_list，再在候选位置中寻找可行点插入：
        1) 位置列表：若 idx 指定则只用该点，否则扫描 [0..len].
        2) 为每个位置 i：
            - 用“全局 live”先尝试生成；若 None 再用“pos live”补试一次
            - 用 _check_feasible_position(verbs, ins_list, i, try_trim_on_destroy=True) 做干运行判定
        3) 用 _choose_insert_pos(feasible, rng, place="best") 从可行集中选一个 (pos, ins_list)
        4) 插入 + destroy 前向切片清理 + 最终一次干运行校验
        """
        if not verbs:
            return False

        rng = self.rng
        candidate_indices = [idx] if idx is not None else list(range(len(verbs) + 1))
        feasible: List[Tuple[int, List[VerbCall]]] = []

        # 可选：安静/详细输出
        verbose = getattr(getattr(self, "cfg", None), "verbose", False)
        # verbose = True

        # 1) 收集可行位置
        global_snapshot = _make_snapshot(verbs, len(verbs))
        for i in candidate_indices:  # 这个居然有随机性？
            # logging.debug(f"Trying to insert at index {i}")

            # 1.1 选模板
            builder = _pick_insertion_template(
                rng, verbs, i, choice, global_snapshot
            )  # 传入verbs的原因是，有些builder需要根据后面的verbs才能确定（对，我说的就是ModifyQP）
            build_fn = builder if callable(builder) else builder[0]

            # 1.2 先用“全局 live”生成；失败再用“当前位置 live”补试一次
            ins_list: Optional[List[VerbCall]] = None
            cand = build_fn(None, rng, _make_snapshot(verbs, i))

            if cand is None:
                # logging.debug("  -> no candidate generated at this position")
                continue

            ins_list = cand if isinstance(cand, list) else [cand]
            # for nv in ins_list:
            #     logging.debug("  + new:" + summarize_verb(nv, deep=True))

            # 1.3 在该位置做可行性干运行检查（允许 destroy 清理后判定）
            # TODO: 我觉得这一步应该不需要才对？
            # if not _check_feasible_position(verbs, ins_list, i, try_trim_on_destroy=True):
            #     # logging.debug("  -> not feasible at this position")
            #     continue

            feasible.append((i, ins_list))
        # logging.debug(f"Feasible insertion points: {feasible}")

        # 2) 从可行集合中选一个位置（偏向靠后）
        choice_pair = _choose_insert_pos(feasible, rng, place="best")
        if not choice_pair:
            if verbose:
                print("No feasible insertion point found.")
            return False

        pos, ins_list = choice_pair
        logging.debug(f"Inserting at position {pos}:")
        for nv in ins_list:
            logging.debug("  + new:" + summarize_verb(nv, deep=True))

        # 3) 真插入 + destroy 前向切片清理
        verbs[pos:pos] = ins_list
        seeds = []
        for v in ins_list:
            seeds.extend(destroyed_targets_stateful(v))  # [(rtype, name, State.ALLOCATED)]
        suffix = verbs[pos + len(ins_list) :]
        all_dep_global_idx = set()
        for seed in seeds:
            try:
                dep_local = find_dependent_verbs_stateful(suffix, seed)  # 返回 suffix 内的局部下标
            except Exception:
                dep_local = []
            for j in dep_local:
                all_dep_global_idx.add(pos + len(ins_list) + j)

        delete_idx = sorted(all_dep_global_idx, reverse=True)
        for k in delete_idx:
            if 0 <= k < len(verbs):
                verbs.pop(k)
        # lost = _lost_from_ins(ins_list)
        # # print("lost from ins:", lost)
        # if lost:  # TODO: 同样，这个也需要统一一下结构
        #     _trim_forward_on_lost(verbs, pos + len(ins_list), lost)

        # 4) 最终一次干运行校验
        dryrun_flag = _dryrun_sequence(verbs)
        if dryrun_flag:
            return True
        else:
            del verbs[pos : pos + len(ins_list)]
            return False

    def mutate_param(self, verbs: List[VerbCall], idx: Optional[int] = None) -> bool:
        if not verbs:
            return False
        rng = self.rng
        if idx:
            # i = idx if 0 <= idx < len(verbs) else len(verbs) - 1
            v = verbs[idx]
        else:
            # 1) 随机选 verb
            idx = rng.randrange(len(verbs))
            v = verbs[idx]

        # 2) 枚举可变路径
        snap = _make_snapshot(verbs, idx)
        contract = v.get_contract()
        paths = _enumerate_mutable_paths(v)
        if not paths:
            return False
        path, leaf = rng.choice(paths)
        # path, leaf = paths[3]  # for debugging only
        logging.debug(f"mutate param: verb idx={idx}, path={path}, leaf={leaf}")
        logging.debug(f"type of leaf:{type(leaf)}")
        leaf.mutate(snap=snap, contract=contract, rng=rng, path=path)
        # 已经禁止对“创建”的资源进行变异，但是可以对“销毁”的资源进行变异
        # 对ResourceValue的变异基本上已经考虑到了前向依赖
        # 不允许变异ModifyQP的state参数，否则会导致比较难以修复的问题
        seeds = destroyed_targets_stateful(v)  # [(rtype, name, State.ALLOCATED)]
        suffix = verbs[idx + 1 :]
        all_dep_global_idx = set()
        for seed in seeds:
            try:
                dep_local = find_dependent_verbs_stateful(suffix, seed)  # 返回 suffix 内的局部下标
            except Exception:
                dep_local = []
            for j in dep_local:
                all_dep_global_idx.add(idx + 1 + j)

        delete_idx = sorted(all_dep_global_idx, reverse=True)
        for k in delete_idx:
            if 0 <= k < len(verbs):
                verbs.pop(k)

    def mutate_move(self, verbs: List[Any], idx: Optional[int] = None, new_pos: Optional[int] = None) -> bool:
        """
        移动单个 verb：
        - 若 new_pos 未指定，则在可行窗口内随机选择一个位置（不等于原 idx）
        - 移动后可选做一次 dry-run（apply/contract），失败则回滚
        """
        if not verbs:
            return False
        if idx is None:
            idx = self.rng.randrange(0, len(verbs))

        lo, hi = compute_move_window(verbs, idx)  # 计算可以移到哪里
        # 没有可移动空间
        logging.debug(f"Move window for idx {idx}: [{lo}, {hi}]")
        if lo == hi == idx:
            return False

        if new_pos is None:
            # 在 [lo,hi] 里采样一个 != idx 的位置
            choices = [p for p in range(lo, hi + 1) if p != idx]
            if not choices:
                return False
            new_pos = self.rng.choice(choices)
        else:
            new_pos = max(lo, min(hi, new_pos))  # clamp 到窗口

        # 执行“抽出-插入”
        v = verbs.pop(idx)
        # 注意：pop 后索引变化，重新计算目标插入位
        if new_pos > idx:
            new_pos -= 1
        verbs.insert(new_pos, v)
        logging.debug(f"Moved verb from {idx} to {new_pos}")

        # 可选：一次轻量校验（不强制回滚，也可以回滚）
        # if getattr(self, "dryrun_contract", False):
        dryrun_flag = _dryrun_sequence(verbs)
        if dryrun_flag:
            return True
        else:
            verbs.pop(new_pos)
            verbs.insert(idx, v)
            return False

    def mutate_swap(
        self,
        verbs: List[VerbCall],
        i: Optional[int] = None,
        j: Optional[int] = None,
        *,
        do_precheck: bool = True,
        dryrun: bool = True,
    ) -> bool:
        """
        原子交换两个 verb：
          - 若未指定 i, j，则随机选两个不同索引
          - 先做必要性预检：j in window(i) 且 i in window(j)
          - 原子交换，整串 dry-run 验证；失败则回滚
        """
        n = len(verbs)
        if n < 2:
            return False

        # rng = getattr(self, "rng", random)
        rng = self.rng
        if i is None or j is None:
            i, j = rng.randrange(0, n), rng.randrange(0, n)
            while j == i:
                j = rng.randrange(0, n)

        if i == j:
            return False
        if i > j:
            i, j = j, i

        # 预检（必要不充分）：确保彼此在各自窗口内
        if do_precheck:
            lo_i, hi_i = compute_move_window(verbs, i)
            lo_j, hi_j = compute_move_window(verbs, j)
            logging.debug(f"swap precheck: i={i} with [{lo_i},{hi_i}], j={j} with [{lo_j},{hi_j}]")
            # i 移到 j 的位置，j 移到 i 的位置
            if not (lo_i <= j + 1 <= hi_i and lo_j <= i - 1 <= hi_j):
                return False

        # 原子交换
        _swap_in_place(verbs, i, j)

        if dryrun:
            dryrun_flag = _dryrun_sequence(verbs)
            if dryrun_flag:
                return True
            else:
                # 回滚
                _swap_in_place(verbs, i, j)  # very unlucky
                return False
        else:
            return True
