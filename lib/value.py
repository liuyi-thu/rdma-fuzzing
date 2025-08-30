import random
from abc import ABC, abstractmethod

try:
    from objtracker import ObjectTracker
except ImportError:
    from .objtracker import ObjectTracker


# ===== 在文件开头加一个全局开关和工具函数 =====
DEBUG = True  # 改成 True 就能打开所有调试信息


def debug_print(*args, **kwargs):
    """只在 DEBUG=True 时输出"""
    if DEBUG:
        print(*args, **kwargs)


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
    def mutate(self, snap=None, contract=None, rng: random.Random = None):
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

    def mutate(self, snap=None, contract=None, rng: random.Random = None):
        rng = rng or random
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


# class IntValue(Value):
#     def __init__(self, value: int = None, range: Range = None, mutable: bool = True):
#         super().__init__(value, mutable)
#         self.range = range  # should be a default Range object or None
#         if isinstance(self.range, int):
#             self.range = Range(0, self.range)

#     def mutate(self):
#         if not self.mutable:
#             debug_print("This IntValue is not mutable.")
#             return
#         # Example mutation: increment or decrement the value
#         if isinstance(self.range, Range):
#             # Ensure the mutation stays within the specified range
#             min_val, max_val = self.range.min_value, self.range.max_value
#             # mutation = random.choice([-1, 1])
#             # self.value = max(min_val, min(max_val, self.value + mutation))
#             self.value = random.randint(min_val, max_val)
#         elif isinstance(self.range, list):
#             # If range is a list, randomly select a value from the list
#             self.value = random.choice(self.range)
#         if self.range is None:
#             # If no range is specified, just increment or decrement
#             # mutation = random.choice([-1, 1])
#             # self.value += mutation
#             self.value = random.randint(0, 100)  # Example: random value between 0 and 100
#             debug_print(f"IntValue mutated to {self.value} within range {self.range}")


class BoolValue(Value):
    def __init__(self, value: bool = None, mutable: bool = True):
        super().__init__(value, mutable)

    def mutate(self, snap=None, contract=None, rng: random.Random = None):
        if not self.mutable:
            debug_print("This BoolValue is not mutable.")
            return
        # Example mutation: flip the boolean value
        self.value = not self.value
        debug_print(f"BoolValue mutated to {self.value}")


class ConstantValue(Value):
    def __init__(self, value: str = None):
        super().__init__(value)

    def mutate(self, snap=None, contract=None, rng: random.Random = None):
        # Constants do not change, so this method does nothing
        debug_print("ConstantValue does not mutate.")
        pass


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

    # def mutate(self):
    #     if not self.mutable:
    #         debug_print("This EnumValue is not mutable.")
    #         return
    #     # Example mutation: change to another value in the enum type
    #     # This is a placeholder; actual implementation would depend on the enum type
    #     debug_print(f"Mutating EnumValue of type {self.enum_type} with value {self.value}")
    #     debug_print(f"Available enums: {self.enums}")
    #     self.value = random.choice(self.enums)
    #     pass  # Implement actual mutation logic based on enum type
    def mutate(self, snap=None, contract=None, rng: random.Random = None):
        rng = rng or random
        if not self.mutable:
            debug_print("This EnumValue is not mutable.")
            return
        pool = list(self.enums)
        if self.value in pool and len(pool) > 1:
            pool.remove(self.value)
        # （可选）按“邻近枚举”权重优先；这里给个简单实现
        self.value = rng.choice(pool)


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

    def mutate(self, snap=None, contract=None, rng: random.Random = None):
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

    # def __init__(self, value: str = None, flag_type=None, mutable: bool = True):
    #     super().__init__(value, mutable)
    #     self.flag_type = flag_type
    #     self.flags = self._get_flag_values(flag_type)
    #     self.flags = list(self.flags)

    # def _get_flag_values(self, flag_type: list) -> list[str]:
    #     # Placeholder for fetching flag values based on the flag type
    #     # In a real implementation, this would fetch from an actual flag definition
    #     if isinstance(flag_type, dict):
    #         return flag_type.keys()
    #     elif isinstance(flag_type, str):
    #         # If flag_type is a string, assume it's a predefined enum type
    #         return getattr(self, flag_type, {}).keys()
    #     return flag_type

    # def mutate(self):  # 随机选一个或者多个，然后combine
    #     if not self.mutable:
    #         debug_print("This FlagValue is not mutable.")
    #         return
    #     debug_print(f"Mutating FlagValue of type {self.flag_type} with value {self.value}")
    #     debug_print(f"Available flags: {self.flags}")
    #     # Randomly select one or more flags and combine them
    #     selected_flags = random.sample(self.flags, k=random.randint(1, len(self.flags)))
    #     self.value = " | ".join(selected_flags)
    #     debug_print(f"New value after mutation: {self.value}")


