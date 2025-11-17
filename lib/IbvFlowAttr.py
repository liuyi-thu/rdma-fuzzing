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

IBV_FLOW_ATTR_TYPE_ENUM = {
    0: "IBV_FLOW_ATTR_NORMAL",
    1: "IBV_FLOW_ATTR_ALL_DEFAULT",
    2: "IBV_FLOW_ATTR_MC_DEFAULT",
    3: "IBV_FLOW_ATTR_SNIFFER",
}


class IbvFlowAttr(Attr):
    FIELD_LIST = ["comp_mask", "type", "size", "priority", "num_of_specs", "port", "flags"]
    MUTABLE_FIELDS = ["comp_mask", "type", "size", "priority", "num_of_specs", "port", "flags"]
    EXPORT_FIELDS = ["comp_mask", "type", "size", "priority", "num_of_specs", "port", "flags"]

    def __init__(self, comp_mask=None, type=None, size=None, priority=None, num_of_specs=None, port=None, flags=None):
        self.comp_mask = OptionalValue(
            IntValue(comp_mask) if comp_mask is not None else None, factory=lambda: IntValue(random.choice([0, 1]))
        )
        self.type = OptionalValue(
            EnumValue(type, enum_type="IBV_FLOW_ATTR_TYPE_ENUM") if type is not None else None,
            factory=lambda: EnumValue(
                random.choice(list(IBV_FLOW_ATTR_TYPE_ENUM.values())), enum_type="IBV_FLOW_ATTR_TYPE_ENUM"
            ),
        )
        self.size = OptionalValue(
            IntValue(size) if size is not None else None, factory=lambda: IntValue(random.choice([40, 64, 128]))
        )
        # 优先级，0-10
        self.priority = OptionalValue(
            IntValue(priority) if priority is not None else None, factory=lambda: IntValue(random.randint(0, 10))
        )
        self.num_of_specs = OptionalValue(
            IntValue(num_of_specs) if num_of_specs is not None else None, factory=lambda: IntValue(random.randint(1, 4))
        )
        self.port = OptionalValue(
            IntValue(port) if port is not None else None, factory=lambda: IntValue(random.choice([1, 2]))
        )
        self.flags = OptionalValue(
            IntValue(flags) if flags is not None else None, factory=lambda: IntValue(random.choice([0, 1, 0x1F]))
        )

    @classmethod
    def random_mutation(cls):
        return cls(
            comp_mask=random.choice([0, 1]),
            type=random.choice(list(IBV_FLOW_ATTR_TYPE_ENUM.values())),
            size=random.choice([40, 64, 128]),
            priority=random.randint(0, 10),
            num_of_specs=random.randint(1, 4),
            port=random.choice([1, 2]),
            flags=random.choice([0, 1, 0x1F]),
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_flow_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        enum_fields = {"type": IBV_FLOW_ATTR_TYPE_ENUM}
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if not val:
                continue
            else:
                s += emit_assign(varname, field, val)
        # for field in self.FIELD_LIST:
        #     val = getattr(self, field)
        #     if val is not None:
        #         # s += emit_assign(varname, field, val, enums=enum_fields)
        #         s += emit_assign(varname, field, val)
        return s


if __name__ == "__main__":
    attr = IbvFlowAttr.random_mutation()
    print(attr.to_cxx("flow_attr"))
    for i in range(10000):
        attr.mutate()
    print(attr.to_cxx("flow_attr"))
