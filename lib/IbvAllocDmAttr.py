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


class IbvAllocDmAttr(Attr):
    FIELD_LIST = ["length", "log_align_req", "comp_mask"]
    MUTABLE_FIELDS = ["length", "log_align_req", "comp_mask"]
    EXPORT_FIELDS = ["length", "log_align_req", "comp_mask"]

    def __init__(self, length=None, log_align_req=None, comp_mask=None):
        # self.length = length
        # self.log_align_req = log_align_req
        # self.comp_mask = comp_mask
        self.length = OptionalValue(
            IntValue(length) if length is not None else None,
            factory=lambda: IntValue(random.choice([4096, 65536, 1048576, 2**24])),
        )  # 否则会把None当成一个值。实际上IntValue(None)是没意义的，跟None没有区别
        self.log_align_req = OptionalValue(
            IntValue(log_align_req) if log_align_req is not None else None,
            factory=lambda: IntValue(random.choice([0, 12, 16])),
        )  # 2^12, 2^16 对齐
        self.comp_mask = OptionalValue(
            IntValue(comp_mask) if comp_mask is not None else None, factory=lambda: IntValue(random.choice([0, 1]))
        )

    @classmethod
    def random_mutation(cls):
        return cls(
            length=random.choice([4096, 65536, 1048576, 2**24]),
            log_align_req=random.choice([0, 12, 16]),  # 2^12, 2^16 对齐
            comp_mask=random.choice([0, 1]),
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_alloc_dm_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if not val:
                continue
            else:
                s += emit_assign(varname, field, val)
        return s


if __name__ == "__main__":
    attr = IbvAllocDmAttr.random_mutation()
    print(attr.to_cxx("dm_attr"))
    for i in range(10000):
        attr.mutate()
    print(attr.to_cxx("dm_attr"))
