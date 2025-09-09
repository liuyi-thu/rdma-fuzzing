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


class IbvModerateCQ(Attr):
    FIELD_LIST = ["cq_count", "cq_period"]
    MUTABLE_FIELDS = ["cq_count", "cq_period"]

    def __init__(self, cq_count=None, cq_period=None):
        self.cq_count = OptionalValue(IntValue(cq_count) if cq_count is not None else None, factory=lambda: IntValue(0))
        self.cq_period = OptionalValue(
            IntValue(cq_period) if cq_period is not None else None, factory=lambda: IntValue(0)
        )

    @classmethod
    def random_mutation(cls):
        return cls(cq_count=random.choice([0, 1, 16, 1024]), cq_period=random.choice([0, 1, 8, 256]))

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_moderate_cq")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if not val:
                continue
            else:
                s += emit_assign(varname, field, val)
        return s


if __name__ == "__main__":
    attr = IbvModerateCQ.random_mutation()
    print(attr.cq_count, attr.cq_period)
    print(attr.to_cxx("moderate_cq"))
    for i in range(10000):
        attr.mutate()
    print(attr.to_cxx("moderate_cq_mutated"))
