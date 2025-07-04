import random
try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging

try:
    from .IbvModerateCQ import IbvModerateCQ  # for package import
except ImportError:
    from IbvModerateCQ import IbvModerateCQ

class IbvModifyCQAttr:
    FIELD_LIST = ["attr_mask", "moderate"]
    def __init__(self, attr_mask=None, moderate=None):
        self.attr_mask = attr_mask
        self.moderate = moderate  # IbvModerateCQ 对象

    @classmethod
    def random_mutation(cls):
        return cls(
            attr_mask=random.choice([0, 1, 3]),
            moderate=IbvModerateCQ.random_mutation()
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_modify_cq_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if val is None:
                continue
            if field == "moderate":
                moderate_var = varname + "_moderate"
                s += val.to_cxx(moderate_var, ctx)
                s += f"    {varname}.moderate = {moderate_var};\n"
            else:
                s += emit_assign(varname, field, val)
        return s

if __name__ == "__main__":
    attr = IbvModifyCQAttr.random_mutation()
    print(attr.to_cxx("modify_cq_attr"))