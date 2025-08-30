# lib/fuzz_mutate.py (refactored)
from __future__ import annotations

import random
import re
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import logging

from termcolor import colored

from lib.debug_dump import diff_verb_snapshots, dump_verbs, snapshot_verbs, summarize_verb, summarize_verb_list

from .verbs import VerbCall

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


# ---- 临时 dry-run：按顺序 apply 一串 verbs 到 ctx，失败抛 ContractError ----
def _apply_slice(ctx, seq):
    for v in seq:
        v.apply(ctx)


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


# ---- 计算 Destroy 造成的前向影响（你已有实现就复用）----
def _lost_from_ins(ins_list):
    lost = set()
    for nv in ins_list:
        if is_destroy_verb(nv):
            lost |= destroyed_targets(nv)
    return lost


def _trim_forward_on_lost(verbs, start_idx, lost):
    if not lost:
        return
    impact = compute_forward_impact(verbs, start_idx, lost)
    for k in sorted(impact, reverse=True):
        verbs.pop(k)


# # ---- 全局搜索可行插入位置 ----
# def _find_feasible_positions(verbs, ins_list, *, try_trim_on_destroy=True) -> list[int]:
#     """
#     返回所有可行插入位置 pos，使得：
#       apply(verbs[:pos]); apply(ins_list); apply(verbs[pos:]) 可成功
#     若 ins_list 包含 destroy，且 try_trim_on_destroy=True，则允许先对 suffix 做“前向切片清理”再验证。
#     """
#     feasible = []
#     n = len(verbs)
#     for pos in range(n + 1):
#         # 前缀
#         ctx = FakeCtx()
#         try:
#             _apply_slice(ctx, verbs[:pos])
#         except Exception:
#             continue

#         # 待插入段
#         ctx_mid = FakeCtx()
#         # 为了简化（tracker/contract 状态延续），这里直接用同一个 ctx 连续 apply 即可
#         ctx_mid = ctx
#         try:
#             _apply_slice(ctx_mid, ins_list)
#         except Exception:
#             continue

#         # 后缀：先直接尝试整条；如果失败且 destroy 可清理，则做一次清理再试
#         suffix = verbs[pos:]
#         ctx_tail = FakeCtx()
#         ctx_tail = ctx_mid
#         try:
#             _apply_slice(ctx_tail, suffix)
#             feasible.append(pos)
#             continue
#         except Exception:
#             # 后缀直接失败，尝试 destroy 清理路径
#             if not try_trim_on_destroy:
#                 continue
#             lost = _lost_from_ins(ins_list)
#             if not lost:
#                 continue
#             # 构造一个“临时序列”，对 suffix 做剪枝再验证
#             tmp = verbs[:pos] + list(ins_list) + verbs[pos:]
#             _trim_forward_on_lost(tmp, pos + len(ins_list), lost)
#             ctx_full = FakeCtx()
#             try:
#                 _apply_slice(ctx_full, tmp)
#                 feasible.append(pos)
#             except Exception:
#                 continue

#     return feasible


def _check_feasible_position(verbs, ins_list, idx, *, try_trim_on_destroy=True):
    n = len(verbs)
    pos = idx
    # print("pos:", pos)
    # 前缀
    ctx = FakeCtx()
    try:
        _apply_slice(ctx, verbs[:pos])
    except Exception as e:
        # print(e)
        return False

    # 待插入段
    ctx_mid = FakeCtx()
    # 为了简化（tracker/contract 状态延续），这里直接用同一个 ctx 连续 apply 即可
    ctx_mid = ctx
    try:
        _apply_slice(ctx_mid, ins_list)
    except Exception as e:
        # print(e)
        return False

    # 后缀：先直接尝试整条；如果失败且 destroy 可清理，则做一次清理再试
    suffix = verbs[pos:]
    ctx_tail = FakeCtx()
    ctx_tail = ctx_mid
    try:
        _apply_slice(ctx_tail, suffix)
        return True
    except Exception as e:
        # print(e)
        # 后缀直接失败，尝试 destroy 清理路径
        if not try_trim_on_destroy:
            return False
        lost = _lost_from_ins(ins_list)
        if not lost:
            return False
        # 构造一个“临时序列”，对 suffix 做剪枝再验证
        tmp = verbs[:pos] + list(ins_list) + verbs[pos:]
        _trim_forward_on_lost(tmp, pos + len(ins_list), lost)
        ctx_full = FakeCtx()
        try:
            _apply_slice(ctx_full, tmp)
            return True
        except Exception:
            return False


