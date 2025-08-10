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

class IbvQPCap(Attr):
    FIELD_LIST = ["max_send_wr", "max_recv_wr", "max_send_sge", "max_recv_sge", "max_inline_data"]
    def __init__(self, max_send_wr=None, max_recv_wr=None, max_send_sge=None, max_recv_sge=None, max_inline_data=None):
        self.max_send_wr = max_send_wr
        self.max_recv_wr = max_recv_wr
        self.max_send_sge = max_send_sge
        self.max_recv_sge = max_recv_sge
        self.max_inline_data = max_inline_data

    @classmethod
    def random_mutation(cls):
        return cls(
            max_send_wr=random.choice([0, 1, 16, 1024, 2**16]),
            max_recv_wr=random.choice([0, 1, 16, 1024, 2**16]),
            max_send_sge=random.choice([0, 1, 2, 16]),
            max_recv_sge=random.choice([0, 1, 2, 16]),
            max_inline_data=random.choice([0, 1, 64, 256, 4096]),
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_qp_cap")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if val is not None:
                s += emit_assign(varname, field, val)
        return s