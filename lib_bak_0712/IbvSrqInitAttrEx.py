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

IBV_SRQ_TYPE_ENUM = {
    0: 'IBV_SRQT_BASIC',
    1: 'IBV_SRQT_XRC',
    2: 'IBV_SRQT_TM',
}


class IbvTMCap(Attr):
    FIELD_LIST = ["max_num_tags", "max_ops"]
    def __init__(self, max_num_tags=None, max_ops=None):
        self.max_num_tags = max_num_tags
        self.max_ops = max_ops

    @classmethod
    def random_mutation(cls):
        return cls(
            max_num_tags=random.choice([0, 1, 128, 1024]),
            max_ops=random.choice([0, 16, 256])
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_tm_cap")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is not None:
                s += emit_assign(varname, f, v)
        return s
    
class IbvSrqInitAttrEx(Attr):
    FIELD_LIST = [
        "srq_context", "attr", "comp_mask", "srq_type", "pd",
        "xrcd", "cq", "tm_cap"
    ]
    def __init__(self, srq_context=None, attr=None, comp_mask=None, srq_type=None,
                 pd=None, xrcd=None, cq=None, tm_cap=None):
        self.srq_context = srq_context
        self.attr = attr    # IbvSrqAttr 对象
        self.comp_mask = comp_mask
        self.srq_type = srq_type
        self.pd = pd
        self.xrcd = xrcd
        self.cq = cq
        self.tm_cap = tm_cap  # IbvTMCap 对象
        self.tracker = None
        self.required_resources = []       # 用于跟踪所需的资源

    @classmethod
    def random_mutation(cls):
        return cls(
            srq_context="NULL",
            attr=IbvSrqAttr.random_mutation(),
            comp_mask=random.choice([0, 1]),
            srq_type=random.choice(list(IBV_SRQ_TYPE_ENUM.keys())),
            pd="pd1",
            xrcd="NULL",
            cq="NULL",
            tm_cap=IbvTMCap.random_mutation()
        )

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # if self.srq_context:
            #     self.tracker.use("srq", self.srq_context)
            # if self.attr:
            #     self.attr.apply(ctx)
            if self.pd:
                self.tracker.use("pd", self.pd)
            if self.xrcd:
                self.tracker.use("xrcd", self.xrcd)
            if self.cq:
                self.tracker.use("cq", self.cq)
            # if self.tm_cap:
            #     self.tm_cap.apply(ctx)

            # 记录所需资源
            if self.pd:
                self.required_resources.append({'type': 'pd', 'name': self.pd, 'position': 'pd'})
            if self.xrcd:
                self.required_resources.append({'type': 'xrcd', 'name': self.xrcd, 'position': 'xrcd'})
            if self.cq:
                self.required_resources.append({'type': 'cq', 'name': self.cq, 'position': 'cq'})

    # def get_required_resources_recursively(self) -> List[Dict[str, str]]:
    #     """Get all required resources recursively."""
    #     resources = self.required_resources.copy()
    #     if self.attr:
    #         resources.extend(self.attr.get_required_resources_recursively())
    #     if self.tm_cap:
    #         resources.extend(self.tm_cap.get_required_resources_recursively())
    #     return resources
    
    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_srq_init_attr_ex")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        enum_fields = {"srq_type": IBV_SRQ_TYPE_ENUM}
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if val is None:
                continue
            if field == "attr":
                attr_var = varname + "_attr"
                s += val.to_cxx(attr_var, ctx)
                s += f"    {varname}.attr = {attr_var};\n"
            elif field == "tm_cap":
                tm_var = varname + "_tm"
                s += val.to_cxx(tm_var, ctx)
                s += f"    {varname}.tm_cap = {tm_var};\n"
            else:
                s += emit_assign(varname, field, val, enums=enum_fields)
        return s
