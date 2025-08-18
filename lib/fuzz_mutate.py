# lib/fuzz_mutate.py
from __future__ import annotations

import random
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .verbs import VerbCall

try:
    from ._codegen_utils import unwrap
except Exception:

    def unwrap(x):
        return getattr(x, "value", x)


try:
    from .contracts import ContractError, ContractTable, InstantiatedContract, State
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

# ===================== 字段角色识别 =====================

RESOURCE_TYPES = {"pd", "cq", "qp", "mr", "mw", "wq", "srq", "flow", "ah", "channel", "table", "dm"}


def is_identifier_field(name: str) -> bool:
    return name.endswith("_var")


def is_resource_field(name: str) -> bool:
    return name.split(".")[-1] in RESOURCE_TYPES


def is_count_field(name: str) -> bool:
    return name.split(".")[-1] in {"num_sge", "num_sges"}


def is_sg_list_field(name: str) -> bool:
    return name.split(".")[-1] in {"sg_list", "sge", "sgl"}


def get_dotted(obj: Any, path: str) -> Any:
    cur = obj
    for p in path.split("."):
        cur = getattr(cur, p)
    return cur


def set_dotted(obj: Any, path: str, val: Any) -> None:
    parts = path.split(".")
    cur = obj
    for p in parts[:-1]:
        cur = getattr(cur, p)
    last = parts[-1]
    cur_val = getattr(cur, last)
    if hasattr(cur_val, "value") and hasattr(val, "value"):
        cur_val.value = val.value
    elif hasattr(cur_val, "value") and not hasattr(val, "value"):
        cur_val.value = val
    else:
        setattr(cur, last, val)


def listify(x) -> List[Any]:
    if x is None:
        return []
    x = unwrap(x)
    if isinstance(x, (list, tuple)):
        return list(x)
    return [x]


def choose_resource(ctx, rtype: str, rng: random.Random, *, allow_destroyed=False) -> Optional[str]:
    if not hasattr(ctx, "contracts") or ctx.contracts is None:
        return None
    snap = ctx.contracts.snapshot()
    pool = [name for (t, name), st in snap.items() if t == rtype and (allow_destroyed or st != "DESTROYED")]
    return rng.choice(pool) if pool else None


# ===================== 不变式修复 =====================


def fix_sg_invariants(obj: Any) -> None:
    sgl_name, n_name = None, None
    for n in ("sg_list", "sge", "sgl"):
        if hasattr(obj, n):
            sgl_name = n
            break
    for n in ("num_sge", "num_sges"):
        if hasattr(obj, n):
            n_name = n
            break
    if not sgl_name or not n_name:
        return
    lst = listify(getattr(obj, sgl_name))
    n = len(lst)
    cur = getattr(obj, n_name)
    if hasattr(cur, "value"):
        try:
            cur.value = n
        except Exception:
            pass
    else:
        try:
            setattr(obj, n_name, n)
        except Exception:
            pass


# ===================== QP 状态机（NEW） =====================

# 合法转移：你可按需变严格（例如不允许 RTR->INIT）
_QP_FSM_NEXT = {
    "RESET": ["INIT"],
    "INIT": ["RTR"],
    "RTR": ["RTS"],
    "RTS": ["RTS"],  # 到顶后保持
    # 未知/ALLOCATED 当作 RESET 处理
}

# 合同状态 <-> ibverbs 枚举字符串 的映射（NEW）
_CONTRACT_TO_QP_ENUM = {
    "RESET": "IBV_QPS_RESET",
    "INIT": "IBV_QPS_INIT",
    "RTR": "IBV_QPS_RTR",
    "RTS": "IBV_QPS_RTS",
}
_QP_ENUM_TO_CONTRACT = {v: k for k, v in _CONTRACT_TO_QP_ENUM.items()}


def _normalize_contract_state(st: str) -> str:
    # 有些路径可能记成 ALLOCATED，把它当 RESET
    if st == "ALLOCATED":
        return "RESET"
    return st


# ===================== 快照（契约感知） =====================


@dataclass
class Snapshot:
    # res_states[(rtype, name)] = State or None
    res_states: Dict[Tuple[str, str], Optional[State]]


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
        self.contracts = ContractTable()

    def alloc_variable(self, name, ty, init=None):
        self._vars.append((name, ty, init))


