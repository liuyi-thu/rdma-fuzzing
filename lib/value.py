import logging
import random
import re
from abc import ABC

try:
    from objtracker import ObjectTracker
except ImportError:
    from .objtracker import ObjectTracker

try:
    from contracts import ContractTable, RequireSpec, State
except ImportError:
    from .contracts import ContractTable, RequireSpec, State

# ===== 在文件开头加一个全局开关和工具函数 =====
DEBUG = True  # 改成 True 就能打开所有调试信息


def debug_print(*args, **kwargs):
    """只在 DEBUG=True 时输出"""
    # if DEBUG:
    #     print(*args, **kwargs)
    logging.debug(*args, **kwargs)


def _tokenize(path: str):
    # "wr_obj.**.sg_list[*].mr" -> ["wr_obj", "**", "sg_list[*]", "mr"]
    return path.split(".")


def _seg_matches(pat_seg: str, path_seg: str) -> bool:
    # 1) ** 在外层处理（不是单段匹配）
    if pat_seg == "**":
        return True  # 交给外层回溯
    # 2) sg_list[*] vs sg_list[0]
    m = re.fullmatch(r"([A-Za-z_]\w*)\[\*\]", pat_seg)
    if m:
        base = m.group(1)
        return bool(re.fullmatch(rf"{re.escape(base)}\[\d+\]", path_seg))
    # 3) 普通字段完全相等
    return pat_seg == path_seg


def _path_matches(pattern: str, path: str) -> bool:
    # 回溯匹配，** 可“吃掉”0~N段
    p = _tokenize(pattern)
    s = _tokenize(path)
    # logging.debug(f"Matching path '{path}' against pattern '{pattern}'")
    # logging.debug(f"Tokenized pattern: {p}")
    # logging.debug(f"Tokenized path: {s}")

    def dfs(i, j):
        if i == len(p) and j == len(s):
            return True
        if i == len(p):
            return False
        if p[i] == "**":
            # ** 可以匹配 0..N 段
            # 尝试不吃段
            if dfs(i + 1, j):
                return True
            # 吃掉一段，再继续
            if j < len(s) and dfs(i, j + 1):
                return True
            return False
        # 普通段
        logging.debug(f"Matching segment '{p[i]}' with '{s[j] if j < len(s) else 'END'}'")
        if j < len(s) and _seg_matches(p[i], s[j]):
            return dfs(i + 1, j + 1)
        return False

    return dfs(0, 0)


class Range:
    def __init__(self, min_value, max_value):
        self.min_value = min_value
        self.max_value = max_value
        assert min_value <= max_value, "Minimum value must be less than or equal to maximum value"

    def __str__(self):
        return f"Range({self.min_value}, {self.max_value})"

    def __repr__(self):
        return f"Range({self.min_value}, {self.max_value})"

    def contains(self, value):
        return self.min_value <= value <= self.max_value


class Value(ABC):
    def __init__(self, value, mutable: bool = True):
        self.value = value
        self.mutable = mutable  # Indicates if the value can be mutated

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return f"Value({self.value})"

    def __eq__(self, other):
        if isinstance(other, Value):
            return self.value == other.value
        return False

    def __hash__(self):
        return hash(self.value)

    # @abstractmethod
    def mutate(self, snap=None, contract=None, rng: random.Random = None, path: str = None, global_snap=None, *kwargs):
        raise NotImplementedError("Mutate method not implemented for Value class")

    def is_none(self):
        """Check if the value is None."""
        return self.value is None

    def is_not_none(self):
        """Check if the value is not None."""
        return self.value is not None

    def get_value(self):
        """Get the actual value, handling None."""
        return self.value if self.value is not None else None

    def set_value(self, value):
        """Set the value, replacing the current one."""
        self.value = value
        # debug_print(f"Value set to {self.value}")  # Uncomment for debugging purposes

    def __len__(self):
        """Get the length of the value if it's a list or string, otherwise return 1."""
        # if isinstance(self.value, (list, str)):
        #     return len(self.value)
        if self.is_none():
            return 0
        return 1

    def get_contract(self):
        return None  # value does not have a contract by default

    def instantiate_contract(self):
        return None

    def __add__(self, other):
        return self.value + other if self.value is not None else other

    def to_dict(self):
        raise NotImplementedError("to_dict method not implemented for Value class")


