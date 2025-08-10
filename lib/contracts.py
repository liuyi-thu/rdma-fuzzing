# lib/contracts.py
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple


# -------- 资源状态机：可按需扩展 --------
class State(Enum):
    ALLOCATED = auto()  # 一般对象刚创建
    RESET = auto()  # QP 创建后初始状态
    INIT = auto()
    RTR = auto()
    RTS = auto()
    DESTROYED = auto()


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
    def apply_contract(self, verb: Any, contract: Contract):
        # 1) 检查 require
        for spec in contract.requires:
            name = getattr(verb, spec.name_attr)
            self.require(spec.rtype, str(name), spec.state)

        # 2) 检查/执行 transition
        for spec in contract.transitions:
            name = getattr(verb, spec.name_attr)
            self.transition(spec.rtype, str(name), spec.to_state, spec.from_state)

        # 3) 执行 produce
        for spec in contract.produces:
            name = getattr(verb, spec.name_attr)
            self.put(spec.rtype, str(name), spec.state)

    # ===== 查询 / 调试 =====
    def snapshot(self) -> Dict[Tuple[str, str], str]:
        return {(k.rtype, k.name): v.state.name for k, v in self._store.items()}