# ---- 位置选择策略：best / append / prepend / random ----
# def _choose_insert_pos(rng, feasible: list[int], *, place: str = "best") -> int | None:
#     if not feasible:
#         return None
#     place = (place or "best").lower()
#     if place == "append":
#         return max(feasible)
#     if place == "prepend":
#         return min(feasible)
#     if place == "random":
#         return rng.choice(feasible)
#     # "best": 偏向靠后，若有多个并列也可随机挑一个靠后的
#     m = max(feasible)
#     # 也可加一点小抖动：在 top-K 里随机
#     topk = [p for p in feasible if p >= m - 2]  # 允许在最后 3 个点内随机
#     return rng.choice(topk) if topk else m


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


def _qp_state_before(verbs, i: int, qp_name: str) -> str:
    ctx = FakeCtx()
    for j in range(0, i):
        verbs[j].apply(ctx)
    snap = ctx.contracts.snapshot() if hasattr(ctx, "contracts") else {}
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


def _resolve_name_for_spec(root, current, name_attr: str):
    if not name_attr:
        return None
    val = _get_dotted(root, name_attr) if "." in name_attr else getattr(current, name_attr, None)
    if val is None or _is_optional_none(val):
        return None
    val = _unwrap_value(val)
    return None if val is None else str(val)


def _iter_children_fields(obj):
    fields = (getattr(obj.__class__, "MUTABLE_FIELDS", []) or []) + [
        f
        for f in (getattr(obj.__class__, "FIELD_LIST", []) or [])
        if f not in getattr(obj.__class__, "MUTABLE_FIELDS", [])
    ]
    seen = set()
    for name in fields:
        if name in seen:
            continue
        seen.add(name)
        try:
            v = getattr(obj, name)
        except Exception:
            continue
        if hasattr(v, "inner"):
            v = getattr(v, "inner")
        if v is None or isinstance(v, (str, int, float, bool)):
            continue
        if isinstance(v, (list, tuple)):
            for it in v:
                if it is None or isinstance(it, (str, int, float, bool)):
                    continue
                yield it
        else:
            yield v


def _extract_edges_recursive(root, obj, visited: set):
    """返回 (requires, produces, destroys)，元素为 (rtype,name)。"""
    oid = id(obj)
    if oid in visited:
        return [], [], []
    visited.add(oid)

    req, pro, des = [], [], []
    # contract = getattr(obj.__class__, "CONTRACT", None)
    contract = obj.get_contract()
    if contract:
        for rq in getattr(contract, "requires", []) or []:
            rtype = str(getattr(rq, "rtype", "") or "")
            name_attr = getattr(rq, "name_attr", "") or ""
            name = _resolve_name_for_spec(root, obj, name_attr)
            # print("resolved:", rtype, name_attr, "->", name)
            if rtype and name:
                req.append((rtype, name))
        for pr in getattr(contract, "produces", []) or []:
            rtype = str(getattr(pr, "rtype", "") or "")
            name_attr = getattr(pr, "name_attr", "") or ""
            name = _resolve_name_for_spec(root, obj, name_attr)
            if rtype and name:
                pro.append((rtype, name))
        for tr in getattr(contract, "transitions", []) or []:
            # if str(getattr(tr, "to_state", None)).upper() == "DESTROYED":
            if getattr(tr, "to_state", None) == State.DESTROYED:
                rtype = str(getattr(tr, "rtype", "") or "")
                name_attr = getattr(tr, "name_attr", "") or ""
                name = _resolve_name_for_spec(root, obj, name_attr)
                if rtype and name:
                    des.append((rtype, name))

    for child in _iter_children_fields(obj):  # TODO: 感觉很奇怪，但是不影响功能
        r, p, d = _extract_edges_recursive(root, child, visited)
        req.extend(r)
        pro.extend(p)
        des.extend(d)
    return req, pro, des


