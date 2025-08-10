import random

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


class IbvParentDomainInitAttr(Attr):
    FIELD_LIST = ["pd", "td", "comp_mask", "alloc", "free", "pd_context"]
    MUTABLE_FIELDS = ["pd", "td", "comp_mask", "alloc", "free", "pd_context"]

    def __init__(self, pd=None, td=None, comp_mask=None, alloc=None, free=None, pd_context=None):
        self.pd = OptionalValue(
            ResourceValue("pd", pd) if pd is not None else None, factory=lambda: ResourceValue("pd", "NULL")
        )  # C++已有变量名或NULL
        self.td = OptionalValue(
            ResourceValue("td", td) if td is not None else None, factory=lambda: ResourceValue("td", "NULL")
        )  # C++已有变量名或NULL
        self.comp_mask = OptionalValue(
            IntValue(comp_mask) if comp_mask is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.alloc = OptionalValue(
            ConstantValue(alloc) if alloc is not None else None, factory=lambda: ConstantValue("NULL")
        )
        self.free = OptionalValue(
            ConstantValue(free) if free is not None else None, factory=lambda: ConstantValue("NULL")
        )
        self.pd_context = OptionalValue(
            ConstantValue(pd_context) if pd_context is not None else None, factory=lambda: ConstantValue("NULL")
        )

        self.required_resources = []  # 用于跟踪所需的资源
        self.tracker = None

    @classmethod
    def random_mutation(cls):
        return cls(
            pd=None,  # 可传已有PD名
            # td=IbvTd.random_mutation(),
            td=None,
            comp_mask=random.choice([0, 1]),
            alloc=None,  # 或"mock_alloc_func"
            free=None,  # 或"mock_free_func"
            pd_context=None,  # 或已有context指针
        )

    def apply(self, ctx: CodeGenContext):
        """Apply this init attr to the context, allocating a new variable if needed."""
        self.required_resources = []
        self.tracker = ctx.tracker if ctx is not None else None
        if self.tracker:
            self.tracker.use("pd", self.pd.get_value())
            self.required_resources.append({"type": "pd", "name": self.pd.get_value(), "position": "pd"})
            if self.td:
                self.tracker.use("td", self.td.get_value())
                self.required_resources.append({"type": "td", "name": self.td.get_value(), "position": "td"})

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_parent_domain_init_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        if self.pd:
            s += emit_assign(varname, "pd", self.pd)  # pd_name 应该是一个变量名字符串
        if self.td:
            s += emit_assign(varname, "td", self.td)  # 应该是一个固定的东西
        if self.comp_mask:
            s += emit_assign(varname, "comp_mask", self.comp_mask)
        if self.alloc:
            s += emit_assign(varname, "alloc", self.alloc)
        if self.free:
            s += emit_assign(varname, "free", self.free)
        if self.pd_context:
            s += emit_assign(varname, "pd_context", self.pd_context)
        return s


if __name__ == "__main__":
    # 简单测试
    attr = IbvParentDomainInitAttr.random_mutation()
    print(attr.to_cxx("attr"))
    for i in range(10000):
        attr.mutate()
        # print(attr.to_cxx("attr"))
    print(attr.to_cxx("attr"))