# --------- 错误解析 ---------
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
    """
    返回 (kind, info)：
      - missing_resource: info={rtype,name}
      - illegal_transition: info={rtype,name,cur,expect_from}
      - dangling_destroy/double_destroy: info={rtype,name}
    其余 UNKNOWN。
    """
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
    # 这两类更多来自生命周期 pass 的 Problem，但也可能由合约抛：
    if "destroy before create" in (msg or ""):
        return ErrKind.DANGLING_DESTROY, {}
    if "destroy twice" in (msg or ""):
        return ErrKind.DOUBLE_DESTROY, {}
    return ErrKind.UNKNOWN, {}


# --- helpers: resolve dotted name from contract spec ---
def _get_dotted(obj, dotted: str):
    cur = obj
    for part in dotted.split("."):
        if cur is None:
            return None
        cur = getattr(cur, part, None)
    return cur


def _unwrap(v):
    if v is None:
        return None
    inner = getattr(v, "inner", None)
    if inner is not None:
        return _unwrap(inner)
    # ResourceValue(name=..., resource_type=...)
    name = getattr(v, "name", None)
    rtype = getattr(v, "resource_type", None)
    if name is not None and rtype is not None:
        return str(name)
    value = getattr(v, "value", None)
    if value is not None:
        return _unwrap(value)
    return v


def _resolve_name(verb, name_attr: str):
    if not name_attr:
        return None
    raw = _get_dotted(verb, name_attr)
    val = _unwrap(raw)
    return None if val is None else str(val)


# # --- read requires / produces (实例级：带具体 name) ---
# def _verb_requires_and_produces(v):  # 还是有点问题，可能需要实例化一下
#     req, pro = [], []
#     c = v.get_contract()
#     if not c:
#         return req, pro
#     for rq in getattr(c, "requires", []) or []:
#         rtype = str(getattr(rq, "rtype", "")) or ""
#         name_attr = getattr(rq, "name_attr", "") or ""
#         name = _resolve_name(v, name_attr) or ""
#         if rtype and name:
#             req.append((rtype, name))
#     for pr in getattr(c, "produces", []) or []:
#         rtype = str(getattr(pr, "rtype", "")) or ""
#         name_attr = getattr(pr, "name_attr", "") or ""
#         name = _resolve_name(v, name_attr) or ""
#         if rtype and name:
#             pro.append((rtype, name))
#     print(req, pro)
#     return req, pro

# # -------- composition-aware requires/produces extraction ----------


# def _is_contract_holder(x) -> bool:
#     try:
#         c = getattr(x, "CONTRACT", None)
#         return c is not None
#     except Exception:
#         return False


# def _iter_child_fields(obj):
#     """
#     优先根据 MUTABLE_FIELDS / FIELD_LIST 选择性地遍历，减少噪音；
#     回退到简单的启发式：只遍历名字看起来像对象容器的字段。
#     """
#     # 首选：显式字段列表
#     fields = []
#     for key in ("MUTABLE_FIELDS", "FIELD_LIST"):
#         fl = getattr(obj, key, None)
#         if isinstance(fl, (list, tuple)):
#             fields.extend(list(fl))
#     if fields:
#         for name in fields:
#             if hasattr(obj, name):
#                 yield name, getattr(obj, name)
#         return

#     # 回退：启发式（保守）
#     for name in dir(obj):
#         if name.startswith("_"):
#             continue
#         try:
#             val = getattr(obj, name)
#         except Exception:
#             continue
#         # 只放行“可能是对象/容器”的字段
#         if _is_contract_holder(val):
#             yield name, val
#         elif isinstance(val, (list, tuple)):
#             yield name, val


# def _unwrap_for_traverse(x):
#     """用于遍历子对象的解包：OptionalValue/… → inner；列表则展开"""
#     if x is None:
#         return []
#     # OptionalValue 风格
#     inner = getattr(x, "inner", None)
#     if inner is not None:
#         return [inner]
#     # 列表/元组
#     if isinstance(x, (list, tuple)):
#         items = []
#         for e in x:
#             items.extend(_unwrap_for_traverse(e) or [e])
#         return items if items else list(x)
#     # 其他：直接用
#     return [x]


# def _resolve_name_dotted(root, dotted: str):
#     """在 root 上用点路径取值并解包为字符串名"""
#     if not dotted:
#         return None
#     cur = root
#     for part in dotted.split("."):
#         if cur is None:
#             return None
#         cur = getattr(cur, part, None)
#     # 解包 ResourceValue/ConstantValue 等
#     v = cur
#     # OptionalValue.inner
#     inner = getattr(v, "inner", None)
#     if inner is not None:
#         v = inner
#     # ResourceValue(name=..., resource_type=...)
#     name = getattr(v, "name", None)
#     if name is not None:
#         return str(name)
#     # 常量包装
#     value = getattr(v, "value", None)
#     if value is not None:
#         return str(value)
#     # 字符串/其他
#     return None if v is None else str(v)


