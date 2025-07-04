import random
try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging

class IbvSrqAttr:
    FIELD_LIST = ["max_wr", "max_sge", "srq_limit"]
    def __init__(self, max_wr=None, max_sge=None, srq_limit=None):
        self.max_wr = max_wr
        self.max_sge = max_sge
        self.srq_limit = srq_limit

    @classmethod
    def random_mutation(cls):
        return cls(
            max_wr=random.choice([1, 8, 64, 256, 4096]),
            max_sge=random.choice([1, 2, 16, 128]),
            srq_limit=random.choice([0, 1, 8, 128])
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_srq_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is not None:
                s += emit_assign(varname, f, v)
        return s
