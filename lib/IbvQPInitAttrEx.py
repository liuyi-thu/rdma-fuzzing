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
    from .value import ConstantValue, EnumValue, FlagValue, IntValue, ListValue, OptionalValue, ResourceValue
except ImportError:
    from value import ConstantValue, EnumValue, FlagValue, IntValue, ListValue, OptionalValue, ResourceValue

IBV_QP_TYPE_ENUM = {
    2: "IBV_QPT_RC",
    3: "IBV_QPT_UC",
    4: "IBV_QPT_UD",
    8: "IBV_QPT_RAW_PACKET",
    9: "IBV_QPT_XRC_SEND",
    10: "IBV_QPT_XRC_RECV",
    255: "IBV_QPT_DRIVER",
}


class IbvRxHashConf(Attr):
    FIELD_LIST = ["rx_hash_function", "rx_hash_key_len", "rx_hash_key", "rx_hash_fields_mask"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(self, rx_hash_function=None, rx_hash_key_len=None, rx_hash_key=None, rx_hash_fields_mask=None):
        self.rx_hash_function = OptionalValue(
            IntValue(rx_hash_function) if rx_hash_function is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.rx_hash_key_len = OptionalValue(
            IntValue(rx_hash_key_len) if rx_hash_key_len is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0 # TODO: binding?
        self.rx_hash_key = OptionalValue(
            ListValue([IntValue(x) for x in rx_hash_key], factory=lambda: IntValue(0))
            if rx_hash_key is not None
            else None,
            factory=lambda: ListValue([], factory=lambda: IntValue(0)),
        )  # 默认值为空列表
        self.rx_hash_fields_mask = OptionalValue(
            IntValue(rx_hash_fields_mask) if rx_hash_fields_mask is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0

    @classmethod
    def random_mutation(cls):
        key_len = random.choice([0, 8, 16, 32])
        rx_hash_key = [random.randint(0, 255) for _ in range(key_len)] if key_len else None
        return cls(
            rx_hash_function=random.choice([0, 1]),
            rx_hash_key_len=key_len,
            rx_hash_key=rx_hash_key,
            rx_hash_fields_mask=random.choice([0, 0xF, 0xFF]),
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_rx_hash_conf")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in ["rx_hash_function", "rx_hash_key_len", "rx_hash_fields_mask"]:
            val = getattr(self, field)
            if val:
                s += emit_assign(varname, field, val)
        if self.rx_hash_key:  # TODO: 要改吗？
            key_var = f"{varname}_key"
            arr_str = ", ".join(str(x) for x in self.rx_hash_key)
            if ctx:
                ctx.alloc_variable(f"{key_var}[{len(self.rx_hash_key)}]", "uint8_t", f"{{ {arr_str} }}")
            s += f"    {varname}.rx_hash_key = {key_var};\n"
        return s


class IbvQPInitAttrEx(Attr):
    FIELD_LIST = [
        "qp_context",
        "send_cq",
        "recv_cq",
        "srq",
        "cap",
        "qp_type",
        "sq_sig_all",
        "comp_mask",
        "pd",
        "xrcd",
        "create_flags",
        "max_tso_header",
        "rwq_ind_tbl",
        "rx_hash_conf",
        "source_qpn",
        "send_ops_flags",
    ]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(
        self,
        qp_context=None,
        send_cq=None,
        recv_cq=None,
        srq=None,
        cap=None,
        qp_type=None,
        sq_sig_all=None,
        comp_mask=None,
        pd=None,
        xrcd=None,
        create_flags=None,
        max_tso_header=None,
        rwq_ind_tbl=None,
        rx_hash_conf=None,
        source_qpn=None,
        send_ops_flags=None,
    ):
        self.qp_context = qp_context
        self.send_cq = OptionalValue(
            ResourceValue(send_cq, resource_type="cq") if send_cq else None,
            factory=lambda: ResourceValue("cq1", resource_type="cq"),
        )
        self.recv_cq = OptionalValue(
            ResourceValue(recv_cq, resource_type="cq") if recv_cq else None,
            factory=lambda: ResourceValue("recv_cq1", resource_type="cq"),
        )
        self.srq = OptionalValue(
            ResourceValue(srq, resource_type="srq") if srq else None,
            factory=lambda: ResourceValue("srq1", resource_type="srq"),
        )
        self.cap = OptionalValue(cap if cap else None, factory=lambda: IbvQPCap.random_mutation())
        self.qp_type = OptionalValue(
            EnumValue(qp_type, IBV_QP_TYPE_ENUM) if qp_type is not None else None,
            factory=lambda: EnumValue(2, IBV_QP_TYPE_ENUM),  # 默认值为IBV_QPT_RC
        )
        self.sq_sig_all = OptionalValue(
            IntValue(sq_sig_all, range=[0, 1]) if sq_sig_all is not None else None,
            factory=lambda: IntValue(0),  # 默认值为0
        )
        self.comp_mask = OptionalValue(
            IntValue(comp_mask, range=[0, 1, 0x400]) if comp_mask is not None else None,
            factory=lambda: IntValue(0),  # 默认值为0
        )
        self.pd = OptionalValue(
            ResourceValue(pd, resource_type="pd") if pd else None,
            factory=lambda: ResourceValue("pd1", resource_type="pd"),
        )
        self.xrcd = OptionalValue(
            ResourceValue(xrcd, resource_type="xrcd") if xrcd else None,
            factory=lambda: ResourceValue("xrcd1", resource_type="xrcd"),
        )
        self.create_flags = OptionalValue(
            IntValue(create_flags, range=[0, 1, 0x10]) if create_flags is not None else None,
            factory=lambda: IntValue(0),  # 默认值为0
        )
        self.max_tso_header = OptionalValue(
            IntValue(max_tso_header, range=[0, 128, 256]) if max_tso_header is not None else None,
            factory=lambda: IntValue(0),  # 默认值为0
        )
        # self.rwq_ind_tbl = rwq_ind_tbl  # 变量名
        # self.rwq_ind_tbl = ConstantValue("NULL")  # 默认值为"rwq_ind_tbl1"
        self.rwq_ind_tbl = None
        self.rx_hash_conf = OptionalValue(
            rx_hash_conf if rx_hash_conf else None, factory=lambda: IbvRxHashConf.random_mutation()
        )
        self.source_qpn = OptionalValue(
            IntValue(source_qpn, range=[0, 0xFFFFFF]) if source_qpn is not None else None,
            factory=lambda: IntValue(0),  # 默认值为0
        )  # TODO: qpn 有必要变成变量？
        self.send_ops_flags = OptionalValue(
            FlagValue(send_ops_flags, flag_type="IBV_QP_CREATE_SEND_OPS_FLAGS_ENUM")
            if send_ops_flags is not None
            else None,
            factory=lambda: FlagValue(0, flag_type="IBV_QP_CREATE_SEND_OPS_FLAGS_ENUM"),  # 默认值为0
        )

        self.tracker = None
        self.required_resources = []  # 用于跟踪所需的资源

    @classmethod
    def random_mutation(cls):
        return cls(
            qp_context="NULL",
            send_cq="send_cq1",
            recv_cq="recv_cq1",
            srq="NULL",
            cap=IbvQPCap.random_mutation(),
            qp_type=random.choice(list(IBV_QP_TYPE_ENUM.keys())),
            sq_sig_all=random.choice([0, 1]),
            comp_mask=random.choice([0, 1, 0x400]),
            pd="pd1",
            xrcd="NULL",
            create_flags=random.choice([0, 1, 0x10]),
            max_tso_header=random.choice([0, 128, 256]),
            rwq_ind_tbl="NULL",
            rx_hash_conf=IbvRxHashConf.random_mutation(),
            source_qpn=random.randint(0, 0xFFFFFF),
            send_ops_flags=random.choice([0, 1, 0xF]),
        )

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # if self.qp_context:
            #     self.tracker.use("qp", self.qp_context)
            if self.send_cq.is_not_none():
                self.tracker.use("cq", self.send_cq.get_value())
                self.required_resources.append({"type": "cq", "name": self.send_cq.get_value(), "position": "send_cq"})
            if self.recv_cq.is_not_none():
                self.tracker.use("cq", self.recv_cq.get_value())
                self.required_resources.append({"type": "cq", "name": self.recv_cq.get_value(), "position": "recv_cq"})
            if self.srq.is_not_none():
                self.tracker.use("srq", self.srq.get_value())
                self.required_resources.append({"type": "srq", "name": self.srq.get_value(), "position": "srq"})
            if self.pd.is_not_none():
                self.tracker.use("pd", self.pd.get_value())
                self.required_resources.append({"type": "pd", "name": self.pd.get_value(), "position": "pd"})
            if self.xrcd.is_not_none():
                self.tracker.use("xrcd", self.xrcd.get_value())  # xrcd is INCOMPLETE, not used in verbs.py
                self.required_resources.append({"type": "xrcd", "name": self.xrcd.get_value(), "position": "xrcd"})
            # if self.rwq_ind_tbl:
            #     self.tracker.use("rwq_ind_tbl", self.rwq_ind_tbl)
            # if self.rx_hash_conf:
            #     # 记录rx_hash_conf的资源依赖
            #     pass

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_qp_init_attr_ex")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        enum_fields = {"qp_type": IBV_QP_TYPE_ENUM}
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if not val:
                continue
            if field == "cap":
                cap_var = varname + "_cap"
                s += val.to_cxx(cap_var, ctx)
                s += f"    {varname}.cap = {cap_var};\n"
            elif field == "rx_hash_conf":
                rxh_var = varname + "_rxh"
                s += val.to_cxx(rxh_var, ctx)
                s += f"    {varname}.rx_hash_conf = {rxh_var};\n"
            else:
                s += emit_assign(varname, field, val, enums=enum_fields)
        return s


if __name__ == "__main__":
    # Example usage
    attr = IbvQPInitAttrEx.random_mutation()
    print(attr.to_cxx("qp_init_attr_ex", ctx=None))  # ctx is None for simplicity in this example
    # This will print the C++ code for initializing an ibv_qp_init_attr_ex structure with random values.
    for i in range(10000):
        attr.mutate()
        print(attr.to_cxx(f"qp_init_attr_ex_{i}", ctx=None))
    print("Done generating random mutations.")
