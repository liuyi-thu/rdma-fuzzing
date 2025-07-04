import random
try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging

IBV_FLOW_ATTR_TYPE_ENUM = {
    0: 'IBV_FLOW_ATTR_NORMAL',
    1: 'IBV_FLOW_ATTR_ALL_DEFAULT',
    2: 'IBV_FLOW_ATTR_MC_DEFAULT',
    3: 'IBV_FLOW_ATTR_SNIFFER'
}

class IbvFlowAttr:
    FIELD_LIST = [
        "comp_mask", "type", "size", "priority",
        "num_of_specs", "port", "flags"
    ]
    def __init__(self, comp_mask=None, type=None, size=None, priority=None,
                 num_of_specs=None, port=None, flags=None):
        self.comp_mask = comp_mask
        self.type = type
        self.size = size
        self.priority = priority
        self.num_of_specs = num_of_specs
        self.port = port
        self.flags = flags

    @classmethod
    def random_mutation(cls):
        return cls(
            comp_mask=random.choice([0, 1]),
            type=random.choice(list(IBV_FLOW_ATTR_TYPE_ENUM.keys())),
            size=random.choice([40, 64, 128]),
            priority=random.randint(0, 10),
            num_of_specs=random.randint(1, 4),
            port=random.choice([1, 2]),
            flags=random.choice([0, 1, 0x1F])
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_flow_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        enum_fields = {"type": IBV_FLOW_ATTR_TYPE_ENUM}
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if val is not None:
                s += emit_assign(varname, field, val, enums=enum_fields)
        return s
