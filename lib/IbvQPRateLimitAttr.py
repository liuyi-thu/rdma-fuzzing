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


class IbvQPRateLimitAttr(Attr):
    FIELD_LIST = ["rate_limit", "max_burst_sz", "typical_pkt_sz", "comp_mask"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(self, rate_limit=None, max_burst_sz=None, typical_pkt_sz=None, comp_mask=None):
        self.rate_limit = OptionalValue(
            IntValue(rate_limit) if rate_limit is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.max_burst_sz = OptionalValue(
            IntValue(max_burst_sz) if max_burst_sz is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.typical_pkt_sz = OptionalValue(
            IntValue(typical_pkt_sz) if typical_pkt_sz is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.comp_mask = OptionalValue(
            IntValue(comp_mask) if comp_mask is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0

    @classmethod
    def random_mutation(cls):
        return cls(
            rate_limit=random.choice([0, 1, 10, 100, 1000, 100000]),
            max_burst_sz=random.choice([0, 1, 32, 1024, 4096]),
            typical_pkt_sz=random.choice([0, 64, 512, 1500, 9000]),
            comp_mask=random.choice([0, 1]),
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_qp_rate_limit_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if not v:
                s += emit_assign(varname, f, v)
        return s


if __name__ == "__main__":
    # Example usage
    attr = IbvQPRateLimitAttr.random_mutation()
    print(attr.to_cxx("qp_rate_limit_attr", ctx=None))  # ctx is None for simplicity in this examples
    for i in range(10000):
        attr.mutate()
        print(attr.to_cxx(f"qp_rate_limit_attr_{i}", ctx=None))
    print("Done generating random mutations.")
