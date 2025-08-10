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
    from .IbvSrqAttr import IbvSrqAttr  # for package import
except ImportError:
    from IbvSrqAttr import IbvSrqAttr

try:
    from .value import ConstantValue, EnumValue, FlagValue, IntValue, OptionalValue, ResourceValue
except ImportError:
    from value import ConstantValue, EnumValue, FlagValue, IntValue, OptionalValue, ResourceValue

IBV_SRQ_TYPE_ENUM = {
    0: "IBV_SRQT_BASIC",
    1: "IBV_SRQT_XRC",
    2: "IBV_SRQT_TM",
}


class IbvTMCap(Attr):
    FIELD_LIST = ["max_num_tags", "max_ops"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(self, max_num_tags=None, max_ops=None):
        self.max_num_tags = OptionalValue(
            IntValue(max_num_tags) if max_num_tags is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.max_ops = OptionalValue(
            IntValue(max_ops) if max_ops is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0

    @classmethod
    def random_mutation(cls):
        return cls(max_num_tags=random.choice([0, 1, 128, 1024]), max_ops=random.choice([0, 16, 256]))

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
    FIELD_LIST = ["srq_context", "attr", "comp_mask", "srq_type", "pd", "xrcd", "cq", "tm_cap"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(
        self, srq_context=None, attr=None, comp_mask=None, srq_type=None, pd=None, xrcd=None, cq=None, tm_cap=None
    ):
        self.srq_context = OptionalValue(
            ConstantValue(srq_context) if srq_context is not None else None, factory=lambda: ConstantValue(0)
        )  # 默认值为0
        self.attr = OptionalValue(
            attr if attr is not None else None, factory=lambda: IbvSrqAttr.random_mutation()
        )  # 默认值为IbvSrqAttr()
        self.comp_mask = OptionalValue(
            IntValue(comp_mask) if comp_mask is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.srq_type = OptionalValue(
            EnumValue(srq_type, enum_type="IBV_SRQ_TYPE_ENUM") if srq_type is not None else None,
            factory=lambda: EnumValue(0, enum_type="IBV_SRQ_TYPE_ENUM"),
        )  # 默认值为IBV_SRQT_BASIC
        self.pd = OptionalValue(
            ResourceValue(value=pd, resource_type="pd") if pd is not None else None,
            factory=lambda: ResourceValue(value="pd1", resource_type="pd"),
        )  # 默认值为"pd1"
        self.xrcd = OptionalValue(
            ResourceValue(value=xrcd, resource_type="xrcd") if xrcd is not None else None,
            factory=lambda: ResourceValue(value="xrcd1", resource_type="xrcd"),
        )  # 默认值为"xrcd1"
        self.cq = OptionalValue(
            ResourceValue(value=cq, resource_type="cq") if cq is not None else None,
            factory=lambda: ResourceValue(value="cq1", resource_type="cq"),
        )  # 默认值为"cq1"
        self.tm_cap = OptionalValue(
            tm_cap if tm_cap is not None else None, factory=lambda: IbvTMCap()
        )  # 默认值为IbvTMCap()

        self.tracker = None
        self.required_resources = []  # 用于跟踪所需的资源

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
            tm_cap=IbvTMCap.random_mutation(),
        )

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # if self.srq_context:
            #     self.tracker.use("srq", self.srq_context)
            # if self.attr:
            #     self.attr.apply(ctx)
            if self.pd.is_not_none():
                self.tracker.use("pd", self.pd.get_value())
                self.required_resources.append({"type": "pd", "name": self.pd, "position": "pd"})
            if self.xrcd.is_not_none():
                self.tracker.use("xrcd", self.xrcd.get_value())
                self.required_resources.append({"type": "xrcd", "name": self.xrcd, "position": "xrcd"})
            if self.cq.is_not_none():
                self.tracker.use("cq", self.cq.get_value())
                self.required_resources.append({"type": "cq", "name": self.cq, "position": "cq"})

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
            if not val:
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
                s += emit_assign(varname, field, val)
        return s


if __name__ == "__main__":
    # For debugging purposes, you can run this file directly to see the output
    srq_init_ex = IbvSrqInitAttrEx.random_mutation()
    print(srq_init_ex.to_cxx("srq_init_attr_ex", ctx=None))
    for i in range(1000):
        srq_init_ex.mutate()
        print(srq_init_ex.to_cxx(f"srq_init_attr_ex_{i}", ctx=None))
