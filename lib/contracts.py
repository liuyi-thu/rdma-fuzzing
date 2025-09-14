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


def _unwrap(v):
    # 解 OptionalValue / ResourceValue / ConstantValue / ListValue
    try:
        # 你的 wrapper 若有统一的 .get_value() 更好；这里做常见分支
        from lib.value import ConstantValue, ListValue, OptionalValue, ResourceValue

        if isinstance(v, OptionalValue):
            inner = v.value
            return _unwrap(inner) if inner is not None else None
        if isinstance(v, ConstantValue):
            return v.value
        if isinstance(v, ResourceValue):
            # 对 require 来说，我们关心资源名字符串
            return v.value
        if isinstance(v, ListValue):
            return [_unwrap(x) for x in v.value]
    except Exception:
        pass
    return v


def _as_iter(v):
    if v is None:
        return []
    v = _unwrap(v)
    if isinstance(v, (list, tuple, set)):
        return list(v)
    return [v]


def _iter_children(obj, seg):
    """
    对当前 obj 应用一个路径段 seg，返回展开后的节点列表。
    支持：
      - 普通字段名： e.g. "sg_list"
      - 列表展开：   "sg_list[*]" 或 "sg_list.*"
      - 纯 "*"：     对 obj 若是 list 则展开
      - 下标：       "sg_list[0]"（可选）
    """
    out = []
    obj = _unwrap(obj)

    # 纯 "*"
    if seg in ("*", "[*]"):
        return list(_as_iter(obj))

    import re

    m = re.match(r"^([A-Za-z_]\w*)(\[(\*|\d+)\])?$", seg)
    if not m:
        # 非法段，直接失败
        return []

    field = m.group(1)
    index = m.group(3)  # None / "*" / digits

    # 取字段
    node = getattr(obj, field, None)
    node = _unwrap(node)

    if index is None:
        # 不带下标：直接返回该字段
        return _as_iter(node)
    if index == "*":
        # 列表展开
        return list(_as_iter(node))

    # 数值下标
    try:
        k = int(index)
        seq = list(_as_iter(node))
        if 0 <= k < len(seq):
            return [seq[k]]
        return []
    except Exception:
        return []


def _walk_double_star(head):
    """
    针对 WR 链：从 head 开始，沿 next 指针一直走到底，返回所有结点。
    其他类型若没有 'next'，就只返回自身。
    """
    out = []
    cur = _unwrap(head)
    seen = set()
    while cur is not None and id(cur) not in seen:
        out.append(cur)
        seen.add(id(cur))
        nxt = getattr(cur, "next", None)
        # next 可能是 OptionalValue，解一下
        cur = _unwrap(nxt)
    return out


def _get_by_path(root, path: str, *, missing_ok: bool = False):
    """
    增强版路径：
      - "a.b.c" 普通字段
      - "a[*].b" 列表展开
      - "**" / "field**" 递归沿 next 链（"**" 从当前节点；"field**" 先取字段再沿链）
    返回扁平 list（元素已做 _unwrap/_as_iter）
    """
    if not path:
        return root

    nodes = [root]
    for seg in path.split("."):
        # 1) 纯 "**"：对当前 nodes 里的每个节点，沿 next 链展开
        if seg == "**":
            expanded = []
            for n in nodes:
                expanded.extend(_walk_double_star(n))
            nodes = expanded
            continue

        # 2) 字段名带后缀 "**"：先取该字段，再沿 next 链展开
        if seg.endswith("**") and seg != "**":
            base = seg[:-2]  # 去掉后缀
            seeds = []
            for n in nodes:
                seeds.extend(_iter_children(n, base))
            expanded = []
            for s in seeds:
                expanded.extend(_walk_double_star(s))
            nodes = expanded
            if not nodes and not missing_ok:
                raise KeyError(f"path seg '{seg}' not found/empty after '**'")
            continue

        # 3) 常规/带 [*] 段
        nxt = []
        for n in nodes:
            nxt.extend(_iter_children(n, seg))
        nodes = nxt

        if not nodes and not missing_ok:
            raise KeyError(f"path seg '{seg}' not found/empty")

    # 扁平化
    flat = []
    for x in nodes:
        flat.extend(_as_iter(x))
    return flat


# -------- 资源状态机：可按需扩展 --------
class State(Enum):
    ALLOCATED = auto()  # 一般对象刚创建
    RESET = auto()  # QP 创建后初始状态
    INIT = auto()
    RTR = auto()
    RTS = auto()
    DESTROYED = auto()
    IMPORTED = auto()
    USED = auto()  # for local resources only


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
    exclude_states: Optional[List[State]] = None  # 排除的状态列表（可选）


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

        for i in range(100):
            self.put("buf", f"bufs[{i}]", State.ALLOCATED)

        for i in range(100):
            self.put("remote_qp", f"srv{i}", State.ALLOCATED)

    # ===== 基本操作 =====
    def put(self, rtype: str, name: str, state: State):
        key = ResourceKey(rtype, str(name))
        rec = self._store.get(key)
        if rec and rec.state is not State.DESTROYED:
            # 同名未销毁就重复创建 -> 抛错
            raise ContractError(f"resource already exists: {rtype} {name} in state {rec.state.name}")
        self._store[key] = ResourceRec(key, state)

    def require(
        self, rtype: str, name: str, state: Optional[State] = None, exclude_states: Optional[List[State]] = None
    ):
        key = ResourceKey(rtype, str(name))
        rec = self._store.get(key)
        if not rec:
            raise ContractError(f"required resource not found: {rtype} {name}")
        if state is not None and rec.state is not state:
            raise ContractError(f"resource {rtype} {name} in state {rec.state.name}, required {state.name}")
        if exclude_states is not None and rec.state in exclude_states:
            exclude_state_names = [s.name for s in exclude_states]
            raise ContractError(
                f"resource {rtype} {name} in state {rec.state.name}, excluded states {exclude_state_names}"
            )

    def transition(self, rtype: str, name: str, to_state: State, from_state: Optional[State] = None):
        key = ResourceKey(rtype, str(name))
        rec = self._store.get(key)
        if not rec:
            raise ContractError(f"transition target not found: {rtype} {name}")
        if from_state is not None and rec.state is not from_state and rec.state is not to_state:
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

    def check(self, rtype: str, name: str) -> bool:
        key = ResourceKey(rtype, str(name))
        rec = self._store.get(key)
        if rec and rec.state is not State.DESTROYED:
            return False
        return True

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
        # 1) requires
        for spec in contract.requires:
            try:
                val = _get_by_path(verb, spec.name_attr, missing_ok=True)
            except Exception as e:
                raise ContractError(f"require: cannot resolve '{spec.name_attr}' on {type(verb).__name__}: {e}")
            for name in _as_iter(val):
                self.require(spec.rtype, str(name), spec.state, spec.exclude_states)

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
        return {(k.rtype, k.name): v.state for k, v in self._store.items()}

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
