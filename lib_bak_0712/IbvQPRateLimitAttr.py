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

class IbvQPRateLimitAttr(Attr):
    FIELD_LIST = ["rate_limit", "max_burst_sz", "typical_pkt_sz", "comp_mask"]
    def __init__(self, rate_limit=None, max_burst_sz=None, typical_pkt_sz=None, comp_mask=None):
        self.rate_limit = rate_limit
        self.max_burst_sz = max_burst_sz
        self.typical_pkt_sz = typical_pkt_sz
        self.comp_mask = comp_mask

    @classmethod
    def random_mutation(cls):
        return cls(
            rate_limit=random.choice([0, 1, 10, 100, 1000, 100000]),
            max_burst_sz=random.choice([0, 1, 32, 1024, 4096]),
            typical_pkt_sz=random.choice([0, 64, 512, 1500, 9000]),
            comp_mask=random.choice([0, 1])
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_qp_rate_limit_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is not None:
                s += emit_assign(varname, f, v)
        return s
    
if __name__ == "__main__":
    attr = IbvQPRateLimitAttr.random_mutation()
    print(attr.to_cxx("rate_limit_attr"))