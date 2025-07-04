import random
try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging


class IbvParentDomainInitAttr:
    FIELD_LIST = ["pd", "td", "comp_mask", "alloc", "free", "pd_context"]

    def __init__(self, pd=None, td=None, comp_mask=None, alloc=None, free=None, pd_context=None, ctx: CodeGenContext = None):
        self.pd = pd          # 通常为变量名字符串
        self.td = td          # IbvTd实例或 None
        self.comp_mask = comp_mask
        self.alloc = alloc    # 通常 None 或已有函数名
        self.free = free      # 通常 None 或已有函数名
        self.pd_context = pd_context  # 通常 None 或已有指针变量名

    @classmethod
    def random_mutation(cls):
        return cls(
            pd=None,  # 可传已有PD名
            # td=IbvTd.random_mutation(),
            td=None,
            comp_mask=random.choice([0, 1]),
            alloc=None,  # 或"mock_alloc_func"
            free=None,   # 或"mock_free_func"
            pd_context=None  # 或已有context指针
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_parent_domain_init_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        if self.pd is not None:
            pd_name = ctx.get_pd(self.pd) if ctx else self.pd
            # s += emit_assign(varname, "pd", self.pd)
            s += emit_assign(varname, "pd", pd_name)  # pd_name 应该是一个变量名字符串
        if self.td is not None:
            # td_var = varname + "_td"
            # s += self.td.to_cxx(td_var, ctx)
            # s += f"    {varname}.td = &{td_var};\n"
            # s += emit_assign(varname, "td", self.td.to_cxx(ctx=ctx) if ctx else self.td)
            td_name = ctx.get_td(self.td) if ctx else self.td
            s += emit_assign(varname, "td", td_name)  # 应该是一个固定的东西
        if self.comp_mask is not None:
            s += emit_assign(varname, "comp_mask", self.comp_mask)
        if self.alloc is not None:
            s += emit_assign(varname, "alloc", self.alloc)
        if self.free is not None:
            s += emit_assign(varname, "free", self.free)
        if self.pd_context is not None:
            s += emit_assign(varname, "pd_context", self.pd_context)
        return s
