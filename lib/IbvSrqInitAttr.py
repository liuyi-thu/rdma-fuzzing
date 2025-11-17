import random

try:
    from .IbvQPCap import IbvQPCap  # for package import
except ImportError:
    from IbvQPCap import IbvQPCap  # for direct script debugging

try:
    from .attr import Attr
except ImportError:
    from attr import Attr

try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging

try:
    from .value import ConstantValue, EnumValue, FlagValue, IntValue, OptionalValue, ResourceValue
except ImportError:
    from value import ConstantValue, EnumValue, FlagValue, IntValue, OptionalValue, ResourceValue

try:
    from .IbvSrqAttr import IbvSrqAttr  # for package import
except ImportError:
    from IbvSrqAttr import IbvSrqAttr


class IbvSrqInitAttr(Attr):
    FIELD_LIST = ["srq_context", "attr"]
    MUTABLE_FIELDS = FIELD_LIST
    EXPORT_FIELDS = ["srq_context", "attr"]

    def __init__(self, srq_context=None, attr=None):
        self.srq_context = OptionalValue(
            ConstantValue(srq_context) if srq_context is not None else None, factory=lambda: ConstantValue(0)
        )  # 默认值为0
        self.attr = OptionalValue(
            attr if attr is not None else None, factory=lambda: IbvSrqAttr()
        )  # 默认值为IbvSrqAttr()

    @classmethod
    def random_mutation(cls):
        return cls(
            srq_context=None,  # 可随机填C++已有的指针变量
            attr=IbvSrqAttr.random_mutation(),
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_srq_init_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        # srq_context 通常是 void*，如果不是None就赋值
        if self.srq_context:
            s += emit_assign(varname, "srq_context", self.srq_context)
        # attr
        if self.attr:
            attr_var = varname + "_attr"
            s += self.attr.to_cxx(attr_var, ctx)
            s += f"    {varname}.attr = {attr_var};\n"
        return s


if __name__ == "__main__":
    srq_init = IbvSrqInitAttr.random_mutation()
    for i in range(1000):
        srq_init.mutate()
        print(srq_init.to_cxx(f"srq_init_attr_{i}", ctx=None))
    # For debugging purposes, you can run this file directly to see the output
