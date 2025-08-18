# lib/contracts.py
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

# ===== 在文件开头加一个全局开关和工具函数 =====
DEBUG = False  # 改成 True 就能打开所有调试信息


def debug_print(*args, **kwargs):
    """只在 DEBUG=True 时输出"""
    if DEBUG:
        print(*args, **kwargs)


def _unwrap(x: Any) -> Any:
    return getattr(x, "value", x)


def _get_by_path(root: Any, path: str, *, missing_ok: bool = True) -> Any:
    """
    支持点路径 'a.b.c'，并在**每一跳**先做 unwrap：
      - 若当前节点是 wrapper（有 .value），先取 .value
      - 若为 None 且 missing_ok=True，直接返回 None（表示“可缺省”）
      - 支持 dict（按 key）与 list/tuple（按下标）访问
    """
    cur = root
    for seg in path.split("."):
        cur = _unwrap(cur)
        if cur is None:
            if missing_ok:
                return None
            raise AttributeError(f"path '{path}' broken at segment '{seg}' (None)")

        # dict 优先
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
            continue

        # list/tuple 下标
        if isinstance(cur, (list, tuple)):
            try:
                idx = int(seg)
                cur = cur[idx]
                continue
            except Exception:
                # 不是下标，继续尝试 getattr
                pass

        # 常规 getattr
        cur = getattr(cur, seg)

    return _unwrap(cur)


def _as_iter(x: Any) -> Iterable:
    """
    对 require/transition/produce 里的 name 值做批量化：
      - None -> 空列表（跳过）
      - list/tuple/set -> 原样迭代
      - 其他 -> 单元素列表
    """
    x = _unwrap(x)
    if x is None:
        return []
    if isinstance(x, (list, tuple, set)):
        return x
    return [x]


# -------- 资源状态机：可按需扩展 --------
class State(Enum):
    ALLOCATED = auto()  # 一般对象刚创建
    RESET = auto()  # QP 创建后初始状态
    INIT = auto()
    RTR = auto()
    RTS = auto()
    DESTROYED = auto()
    IMPORTED = auto()


@dataclass(frozen=True)
class ResourceKey:
    rtype: str  # 资源类型：'pd' / 'cq' / 'qp' / 'mr' / ...
    name: str  # 资源名：'pd0' / 'cq0' / 'qp0' / ...


@dataclass
class ResourceRec:
    key: ResourceKey
    state: State


class ContractError(RuntimeError):
    pass


@dataclass
class RequireSpec:
    rtype: str  # 资源类型
    state: Optional[State]  # 允许的状态（可为 None 表示只要求存在）
    name_attr: str  # 从 verb 上读取资源名的属性名（如 'pd' / 'qp'）


@dataclass
class ProduceSpec:
    rtype: str  # 资源类型
    state: State  # 生产后的状态
    name_attr: str  # 从 verb 上读取新资源名的属性名（如 'qp' / 'mw'）


@dataclass
class TransitionSpec:
    rtype: str
    from_state: Optional[State]  # 可为 None 表示不检查来源状态
    to_state: State
    name_attr: str  # 从 verb 上读取目标资源名（如 'qp'）


@dataclass
class Contract:
    requires: List[RequireSpec]
    produces: List[ProduceSpec]
    transitions: List[TransitionSpec]

    @staticmethod
    def empty() -> Contract:
        return Contract([], [], [])


@dataclass
class InstantiatedContract(Contract):
    """
    用于测试时的契约验证。
    主要用于测试时的契约验证。
    """

    @staticmethod
    def instantiate(verb: Any, contract: Contract) -> InstantiatedContract:
        requires = []
        for spec in contract.requires:
            try:
                val = _get_by_path(verb, spec.name_attr, missing_ok=True)
            except Exception as e:
                raise ContractError(f"require: cannot resolve '{spec.name_attr}' on {type(verb).__name__}: {e}")
            for name in _as_iter(val):
                requires.append(RequireSpec(rtype=spec.rtype, state=spec.state, name_attr=str(name)))
        produces = []
        for spec in contract.produces:
            try:
                val = _get_by_path(verb, spec.name_attr, missing_ok=True)
            except Exception as e:
                raise ContractError(f"produce: cannot resolve '{spec.name_attr}' on {type(verb).__name__}: {e}")
            for name in _as_iter(val):
                produces.append(ProduceSpec(rtype=spec.rtype, state=spec.state, name_attr=str(name)))
        transitions = []
        for spec in contract.transitions:
            try:
                val = _get_by_path(verb, spec.name_attr, missing_ok=True)
            except Exception as e:
                raise ContractError(f"transition: cannot resolve '{spec.name_attr}' on {type(verb).__name__}: {e}")
            for name in _as_iter(val):
                transitions.append(
                    TransitionSpec(
                        rtype=spec.rtype, from_state=spec.from_state, to_state=spec.to_state, name_attr=str(name)
                    )
                )
        return InstantiatedContract(
            requires=requires,
            produces=produces,
            transitions=transitions,
        )

    @staticmethod
    # def merge(self, other: InstantiatedContract) -> InstantiatedContract:
    #     """
    #     合并两个契约实例，返回一个新的实例。
    #     """
    #     return InstantiatedContract(
    #         requires=self.requires + other.requires,
    #         produces=self.produces + other.produces,
    #         transitions=self.transitions + other.transitions,
    #     )
    def merge(list_of_contracts: List[InstantiatedContract]) -> InstantiatedContract:
        """
        合并多个契约实例，返回一个新的实例。
        """
        requires = []
        produces = []
        transitions = []
        for contract in list_of_contracts:
            requires.extend(contract.requires)
            produces.extend(contract.produces)
            transitions.extend(contract.transitions)

        def remove_duplicates_by_eq_loop(data_list):
            """
            使用循环实现列表去重（基于相等性）。

            Args:
                data_list: 包含重复元素的列表。

            Returns:
                去重后的列表。
            """
            unique_list = []
            for item in data_list:
                if item not in unique_list:
                    unique_list.append(item)
            return unique_list

        requires = remove_duplicates_by_eq_loop(requires)
        produces = remove_duplicates_by_eq_loop(produces)
        transitions = remove_duplicates_by_eq_loop(transitions)

        return InstantiatedContract(
            requires=requires,
            produces=produces,
            transitions=transitions,
        )