class ResourceValue(Value):
    def __init__(self, value: str = None, resource_type: str = None, mutable: bool = True):
        super().__init__(value, mutable)
        self.resource_type = resource_type
        if not resource_type:
            raise ValueError("ResourceValue must have a resource type defined.")

    # def mutate(self, tracker: ObjectTracker = None):
    #     if not self.mutable:
    #         debug_print("This ResourceValue is not mutable.")
    #         return
    #     # # Resource values may not change, so this method does nothing
    #     # debug_print("ResourceValue does not mutate.")
    #     if tracker:
    #         # Example mutation: randomly select a resource from the tracker
    #         # resources = tracker.all_objs(self.resource_type)
    #         # if resources:
    #         #     self.value = random.choice(resources)
    #         # else:
    #         #     debug_print(f"No resources of type {self.resource_type} available for mutation.")
    #         self.value = tracker.random_choose(self.resource_type, exclude=self.value)
    #         if self.value is None:
    #             debug_print(f"No resources of type {self.resource_type} available for mutation.")
    #     else:
    #         debug_print("No ObjectTracker provided, cannot mutate ResourceValue.")
    #     pass

    # def mutate(
    #     self, tracker: ObjectTracker = None, contracts=None, want_type: str | None = None, allow_destroyed=False
    # ):
    #     if not self.mutable:
    #         debug_print("This ResourceValue is not mutable.")
    #         return
    #     if contracts is not None and hasattr(contracts, "snapshot"):
    #         typ = want_type or self.resource_type
    #         snap = contracts.snapshot()
    #         cands = [name for (t, name), st in snap.items() if t == typ and (allow_destroyed or st != "DESTROYED")]
    #         if cands:
    #             self.value = random.choice([x for x in cands if x != self.value] or cands)
    #             return
    #     if tracker:
    #         self.value = tracker.random_choose(self.resource_type, exclude=self.value)
    def fill(self, snap=None, contract=None, rng: random.Random = None):
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
        for (t, name), st in (snap or {}).items():
            if t == required_type and (required_state is None or st == required_state):
                cands.append(name)
        if cands:
            rng = rng or random
            cands = [x for x in cands if x != self.value] or cands
            self.value = rng.choice(cands)
            return True
        return False

    def mutate(self, snap=None, contract=None, rng: random.Random = None):
        # TODO: 这里的实现其实是错误的，但是先这样凑合着用
        if not self.mutable:
            debug_print("This ResourceValue is not mutable.")
            return
        required_type = self.resource_type
        required_state = None
        for item in contract.requires or []:
            if item.rtype == required_type:
                required_state = item.state
                break
        # print(required_state, required_type)
        cands = []
        for (t, name), st in (snap or {}).items():
            if t == required_type and (required_state is None or st == required_state):
                cands.append(name)
        if cands:
            rng = rng or random
            cands = [x for x in cands if x != self.value] or cands
            self.value = rng.choice(cands)
            return
        # if snap is not None and hasattr(snap, "snapshot"):
        #     typ = self.resource_type
        #     snap_dict = snap.snapshot()
        #     cands = [name for (t, name), st in snap_dict.items() if t == typ and st != "DESTROYED"]
        #     if cands:
        #         rng = rng or random
        #         self.value = rng.choice([x for x in cands if x != self.value] or cands)
        #         return
        pass


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
        self.factory = factory  # Factory function to create new Value objects

        self.on_after_mutate = on_after_mutate

    def mutate(self, snap=None, contract=None, rng: random.Random = None):
        rng = rng or random
        if not self.mutable:
            debug_print("This ListValue is not mutable.")
            return
        # Choices: (1) add a new item, (2) remove an item, (3) mutate an existing item, (4) swap two items
        mutation_choice = rng.choice(self.MUTATION_CHOICES)
        debug_print(f"Mutating ListValue with choice: {mutation_choice}")
        if mutation_choice == "add_item":
            # Add a new item to the list
            new_item = self.factory()
            self.value.append(new_item)
            debug_print(f"Added new item: {new_item}")
        elif mutation_choice == "remove_item":
            # Remove an existing item from the list
            if self.value:
                removed_item = rng.choice(self.value)
                self.value.remove(removed_item)
                debug_print(f"Removed item: {removed_item}")
            else:
                debug_print("list is empty, cannot remove item.")
        elif mutation_choice == "mutate_item":
            # Mutate an existing item in the list
            if self.value:
                item_to_mutate = rng.choice(self.value)
                if hasattr(item_to_mutate, "mutate"):
                    item_to_mutate.mutate(snap, contract, rng)
                    debug_print(f"Mutated item: {item_to_mutate}")
                else:
                    debug_print(f"Item {item_to_mutate} cannot be mutated.")
            else:
                debug_print("list is empty, cannot mutate item.")
        elif mutation_choice == "swap_items":
            # Swap two items in the list
            if len(self.value) > 1:
                idx1, idx2 = rng.sample(range(len(self.value)), 2)
                self.value[idx1], self.value[idx2] = self.value[idx2], self.value[idx1]
                debug_print(f"Swapped items: {self.value[idx1]} and {self.value[idx2]}")
            else:
                debug_print("Not enough items to swap in the list.")
        if callable(self.on_after_mutate):
            self.on_after_mutate(self)

    def __iter__(self):
        """Make ListValue iterable."""
        return iter(self.value)

    def __next__(self):
        """Get the next item in the list."""
        return next(iter(self.value))

    def __len__(self):
        """Get the length of the list."""
        return len(self.value)


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

    def mutate(self, snap=None, contract=None, rng: random.Random = None):
        if not self.mutable:
            debug_print("This OptionalValue is not mutable.")
            return
        # 1/3概率变成None，1/3递归变异，1/3换新
        rng = rng or random
        r = rng.random()
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
                    self.value.mutate(snap, contract, rng)
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


