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


class IbvXRCDInitAttr(Attr):
    FIELD_LIST = ["comp_mask", "fd", "oflags"]
    MUTABLE_FIELDS = FIELD_LIST
    EXPORT_FIELDS = ["comp_mask", "fd", "oflags"]

    def __init__(self, comp_mask=None, fd=None, oflags=None):
        self.comp_mask = OptionalValue(
            IntValue(comp_mask) if comp_mask is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.fd = OptionalValue(IntValue(fd) if fd is not None else None, factory=lambda: IntValue(-1))
        self.oflags = OptionalValue(
            IntValue(oflags) if oflags is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0

    @classmethod
    def random_mutation(cls):
        return cls(
            comp_mask=random.choice([0, 1]),
            fd=random.choice([-1, 0, 3, 10, 100]),  # -1: let library open, or specify fd
            oflags=random.choice([0, 2, 1024, 2048]),  # open(2) flags or special XRC flags
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_xrcd_init_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v:
                s += emit_assign(varname, f, v)
        return s
