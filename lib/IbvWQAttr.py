import random

try:
    from .attr import Attr
except ImportError:
    from attr import Attr

try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging

try:
    from .value import ConstantValue, EnumValue, FlagValue, IntValue, OptionalValue, ResourceValue
except ImportError:
    from value import ConstantValue, EnumValue, FlagValue, IntValue, OptionalValue, ResourceValue


IBV_WQ_STATE_ENUM = {0: "IBV_WQS_RESET", 1: "IBV_WQS_RDY", 2: "IBV_WQS_ERR", 3: "IBV_WQS_UNKNOWN"}

# 可选：也可为 attr_mask/flags/flags_mask 预设常用宏名
# 这里直接使用 int，trace/replay 可进一步增强


class IbvWQAttr(Attr):
    FIELD_LIST = ["attr_mask", "wq_state", "curr_wq_state", "flags", "flags_mask"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(self, attr_mask=None, wq_state=None, curr_wq_state=None, flags=None, flags_mask=None):
        self.attr_mask = OptionalValue(
            FlagValue(attr_mask, flag_type="IBV_WQ_ATTR_MASK_ENUM") if attr_mask is not None else None,
            factory=lambda: FlagValue(0, flag_type="IBV_WQ_ATTR_MASK_ENUM"),
        )  # 默认值为0
        self.wq_state = OptionalValue(
            EnumValue(wq_state, enum_type="IBV_WQ_STATE_ENUM") if wq_state is not None else None,
            factory=lambda: EnumValue(0, enum_type="IBV_WQ_STATE_ENUM"),
        )
        self.curr_wq_state = OptionalValue(
            EnumValue(curr_wq_state, enum_type="IBV_WQ_STATE_ENUM") if curr_wq_state is not None else None,
            factory=lambda: EnumValue(0, enum_type="IBV_WQ_STATE_ENUM"),
        )
        self.flags = OptionalValue(
            FlagValue(flags, flag_type="IBV_WQ_FLAGS_ENUM") if flags is not None else None,
            factory=lambda: FlagValue(0, flag_type="IBV_WQ_FLAGS_ENUM"),
        )  # 默认值为0
        self.flags_mask = OptionalValue(
            FlagValue(flags_mask, flag_type="IBV_WQ_FLAGS_ENUM") if flags_mask is not None else None,
            factory=lambda: FlagValue(0, flag_type="IBV_WQ_FLAGS_ENUM"),
        )  # 默认值为0

    @classmethod
    def random_mutation(cls):
        return cls(
            attr_mask=random.choice([1, 3, 7, 15]),
            wq_state=random.choice(list(IBV_WQ_STATE_ENUM.keys())),
            curr_wq_state=random.choice(list(IBV_WQ_STATE_ENUM.keys())),
            flags=random.choice([0, 1, 2, 4, 8, 15]),
            flags_mask=random.choice([0, 1, 3, 7, 15]),
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_wq_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        # enum_fields = {
        #     'wq_state': IBV_WQ_STATE_ENUM,
        #     'curr_wq_state': IBV_WQ_STATE_ENUM,
        # }
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v:
                # s += emit_assign(varname, f, v, enums=enum_fields)
                s += emit_assign(varname, f, v)
        return s


if __name__ == "__main__":
    # For debugging purposes, you can run this file directly
    attr = IbvWQAttr.random_mutation()
    print(attr.to_cxx("wq_attr", CodeGenContext()))
    # This will generate a random IbvWQAttr and print its C++ representation
    for i in range(1000):
        attr = IbvWQAttr.random_mutation()
        print(attr.to_cxx(f"wq_attr_{i}", CodeGenContext()))
        print("\n")
