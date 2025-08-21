# lib/fuzz_mutate.py (refactored)
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

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
        self._vars = []
        self.contracts = ContractTable()

    def alloc_variable(self, name, ty, init=None):
        self._vars.append((name, ty, init))


# ========================= Helpers (unwrap/dotted) =========================
def _get_dotted(obj: Any, dotted: str) -> Any:
    cur = obj
    for p in dotted.split("."):
        if cur is None:
            return None
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
    if not fields:
        fields = list(getattr(obj, "__dict__", {}).keys())
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
    contract = getattr(obj.__class__, "CONTRACT", None)
    if contract:
        for rq in getattr(contract, "requires", []) or []:
            rtype = str(getattr(rq, "rtype", "") or "")
            name_attr = getattr(rq, "name_attr", "") or ""
            name = _resolve_name_for_spec(root, obj, name_attr)
            if rtype and name:
                req.append((rtype, name))
        for pr in getattr(contract, "produces", []) or []:
            rtype = str(getattr(pr, "rtype", "") or "")
            name_attr = getattr(pr, "name_attr", "") or ""
            name = _resolve_name_for_spec(root, obj, name_attr)
            if rtype and name:
                pro.append((rtype, name))
        for tr in getattr(contract, "transitions", []) or []:
            if str(getattr(tr, "to_state", None)).upper() == "DESTROYED":
                rtype = str(getattr(tr, "rtype", "") or "")
                name_attr = getattr(tr, "name_attr", "") or ""
                name = _resolve_name_for_spec(root, obj, name_attr)
                if rtype and name:
                    des.append((rtype, name))

    for child in _iter_children_fields(obj):
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
    from lib.ibv_all import IbvQPCap, IbvQPInitAttr

    from .verbs import AllocPD, CreateCQ, CreateQP, RegMR

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

    return {"pd": mk_pd, "cq": mk_cq, "qp": mk_qp, "mr": mk_mr}


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


# ========================= Insertion templates =========================
def _pick_insertion_template(rng: random.Random, verbs: List[VerbCall], i: int):
    from lib.ibv_all import IbvSendWR, IbvSge

    from .verbs import CreateCQ, ModifyQP, PollCQ, PostSend, RegMR

    def pick_qp_name():
        qps = [n for (t, n) in _live_before(verbs, i) if t == "qp"]
        return rng.choice(qps) if qps else None

    def pick_cq_name():
        cqs = [n for (t, n) in _live_before(verbs, i) if t == "cq"]
        return rng.choice(cqs) if cqs else None

    def pick_pd_name():
        pds = [n for (t, n) in _live_before(verbs, i) if t == "pd"]
        return rng.choice(pds) if pds else None

    def build_modify_qp(ctx, rng, live):
        qp = pick_qp_name()
        if not qp:
            return None
        return (
            build_modify_qp_safe_chain(verbs, i, qp, rng)
            if rng.random() < 0.6
            else build_modify_qp_stateless(verbs, i, qp, rng)
        )

    def build_post_send(ctx, rng, live):
        qp = pick_qp_name()
        if not qp:
            return None
        sge = IbvSge(addr=0x1000, length=16, lkey=0x1234)
        wr = IbvSendWR(opcode="IBV_WR_SEND", num_sge=1, sg_list=[sge])
        return PostSend(qp=qp, wr_obj=wr)

    def build_poll_cq(ctx, rng, live):
        cq = pick_cq_name()
        return None if not cq else PollCQ(cq=cq, num_entries=1)

    def build_reg_mr(ctx, rng, live):
        pd = pick_pd_name()
        return (
            None
            if not pd
            else RegMR(
                pd=pd, mr=f"mr_{rng.randrange(1 << 16)}", addr="buf0", length=4096, access="IBV_ACCESS_LOCAL_WRITE"
            )
        )

    def build_create_cq(ctx, rng, live):
        return CreateCQ(cq=f"cq_{rng.randrange(1 << 16)}", cqe=16, comp_vector=0, channel="NULL")

    return rng.choice([build_modify_qp, build_post_send, build_poll_cq, build_reg_mr, build_create_cq])


# ========================= Mutator =========================
class ContractAwareMutator:
    def __init__(self, rng: Optional[random.Random] = None, *, cfg: MutatorConfig | None = None):
        self.rng = rng or random.Random()
        self.cfg = cfg or MutatorConfig()

    # —— 删除变异（保留你的思路；若已有实现可直接替换/合并） ——
    def mutate_delete(self, verbs: List[VerbCall]) -> bool:
        if not verbs:
            return False
        idx = self.rng.randrange(len(verbs))
        victim = verbs[idx]
        del verbs[idx]
        # 级联清理：删除受其 produces 影响的后续
        req, pro, _ = verb_edges_recursive(victim)
        lost = set(pro)
        impact = compute_forward_impact(verbs, idx, lost)
        for k in sorted(impact, reverse=True):
            verbs.pop(k)
        return True

    # —— 插入变异（有/无状态 ModifyQP 等） ——
    def mutate_insert(self, verbs: List[VerbCall], idx: Optional[int] = None) -> bool:
        if not verbs:
            return False
        rng = self.rng
        i = rng.randrange(0, len(verbs) + 1) if idx is None else idx
        builder = _pick_insertion_template(rng, verbs, i)
        new_v = builder(None, rng, _live_before(verbs, i))
        if new_v is None:
            return False
        ins_list = new_v if isinstance(new_v, list) else [new_v]

        # 插入前补依赖
        if not all(_ensure_requires_before(verbs, i, v) for v in ins_list):
            return False

        verbs[i:i] = ins_list

        # dry-run & repair
        MAX_FIX, fixes, k = 16, 0, 0
        while k < len(verbs):
            try:
                ctx = FakeCtx()
                for j in range(0, k + 1):
                    verbs[j].apply(ctx)
                k += 1
                continue
            except ContractError as e:
                kind, info = classify_contract_error(str(e))
                repaired = False

                if kind == ErrKind.MISSING_RESOURCE:
                    repaired = _ensure_requires_before(verbs, k, verbs[k])
                    if not repaired:
                        # 回退本次插入
                        for v in ins_list:
                            try:
                                verbs.remove(v)
                            except ValueError:
                                pass
                        return False

                elif kind == ErrKind.ILLEGAL_TRANSITION and info.get("rtype") == "qp":
                    # 注意：这里使用 expect_from（修复了原实现里写成 from 的问题）
                    path = _qp_path(info.get("expect_from"), info.get("to"))
                    if path:
                        from lib.ibv_all import IbvQPAttr

                        from .verbs import ModifyQP

                        chain = [
                            ModifyQP(
                                qp=info.get("name"),
                                attr_obj=IbvQPAttr(qp_state=f"IBV_QPS_{st}"),
                                attr_mask="IBV_QP_STATE",
                            )
                            for st in path
                        ]
                        verbs[k:k] = chain
                        repaired = True

                elif kind in (ErrKind.DANGLING_DESTROY, ErrKind.DOUBLE_DESTROY):
                    verbs.pop(k)
                    repaired = True

                if not repaired:
                    # 未识别：回退插入
                    for v in ins_list:
                        try:
                            verbs.remove(v)
                        except ValueError:
                            pass
                    return False

                fixes += 1
                if fixes > MAX_FIX:
                    return False
                continue
        return True

    # —— 总入口：可路由到不同策略 ——
    def mutate(self, verbs: List[VerbCall]) -> bool:
        r = self.rng.random()
        if r < 0.5:
            return self.mutate_insert(verbs)
        else:
            return self.mutate_delete(verbs)