class IntValue(Value):
    def __init__(
        self,
        value: int | None = None,
        range: Range | list | None = None,
        step: int | None = None,
        rng: random.Random = None,
        mutable=True,
    ):
        super().__init__(value, mutable)
        self.range = Range(0, range) if isinstance(range, int) else range
        self.step = step
        # self.rng = rng or random

    def mutate(self, snap=None, contract=None, rng: random.Random = None, path: str = None, global_snap=None, *kwargs):
        # rng = rng or random
        if not self.mutable:
            debug_print("This IntValue is not mutable.")
            return
        if isinstance(self.range, Range):
            if self.step:  # 小步走，更利于“梯度式”探索
                delta = rng.choice([-self.step, self.step])
                v = (self.value or 0) + delta
                self.value = max(self.range.min_value, min(self.range.max_value, v))
            else:  # 整体重采样
                self.value = rng.randint(self.range.min_value, self.range.max_value)
        elif isinstance(self.range, list):  # 离散集合
            # 避免原地踏步
            candidates = [x for x in self.range if x != self.value] or self.range
            self.value = rng.choice(candidates)
        else:
            # 无约束：温和扰动
            v = (self.value or 0) + rng.choice([-1, 1])
            self.value = max(0, v)

    def to_dict(self):
        return {
            "type": "IntValue",
            "value": self.value,
            # "range": (self.range.min_value, self.range.max_value) if isinstance(self.range, Range) else self.range,
            # "step": self.step,
            # "mutable": self.mutable,
        }


class BoolValue(Value):
    def __init__(self, value: bool = None, mutable: bool = True):
        super().__init__(value, mutable)

    def mutate(self, snap=None, contract=None, rng: random.Random = None, path: str = None, global_snap=None, *kwargs):
        if not self.mutable:
            debug_print("This BoolValue is not mutable.")
            return
        # Example mutation: flip the boolean value
        self.value = not self.value
        debug_print(f"BoolValue mutated to {self.value}")

    def to_dict(self):
        return {
            "type": "BoolValue",
            "value": self.value,
            # "mutable": self.mutable,
        }


class ConstantValue(Value):
    def __init__(self, value: str = None):
        super().__init__(value)

    def mutate(self, snap=None, contract=None, rng: random.Random = None, path: str = None, global_snap=None, *kwargs):
        # Constants do not change, so this method does nothing
        debug_print("ConstantValue does not mutate.")
        pass

    def to_dict(self):
        return {
            "type": "ConstantValue",
            "value": self.value,
        }