def verb_edges_recursive(verb):
    return _extract_edges_recursive(verb, verb, set())


def compute_forward_impact(verbs, start_idx: int, lost_resources: set):
    """级联删除：从 start_idx 起，凡 requires 命中 lost 的 verb 均删除，并把其 produces 继续加入 lost。"""
    to_drop, frontier = set(), set(lost_resources)
    for i in range(start_idx, len(verbs)):
        req, pro, _ = verb_edges_recursive(verbs[i])
        # print(summarize_verb(verbs[i], deep=True))
        # print("f:", frontier, "r:", req)
        if any((r, n) in frontier for (r, n) in req):
            to_drop.add(i)
            for item in pro:
                frontier.add(item)
    return to_drop


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


def _mk_min_mw_bind(live, rng):
    """
    返回 (mw_bind_obj, mr_name)。若现场没有 MR，则生成一个占位名并交给 requires-filler 去补链。
    """
    from lib.ibv_all import IbvMwBind, IbvMwBindInfo

    # 选一个现场 MR；没有就造一个占位名（让 requires-filler 去补 Register）
    mr_live = [n for (t, n) in live if t == "mr"]
    mr_name = rng.choice(mr_live) if mr_live else f"mr_{rng.randrange(1 << 16)}"
    bind_info = IbvMwBindInfo(mr=mr_name, addr=0x0, length=0x1000, mw_access_flags=0)  # 最小配置
    return IbvMwBind(bind_info=bind_info), mr_name


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


# ========================= Live / factories / requires-filler =========================
def _live_before(verbs: List[VerbCall], i: int) -> set[tuple[str, str]]:
    live = set()
    ctx = FakeCtx()
    for j in range(0, i):
        try:
            verbs[j].apply(ctx)
        except ContractError:
            break
    snap = ctx.contracts.snapshot() if hasattr(ctx, "contracts") else {}
    for (rtype, name), st in snap.items():
        if st != "DESTROYED":
            live.add((rtype, name))
    return live


def _default_factories():
    from lib.ibv_all import IbvAllocDmAttr, IbvQPCap, IbvQPInitAttr

    from .verbs import AllocDM, AllocPD, CreateCQ, CreateQP, RegMR

    def mk_pd(ctx, name):
        return AllocPD(pd=name)

    def mk_cq(ctx, name):
        return CreateCQ(cq=name, cqe=16, comp_vector=0, channel="NULL")

    def mk_qp(ctx, name):
        init = IbvQPInitAttr(
            qp_type="IBV_QPT_RC",
            send_cq="cq0",
            recv_cq="cq0",
            cap=IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1),
        )
        return CreateQP(pd="pd0", qp=name, init_attr_obj=init)

    def mk_mr(ctx, name):
        return RegMR(pd="pd0", mr=name, addr="buf0", length=4096, access="IBV_ACCESS_LOCAL_WRITE")

    def mk_dm(ctx, name):
        return AllocDM(dm=name, attr_obj=IbvAllocDmAttr(length=0x2000, log_align_req=64))

    return {"pd": mk_pd, "cq": mk_cq, "qp": mk_qp, "mr": mk_mr, "dm": mk_dm}


def _ensure_requires_before(verbs: List[VerbCall], i: int, v_new: VerbCall, *, factories=None, max_chain=8) -> bool:
    if factories is None:
        factories = _default_factories()
    reqs, _pros, _des = verb_edges_recursive(v_new)
    if not reqs:
        return True
    for _ in range(max_chain):
        live = _live_before(verbs, i)
        missing = [(r, n) for (r, n) in reqs if (r, n) not in live]
        if not missing:
            return True
        rtype, name = missing[0]
        f = factories.get(rtype)
        if not f:
            return False
        pre = f(None, name)
        chain = pre if isinstance(pre, list) else [pre]
        verbs[i:i] = chain
    return False


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