# def _collect_contract_edges_recursive(root_obj, cur_obj, prefix, seen_objs, out_req, out_pro):
#     """
#     root_obj: 根 verb（用于点路径求值）
#     cur_obj:  当前对象（verb 或子对象）
#     prefix:   当前对象在根上的前缀（如 "init_attr_obj."）
#     seen_objs: 去重
#     out_req / out_pro: 累计结果（set of (rtype, name)）
#     """
#     if id(cur_obj) in seen_objs:
#         return
#     seen_objs.add(id(cur_obj))

#     # 1) 读取当前对象的 CONTRACT
#     contract = getattr(cur_obj, "CONTRACT", None)
#     if contract:
#         # requires
#         for rq in getattr(contract, "requires", []) or []:
#             rtype = str(getattr(rq, "rtype", "") or "")
#             name_attr = getattr(rq, "name_attr", "") or ""
#             if not rtype or not name_attr:
#                 continue
#             dotted = prefix + name_attr  # 关键：相对路径 → 绝对点路径
#             name = _resolve_name_dotted(root_obj, dotted)
#             if name:
#                 out_req.add((rtype, name))
#         # produces
#         for pr in getattr(contract, "produces", []) or []:
#             rtype = str(getattr(pr, "rtype", "") or "")
#             name_attr = getattr(pr, "name_attr", "") or ""
#             if not rtype or not name_attr:
#                 continue
#             dotted = prefix + name_attr
#             name = _resolve_name_dotted(root_obj, dotted)
#             if name:
#                 out_pro.add((rtype, name))
#         # transitions：如果需要可以同样收集（例如 DESTROYED 也可以算“produce 了 destroyed 状态的实例”）

#     # 2) 递归到子对象
#     for field_name, field_val in _iter_child_fields(cur_obj):
#         for child in _unwrap_for_traverse(field_val):
#             if child is None:
#                 continue
#             # 只对“像 Attr 的对象（带 CONTRACT）”或容器内元素继续递归
#             if _is_contract_holder(child):
#                 _collect_contract_edges_recursive(
#                     root_obj,
#                     child,
#                     prefix + field_name + ".",  # 叠加路径前缀
#                     seen_objs,
#                     out_req,
#                     out_pro,
#                 )


# def _verb_requires_and_produces(verb):
#     """
#     递归读取 verb 及其子对象的 requires/produces。
#     返回: (req, pro) ；都是去重后的 list[(rtype, name)]。
#     """
#     out_req, out_pro = set(), set()
#     seen = set()
#     _collect_contract_edges_recursive(
#         root_obj=verb,
#         cur_obj=verb,
#         prefix="",
#         seen_objs=seen,
#         out_req=out_req,
#         out_pro=out_pro,
#     )
#     return list(out_req), list(out_pro)


# def compute_forward_impact(verbs, start_idx: int, lost_resources: set):
#     """
#     从 start_idx 开始，凡是 requires 命中 lost_resources 的 verb 标记删除，
#     同时把它 produces 的资源加入 lost_resources 继续向前扩散。
#     返回 indices_to_drop（>= start_idx 的一组索引）
#     """
#     to_drop = set()
#     frontier = set(lost_resources)
#     for i in range(start_idx, len(verbs)):
#         v = verbs[i]
#         req, pro = _verb_requires_and_produces(v)
#         if any((r, n) in frontier for (r, n) in req):
#             to_drop.add(i)
#             for item in pro:
#                 if item not in frontier:
#                     frontier.add(item)
#     return to_drop


# ---------- generic, contract-aware, recursive edges extractor ----------


def _is_optional_none(x):
    try:
        return hasattr(x, "is_none") and x.is_none()
    except Exception:
        return False


def _unwrap_value(x):
    if x is None:
        return None
    if hasattr(x, "inner"):  # OptionalValue
        return _unwrap_value(getattr(x, "inner"))
    if hasattr(x, "name") and hasattr(x, "resource_type"):  # ResourceValue
        return getattr(x, "name")
    if hasattr(x, "value"):  # ConstantValue/IntValue/FlagValue...
        return _unwrap_value(getattr(x, "value"))
    return x


def _get_dotted(root, dotted: str):
    cur = root
    for p in dotted.split("."):
        if cur is None:
            return None
        cur = getattr(cur, p, None)
    return cur