class EnumValue(Value):
    # predefine some enum types for demonstration
    IB_UVERBS_ADVISE_MR_ADVICE_ENUM = {
        0: "IB_UVERBS_ADVISE_MR_ADVICE_PREFETCH",
        1: "IB_UVERBS_ADVISE_MR_ADVICE_PREFETCH_WRITE",
        2: "IB_UVERBS_ADVISE_MR_ADVICE_PREFETCH_NO_FAULT",
    }

    IBV_QP_STATE_ENUM = {
        0: "IBV_QPS_RESET",
        1: "IBV_QPS_INIT",
        2: "IBV_QPS_RTR",
        3: "IBV_QPS_RTS",
        4: "IBV_QPS_SQD",
        5: "IBV_QPS_SQE",
        6: "IBV_QPS_ERR",
        7: "IBV_QPS_UNKNOWN",
    }

    IBV_MIG_STATE_ENUM = {0: "IBV_MIG_MIGRATED", 1: "IBV_MIG_REARM", 2: "IBV_MIG_ARMED"}

    IBV_MTU_ENUM = {1: "IBV_MTU_256", 2: "IBV_MTU_512", 3: "IBV_MTU_1024", 4: "IBV_MTU_2048", 5: "IBV_MTU_4096"}

    IBV_FLOW_ATTR_TYPE_ENUM = {
        0: "IBV_FLOW_ATTR_NORMAL",
        1: "IBV_FLOW_ATTR_ALL_DEFAULT",
        2: "IBV_FLOW_ATTR_MC_DEFAULT",
        3: "IBV_FLOW_ATTR_SNIFFER",
    }

    IBV_QP_TYPE_ENUM = {
        2: "IBV_QPT_RC",
        3: "IBV_QPT_UC",
        4: "IBV_QPT_UD",
        8: "IBV_QPT_RAW_PACKET",
        9: "IBV_QPT_XRC_SEND",
        10: "IBV_QPT_XRC_RECV",
        255: "IBV_QPT_DRIVER",
    }

    IBV_WR_OPCODE_ENUM = {
        0: "IBV_WR_RDMA_WRITE",
        1: "IBV_WR_RDMA_WRITE_WITH_IMM",
        2: "IBV_WR_SEND",
        3: "IBV_WR_SEND_WITH_IMM",
        4: "IBV_WR_RDMA_READ",
        5: "IBV_WR_ATOMIC_CMP_AND_SWP",
        6: "IBV_WR_ATOMIC_FETCH_AND_ADD",
        7: "IBV_WR_LOCAL_INV",
        8: "IBV_WR_BIND_MW",
        9: "IBV_WR_SEND_WITH_INV",
        10: "IBV_WR_TSO",
        11: "IBV_WR_DRIVER1",
        14: "IBV_WR_FLUSH",
        15: "IBV_WR_ATOMIC_WRITE",
    }

    IBV_SRQ_TYPE_ENUM = {
        0: "IBV_SRQT_BASIC",
        1: "IBV_SRQT_XRC",
        2: "IBV_SRQT_TM",
    }

    IBV_WQ_TYPE_ENUM = {
        0: "IBV_WQT_RQ",  # Receive Queue
        1: "IBV_WQT_RQ_WITH_SRQ",  # Receive Queue with SRQ
        2: "IBV_WQT_SRQ",  # Shared Receive Queue
        # 若有更多类型可补充
    }

    IBV_WQ_STATE_ENUM = {0: "IBV_WQS_RESET", 1: "IBV_WQS_RDY", 2: "IBV_WQS_ERR", 3: "IBV_WQS_UNKNOWN"}

    IBV_MW_TYPE_ENUM = {
        # 0: 'IBV_MW_TYPE_1',
        # 1: 'IBV_MW_TYPE_2',
        # 2: 'IBV_MW_TYPE_3',
        # 3: 'IBV_MW_TYPE_4',
        1: "IBV_MW_TYPE_1",
        2: "IBV_MW_TYPE_2",
    }

    rdma_port_space = {
        0x0002: "RDMA_PS_IPOIB",
        0x0106: "RDMA_PS_TCP",
        0x0111: "RDMA_PS_UDP",
        0x013F: "RDMA_PS_IB",
    }

    def __init__(self, value: str = None, enum_type: str = None, mutable: bool = True):
        super().__init__(value, mutable)
        self.enum_type = enum_type
        self.enums = self._get_enum_values(enum_type)
        self.enums = list(self.enums)
        self.enum_dict = self._get_enum_dict(enum_type)
        if isinstance(value, str):
            self.value = value
        elif isinstance(value, int):
            # If value is an integer, convert it to the corresponding enum string
            if value in self.enum_dict:
                self.value = self.enum_dict[value]
            else:
                raise ValueError(f"Value {value} not found in enum {enum_type}")
        else:
            raise TypeError("Value must be a string or an integer representing the enum value")

    def _get_enum_values(self, enum_type: str) -> list[str]:
        # Placeholder for fetching enum values based on the enum type
        # In a real implementation, this would fetch from an actual enum definition
        # return ["ENUM_VALUE_1", "ENUM_VALUE_2", "ENUM_VALUE_3"]
        if isinstance(enum_type, dict):
            return enum_type.values()
        return getattr(self, enum_type, {}).values()

    def _get_enum_dict(self, enum_type: str) -> dict:
        """Get the enum dictionary based on the enum type."""
        if isinstance(enum_type, dict):
            return enum_type
        elif hasattr(self, enum_type):
            return getattr(self, enum_type)
        else:
            raise ValueError(f"Enum type {enum_type} not found in EnumValue class.")

    def mutate(self, snap=None, contract=None, rng: random.Random = None, path: str = None, global_snap=None, *kwargs):
        rng = rng or random
        if not self.mutable:
            debug_print("This EnumValue is not mutable.")
            return
        pool = list(self.enums)
        if self.value in pool and len(pool) > 1:
            pool.remove(self.value)
        # （可选）按“邻近枚举”权重优先；这里给个简单实现
        self.value = rng.choice(pool)

    def to_dict(self):
        return {
            "type": "EnumValue",
            "value": self.value,
            # "enum_type": self.enum_type,
            # "mutable": self.mutable,
        }