def build_modify_qp_out(verbs, i: int, qp_name: str, rng):
    if rng.random() < 0.5:
        res = build_modify_qp_safe_chain(verbs, i, qp_name, rng)
        if res:
            return res
        else:
            return build_modify_qp_stateless(verbs, i, qp_name, rng)
    else:
        return build_modify_qp_stateless(verbs, i, qp_name, rng)


def build_modify_qp_safe_chain(verbs, i: int, qp_name: str, rng) -> List[VerbCall]:
    from lib.ibv_all import IbvQPAttr

    from .verbs import ModifyQP

    cur = _qp_state_before(verbs, i, qp_name)
    succ = _first_successor_target_after(verbs, i, qp_name)

    def _rand_target_from(s):
        idx = _QP_ORDER.index(s) if s in _QP_ORDER else 0
        end = min(idx + 2, len(_QP_ORDER) - 1)
        return _QP_ORDER[random.randint(idx + 1, end)]

    target = succ if succ is not None and _state_leq(cur, succ) else _rand_target_from(cur)
    path = _qp_path(cur, target)
    if not path:
        return []
    L = rng.randrange(1, len(path) + 1)
    prefix = path[:L]
    return [
        ModifyQP(qp=qp_name, attr_obj=IbvQPAttr(qp_state=f"IBV_QPS_{st}"), attr_mask="IBV_QP_STATE") for st in prefix
    ]


def build_modify_qp_stateless(verbs, i: int, qp_name: str, rng) -> Optional[VerbCall]:
    from lib.ibv_all import IbvQPAttr

    from .verbs import ModifyQP

    cur = _qp_state_before(verbs, i, qp_name)
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
def _build_destroy_of_type(rng, verbs, i, rtype: str):
    """
    从 live 集合里挑选一个 rtype 资源，构造相应 Destroy verb。
    若该类型在现场没有实例，返回 None。
    """
    live = _live_before(verbs, i)
    cand = [n for (t, n) in live if t == rtype]
    if not cand:
        return None

    name = rng.choice(cand)

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


def build_destroy_generic(ctx, rng, live, verbs, i):
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
        v = _build_destroy_of_type(rng, verbs, i, rt)
        if v is not None:
            return v
    return None


