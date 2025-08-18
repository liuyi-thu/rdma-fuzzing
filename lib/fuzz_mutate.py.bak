# lib/fuzz_mutate.py
from __future__ import annotations

import random
from collections.abc import Iterable
from typing import Any, Dict, List, Optional

try:
    from ._codegen_utils import unwrap
except Exception:

    def unwrap(x):
        return getattr(x, "value", x)


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
    def mutate(self, verb: Any, ctx: Any) -> bool:
        if not hasattr(verb, "get_mutable_params"):
            return False

        params: Dict[str, Any] = verb.get_mutable_params()

        # 1) 字段级变异：优先交给 wrapper.mutate(...)
        for key, _ in params.items():
            role = self._role_of(key)
            self._mutate_field(verb, key, role, ctx)

            # (NEW) 若是 qp_state，尝试 QP FSM 引导
            if key.endswith("qp_state"):
                try:
                    self._mutate_qp_state_in_place(verb, key, ctx)
                except Exception:
                    pass

        # 2) 不变式修复（verb + wr_obj）
        fix_sg_invariants(verb)
        wr = getattr(verb, "wr_obj", None)
        if wr is not None:
            fix_sg_invariants(unwrap(wr))
            if self.sge_factory and self.rng.random() < 0.3:
                self._maybe_append_sge(wr)

        # 3) 契约 dry-run + 可选修复
        # if self.dryrun_contract and hasattr(ctx, "contracts"):
        #     if not self._dryrun_contract_ok(verb, ctx):
        #         print("Contract dry-run failed, attempting repair...")
        #         if not self.repair:
        #             return False
        #         if not self._attempt_repair(verb, ctx):
        #             return False
        # return True

        if self.dryrun_contract and hasattr(ctx, "contracts"):
            if not self._dryrun_contract_ok(verb, ctx):
                # 20% 概率直接放行（fuzz 模式）
                if self.pass_through_fail_prob > 0 and self.rng.random() < self.pass_through_fail_prob:
                    return True
                if not self.repair:
                    return False
                if not self._attempt_repair(verb, ctx):
                    # 修不动，仍可按概率放行
                    if self.pass_through_fail_prob > 0 and self.rng.random() < self.pass_through_fail_prob:
                        return True
                    return False
        return True

    # ----------- 内部：字段变异 -----------
    def _role_of(self, key: str) -> str:
        if is_identifier_field(key):
            return "identifier"
        if is_resource_field(key):
            return "resource"
        if is_sg_list_field(key):
            return "sg_list"
        if is_count_field(key):
            return "count"
        return "generic"

    def _mutate_field(self, verb: Any, key: str, role: str, ctx: Any) -> None:
        obj = get_dotted(verb, key)
        # 1) wrapper 优先
        if hasattr(obj, "mutate") and callable(getattr(obj, "mutate")):
            try:
                obj.mutate(
                    tracker=getattr(ctx, "tracker", None),
                    contracts=getattr(ctx, "contracts", None),
                    role=role,
                    rng=self.rng,
                    policy="contract-aware",
                )
                return
            except TypeError:
                try:
                    obj.mutate()
                    return
                except Exception:
                    pass
            except Exception:
                pass

        # 2) 默认变异（保底）
        try:
            cur = unwrap(obj)
            if role == "identifier":
                set_dotted(verb, key, str(cur) + "_m")
            elif role == "resource":
                rtype = key.split(".")[-1]
                cand = choose_resource(ctx, rtype, self.rng)
                if cand:
                    set_dotted(verb, key, cand)
            elif role == "count":
                if isinstance(cur, int):
                    set_dotted(verb, key, max(0, cur + (1 if self.rng.random() < 0.5 else -1)))
            elif role == "sg_list":
                lst = listify(cur)
                if self.sge_factory and lst and self.rng.random() < 0.5:
                    try:
                        lst.append(self.sge_factory())
                    except Exception:
                        lst.append(lst[0])
                set_dotted(verb, key, lst)
            else:
                if isinstance(cur, int):
                    set_dotted(verb, key, max(0, cur + (1 if self.rng.random() < 0.5 else -1)))
                elif isinstance(cur, str):
                    set_dotted(verb, key, cur + "_m")
        except Exception:
            pass

    # (NEW) QP 状态机引导：根据 contracts 中 qp 当前状态，优先挑“下一步合法状态”
    def _mutate_qp_state_in_place(self, verb: Any, key: str, ctx: Any) -> None:
        # 只有 ModifyQP 这类动词才有意义，确保拿到 qp 名
        qp_name = getattr(verb, "qp", None)
        if qp_name is None or not hasattr(ctx, "contracts"):
            return

        snap = ctx.contracts.snapshot()
        cur_contract_state = snap.get(("qp", str(qp_name)))
        if cur_contract_state is None:
            return
        cur_contract_state = _normalize_contract_state(cur_contract_state)
        next_states = _QP_FSM_NEXT.get(cur_contract_state, _QP_FSM_NEXT.get("RESET", []))
        if not next_states:
            return
        # 从候选里挑一个（通常只有一个）
        target_contract_state = next_states[0]
        target_enum = _CONTRACT_TO_QP_ENUM.get(target_contract_state)
        if not target_enum:
            return

        # 把 attr_obj.qp_state 设置为目标枚举；wrapper/Value 通过 set_dotted 兼容
        set_dotted(verb, key, target_enum)

    def _maybe_append_sge(self, wr_obj: Any) -> None:
        for name in ("sg_list", "sge", "sgl"):
            if hasattr(wr_obj, name):
                lst = listify(getattr(wr_obj, name))
                try:
                    lst.append(self.sge_factory())
                    setattr(wr_obj, name, lst)
                    fix_sg_invariants(wr_obj)
                except Exception:
                    pass
                break

    # ----------- 内部：契约 dry-run/修复 -----------
    def _dryrun_contract_ok(self, verb: Any, ctx: Any) -> bool:
        try:
            shadow = self._clone_contracts(ctx)
            contract = getattr(verb, "CONTRACT", None)
            if contract is None and hasattr(verb, "_contract"):
                contract = verb._contract()
            if contract is None:
                return True
            shadow.apply_contract(verb, contract)
            return True
        except ContractError as e:
            print(f"Contract dry-run failed: {e}")
            return False
        except Exception:
            return False

    def _clone_contracts(self, ctx: Any):
        shadow = type(ctx.contracts)()
        for (rtype, name), st in ctx.contracts.snapshot().items():
            if st == "DESTROYED":
                shadow.put(rtype, name, State.ALLOCATED if hasattr(State, "ALLOCATED") else "ALLOCATED")
                shadow.destroy(rtype, name)
            else:
                target_state = getattr(State, st) if hasattr(State, st) else st
                shadow.put(rtype, name, target_state)
        return shadow

    # def _attempt_repair(self, verb: Any, ctx: Any) -> bool:
    #     changed = False
    #     params: Dict[str, Any] = verb.get_mutable_params()
    #     for key in params.keys():
    #         if is_resource_field(key):
    #             rtype = key.split(".")[-1]
    #             cand = choose_resource(ctx, rtype, self.rng)
    #             if cand and cand != get_dotted(verb, key):
    #                 set_dotted(verb, key, cand)
    #                 changed = True
    #     fix_sg_invariants(verb)
    #     wr = getattr(verb, "wr_obj", None)
    #     if wr is not None:
    #         fix_sg_invariants(unwrap(wr))
    #     # 修复后再试 dry-run
    #     return self._dryrun_contract_ok(verb, ctx)
    # 在 _attempt_repair 的开头插入这段（保留原来的资源修复逻辑）：
    def _attempt_repair(self, verb, ctx) -> bool:
        changed = False

        # --- NEW: 若是 ModifyQP，按当前状态修正目标 qp_state ---
        try:
            if type(verb).__name__ == "ModifyQP" and hasattr(ctx, "contracts"):
                # 当前 QP 状态
                qp_name = getattr(verb, "qp", None)
                if qp_name is not None:
                    snap = ctx.contracts.snapshot()
                    cur = snap.get(("qp", str(qp_name)))
                    if cur in ("ALLOCATED", None):
                        cur = "RESET"
                    # 下一步合法状态
                    fsm_next = {
                        "RESET": "IBV_QPS_INIT",
                        "INIT": "IBV_QPS_RTR",
                        "RTR": "IBV_QPS_RTS",
                        "RTS": "IBV_QPS_RTS",
                    }
                    target_enum = fsm_next.get(cur)
                    if target_enum:
                        # 写回 attr_obj.qp_state（兼容 wrapper）
                        ao = getattr(verb, "attr_obj", None) or getattr(verb, "attr", None)
                        if ao is not None and hasattr(ao, "qp_state"):
                            val = getattr(ao, "qp_state")
                            if hasattr(val, "value"):
                                val.value = target_enum
                            else:
                                setattr(ao, "qp_state", target_enum)
                            changed = True
        except Exception:
            pass

        # --- 原来的资源字段修复 ---
        params: Dict[str, Any] = verb.get_mutable_params()
        for key in params.keys():
            if is_resource_field(key):
                rtype = key.split(".")[-1]
                cand = choose_resource(ctx, rtype, self.rng)
                if cand and cand != get_dotted(verb, key):
                    set_dotted(verb, key, cand)
                    changed = True

        fix_sg_invariants(verb)
        wr = getattr(verb, "wr_obj", None)
        if wr is not None:
            fix_sg_invariants(unwrap(wr))

        return self._dryrun_contract_ok(verb, ctx)