class FlagValue(Value):
    IBV_QP_ATTR_MASK_ENUM = {
        "IBV_QP_STATE": 1 << 0,
        "IBV_QP_CUR_STATE": 1 << 1,
        "IBV_QP_EN_SQD_ASYNC_NOTIFY": 1 << 2,
        "IBV_QP_ACCESS_FLAGS": 1 << 3,
        "IBV_QP_PKEY_INDEX": 1 << 4,
        "IBV_QP_PORT": 1 << 5,
        "IBV_QP_QKEY": 1 << 6,
        "IBV_QP_AV": 1 << 7,
        "IBV_QP_PATH_MTU": 1 << 8,
        "IBV_QP_TIMEOUT": 1 << 9,
        "IBV_QP_RETRY_CNT": 1 << 10,
        "IBV_QP_RNR_RETRY": 1 << 11,
        "IBV_QP_RQ_PSN": 1 << 12,
        "IBV_QP_MAX_QP_RD_ATOMIC": 1 << 13,
        "IBV_QP_ALT_PATH": 1 << 14,
        "IBV_QP_MIN_RNR_TIMER": 1 << 15,
        "IBV_QP_SQ_PSN": 1 << 16,
        "IBV_QP_MAX_DEST_RD_ATOMIC": 1 << 17,
        "IBV_QP_PATH_MIG_STATE": 1 << 18,
        "IBV_QP_CAP": 1 << 19,
        "IBV_QP_DEST_QPN": 1 << 20,
        "IBV_QP_RATE_LIMIT": 1 << 25,
    }

    IBV_SRQ_ATTR_MASK_ENUM = {
        "IBV_SRQ_MAX_WR": 1 << 0,
        "IBV_SRQ_LIMIT": 1 << 1,
    }

    IBV_ACCESS_FLAGS_ENUM = {
        "IBV_ACCESS_LOCAL_WRITE": 1 << 0,
        "IBV_ACCESS_REMOTE_WRITE": 1 << 1,
        "IBV_ACCESS_REMOTE_READ": 1 << 2,
        "IBV_ACCESS_REMOTE_ATOMIC": 1 << 3,
        "IBV_ACCESS_MW_BIND": 1 << 4,
        "IBV_ACCESS_ZERO_BASED": 1 << 5,
        "IBV_ACCESS_ON_DEMAND": 1 << 6,
        "IBV_ACCESS_HUGETLB": 1 << 7,
        "IBV_ACCESS_FLUSH_GLOBAL": 1 << 8,
        "IBV_ACCESS_FLUSH_PERSISTENT": 1 << 9,
        "IBV_ACCESS_RELAXED_ORDERING": 1 << 20,
    }

    IBV_REREG_MR_FLAGS_ENUM = {
        "IBV_REREG_MR_CHANGE_TRANSLATION": 1 << 0,
        "IBV_REREG_MR_CHANGE_PD": 1 << 1,
        "IBV_REREG_MR_CHANGE_ACCESS": 1 << 2,
        "IBV_REREG_MR_FLAGS_SUPPORTED": (1 << 3) - 1,
    }

    IBV_SEND_FLAGS_ENUM = {
        "IBV_SEND_FENCE": 1 << 0,
        "IBV_SEND_SIGNALED": 1 << 1,
        "IBV_SEND_SOLICITED": 1 << 2,
        "IBV_SEND_INLINE": 1 << 3,
        "IBV_SEND_IP_CSUM": 1 << 4,
        # "IBV_SEND_TSO":            1 << 5,
        # "IBV_SEND_LSO":            1 << 6,
        # "IBV_SEND_VLAN":           1 << 7,
        # "IBV_SEND_IP_CSUM_IPV6":   1 << 8,
    }

    IBV_WQ_ATTR_MASK_ENUM = {
        "IBV_WQ_ATTR_STATE": 1 << 0,
        "IBV_WQ_ATTR_CUR_STATE": 1 << 1,
        "IBV_WQ_ATTR_FLAGS": 1 << 2,
        "IBV_WQ_ATTR_RESERVED": 1 << 3,
    }

    IBV_WQ_FLAGS_ENUM = {
        "IBV_WQ_FLAGS_CVLAN_STRIPPING": 1 << 0,
        "IBV_WQ_FLAGS_SCATTER_FCS": 1 << 1,
        "IBV_WQ_FLAGS_DELAY_DROP": 1 << 2,
        "IBV_WQ_FLAGS_SCATTER_FCS_MASK": 1 << 3,
        "IBV_WQ_FLAGS_CVLAN_STRIPPING_MASK": 1 << 4,
    }

    IBV_QP_CREATE_SEND_OPS_FLAGS_ENUM = {
        "IBV_QP_EX_WITH_RDMA_WRITE": 1 << 0,
        "IBV_QP_EX_WITH_RDMA_WRITE_WITH_IMM": 1 << 1,
        "IBV_QP_EX_WITH_SEND": 1 << 2,
        "IBV_QP_EX_WITH_SEND_WITH_IMM": 1 << 3,
        "IBV_QP_EX_WITH_RDMA_READ": 1 << 4,
        "IBV_QP_EX_WITH_ATOMIC_CMP_AND_SWP": 1 << 5,
        "IBV_QP_EX_WITH_ATOMIC_FETCH_AND_ADD": 1 << 6,
        "IBV_QP_EX_WITH_LOCAL_INV": 1 << 7,
        "IBV_QP_EX_WITH_BIND_MW": 1 << 8,
        "IBV_QP_EX_WITH_SEND_WITH_INV": 1 << 9,
        "IBV_QP_EX_WITH_TSO": 1 << 10,
        "IBV_QP_EX_WITH_FLUSH": 1 << 11,
        "IBV_QP_EX_WITH_ATOMIC_WRITE": 1 << 12,
    }

    def __init__(self, value: int | None = None, flag_type=None, mutable=True):
        super().__init__(value, mutable)
        self.flag_type = flag_type
        self.flags = list(self._get_flag_values(flag_type))  # -> keys like "IBV_QP_STATE"
        self.map = getattr(self, flag_type) if isinstance(flag_type, str) else flag_type  # name->int

    def _get_flag_values(self, flag_type: str) -> list[str]:
        """Get the flag values based on the flag type."""
        if isinstance(flag_type, dict):
            return flag_type.keys()
        elif hasattr(self, flag_type):
            return getattr(self, flag_type).keys()
        else:
            raise ValueError(f"Flag type {flag_type} not found in FlagValue class.")

    def mutate(self, snap=None, contract=None, rng: random.Random = None, path: str = None, global_snap=None, *kwargs):
        rng = rng or random
        if not self.mutable:
            return
        k = rng.randint(1, max(1, len(self.flags)))
        picked = rng.sample(self.flags, k=k)
        mask = 0
        for name in picked:
            mask |= self.map[name]
        self.value = mask

    def to_c_expr(self) -> str:
        # 可选：把当前 mask 转回 "A | B" 便于代码生成
        if self.value is None:
            return "0"
        names = [n for n, v in self.map.items() if (self.value & v)]
        return " | ".join(names) if names else "0"

    def to_dict(self):
        return {
            "type": "FlagValue",
            "value": self.value,
            # "flag_type": self.flag_type,
            # "mutable": self.mutable,
        }