# ========================= Insertion templates =========================
def _pick_insertion_template(rng: random.Random, verbs: List[VerbCall], i: int, choice: str = None):
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

    def live_set():
        return _live_before(verbs, i)

    def pick_rnames(kind):
        xs = [n for (t, n) in live_set() if t == kind]
        return xs

    def pick(kind):
        xs = [n for (t, n) in live_set() if t == kind]
        return rng.choice(xs) if xs else None

    # def pick(kind):
    #     # return pick_rnames(kind) or [f"{kind}_{rng.randrange(1 << 16)}"]
    #     return pick_rnames(kind)

    def pick_qp_name():
        qps = [n for (t, n) in live_set() if t == "qp"]
        return rng.choice(qps) if qps else None

    def pick_cq_name():
        cqs = [n for (t, n) in live_set() if t == "cq"]
        return rng.choice(cqs) if cqs else None

    def pick_pd_name():
        pds = [n for (t, n) in live_set() if t == "pd"]
        return rng.choice(pds) if pds else None

    def pick_mw_name():
        mws = [n for (t, n) in live_set() if t == "mw"]
        return rng.choice(mws) if mws else None

    def gen_new_name(kind, snap):
        existing = {n for (t, n) in snap.keys() if t == kind}
        for _ in range(100):
            name = f"{kind}_{rng.randrange(1 << 16)}"
            if name not in existing:
                return name
        return None

    # 1) ModifyQP：复用你已有的有/无状态策略
    def build_modify_qp(ctx, rng, live, snap):
        qp = pick_qp_name()
        if not qp:
            return None
        return build_modify_qp_out(verbs, i, qp, rng)  # 你现有的包装

    # 2) PostSend：最小 WR（1 SGE）
    def build_post_send(ctx, rng, live, snap):
        qp = pick_qp_name()
        if not qp:
            return None
        wr = _mk_min_send_wr()
        return PostSend(qp=qp, wr_obj=wr)

    # 3) PollCQ
    def build_poll_cq(ctx, rng, live, snap):
        cq = pick_cq_name()
        # return None if not cq else PollCQ(cq=cq, num_entries=1)
        return None if not cq else PollCQ(cq=cq)

    # 4) RegMR（绑定已有 PD）
    def build_reg_mr(ctx, rng, live, snap):
        pd = pick_pd_name()
        if not pd:
            return None
        # mr_name = f"mr_{rng.randrange(1 << 16)}"
        mr_name = gen_new_name("mr", snap)
        return RegMR(pd=pd, mr=mr_name, addr="buf0", length=4096, access="IBV_ACCESS_LOCAL_WRITE")

    # 5) CreateCQ（纯创建）
    def build_create_cq(ctx, rng, live, snap):
        # cq_name = f"cq_{rng.randrange(1 << 16)}"
        cq_name = gen_new_name("cq", snap)
        return CreateCQ(cq=cq_name, cqe=16, comp_vector=0, channel="NULL")

    # 6) **PostRecv**（最小 WR：1 SGE）
    def build_post_recv(ctx, rng, live, snap):
        qp = pick_qp_name()
        if not qp:
            return None
        wr = _mk_min_recv_wr()
        return PostRecv(qp=qp, wr_obj=wr)

    # 7) **BindMW**（绑定已有 MR，产出 MW）
    def build_bind_mw(ctx, rng, live, snap):
        qp = pick_qp_name()
        if not qp:
            return None
        mw = pick_mw_name()
        if not mw:
            return None
        # mw_name = f"mw_{rng.randrange(1 << 16)}"
        mw_name = mw
        mw_bind_obj, mr_name = _mk_min_mw_bind(live_set(), rng)
        # BindMW 的 CONTRACT: 需要 qp 和 mw_bind_obj.bind_info.mr；产出 mw
        # （没有 MR 时，_ensure_requires_before 会补建 RegMR）
        return BindMW(qp=qp, mw=mw_name, mw_bind_obj=mw_bind_obj)

    # 8) **AttachMcast**（最小 gid/lid）
    def build_attach_mcast(ctx, rng, live, snap):
        qp = pick_qp_name()
        if not qp:
            return None
        # 用最小 GID 变量名（假设你的 ctx 里会有 gid 变量，或者后续你可以在 factories 里补一个定义 GID 的 helper）
        gid_var = "gid0"
        return AttachMcast(qp=qp, gid=gid_var, lid=0)

    # 9) （可选）**RegDmaBufMR**（需要 pd）
    def build_reg_dmabuf_mr(ctx, rng, live, snap):
        pd = pick_pd_name()
        if not pd:
            return None
        # mr_name = f"mr_{rng.randrange(1 << 16)}"
        mr_name = gen_new_name("mr", snap)
        # 随便给一个小范围
        return RegDmaBufMR(pd=pd, mr=mr_name, offset=0, length=0x2000, iova=0, fd=3, access="IBV_ACCESS_LOCAL_WRITE")

    # 新增：销毁类模板（支持点名 destroy_XXX，也支持 generic）
    def build_destroy(ctx, rng, live, snap):
        return build_destroy_generic(ctx, rng, live, verbs, i)

    def build_destroy_qp(ctx, rng, live, snap):
        return _build_destroy_of_type(rng, verbs, i, "qp")

    def build_destroy_cq(ctx, rng, live, snap):
        return _build_destroy_of_type(rng, verbs, i, "cq")

    def build_dealloc_pd(ctx, rng, live, snap):
        return _build_destroy_of_type(rng, verbs, i, "pd")

    def build_dereg_mr(ctx, rng, live, snap):
        return _build_destroy_of_type(rng, verbs, i, "mr")

    def build_dealloc_mw(ctx, rng, live, snap):
        return _build_destroy_of_type(rng, verbs, i, "mw")

    # ---------- SRQ ----------
    def build_create_srq(ctx, rng, live, snap):
        pds = pick_rnames("pd")
        if not pds:
            return None
        pd = rng.choice(pds)
        # srq_name = f"srq_{rng.randrange(1 << 16)}"
        srq_name = gen_new_name("srq", snap)
        return CreateSRQ(pd=pd, srq=srq_name, srq_init_obj=_mk_min_srq_init())

    def build_post_srq_recv(ctx, rng, live, snap):
        srqs = pick_rnames("srq")
        if not srqs:
            return None
        from lib.ibv_all import IbvRecvWR

        return PostSRQRecv(srq=rng.choice(srqs), wr_obj=_mk_min_recv_wr())

    def build_modify_srq(ctx, rng, live, snap):
        srqs = pick_rnames("srq")
        if not srqs:
            return None
        # 你的 ModifySRQ 支持 IbvSrqAttr + mask（verbs 里定义了 attr_mask: IBV_SRQ_ATTR_*）
        from lib.ibv_all import IbvSrqAttr

        return ModifySRQ(
            srq=rng.choice(srqs), attr_obj=IbvSrqAttr(max_wr=1, srq_limit=0), attr_mask="IBV_SRQ_MAX_WR | IBV_SRQ_LIMIT"
        )

    # ---------- WQ ----------
    def build_create_wq(ctx, rng, live, snap):
        pds = pick_rnames("pd")
        cqs = pick_rnames("cq")
        if not (pds and cqs):
            return None
        pd, cq = rng.choice(pds), rng.choice(cqs)
        # wq_name = f"wq_{rng.randrange(1 << 16)}"
        wq_name = gen_new_name("wq", snap)
        return CreateWQ(ctx_name="ctx", wq=wq_name, wq_attr_obj=_mk_min_wq_init(pd, cq))

    # ---------- AH ----------
    def build_create_ah(ctx, rng, live, snap):
        pds = pick_rnames("pd")
        if not pds:
            return None
        ah_name = gen_new_name("ah", snap)
        return CreateAH(pd=rng.choice(pds), ah=ah_name, attr_obj=_mk_min_ah_attr())

    # ---------- Flow ----------
    def build_create_flow(ctx, rng, live, snap):
        qps = pick_rnames("qp")
        if not qps:
            return None
        flow_name = gen_new_name("flow", snap)
        return CreateFlow(qp=rng.choice(qps), flow=flow_name, flow_attr_obj=_mk_min_flow_attr())

    # ---------- CQ notify ----------
    def build_req_notify_cq(ctx, rng, live, snap):
        cqs = pick_rnames("cq")
        if not cqs:
            return None
        return ReqNotifyCQ(cq=rng.choice(cqs), solicited_only=rng.choice([0, 1]))

    # ---------- 查询类 ----------
    def build_query_qp(ctx, rng, live, snap):
        qps = pick_rnames("qp")
        if not qps:
            return None
        return QueryQP(qp=rng.choice(qps), attr_mask="IBV_QP_STATE | IBV_QP_PORT | IBV_QP_PKEY_INDEX")

    def build_query_srq(ctx, rng, live, snap):
        srqs = pick_rnames("srq")
        if not srqs:
            return None
        return QuerySRQ(srq=rng.choice(srqs))

    # --- AllocPD: 直接产一个 PD ---
    def build_alloc_pd(ctx, rng, live, snap):
        # pd_name = f"pd_{rng.randrange(1 << 16)}"
        pd_name = gen_new_name("pd", snap)
        return AllocPD(pd=pd_name)

    # --- CreateQP: 需要 pd/cq，init_attr_obj 引用已有 cq（缺就补链）---
    def build_create_qp(ctx, rng, live, snap):
        pd = pick("pd") or "pd0"
        send_cq = pick("cq") or "cq0"
        recv_cq = pick("cq") or send_cq
        init = _mk_min_qp_init(send_cq, recv_cq)
        qp_name = gen_new_name("qp", snap)
        return CreateQP(pd=pd, qp=qp_name, init_attr_obj=init)

    # --- ModifyCQ: 改调度/容量等（按你的 IbvCQAttr 定义）---
    def build_modify_cq(ctx, rng, live, snap):
        cq = pick("cq")
        if not cq:
            return None
        # return ModifyCQ(cq=cq, attr_obj=_mk_min_cq_attr(), attr_mask="IBV_CQ_MODERATION")
        return ModifyCQ(cq=cq, attr_obj=_mk_min_cq_attr())

    # --- AllocMW: 需要 pd，产出 mw ---
    def build_alloc_mw(ctx, rng, live, snap):
        pd = pick("pd")
        if not pd:
            return None
        return _mk_min_alloc_mw(pd, mw_name=gen_new_name("mw", snap))

    # --- AllocDM / FreeDM: 产出/释放 dm ---
    def build_alloc_dm(ctx, rng, live, snap):
        return _mk_min_alloc_dm(dm_name=gen_new_name("dm", snap))

    def build_free_dm(ctx, rng, live, snap):
        dms = [n for (t, n) in live_set() if t == "dm"]
        if not dms:
            return None
        return FreeDM(dm=rng.choice(dms))

    # --- ReRegMR: 需要已存在 mr & pd（flags 简化一版）---
    def build_rereg_mr(ctx, rng, live, snap):
        mr = pick("mr")
        pd = pick("pd")
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
def _enumerate_mutable_objects(obj):
    """
    返回 [leaf_obj]，即所有可变叶子对象（Attr/Verb/Value等）
    规则：
      - 优先使用 Attr/Verb 的 MUTABLE_FIELDS / MUTABLE_FIELD_LIST
      - OptionalValue/ListValue/ResourceValue 等 wrapper 继续深入其 .value / 内部元素
    """
    return [leaf for (_path, leaf) in _enumerate_mutable_paths(obj)]


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


