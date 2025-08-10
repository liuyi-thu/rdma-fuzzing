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

IBV_QP_TYPE_ENUM = {
    2: "IBV_QPT_RC",
    3: "IBV_QPT_UC",
    4: "IBV_QPT_UD",
    8: "IBV_QPT_RAW_PACKET",
    9: "IBV_QPT_XRC_SEND",
    10: "IBV_QPT_XRC_RECV",
    255: "IBV_QPT_DRIVER",
}


class IbvQPOpenAttr(Attr):
    FIELD_LIST = ["comp_mask", "qp_num", "xrcd", "qp_context", "qp_type"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(self, comp_mask=None, qp_num=None, xrcd=None, qp_context=None, qp_type=None):
        self.comp_mask = OptionalValue(
            IntValue(comp_mask) if comp_mask is not None else None, factory=lambda: IntValue(0)
        )
        self.qp_num = OptionalValue(
            IntValue(qp_num) if qp_num is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.xrcd = OptionalValue(
            ResourceValue(value=xrcd, resource_type="xrcd") if xrcd is not None else None,
            factory=lambda: ResourceValue(value="xrcd_0", resource_type="xrcd"),
        )
        self.qp_context = OptionalValue(
            ConstantValue(qp_context) if qp_context is not None else None, factory=lambda: ConstantValue(0)
        )
        self.qp_type = OptionalValue(
            EnumValue(qp_type, enum_type="IBV_QP_TYPE_ENUM") if qp_type is not None else None,
            factory=lambda: EnumValue(2, enum_type="IBV_QP_TYPE_ENUM"),
        )
        self.tracker = None
        self.required_resources = []  # 用于跟踪所需的资源

    @classmethod
    def random_mutation(cls):
        return cls(
            comp_mask=random.choice([0, 1]),
            qp_num=random.randint(0, 0xFFFFFF),
            xrcd=None,  # trace/replay下由变量池决定
            qp_context="NULL",
            qp_type=random.choice(list(IBV_QP_TYPE_ENUM.keys())),
        )

    def apply(self, ctx: CodeGenContext):
        """Apply this QP open attr to the context, allocating a new variable if needed."""
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            if not self.xrcd.is_none():
                self.tracker.use("xrcd", self.xrcd.get_value())
                self.required_resources.append({"type": "xrcd", "name": self.xrcd.get_value(), "position": "xrcd"})
            # # Register the QP open attributes variable
            # ctx.alloc_variable("qp_open_attr", "struct ibv_qp_open_attr")
            # self.tracker.create('qp_open_attr', "qp_open_attr", qp=self.qp_num)

    def to_cxx(self, varname, ctx: CodeGenContext = None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_qp_open_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        # enum_fields = {
        #     "qp_type": IBV_QP_TYPE_ENUM,
        # }
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if not v:
                continue
            if f == "xrcd":
                # v = ctx.get_xrcd(v) if isinstance(v, str) else v
                s += f"    {varname}.xrcd = {v};\n"
            else:
                s += emit_assign(varname, f, v)
        return s


if __name__ == "__main__":
    # Example usage
    attr = IbvQPOpenAttr.random_mutation()
    print(attr.to_cxx("qp_open_attr", ctx=None))  # ctx is None for simplicity in this examples
    for i in range(10000):
        attr.mutate()
        print(attr.to_cxx(f"qp_open_attr_{i}", ctx=None))
    print("Done generating random mutations.")
