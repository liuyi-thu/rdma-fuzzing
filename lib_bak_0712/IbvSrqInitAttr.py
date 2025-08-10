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

try:
    from .IbvSrqAttr import IbvSrqAttr  # for package import
except ImportError:
    from IbvSrqAttr import IbvSrqAttr   

class IbvSrqInitAttr(Attr):
    FIELD_LIST = ["srq_context", "attr"]
    def __init__(self, srq_context=None, attr=None):
        self.srq_context = srq_context  # 一般C++已有指针变量名或None
        self.attr = attr  # IbvSrqAttr对象

    @classmethod
    def random_mutation(cls):
        return cls(
            srq_context=None,  # 可随机填C++已有的指针变量
            attr=IbvSrqAttr.random_mutation()
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_srq_init_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        # srq_context 通常是 void*，如果不是None就赋值
        if self.srq_context is not None:
            s += emit_assign(varname, "srq_context", self.srq_context)
        # attr
        if self.attr is not None:
            attr_var = varname + "_attr"
            s += self.attr.to_cxx(attr_var, ctx)
            s += f"    {varname}.attr = {attr_var};\n"
        return s

if __name__ == "__main__":
    srq_init = IbvSrqInitAttr.random_mutation()
    print(srq_init.to_cxx("srq_init_attr"))
