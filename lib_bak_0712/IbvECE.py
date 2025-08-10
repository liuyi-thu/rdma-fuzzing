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
    
class IbvECE(Attr):
    FIELD_LIST = ["vendor_id", "options", "comp_mask"]

    def __init__(self, vendor_id=None, options=None, comp_mask=None):
        self.vendor_id = vendor_id
        self.options = options
        self.comp_mask = comp_mask

    @classmethod
    def random_mutation(cls):
        return cls(
            vendor_id=random.randint(0, 0xffff),
            options=random.randint(0, 0xffffffff),
            comp_mask=random.choice([0, 1])
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_ece")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is not None:
                s += emit_assign(varname, f, v)
        return s