# ========================= Mutator =========================


class ContractAwareMutator:
    def __init__(self, rng: random.Random | None = None, *, cfg: MutatorConfig | None = None):
        self.rng = rng or random.Random()
        self.cfg = cfg or MutatorConfig()

    def mutate(self, verbs: List[VerbCall], idx: Optional[int] = None, choice: str = None) -> bool:
        if choice:
            if choice == "insert":
                return self.mutate_insert(verbs, idx)
            elif choice == "delete":
                return self.mutate_delete(verbs, idx)
            else:
                raise ValueError(f"Unknown mutation choice: {choice}")
        else:
            r = self.rng.random()
            if r < 0.5:
                return self.mutate_insert(verbs, idx)
            else:
                # return self.mutate_delete(verbs, idx)
                return self.mutate_param(verbs, idx)

    def mutate_delete(self, verbs: List[VerbCall], idx_: Optional[int] = None) -> bool:
        if not verbs:
            return False
        idx = self.rng.randrange(len(verbs)) if idx_ is None else idx_
        victim = verbs[idx]
        del verbs[idx]
        lost = set(verb_edges_recursive(victim)[1])  # produces
        impact = compute_forward_impact(verbs, idx, lost)
        for k in sorted(impact, reverse=True):
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
        if verbose:
            print("=== VERBS (before) ===")
            for j, v in enumerate(verbs):
                print(f"[{j:02d}] {summarize_verb(v, deep=True)}")

        # 1) 收集可行位置
        global_snapshot = _make_snapshot(verbs, len(verbs))
        for i in candidate_indices:
            if verbose:
                print(f"Trying to insert at index {i}")

            # 1.1 选模板
            builder = _pick_insertion_template(rng, verbs, i, choice)
            build_fn = builder if callable(builder) else builder[0]

            # 1.2 先用“全局 live”生成；失败再用“当前位置 live”补试一次
            ins_list: Optional[List[VerbCall]] = None
            # global_live = _live_before(verbs, len(verbs))
            # cand = build_fn(None, rng, global_live, global_snapshot)
            # if cand is None:
            #     pos_live = _live_before(verbs, i)
            #     cand = build_fn(None, rng, pos_live, global_snap)
            pos_live = _live_before(verbs, i)
            cand = build_fn(None, rng, pos_live, global_snapshot)

            if cand is None:
                if verbose:
                    print("  -> no candidate generated at this position")
                continue

            ins_list = cand if isinstance(cand, list) else [cand]
            if verbose:
                for nv in ins_list:
                    print("  + new:", summarize_verb(nv, deep=True))

            # 1.3 在该位置做可行性干运行检查（允许 destroy 清理后判定）
            if not _check_feasible_position(verbs, ins_list, i, try_trim_on_destroy=True):
                if verbose:
                    print("  -> not feasible at this position")
                continue

            feasible.append((i, ins_list))

        # 2) 从可行集合中选一个位置（偏向靠后）
        choice_pair = _choose_insert_pos(feasible, rng, place="best")
        if not choice_pair:
            if verbose:
                print("No feasible insertion point found.")
            return False

        pos, ins_list = choice_pair

        # 3) 真插入 + destroy 前向切片清理
        verbs[pos:pos] = ins_list
        lost = _lost_from_ins(ins_list)
        # print("lost from ins:", lost)
        if lost:
            _trim_forward_on_lost(verbs, pos + len(ins_list), lost)

        # 4) 最终一次干运行校验
        ctx = FakeCtx()
        try:
            _apply_slice(ctx, verbs)
            if verbose:
                print("=== VERBS (after) ===")
                for j, v in enumerate(verbs):
                    print(f"[{j:02d}] {summarize_verb(v, deep=True)}")
            return True
        except ContractError:
            # 理论上不应触发（pos 源自可行集），但回退以保证幂等
            del verbs[pos : pos + len(ins_list)]
            print(traceback.format_exc())
            if verbose:
                print("Final dry-run failed; reverted insertion.")
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
        # print("mutate param idx:", idx)
        # 2) 枚举可变路径
        snap = _make_snapshot(verbs, idx)
        contract = v.get_contract()
        # print("snap:", snap)
        # print("contract:", contract)
        paths = _enumerate_mutable_paths(v)
        if not paths:
            return False
        path, leaf = rng.choice(paths)
        # print(summarize_verb(v, deep=True))
        # print(path, leaf)
        leaf.mutate(snap=snap, contract=contract, rng=rng)
        # print(leaf)
        # print(type(leaf))
        # print()
        lost = destroyed_targets(v)
        # print("lost from param mutation:", lost)
        if lost:
            _trim_forward_on_lost(verbs, idx, lost)

        # # 3) 变异 leaf
        # if leaf is None:
        #     # None -> OptionalValue.factory 构建
        #     from lib.value import OptionalValue

        #     new_leaf = OptionalValue.factory(rng)
        #     if new_leaf is None:
        #         return False
        #     _set_dotted(v, path, new_leaf)
        #     return True

        # from lib.value import ConstantValue, EnumValue, FlagValue, IntValue, ListValue, OptionalValue, ResourceValue

        # if isinstance(leaf, OptionalValue):
        #     # flip present/absent；若 present，递归变异其 value
        #     if rng.random() < 0.5:
        #         # flip to absent
        #         leaf.present = False
        #         leaf.value = None
        #         return True
        #     else:
        #         # mutate inner value (if any)
        #         if leaf.value is None:
        #             return False
        #         inner_paths = _enumerate_mutable_paths(leaf.value)
        #         if not inner_paths:
        #             return False
        #         inner_path, inner_leaf = rng.choice(inner_paths)
        #         return self._mutate_value(inner_leaf, lambda newv: _set_dotted(leaf.value, inner_path, newv))
        # elif isinstance(leaf, ListValue):
        #     # 变长或变异元素
        #     if rng.random() < 0.3 and len(leaf.value) > 0:
        #         # 删除一个元素
        #         idx = rng.randrange(len(leaf.value))
        #         leaf.value.pop(idx)
        #         return True
        #     elif rng.random() < 0.6:
        #         # 添加一个新元素（尝试用第一个元素的类型构造）
        #         if not leaf.value:
        #             return False
        #         sample_elem = leaf.value[0]
        #         new_elem = self._construct_sample(sample_elem, rng)
        #         if new_elem is None:
        #             return False
        #         leaf.value.append(new_elem)
        #         return True
        #     else:
        #         # 变异一个元素
        #         if not leaf.value:
        #             return