def _resolve_name_for_spec(root, current, name_attr: str):
    """
    dotted 路径从 root 解析（兼容老写法 "qp_attr_obj.pd"）；
    简单字段名从 current 对象解析（适配嵌套对象自己的 CONTRACT）。
    OptionalValue 为空则返回 None（表示跳过该 require/produce）。
    """
    if not name_attr:
        return None
    val = _get_dotted(root, name_attr) if "." in name_attr else getattr(current, name_attr, None)
    if val is None or _is_optional_none(val):
        return None
    val = _unwrap_value(val)
    return None if val is None else str(val)


def _iter_children_fields(obj):
    # 优先 MUTABLE_FIELDS > FIELD_LIST > __dict__
    seen, fields = set(), []
    fields += getattr(obj.__class__, "MUTABLE_FIELDS", []) or []
    for f in getattr(obj.__class__, "FIELD_LIST", []) or []:
        if f not in fields:
            fields.append(f)
    if not fields:
        fields = list(getattr(obj, "__dict__", {}).keys())

    for name in fields:
        if name in seen:
            continue
        seen.add(name)
        try:
            v = getattr(obj, name)
        except Exception:
            continue
        if hasattr(v, "inner"):
            v = getattr(v, "inner")  # OptionalValue
        if v is None or isinstance(v, (str, int, float, bool)):
            continue
        if isinstance(v, (list, tuple)):
            for item in v:
                if item is None or isinstance(item, (str, int, float, bool)):
                    continue
                yield item
        else:
            yield v


def _extract_edges_recursive(root, obj, visited: set):  # 感觉有个问题，用的是getattr，那么那种动态contract就不支持了？
    # 但好像影响不大，因为动态conctract仅仅出现在transition时，我这里不需要
    """返回 (requires, produces, destroys)，元素为 (rtype, name)。"""
    oid = id(obj)
    if oid in visited:
        return [], [], []
    visited.add(oid)

    req, pro, des = [], [], []
    contract = getattr(obj.__class__, "CONTRACT", None)
    if contract:
        # requires
        for rq in getattr(contract, "requires", []) or []:
            rtype = str(getattr(rq, "rtype", "") or "")
            name_attr = getattr(rq, "name_attr", "") or ""
            name = _resolve_name_for_spec(root, obj, name_attr)
            if rtype and name:
                req.append((rtype, name))
        # produces
        for pr in getattr(contract, "produces", []) or []:
            rtype = str(getattr(pr, "rtype", "") or "")
            name_attr = getattr(pr, "name_attr", "") or ""
            name = _resolve_name_for_spec(root, obj, name_attr)
            if rtype and name:
                pro.append((rtype, name))
        # transitions → DESTROYED 视作 destroy（便于生命周期 pass）
        for tr in getattr(contract, "transitions", []) or []:
            to_state = getattr(tr, "to_state", None)
            if str(to_state).upper() == "DESTROYED":
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
    """
    从 start_idx 开始，凡是 requires 命中 lost_resources 的 verb 标记删除，
    并把该 verb 的 produces 加入 lost_resources 继续扩散。
    返回 indices_to_drop（>= start_idx 的索引集合）。
    """
    to_drop = set()
    frontier = set(lost_resources)

    for i in range(start_idx, len(verbs)):
        req, pro, _des = verb_edges_recursive(verbs[i])
        if any((r, n) in frontier for (r, n) in req):
            to_drop.add(i)
            # 级联：把它新产生的资源加入 frontier，使后续依赖也会被删除
            for item in pro:
                if item not in frontier:
                    frontier.add(item)
    return to_drop


# ===================== 编排器（契约感知） =====================