class ContractTable:
    """
    维护资源状态机；你可以把它挂在 CodeGenContext/ctx 上为 ctx.contracts。
    与现有 tracker 并行，不互相干扰。
    """

    def __init__(self):
        self._store: Dict[ResourceKey, ResourceRec] = {}

    # ===== 基本操作 =====
    def put(self, rtype: str, name: str, state: State):
        key = ResourceKey(rtype, str(name))
        rec = self._store.get(key)
        if rec and rec.state is not State.DESTROYED:
            # 同名未销毁就重复创建 -> 抛错
            raise ContractError(f"resource already exists: {rtype} {name} in state {rec.state.name}")
        self._store[key] = ResourceRec(key, state)

    def require(self, rtype: str, name: str, state: Optional[State] = None):
        key = ResourceKey(rtype, str(name))
        rec = self._store.get(key)
        if not rec:
            raise ContractError(f"required resource not found: {rtype} {name}")
        if state is not None and rec.state is not state:
            raise ContractError(f"resource {rtype} {name} in state {rec.state.name}, required {state.name}")

    def transition(self, rtype: str, name: str, to_state: State, from_state: Optional[State] = None):
        key = ResourceKey(rtype, str(name))
        rec = self._store.get(key)
        if not rec:
            raise ContractError(f"transition target not found: {rtype} {name}")
        if from_state is not None and rec.state is not from_state:
            raise ContractError(
                f"illegal transition for {rtype} {name}: {rec.state.name} -> {to_state.name}, expected from {from_state.name}"
            )
        rec.state = to_state

    def destroy(self, rtype: str, name: str):
        key = ResourceKey(rtype, str(name))
        rec = self._store.get(key)
        if not rec:
            # 允许“宽松销毁”（也可以改成严格报错）
            raise ContractError(f"destroy target not found: {rtype} {name}")
        rec.state = State.DESTROYED

    # ===== 契约执行 =====
    # def apply_contract(self, verb: Any, contract: Contract):
    #     # 1) 检查 require
    #     for spec in contract.requires:
    #         name = getattr(verb, spec.name_attr)
    #         self.require(spec.rtype, str(name), spec.state)

    #     # 2) 检查/执行 transition
    #     for spec in contract.transitions:
    #         name = getattr(verb, spec.name_attr)
    #         self.transition(spec.rtype, str(name), spec.to_state, spec.from_state)

    #     # 3) 执行 produce
    #     for spec in contract.produces:
    #         name = getattr(verb, spec.name_attr)
    #         self.put(spec.rtype, str(name), spec.state)
    def apply_contract(self, verb: Any, contract: Contract):
        contract = verb.get_contract()
        print(contract)
        # 1) requires
        for spec in contract.requires:
            try:
                val = _get_by_path(verb, spec.name_attr, missing_ok=True)
            except Exception as e:
                raise ContractError(f"require: cannot resolve '{spec.name_attr}' on {type(verb).__name__}: {e}")
            for name in _as_iter(val):
                self.require(spec.rtype, str(name), spec.state)

        # 2) transitions
        for spec in contract.transitions:
            try:
                val = _get_by_path(verb, spec.name_attr, missing_ok=True)
            except Exception as e:
                raise ContractError(f"transition: cannot resolve '{spec.name_attr}' on {type(verb).__name__}: {e}")
            for name in _as_iter(val):
                self.transition(spec.rtype, str(name), spec.to_state, spec.from_state)

        # 3) produces
        for spec in contract.produces:
            try:
                val = _get_by_path(verb, spec.name_attr, missing_ok=True)
            except Exception as e:
                raise ContractError(f"produce: cannot resolve '{spec.name_attr}' on {type(verb).__name__}: {e}")
            for name in _as_iter(val):
                self.put(spec.rtype, str(name), spec.state)

    # ===== 查询 / 调试 =====
    def snapshot(self) -> Dict[Tuple[str, str], str]:
        return {(k.rtype, k.name): v.state.name for k, v in self._store.items()}

    # @staticmethod
    # def instantiate_contract(verb: Any, contract: Contract):
    #     """
    #     实例化一个 Contract 对象，便于在测试中使用。
    #     主要用于测试时的契约验证。
    #     """
    #     # return Contract(
    #     #     requires=[RequireSpec(rtype=spec.rtype, state=spec.state, name_attr=spec.name_attr) for spec in contract.requires],
    #     #     produces=[ProduceSpec(rtype=spec.rtype, state=spec.state, name_attr=spec.name_attr) for spec in contract.produces],
    #     #     transitions=[TransitionSpec(rtype=spec.rtype, from_state=spec.from_state, to_state=spec.to_state, name_attr=spec.name_attr) for spec in contract.transitions],
    #     # )
    #     requires = []

    #     for spec in contract.requires:
    #         try:
    #             val = _get_by_path(verb, spec.name_attr, missing_ok=True)
    #         except Exception as e:
    #             raise ContractError(f"require: cannot resolve '{spec.name_attr}' on {type(verb).__name__}: {e}")
