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


class IbvECE(Attr):
    FIELD_LIST = ["vendor_id", "options", "comp_mask"]
    MUTABLE_FIELDS = ["vendor_id", "options", "comp_mask"]

    def __init__(self, vendor_id=None, options=None, comp_mask=None):
        self.vendor_id = OptionalValue(
            IntValue(vendor_id) if vendor_id is not None else None, factory=lambda: IntValue(random.randint(0, 0xFFFF))
        )
        self.options = OptionalValue(
            IntValue(options) if options is not None else None, factory=lambda: IntValue(random.randint(0, 0xFFFFFFFF))
        )
        self.comp_mask = OptionalValue(
            IntValue(comp_mask) if comp_mask is not None else None, factory=lambda: IntValue(random.choice([0, 1]))
        )

    @classmethod
    def random_mutation(cls):
        return cls(
            vendor_id=random.randint(0, 0xFFFF), options=random.randint(0, 0xFFFFFFFF), comp_mask=random.choice([0, 1])
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_ece")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if not val:
                continue
            else:
                s += emit_assign(varname, field, val)
        return s


if __name__ == "__main__":
    attr = IbvECE.random_mutation()
    print(attr.to_cxx("ece"))
    for i in range(10000):
        attr.mutate()
    print(attr.to_cxx("ece"))