class ResourceValue(Value):
    def __init__(self, value: str = None, resource_type: str = None, mutable: bool = True):
        super().__init__(value, mutable)
        self.resource_type = resource_type
        if not resource_type:
            raise ValueError("ResourceValue must have a resource type defined.")

    def fill(self, snap=None, contract=None, rng: random.Random = None):  # TODO: to be checked
        if self.value is not None:
            return False
        required_type = self.resource_type
        required_state = None
        for item in contract.requires or []:
            if item.rtype == required_type:
                required_state = item.state
                break
        # print(required_state, required_type)
        cands = []
        for (t, name), (st, _) in (snap or {}).items():
            if t == required_type and (required_state is None or st == required_state):
                cands.append(name)
        if cands:
            rng = rng or random
            cands = [x for x in cands if x != self.value] or cands
            self.value = rng.choice(cands)
            return True
        return False

    def mutate(self, snap=None, contract=None, rng: random.Random = None, path: str = None, global_snap=None, *kwargs):
        if not self.mutable or not path or not contract:
            return

        # 1) 找到与当前 path 匹配的 require/produce 规格
        reqs = [spec for spec in (contract.requires or []) if _path_matches(spec.name_attr, path)]
        prods = [spec for spec in (contract.produces or []) if _path_matches(spec.name_attr, path)]
        logging.debug(f"Mutating ResourceValue at {path}")
        logging.debug(f"Found reqs: {reqs}, prods: {prods}")
        # 2) 产出位点（produces）通常不改名：直接返回
        if prods:
            return

        # 3) 按 require 规则挑候选
        if not reqs:
            return
        req = reqs[0]
        assert req.rtype == self.resource_type

        rng = rng or random
        cands = []
        for (t, name), (st, _) in (snap or {}).items():
            if t != req.rtype:
                continue
            if (req.state is None or st == req.state) and (st not in (req.exclude_states or [])):
                cands.append(name)

        if not cands:
            return
        # 尽量换个名字
        choices = [x for x in cands if x != self.value] or cands
        self.value = rng.choice(choices)

    def to_dict(self):
        return {
            "type": "ResourceValue",
            "value": self.value,
            # "resource_type": self.resource_type,
            # "mutable": self.mutable,
        }