class ContractAwareMutator:
    """
    - 先尝试调用 wrapper.mutate(tracker, contracts, role, rng, policy)
    - 若无 wrapper 或抛错，再回退到轻量默认变异
    - 特例（NEW）：检测到 *.qp_state 字段时，按 QP FSM 引导到下一合法状态
    - 变异后修复不变式（sg_list<->num_sge）
    - 对 verb.CONTRACT 做一次 dry-run；失败则尝试修复资源字段
    """

    def __init__(
        self,
        rng: Optional[random.Random] = None,
        *,
        repair=True,
        dryrun_contract=True,
        sge_factory: Optional[callable] = None,
        pass_through_fail_prob: float = 0.0,
    ):
        self.rng = rng or random.Random()
        self.repair = repair
        self.dryrun_contract = dryrun_contract
        self.sge_factory = sge_factory  # 需要新增 SGE 时使用（可选）
        self.pass_through_fail_prob = pass_through_fail_prob

    # ----------- 对外入口 -----------
    def mutate(self, verbs: List[VerbCall], idx: int) -> bool:  # 目前只支持删除verb？
        # 随机选取一个verb准备删除
        if not verbs:
            return False
        # idx = self.rng.randint(0, len(verbs) - 1)
        # idx = 1
        verb = verbs[idx]
        if not isinstance(verb, VerbCall):
            return False
        print(f"Mutating verb: {verb}")
        pass

        verbs.remove(verb)  # 删除选中的 verb
        print(f"Removed verb: {verb}")

        # ctx = FakeCtx()
        # for v in verbs:
        #     v.apply(ctx)
        # exit(0)

        MAX_FIX, fixes = 16, 0
        i = 0
        while i < len(verbs):
            try:
                ctx = FakeCtx()
                for j in range(0, i + 1):
                    # fix_sg_invariants(verbs[j])
                    verbs[j].apply(ctx)
                i += 1
                continue
            except ContractError as e:
                print(f"Contract error at index {i}: {e}")
                kind, info = classify_contract_error(str(e))
                print(kind, info)
                fail_i = i  # 关键：用失败位置作为切片起点

                repaired = False
                if kind == ErrKind.MISSING_RESOURCE:
                    # 先尝试回补（若命中黑名单会拒绝）
                    # repaired = self._repair_missing_resource(verbs, fail_i, info)
                    repaired = False  # TODO: 实现回补逻辑
                    if not repaired:
                        # 不回补：做前向切片，成块删除所有受影响 verbs
                        lost = {(info.get("rtype"), info.get("name"))}
                        impact = compute_forward_impact(verbs, fail_i, lost)
                        if impact:
                            for k in sorted(impact, reverse=True):
                                verbs.pop(k)
                            repaired = True
                        else:
                            # 没有受影响者（少见），删除当前 verb 自身
                            verbs.pop(fail_i)
                            repaired = True

                elif kind == ErrKind.ILLEGAL_TRANSITION:
                    print("what?")
                    if info.get("rtype") == "qp":
                        print("illegal transition:", info)
                        _QP_FSM_NEXT = {
                            "RESET": ["INIT"],
                            "INIT": ["RTR"],
                            "RTR": ["RTS"],
                            "RTS": ["RTS"],
                        }

                        def _qp_path(from_state: str, to_state: str) -> Optional[List[str]]:
                            """给出 from->to 所需的状态链（含目标，不含起点）。"""
                            from_state = "RESET" if from_state in (None, "ALLOCATED") else from_state
                            if from_state == to_state:
                                return []
                            path = []
                            cur = from_state
                            visited = set()
                            while cur != to_state:
                                if cur in visited:
                                    return None
                                visited.add(cur)
                                nxts = _QP_FSM_NEXT.get(cur, [])
                                if not nxts:
                                    return None
                                nxt = nxts[0]
                                path.append(nxt)
                                cur = nxt
                                if len(path) > 8:
                                    return None
                            return path

                        def _insert_qp_transitions(verbs, at_idx: int, qp_name: str, path_states: list):
                            from lib.ibv_all import IbvQPAttr  # 使用你的聚合

                            from .verbs import ModifyQP

                            new_vs = []
                            for st in path_states:
                                attr = IbvQPAttr(qp_state=f"IBV_QPS_{st}")
                                new_vs.append(ModifyQP(qp=qp_name, attr_obj=attr, attr_mask="IBV_QP_STATE"))
                            verbs[at_idx:at_idx] = new_vs
                            return True

                        path = _qp_path(info.get("cur"), info.get("expect_from"))
                        print(path)
                        if path is not None:
                            repaired = _insert_qp_transitions(verbs, fail_i, info.get("name"), path)

                # elif kind in (ErrKind.DANGLING_DESTROY, ErrKind.DOUBLE_DESTROY):
                #     verbs.pop(fail_i)
                #     repaired = True

                else:
                    return False

                if not repaired:
                    return False
                fixes += 1
                if fixes > MAX_FIX:
                    return False
                # 修完后，不挪动 i，从同一位置再重放
                continue

        ctx = FakeCtx()
        for v in verbs:
            print(v)
            v.apply(ctx)
        # if self.dryrun_contract:
        #     try:
        #         v.apply(ctx)
        #     except ContractError as e:
        #         kind, info = classify_contract_error(str(e))
        #         print(f"Dry-run contract error: {kind}, info: {info}")
        #         if self.pass_through_fail_prob > 0 and self.rng.random() < self.pass_through_fail_prob:
        #             print("Passing through failure due to configured probability.")
        #             continue
        #         # 这里可以添加更多的错误处理逻辑
        #         return False
