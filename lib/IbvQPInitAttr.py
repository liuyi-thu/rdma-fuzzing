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

from lib.contracts import Contract

IBV_QP_TYPE_ENUM = {
    2: "IBV_QPT_RC",
    3: "IBV_QPT_UC",
    4: "IBV_QPT_UD",
    8: "IBV_QPT_RAW_PACKET",
    9: "IBV_QPT_XRC_SEND",
    10: "IBV_QPT_XRC_RECV",
    255: "IBV_QPT_DRIVER",
}


class IbvQPInitAttr(Attr):
    FIELD_LIST = ["qp_context", "send_cq", "recv_cq", "srq", "cap", "qp_type", "sq_sig_all"]
    MUTABLE_FIELDS = FIELD_LIST
    EXPORT_FIELDS = ["qp_context", "send_cq", "recv_cq", "srq", "cap", "qp_type", "sq_sig_all"]
    CONTRACT = Contract(
        requires=[
            # RequireSpec(rtype="cq", state=State.ALLOCATED, name_attr="send_cq"),
            # RequireSpec(rtype="cq", state=State.ALLOCATED, name_attr="recv_cq"),
            # RequireSpec(rtype="srq", state=State.ALLOCATED, name_attr="srq"),
            # this is duplicated
        ],
        produces=[],
        transitions=[],
    )

    def __init__(self, qp_context=None, send_cq=None, recv_cq=None, srq=None, cap=None, qp_type=None, sq_sig_all=None):
        self.qp_context = OptionalValue(
            ConstantValue(qp_context) if qp_context is not None else None, factory=lambda: ConstantValue(0)
        )  # 默认值为0
        self.send_cq = OptionalValue(
            ResourceValue(value=send_cq, resource_type="cq") if send_cq is not None else None,
            factory=lambda: ResourceValue(value="NULL", resource_type="cq"),
        )  # 默认值为"send_cq_0"
        self.recv_cq = OptionalValue(
            ResourceValue(value=recv_cq, resource_type="cq") if recv_cq is not None else None,
            factory=lambda: ResourceValue(value="NULL", resource_type="cq"),
        )  # 默认值为"recv_cq_0"
        self.srq = OptionalValue(
            ResourceValue(value=srq, resource_type="srq") if srq is not None else None,
            factory=lambda: ResourceValue(value="NULL", resource_type="srq"),
        )  # 默认值为"srq_0"
        self.cap = OptionalValue(cap if cap is not None else None, factory=lambda: IbvQPCap())  # 默认值为IbvQPCap()
        self.qp_type = OptionalValue(
            EnumValue(qp_type, enum_type="IBV_QP_TYPE_ENUM") if qp_type is not None else None,
            factory=lambda: EnumValue(2, enum_type="IBV_QP_TYPE_ENUM"),
        )
        self.sq_sig_all = OptionalValue(
            IntValue(sq_sig_all) if sq_sig_all is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.tracker = None
        self.required_resources = []  # 用于跟踪所需的资源

    @classmethod
    def random_mutation(cls):
        return cls(
            qp_context=None,
            send_cq="send_cq_0",
            recv_cq="recv_cq_0",
            srq=None,
            cap=IbvQPCap.random_mutation(),
            qp_type=random.choice(list(IBV_QP_TYPE_ENUM.keys())),
            sq_sig_all=random.choice([0, 1]),
        )

    def apply(self, ctx: CodeGenContext):
        """Apply this init attribute to the context, allocating a new variable if needed."""
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        # self.context = ctx  # TEMP
        # if self.context:
        #     self.context.alloc_variable(str(self), "struct ibv_qp_init_attr")

        if self.tracker:
            # if self.qp_context:
            #     self.tracker.use("qp", self.qp_context)
            if not self.send_cq.is_none():
                self.tracker.use("cq", self.send_cq.get_value())
                self.required_resources.append({"type": "cq", "name": self.send_cq.get_value(), "position": "send_cq"})
            if not self.recv_cq.is_none():
                self.tracker.use("cq", self.recv_cq.get_value())
                self.required_resources.append({"type": "cq", "name": self.recv_cq.get_value(), "position": "recv_cq"})
            if not self.srq.is_none():
                self.tracker.use("srq", self.srq.get_value())
                self.required_resources.append({"type": "srq", "name": self.srq.get_value(), "position": "srq"})
            # if self.cap:
            #     self.cap.apply(ctx)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    # def get_required_resources_recursively(self) -> List[Dict[str, str]]:
    #     """Get all required resources recursively."""
    #     resources = self.required_resources.copy()
    #     # if self.cap:
    #     #     resources.extend(self.cap.get_required_resources_recursively())
    #     return resources

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_qp_init_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        # enum_fields = {"qp_type": IBV_QP_TYPE_ENUM}
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if not val:
                continue
            if field == "cap":
                cap_var = varname + "_cap"
                s += val.to_cxx(cap_var, ctx)
                s += f"    {varname}.cap = {cap_var};\n"
            else:
                # s += emit_assign(varname, field, val, enum_fields)
                s += emit_assign(varname, field, val)
        return s


if __name__ == "__main__":
    init_attr = IbvQPInitAttr.random_mutation()
    # print(init_attr.to_cxx("init_attr"))

    for i in range(10000):
        init_attr.mutate()
    print(init_attr.to_cxx("init_attr"))