# value.py

import re


class DeferredValue(Value):
    __slots__ = ("key", "c_type", "source", "default", "by_id")

    def __init__(self, key: str, c_type: str = "uint32_t", source: str = "runtime", default=None, by_id=None):
        self.key, self.c_type, self.source, self.default, self.by_id = key, c_type, source, default, by_id

    @classmethod
    def from_id(cls, kind: str, id_str: str, field: str, c_type: str = "uint32_t"):
        return cls(key=f"{kind}|{id_str}|{field}", c_type=c_type, source="runtime_by_id", by_id=(kind, id_str, field))

    def mutate(self, snap=None, contract=None, rng: random.Random = None):
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


# class DeferredValue:
#     """
#     表示“运行时（exec 时）才从外部解析器拿到”的值。
#     - key:    逻辑键，如 "remote.QP[0].qpn" / "local.MR[0].lkey"
#     - c_type: 目标C类型，"uint32_t" | "uint64_t" | "const char *" 等
#     - source: 解析方式，当前固定用 runtime_resolver: rr_u32/rr_u64/rr_str
#     - default: 兜底值（解析失败时的默认；一般不用）
#     """

#     __slots__ = ("key", "c_type", "source", "default")

#     def __init__(self, key: str, c_type: str = "uint32_t", source: str = "runtime", default=None):
#         self.key = key
#         self.c_type = c_type
#         self.source = source
#         self.default = default

#     # === 供 orchestrator/mutator 使用的统一接口 ===
#     def is_none(self) -> bool:
#         # 对外表现为“有值”（只是延迟取），避免 OptionalValue 把它当空
#         return False

#     def get_value(self):
#         # 返回自身即可；mutator 不应直接取字面量
#         return self

#     def mutate(self, *args, **kwargs) -> bool:
#         # 不对延迟值做随机变异；structure-level 的 on/off 由 OptionalValue 负责
#         return False

#     def __str__(self) -> str:
#         return f"Deferred({self.c_type}:{self.key})"