class ListValue(Value):  # 能不能限定：列表的元素都一样；传入时知道元素类型，比如IbvSge
    MUTATION_CHOICES = [
        "add_item",  # Add a new item to the list
        "remove_item",  # Remove an existing item from the list
        "mutate_item",  # Mutate an existing item in the list
        "swap_items",  # Swap two items in the list
    ]

    def __init__(self, value: list[Value] = None, factory=None, mutable: bool = True, on_after_mutate=None):
        super().__init__(value, mutable)
        if value is None:
            self.value = []
        elif not isinstance(value, list):
            raise TypeError("Value must be a list of Value objects.")
        else:
            self.value = value

        if factory is None:
            raise ValueError("Factory must be provided to create new Value objects.")
        if factory is not None and not callable(factory):
            raise TypeError("Factory must be a callable that returns a Value object.")
        self.factory = factory
        self.on_after_mutate = on_after_mutate

    def _call_factory(self, snap=None, contract=None, rng=None):
        try:
            # 支持上下文工厂：(snap, contract, rng) -> Value
            return self.factory(snap, contract, rng)
        except TypeError:
            # 退化为无参工厂：() -> Value
            return self.factory()

    def mutate(self, snap=None, contract=None, rng: random.Random = None, path: str = None, global_snap=None, *kwargs):
        rng = rng or random
        if not self.mutable:
            debug_print("This ListValue is not mutable.")
            return
        # Choices: (1) add a new item, (2) remove an item, (3) mutate an existing item, (4) swap two items
        mutation_choice = rng.choice(self.MUTATION_CHOICES)

        # mutation_choice = "mutate_item"  # debugging only

        debug_print(f"Mutating ListValue with choice: {mutation_choice}")
        if mutation_choice == "add_item":
            # Add a new item to the list
            new_item = self._call_factory(snap, contract, rng)
            self.value.append(new_item)
            if callable(self.on_after_mutate):
                self.on_after_mutate(
                    kind="add_item",
                    lv=self,
                    idx=len(self.value) - 1,
                    item=new_item,
                    snap=snap,
                    contract=contract,
                    rng=rng,
                    path=path,
                )
            debug_print(f"Added new item: {new_item}")
        elif mutation_choice == "remove_item":
            # Remove an existing item from the list
            if self.value:
                k = rng.randrange(0, len(self.value))
                removed = self.value.pop(k)
                if callable(self.on_after_mutate):
                    self.on_after_mutate(
                        kind="remove_item",
                        lv=self,
                        idx=k,
                        item=removed,
                        snap=snap,
                        contract=contract,
                        rng=rng,
                        path=path,
                    )
                debug_print(f"Removed item: {removed}")
            else:
                debug_print("list is empty, cannot remove item.")
        elif mutation_choice == "mutate_item":
            # Mutate an existing item in the list
            if self.value:
                k = rng.randrange(0, len(self.value))
                itm = self.value[k]
                if hasattr(itm, "mutate"):
                    sub_path = f"{path}[{k}]" if path else f"[{k}]"
                    try:
                        itm.mutate(snap=snap, contract=contract, rng=rng, path=sub_path)
                    except TypeError:
                        itm.mutate(snap, contract, rng)
                    # itm.mutate(snap=snap, contract=contract, rng=rng, path=(path or "") + f".[{k}]")
                    debug_print(f"Mutated item: {itm}")
                    if callable(self.on_after_mutate):
                        self.on_after_mutate(
                            kind="mutate_item",
                            lv=self,
                            idx=k,
                            item=itm,
                            snap=snap,
                            contract=contract,
                            rng=rng,
                            path=path,
                        )
                else:
                    debug_print(f"Item {itm} cannot be mutated.")
            else:
                debug_print("list is empty, cannot mutate item.")
        elif mutation_choice == "swap_items":
            # Swap two items in the list
            if len(self.value) > 1:
                idx1, idx2 = rng.sample(range(len(self.value)), 2)
                self.value[idx1], self.value[idx2] = self.value[idx2], self.value[idx1]
                # if callable(self.on_after_mutate):
                #     self.on_after_mutate(kind="swap_items", lv=self, idx=i,
                #                         item=self.value[i], snap=snap, contract=contract, rng=rng, path=path)

                debug_print(f"Swapped items: {self.value[idx1]} and {self.value[idx2]}")
            else:
                debug_print("Not enough items to swap in the list.")
        # if callable(self.on_after_mutate):
        #     self.on_after_mutate(self)

    def __iter__(self):
        """Make ListValue iterable."""
        return iter(self.value)

    def __next__(self):
        """Get the next item in the list."""
        return next(iter(self.value))

    def __len__(self):
        """Get the length of the list."""
        return len(self.value)

    def to_dict(self):
        return {
            "type": "ListValue",
            "value": [item.to_dict() for item in self.value],
            # "mutable": self.mutable,
        }


