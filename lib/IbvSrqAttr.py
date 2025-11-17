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


class IbvSrqAttr(Attr):
    FIELD_LIST = ["max_wr", "max_sge", "srq_limit"]
    MUTABLE_FIELDS = FIELD_LIST
    EXPORT_FIELDS = ["max_wr", "max_sge", "srq_limit"]

    def __init__(self, max_wr=None, max_sge=None, srq_limit=None):
        self.max_wr = OptionalValue(IntValue(max_wr) if max_wr is not None else None, factory=lambda: IntValue(0))
        self.max_sge = OptionalValue(IntValue(max_sge) if max_sge is not None else None, factory=lambda: IntValue(0))
        self.srq_limit = OptionalValue(
            IntValue(srq_limit) if srq_limit is not None else None, factory=lambda: IntValue(0)
        )

    @classmethod
    def random_mutation(cls):
        return cls(
            max_wr=random.choice([1, 8, 64, 256, 4096]),
            max_sge=random.choice([1, 2, 16, 128]),
            srq_limit=random.choice([0, 1, 8, 128]),
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_srq_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v:
                s += emit_assign(varname, f, v)
        return s


if __name__ == "__main__":
    # For debugging purposes, you can run this file directly to see the output
    srq_attr = IbvSrqAttr.random_mutation()
    print(srq_attr.to_cxx("srq_attr_instance", ctx=None))
    for i in range(1000):
        srq_attr.mutate()
        print(srq_attr.to_cxx(f"srq_attr_instance_{i}", ctx=None))
