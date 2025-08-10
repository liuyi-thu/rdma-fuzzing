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


class IbvTdInitAttr(Attr):
    FIELD_LIST = ["comp_mask"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(self, comp_mask=None):
        self.comp_mask = OptionalValue(
            IntValue(comp_mask) if comp_mask is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0

    @classmethod
    def random_mutation(cls):
        return cls(comp_mask=random.choice([0, 1, 0xFFFFFFFF]))

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_td_init_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        if self.comp_mask:
            s += emit_assign(varname, "comp_mask", self.comp_mask)
        return s


if __name__ == "__main__":
    # For debugging purposes, you can run this file directly
    attr = IbvTdInitAttr.random_mutation()
    print(attr.to_cxx("td_init_attr", CodeGenContext()))
    # This will generate a random IbvTdInitAttr and print its C++ representation
    for i in range(1000):
        attr = IbvTdInitAttr.random_mutation()
        print(attr.to_cxx(f"td_init_attr_{i}", CodeGenContext()))
        print("\n")
