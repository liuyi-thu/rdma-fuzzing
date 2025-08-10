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

class IbvSge(Attr):
    FIELD_LIST = ["addr", "length", "lkey"]
    def __init__(self, addr=None, length=None, lkey=None):
        self.addr = addr
        self.length = length
        self.lkey = lkey

    @classmethod
    def random_mutation(cls):
        return cls(
            addr=random.randint(0, 2**48),
            length=random.choice([0, 1, 1024, 4096]),
            lkey=random.randint(0, 0xffffffff)
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_sge")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if val is not None:
                s += emit_assign(varname, field, val)
        return s