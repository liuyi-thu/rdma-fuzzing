from .attr import Attr
import random
try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging

class IbvModerateCQ(Attr):
    FIELD_LIST = ["cq_count", "cq_period"]
    def __init__(self, cq_count=None, cq_period=None):
        self.cq_count = cq_count
        self.cq_period = cq_period

    @classmethod
    def random_mutation(cls):
        return cls(
            cq_count=random.choice([0, 1, 16, 1024]),
            cq_period=random.choice([0, 1, 8, 256])
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_moderate_cq")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is not None:
                s += emit_assign(varname, f, v)
        return s
