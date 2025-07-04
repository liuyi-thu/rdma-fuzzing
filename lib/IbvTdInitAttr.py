import random
try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging

class IbvTdInitAttr:
    FIELD_LIST = ["comp_mask"]
    def __init__(self, comp_mask=None):
        self.comp_mask = comp_mask

    @classmethod
    def random_mutation(cls):
        return cls(comp_mask=random.choice([0, 1, 0xffffffff]))

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_td_init_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        if self.comp_mask is not None:
            s += emit_assign(varname, "comp_mask", self.comp_mask)
        return s