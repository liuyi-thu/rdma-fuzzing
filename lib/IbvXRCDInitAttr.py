import random
try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging


class IbvXRCDInitAttr:
    FIELD_LIST = ["comp_mask", "fd", "oflags"]

    def __init__(self, comp_mask=None, fd=None, oflags=None):
        self.comp_mask = comp_mask
        self.fd = fd
        self.oflags = oflags

    @classmethod
    def random_mutation(cls):
        return cls(
            comp_mask=random.choice([0, 1]),
            fd=random.choice([-1, 0, 3, 10, 100]),  # -1: let library open, or specify fd
            oflags=random.choice([0, 2, 1024, 2048])  # open(2) flags or special XRC flags
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_xrcd_init_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is not None:
                s += emit_assign(varname, f, v)
        return s
