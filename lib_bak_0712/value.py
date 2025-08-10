import random
from typing import List
try:
    from objtracker import ObjectTracker
except ImportError:
    from .objtracker import ObjectTracker

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


class Value:
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

    def mutate(self):
        raise NotImplementedError(
            "Mutate method not implemented for Value class")
        
    def is_none(self):
        """Check if the value is None."""
        return self.value is None


class IntValue(Value):
    def __init__(self, value: int = None, range: Range = None, mutable: bool = True):
        super().__init__(value, mutable)
        self.range = range # should be a default Range object or None

    def mutate(self):
        if not self.mutable:
            print("This IntValue is not mutable.")
            return
        # Example mutation: increment or decrement the value
        if isinstance(self.range, Range):
            # Ensure the mutation stays within the specified range
            min_val, max_val = self.range.min_value, self.range.max_value
            # mutation = random.choice([-1, 1])
            # self.value = max(min_val, min(max_val, self.value + mutation))
            self.value = random.randint(min_val, max_val)
        elif isinstance(self.range, list):
            # If range is a list, randomly select a value from the list
            self.value = random.choice(self.range)


class ConstantValue(Value):
    def __init__(self, value: str = None):
        super().__init__(value)

    def mutate(self):
        # Constants do not change, so this method does nothing
        print("ConstantValue does not mutate.")
        pass


class EnumValue(Value):
    # predefine some enum types for demonstration
    IB_UVERBS_ADVISE_MR_ADVICE_ENUM = {
        0: "IB_UVERBS_ADVISE_MR_ADVICE_PREFETCH",
        1: "IB_UVERBS_ADVISE_MR_ADVICE_PREFETCH_WRITE",
        2: "IB_UVERBS_ADVISE_MR_ADVICE_PREFETCH_NO_FAULT",
    }

    IBV_QP_STATE_ENUM = {
        0: 'IBV_QPS_RESET',
        1: 'IBV_QPS_INIT',
        2: 'IBV_QPS_RTR',
        3: 'IBV_QPS_RTS',
        4: 'IBV_QPS_SQD',
        5: 'IBV_QPS_SQE',
        6: 'IBV_QPS_ERR',
        7: 'IBV_QPS_UNKNOWN'
    }

    IBV_MIG_STATE_ENUM = {
        0: 'IBV_MIG_MIGRATED',
        1: 'IBV_MIG_REARM',
        2: 'IBV_MIG_ARMED'
    }

    IBV_MTU_ENUM = {
        1: 'IBV_MTU_256',
        2: 'IBV_MTU_512',
        3: 'IBV_MTU_1024',
        4: 'IBV_MTU_2048',
        5: 'IBV_MTU_4096'
    }

    IBV_FLOW_ATTR_TYPE_ENUM = {
        0: 'IBV_FLOW_ATTR_NORMAL',
        1: 'IBV_FLOW_ATTR_ALL_DEFAULT',
        2: 'IBV_FLOW_ATTR_MC_DEFAULT',
        3: 'IBV_FLOW_ATTR_SNIFFER'
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
        0: 'IBV_WR_RDMA_WRITE',
        1: 'IBV_WR_RDMA_WRITE_WITH_IMM',
        2: 'IBV_WR_SEND',
        3: 'IBV_WR_SEND_WITH_IMM',
        4: 'IBV_WR_RDMA_READ',
        5: 'IBV_WR_ATOMIC_CMP_AND_SWP',
        6: 'IBV_WR_ATOMIC_FETCH_AND_ADD',
        7: 'IBV_WR_LOCAL_INV',
        8: 'IBV_WR_BIND_MW',
        9: 'IBV_WR_SEND_WITH_INV',
        10: 'IBV_WR_TSO',
        11: 'IBV_WR_DRIVER1',
        14: 'IBV_WR_FLUSH',
        15: 'IBV_WR_ATOMIC_WRITE'
    }

    IBV_SRQ_TYPE_ENUM = {
        0: 'IBV_SRQT_BASIC',
        1: 'IBV_SRQT_XRC',
        2: 'IBV_SRQT_TM',
    }

    IBV_WQ_TYPE_ENUM = {
        0: 'IBV_WQT_RQ',       # Receive Queue
        1: 'IBV_WQT_RQ_WITH_SRQ',  # Receive Queue with SRQ
        2: 'IBV_WQT_SRQ',      # Shared Receive Queue
        # 若有更多类型可补充
    }

    IBV_WQ_STATE_ENUM = {
        0: 'IBV_WQS_RESET',
        1: 'IBV_WQS_RDY',
        2: 'IBV_WQS_ERR',
        3: 'IBV_WQS_UNKNOWN'
    }

    IBV_MW_TYPE_ENUM = {
        # 0: 'IBV_MW_TYPE_1',
        # 1: 'IBV_MW_TYPE_2',
        # 2: 'IBV_MW_TYPE_3',
        # 3: 'IBV_MW_TYPE_4',
        1: 'IBV_MW_TYPE_1',
        2: 'IBV_MW_TYPE_2',
    }

    def __init__(self, value: str = None, enum_type: str = None, mutable: bool = True):
        super().__init__(value, mutable)
        self.enum_type = enum_type
        self.enums = self._get_enum_values(enum_type)
        self.enums = list(self.enums)

    def _get_enum_values(self, enum_type: str) -> List[str]:
        # Placeholder for fetching enum values based on the enum type
        # In a real implementation, this would fetch from an actual enum definition
        # return ["ENUM_VALUE_1", "ENUM_VALUE_2", "ENUM_VALUE_3"]
        if isinstance(enum_type, dict):
            return enum_type.values()
        return getattr(self, enum_type, {}).values()

    def mutate(self):
        if not self.mutable:
            print("This EnumValue is not mutable.")
            return
        # Example mutation: change to another value in the enum type
        # This is a placeholder; actual implementation would depend on the enum type
        print(
            f"Mutating EnumValue of type {self.enum_type} with value {self.value}")
        print(f"Available enums: {self.enums}")
        self.value = random.choice(self.enums)
        pass  # Implement actual mutation logic based on enum type