class OptionalValue(Value):
    """
    Optional parameter wrapper for fuzzing RDMA verbs.
    - value: Value 类型或 None
    - factory: lambda/函数，每次调用能创建一个新的 Value（如 IntValue()）
    """

    def __init__(self, value: Value = None, factory=None, mutable: bool = True):
        super().__init__(value, mutable)
        self.value = value  # 类型: Value 或 None
        self.factory = factory  # 新建时用，比如 lambda: IntValue(...)

    def mutate(self, snap=None, contract=None, rng: random.Random = None, path: str = None, global_snap=None, *kwargs):
        if not self.mutable:
            debug_print("This OptionalValue is not mutable.")
            return
        # 1/3概率变成None，1/3递归变异，1/3换新
        rng = rng or random
        r = rng.random()
        # if hasattr(self.value, "mutate"):  # debugging only
        #     self.value.mutate(snap, contract, rng, path)
        # return

        if self.value is None:
            if self.factory:
                self.value = self.factory()  # TODO: factory should return a Value type（重新生成一份新的？）
                # self.value.mutate()  # 如果有 factory，生成一个新的 Values
                # fill with some initial value, especially resource values
                if isinstance(self.value, ResourceValue):
                    filled = self.value.fill(snap, contract, rng)
                    if not filled:
                        debug_print("OptionalValue: could not fill ResourceValue, setting to None")
                        self.value = None
                        return
                # self.value.mutate(snap, contract, rng)  # 如果有 factory，生成一个新的 Values
                debug_print(f"OptionalValue: created new value {self.value}")
        else:
            if r < 0.33:
                self.value = None
                debug_print("OptionalValue: set to None")
            elif r < 0.66:
                # 对内部 value 做变异
                if hasattr(self.value, "mutate"):
                    self.value.mutate(snap, contract, rng, path)
                    debug_print("OptionalValue: mutated internal value")
            else:
                # 重新生成一个新的 value
                if self.factory:
                    self.value = self.factory()
                    if isinstance(self.value, ResourceValue):
                        filled = self.value.fill(snap, contract, rng)
                        if not filled:
                            debug_print("OptionalValue: could not fill ResourceValue, setting to None")
                            self.value = None
                            return
                    # self.value.mutate(snap, contract, rng)  # 如果有 factory，生成一个新的 Values
                    debug_print(f"OptionalValue: replaced with new value {self.value}")

    # def __str__(self):
    #     return f"Optional[{self.value}]"
    def to_cxx(self, varname: str, ctx=None):
        if self.value is None:
            raise ValueError("OptionalValue is None, cannot convert to C++")
        else:
            return self.value.to_cxx(varname, ctx)

    def get_value(self):
        """Get the actual value, handling None."""
        return self.value.get_value() if self.value is not None else None

    def set_value(self, value):
        """Set the value, replacing the current one."""
        self.value.set_value(value)
        # debug_print(f"OptionalValue set to {self.value}")

    def __iter__(self):
        """Make OptionalValue iterable."""
        if isinstance(self.value, ListValue):
            return iter(self.value)
        else:
            raise TypeError("OptionalValue is not iterable unless it contains a ListValue")

    def __next__(self):
        """Get the next item in the OptionalValue."""
        if isinstance(self.value, ListValue):
            return next(iter(self.value))
        else:
            raise TypeError("OptionalValue is not iterable unless it contains a ListValue")

    def __len__(self):
        """Get the length of the OptionalValue."""
        if isinstance(self.value, ListValue):
            return len(self.value)
        else:
            return 1 if self.value is not None else 0

    def init(self):
        self.value = self.factory() if self.factory else None

    def __int__(self):
        """Convert OptionalValue to int, if possible."""
        if self.value is not None and isinstance(self.value, IntValue):
            return int(self.value.value)
        raise TypeError("Cannot convert OptionalValue to int, value is None or not an IntValue")

    def apply(self, ctx):
        """Apply the value to the context, if applicable."""
        if self.value is not None and hasattr(self.value, "apply"):
            self.value.apply(ctx)
        else:
            debug_print("OptionalValue has no value or cannot be applied.")

    # def __add__(self, other):
    #     """Add another OptionalValue or Value to this one."""
    #     # if isinstance(other, OptionalValue):
    #     #     return OptionalValue(self.value + other.value, self.factory, self.mutable)
    #     # elif isinstance(other, Value):
    #     #     return OptionalValue(self.value + other, self.factory, self.mutable)
    #     # else:
    #     #     raise TypeError("Can only add OptionalValue or Value to OptionalValue")
    #     pass

    def to_dict(self):
        # return {
        #     "type": "OptionalValue",
        #     "value": self.value.to_dict() if self.value is not None else None,
        #     # "mutable": self.mutable,
        # }
        return self.value.to_dict() if self.value is not None else {"type": "None", "value": None}