#     # === 代码生成：把自身展开为 C 端取值逻辑 ===
#     def to_cxx(self, varname: str, ctx=None) -> str:
#         """
#         生成：
#           <c_type> <varname>;
#           <varname> = rr_u32("remote.QP[0].qpn");  // 例如
#         并要求编译单元已包含 runtime_resolver.h
#         """
#         if ctx:
#             ctx.alloc_variable(varname, self.c_type)
#         getter = _rr_getter_for_ctype(self.c_type)
#         s = ""
#         if self.source == "runtime":
#             s += f'    {varname} = {getter}("{self.key}");\n'
#         else:
#             # 预留其它 source 的扩展点
#             s += f"    /* TODO: load {self.c_type} {varname} from {self.source}:{self.key} */\n"
#             if self.default is not None:
#                 s += f"    {varname} = ({self.c_type})({self.default});\n"
#             else:
#                 # 给个零值兜底，避免未初始化警告
#                 s += f"    {varname} = ({self.c_type})(0);\n"
#         return s


# def _rr_getter_for_ctype(c_type: str) -> str:
#     """将 C 类型映射到运行时解析器函数名。"""
#     t = c_type.strip().replace(" ", "").lower()
#     if t in ("uint32_t", "unsignedint", "u32", "uint32t"):
#         return "rr_u32"
#     if t in ("uint64_t", "unsignedlong", "unsignedlonglong", "u64", "uint64t"):
#         return "rr_u64"
#     if t in ("constchar*", "char*", "constchar *", "char *"):
#         return "rr_str"
#     # 默认为 u32，可按需扩展
#     return "rr_u32"


# --- 帮助函数：识别/解包延迟值（供 emit_assign / contracts 使用） ---
def is_deferred(x) -> bool:
    return isinstance(x, DeferredValue)


def unwrap_runtime(x):
    # OptionalValue(inner=DeferredValue) 的场景下使用
    return x.value if hasattr(x, "value") and isinstance(x.value, DeferredValue) else x


if __name__ == "__main__":
    # Example usage
    # int_value = IntValue(10, range=(0, 20))
    # debug_print(int_value)  # Output: 10
    # int_value.mutate()
    # debug_print(int_value)  # Output: 9 or 11 (or any value within the range)

    # str_value = Value("Hello")
    # print(str_value)  # Output: Hello
    # print(repr(str_value))  # Output: Value(Hello)

    # enum_value = EnumValue("IBV_QPT_RC", "IBV_QP_TYPE_ENUM")
    # print(enum_value)  # Output: IBV_QPT_RC
    # enum_value.mutate()
    # print(enum_value)  # Output: Randomly selected value from IBV_QP_TYPE

    # flag_value = FlagValue("IBV_QP_STATE", FlagValue.IBV_QP_ATTR_MASK_ENUM)
    # flag_value = FlagValue("IBV_QP_STATE", "IBV_QP_ATTR_MASK_ENUM")
    # # print(flag_value.IBV_QP_ATTR_MASK_ENUM)
    # print(flag_value)  # Output: IBV_QP_STATE
    # flag_value.mutate()

    # resource_value = ResourceValue(value = "xrcd_0", resource_type = "xrcd")

    # print()
    # print(f"{int_value} {str_value} {enum_value} {flag_value}")

    # opt_int = OptionalValue(
    #     None, factory=lambda: IntValue(random.randint(0, 100)))
    # for i in range(5):
    #     opt_int.mutate()
    #     print(opt_int)
    # list_value = ListValue(value=[IntValue(1), IntValue(2)], factory=lambda: IntValue(random.randint(0, 100)))
    # for i in range(5):
    #     list_value.mutate()
    #     print(list_value)

    # for i, item in enumerate(list_value):
    #     print(f"Item {i}: {item}")
    # print(len(list_value))  # Should print the length of the list

    # opt_int = OptionalValue(None, factory=lambda: IntValue(0))
    # opt_int.init()  # Initialize the OptionalValue
    # print(opt_int)
    # print(opt_int.value)
    defv = DeferredValue.from_id("remote.QP", "peer0", "qpn", "uint32_t")
    print(defv)
    print(defv.to_cxx("qpn"))
    # opt_defv = OptionalValue(None, factory=lambda: DeferredValue("local.MR[0].lkey", "uint32_t"))
    # opt_defv.init()
    # print(opt_defv)
    # print(opt_defv.value)
    # print(opt_defv.to_cxx("lkey"))