class FlagValue(Value):
    IBV_QP_ATTR_MASK_ENUM = {
        "IBV_QP_STATE":              1 << 0,
        "IBV_QP_CUR_STATE":          1 << 1,
        "IBV_QP_EN_SQD_ASYNC_NOTIFY": 1 << 2,
        "IBV_QP_ACCESS_FLAGS":       1 << 3,
        "IBV_QP_PKEY_INDEX":         1 << 4,
        "IBV_QP_PORT":               1 << 5,
        "IBV_QP_QKEY":               1 << 6,
        "IBV_QP_AV":                 1 << 7,
        "IBV_QP_PATH_MTU":           1 << 8,
        "IBV_QP_TIMEOUT":            1 << 9,
        "IBV_QP_RETRY_CNT":          1 << 10,
        "IBV_QP_RNR_RETRY":          1 << 11,
        "IBV_QP_RQ_PSN":             1 << 12,
        "IBV_QP_MAX_QP_RD_ATOMIC":   1 << 13,
        "IBV_QP_ALT_PATH":           1 << 14,
        "IBV_QP_MIN_RNR_TIMER":      1 << 15,
        "IBV_QP_SQ_PSN":             1 << 16,
        "IBV_QP_MAX_DEST_RD_ATOMIC": 1 << 17,
        "IBV_QP_PATH_MIG_STATE":     1 << 18,
        "IBV_QP_CAP":                1 << 19,
        "IBV_QP_DEST_QPN":           1 << 20,
        "IBV_QP_RATE_LIMIT":         1 << 25,
    }
    
    IBV_SRQ_ATTR_MASK_ENUM = {
        "IBV_SRQ_MAX_WR":              1 << 0,
        "IBV_SRQ_LIMIT":              1 << 1,
    }

    IBV_ACCESS_FLAGS_ENUM = {
        "IBV_ACCESS_LOCAL_WRITE":      1 << 0,
        "IBV_ACCESS_REMOTE_WRITE":     1 << 1,
        "IBV_ACCESS_REMOTE_READ":      1 << 2,
        "IBV_ACCESS_REMOTE_ATOMIC":    1 << 3,
        "IBV_ACCESS_MW_BIND":          1 << 4,
        "IBV_ACCESS_ZERO_BASED":       1 << 5,
        "IBV_ACCESS_ON_DEMAND":        1 << 6,
        "IBV_ACCESS_HUGETLB":          1 << 7,
        "IBV_ACCESS_FLUSH_GLOBAL":       1 << 8,
        "IBV_ACCESS_FLUSH_PERSISTENT": 1 << 9,
        "IBV_ACCESS_RELAXED_ORDERING": 1 << 20,
    }
    
    IBV_REREG_MR_FLAGS_ENUM = {
        "IBV_REREG_MR_CHANGE_TRANSLATION": 1 << 0,
        "IBV_REREG_MR_CHANGE_PD":           1 << 1,
        "IBV_REREG_MR_CHANGE_ACCESS":       1 << 2,
        "IBV_REREG_MR_FLAGS_SUPPORTED":        1 << 3 -1,
    }
        

    def __init__(self, value: str = None, flag_type = None, mutable: bool = True):
        super().__init__(value, mutable)
        self.flag_type = flag_type
        self.flags = self._get_flag_values(flag_type)
        self.flags = list(self.flags)

    def _get_flag_values(self, flag_type: list) -> List[str]:
        # Placeholder for fetching flag values based on the flag type
        # In a real implementation, this would fetch from an actual flag definition
        if isinstance(flag_type, dict):
            return flag_type.keys()
        elif isinstance(flag_type, str):
            # If flag_type is a string, assume it's a predefined enum type
            return getattr(self, flag_type, {}).keys()
        return flag_type
    
    def mutate(self): # 随机选一个或者多个，然后combine
        if not self.mutable:
            print("This FlagValue is not mutable.")
            return
        print(f"Mutating FlagValue of type {self.flag_type} with value {self.value}")
        print(f"Available flags: {self.flags}")
        # Randomly select one or more flags and combine them
        selected_flags = random.sample(self.flags, k=random.randint(1, len(self.flags)))
        self.value = ' | '.join(selected_flags)
        print(f"New value after mutation: {self.value}")