class DeferredValue(Value):
    __slots__ = ("key", "c_type", "source", "default", "by_id")

    def __init__(self, key: str, c_type: str = "uint32_t", source: str = "runtime", default=None, by_id=None):
        self.key, self.c_type, self.source, self.default, self.by_id = key, c_type, source, default, by_id

    @classmethod
    def from_id(cls, kind: str, id_str: str, field: str, c_type: str = "uint32_t"):
        return cls(key=f"{kind}|{id_str}|{field}", c_type=c_type, source="runtime_by_id", by_id=(kind, id_str, field))

    def mutate(self, snap=None, contract=None, rng: random.Random = None, path: str = None, global_snap=None, *kwargs):
        # DeferredValue 不变异
        return

    def to_cxx(self, varname: str, ctx=None, assign=False) -> str:
        if ctx:
            ctx.alloc_variable(varname, self.c_type)
        if assign and varname is None:
            raise ValueError("Variable name must be provided for assignment.")
        t = (self.c_type or "").replace(" ", "").lower()
        if self.source == "runtime_by_id" and self.by_id:
            kind, id_str, field = self.by_id
            getter = "rr_u32_by_id"
            if t in ("uint64_t", "u64", "unsignedlonglong"):
                getter = "rr_u64_by_id"
            elif t in ("constchar*", "char*", "constchar *", "char *"):
                getter = "rr_str_by_id"
            if assign:
                return f'    {varname} = {getter}("{kind}", "{id_str}", "{field}");\n'
            else:
                return f'{getter}("{kind}", "{id_str}", "{field}")'
        getter = "rr_u32"
        if t in ("uint64_t", "u64", "unsignedlonglong"):
            getter = "rr_u64"
        elif t in ("constchar*", "char*", "constchar *", "char *"):
            getter = "rr_str"
        if assign:
            return f'    {varname} = {getter}("{self.key}");\n'
        else:
            return f'{getter}("{self.key}")'

    def __str__(self):
        return self.to_cxx(varname=None, assign=False)

    def is_none(self) -> bool:
        return False

    def to_dict(self):
        return {
            "type": "DeferredValue",
            "value": "UNAVAILABLE",
            # "key": self.key,
            # "c_type": self.c_type,
            # "source": self.source,
            # "default": self.default,
            # "by_id": self.by_id,
        }


class LocalResourceValue(Value):  # buf
    def __init__(self, value: str = None, resource_type: str = None, mutable: bool = True):
        super().__init__(value, mutable)
        self.resource_type = resource_type
        if not resource_type:
            raise ValueError("LocalResourceValue must have a resource type defined.")

    def mutate(self, snap=None, contract=None, rng: random.Random = None, path: str = None, global_snap=None, *kwargs):
        if not self.mutable:
            return

        cands = []

        for (t, name), (st, metadata) in (global_snap or {}).items():  # should filter by resource_type
            if t == self.resource_type and name != self.value and st != State.USED:
                cands.append(name)

        if not cands:
            return
        logging.debug(f"Mutating LocalResourceValue: {self.value} -> {cands}")
        rng = rng or random
        self.value = rng.choice(cands)
        # do not need contract, for simplicity
    
    def to_dict(self):
        return {
            "type": "LocalResourceValue",
            "value": self.value,
            # "resource_type": self.resource_type,
            # "mutable": self.mutable,
        }


# --- 帮助函数：识别/解包延迟值（供 emit_assign / contracts 使用） ---
def is_deferred(x) -> bool:
    return isinstance(x, DeferredValue)


def unwrap_runtime(x):
    # OptionalValue(inner=DeferredValue) 的场景下使用
    return x.value if hasattr(x, "value") and isinstance(x.value, DeferredValue) else x