class ResourceValue(Value):
    def __init__(self, value: str = None, resource_type: str = None, mutable: bool = True):
        super().__init__(value, mutable)
        self.resource_type = resource_type
        if not resource_type:
            raise ValueError("ResourceValue must have a resource type defined.")

    def mutate(self, tracker: ObjectTracker = None):
        if not self.mutable:
            print("This ResourceValue is not mutable.")
            return
        # # Resource values may not change, so this method does nothing
        # print("ResourceValue does not mutate.")
        if tracker:
            # Example mutation: randomly select a resource from the tracker
            # resources = tracker.all_objs(self.resource_type)
            # if resources:
            #     self.value = random.choice(resources)
            # else:
            #     print(f"No resources of type {self.resource_type} available for mutation.")
            self.value = tracker.random_choose(self.resource_type, exclude=self.value)
            if self.value is None:
                print(f"No resources of type {self.resource_type} available for mutation.")
        else:
            print("No ObjectTracker provided, cannot mutate ResourceValue.")
        pass

class ListValue(Value): # 能不能限定：列表的元素都一样；传入时知道元素类型，比如IbvSge
    def __init__(self, value: List[Value] = None, mutable: bool = True):
        super().__init__(value, mutable)
        if value is None:
            self.value = []
        elif not isinstance(value, list):
            raise TypeError("Value must be a list of Value objects.")
        else:
            self.value = value

    def mutate(self):
        if not self.mutable:
            print("This ListValue is not mutable.")
            return
        # Example mutation: randomly add or remove an item from the list
        if random.choice([True, False]) and self.value:
            # Remove a random item
            removed_item = random.choice(self.value)
            self.value.remove(removed_item)
            print(f"Removed item: {removed_item}")
        else:
            # Add a new random Value object
            new_value = IntValue(random.randint(0, 100))  # Example of adding an IntValue
            self.value.append(new_value)
            print(f"Added new item: {new_value}")
    
if __name__ == "__main__":
    # Example usage
    int_value = IntValue(10, range=(0, 20))
    print(int_value)  # Output: 10
    int_value.mutate()
    print(int_value)  # Output: 9 or 11 (or any value within the range)

    str_value = Value("Hello")
    print(str_value)  # Output: Hello
    print(repr(str_value))  # Output: Value(Hello)

    enum_value = EnumValue("IBV_QPT_RC", "IBV_QP_TYPE_ENUM")
    print(enum_value)  # Output: IBV_QPT_RC
    enum_value.mutate()
    print(enum_value)  # Output: Randomly selected value from IBV_QP_TYPE

    flag_value = FlagValue("IBV_QP_STATE", FlagValue.IBV_QP_ATTR_MASK_ENUM)
    flag_value = FlagValue("IBV_QP_STATE", "IBV_QP_ATTR_MASK_ENUM")
    # print(flag_value.IBV_QP_ATTR_MASK_ENUM)
    print(flag_value)  # Output: IBV_QP_STATE
    flag_value.mutate()

    print()
    print(f"{int_value} {str_value} {enum_value} {flag_value}")