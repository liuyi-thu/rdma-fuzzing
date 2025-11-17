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
        "comp_mask",  # 允许手工覆盖（若不提供则自动计算）
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

    # ---- comp_mask 映射（由字段名 → 掩码位）----
    _MASK_BY_FIELD = {
        "pd": "IBV_QP_INIT_ATTR_PD",
        "xrcd": "IBV_QP_INIT_ATTR_XRCD",
        "create_flags": "IBV_QP_INIT_ATTR_CREATE_FLAGS",
        "max_tso_header": "IBV_QP_INIT_ATTR_MAX_TSO_HEADER",
        "rwq_ind_tbl": "IBV_QP_INIT_ATTR_IND_TABLE",
        "rx_hash_conf": "IBV_QP_INIT_ATTR_RX_HASH",
        "send_ops_flags": "IBV_QP_INIT_ATTR_SEND_OPS_FLAGS",
        # 其余基础字段（send_cq/recv_cq/cap/qp_type/sq_sig_all）不需要 comp_mask 位
    }

    def __init__(
        self,
        qp_context=None,
        send_cq=None,
        recv_cq=None,
        srq=None,
        cap=None,
        qp_type=None,
        sq_sig_all=None,
        comp_mask=None,  # 若 None 则自动计算
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
            factory=lambda: ResourceValue("cq_send", resource_type="cq"),
        )
        self.recv_cq = OptionalValue(
            ResourceValue(recv_cq, resource_type="cq") if recv_cq else None,
            factory=lambda: ResourceValue("cq_recv", resource_type="cq"),
        )
        self.srq = OptionalValue(
            ResourceValue(srq, resource_type="srq") if srq else None,
            factory=lambda: None,  # SRQ 非必需
        )

        # cap 是 struct，保持你工程的对象生成方式
        self.cap = OptionalValue(cap if cap else None, factory=lambda: IbvQPCap.random_mutation())

        self.qp_type = OptionalValue(
            EnumValue(qp_type, IBV_QP_TYPE_ENUM) if qp_type is not None else None,
            factory=lambda: EnumValue(2, IBV_QP_TYPE_ENUM),  # 默认 RC
        )

        self.sq_sig_all = OptionalValue(
            IntValue(sq_sig_all, range=[0, 1]) if sq_sig_all is not None else None,
            factory=lambda: IntValue(0),
        )

        # comp_mask：支持手工值；否则自动计算
        self._comp_mask_user = comp_mask is not None
        self.comp_mask = OptionalValue(
            IntValue(comp_mask) if comp_mask is not None else None,
            factory=lambda: IntValue(0),
        )

        # 扩展字段（触发 comp_mask 位）
        self.pd = OptionalValue(
            ResourceValue(pd, resource_type="pd") if pd else None,
            factory=lambda: ResourceValue("pd1", resource_type="pd"),
        )
        self.xrcd = OptionalValue(
            ResourceValue(xrcd, resource_type="xrcd") if xrcd else None,
            factory=lambda: None,  # XRC 可选
        )
        self.create_flags = OptionalValue(
            FlagValue(create_flags or 0, flag_type="IBV_QP_CREATE_FLAGS_ENUM"),
            factory=lambda: FlagValue(0, flag_type="IBV_QP_CREATE_FLAGS_ENUM"),
        )
        self.max_tso_header = OptionalValue(
            IntValue(max_tso_header) if max_tso_header is not None else None,
            factory=lambda: IntValue(0),
        )

        # RWQ indirection table（RAW_PACKET/RSS 场景）
        self.rwq_ind_tbl = OptionalValue(
            ResourceValue(rwq_ind_tbl, resource_type="rwq_ind_tbl") if rwq_ind_tbl else None,
            factory=lambda: None,
        )

        self.rx_hash_conf = OptionalValue(
            rx_hash_conf if rx_hash_conf else None,
            factory=lambda: None,  # 仅当用户显式需要 RSS hash config 时生成
        )

        self.source_qpn = OptionalValue(
            IntValue(source_qpn, range=[0, 0xFFFFFF]) if source_qpn is not None else None,
            factory=lambda: IntValue(0),
        )

        self.send_ops_flags = OptionalValue(
            FlagValue(send_ops_flags or 0, flag_type="IBV_QP_CREATE_SEND_OPS_FLAGS_ENUM"),
            factory=lambda: FlagValue(0, flag_type="IBV_QP_CREATE_SEND_OPS_FLAGS_ENUM"),
        )

        self.tracker = None
        self.required_resources = []

    # # ---------- 依赖收集：只有用到的字段才声明资源需求 ----------
    # def get_required_resources(self) -> list[dict[str, str]]:
    #     req = []
    #     # CQ 基本必需
    #     if self.send_cq.value:
    #         req.append({"type": "cq", "name": self.send_cq.value.value})
    #     if self.recv_cq.value:
    #         req.append({"type": "cq", "name": self.recv_cq.value.value})

    #     # PD / XRCD 二选一（大多数设备 PD）
    #     if self.pd.value:
    #         req.append({"type": "pd", "name": self.pd.value.value})
    #     if self.xrcd.value:
    #         req.append({"type": "xrcd", "name": self.xrcd.value.value})

    #     if self.srq.value:
    #         req.append({"type": "srq", "name": self.srq.value.value})
    #     if self.rwq_ind_tbl.value:
    #         req.append({"type": "rwq_ind_tbl", "name": self.rwq_ind_tbl.value.value})
    #     return req

    # def get_required_resources_recursively(self) -> list[dict[str, str]]:
    #     res = self.get_required_resources()
    #     if self.cap and self.cap.value and hasattr(self.cap.value, "get_required_resources"):
    #         res.extend(self.cap.value.get_required_resources())
    #     if self.rx_hash_conf and self.rx_hash_conf.value and hasattr(self.rx_hash_conf.value, "get_required_resources"):
    #         res.extend(self.rx_hash_conf.value.get_required_resources())
    #     return res

    # def set_resource_recursively(self, res_type: str, old_res_name: str, new_res_name: str):
    #     for field in ["send_cq", "recv_cq", "srq", "pd", "xrcd", "rwq_ind_tbl"]:
    #         opt = getattr(self, field)
    #         if opt and opt.value and isinstance(opt.value, ResourceValue):
    #             if opt.value.resource_type == res_type and opt.value.value == old_res_name:
    #                 opt.value = ResourceValue(new_res_name, resource_type=res_type)

    # ---------- 自动 comp_mask 计算 ----------
    def _auto_comp_mask_value(self) -> int:
        # 若用户手工提供，则尊重
        if self._comp_mask_user and self.comp_mask and self.comp_mask.value:
            return int(self.comp_mask.value.value)

        bit = 0

        def set_bit(mask_name):
            nonlocal bit
            bit |= globals()[mask_name] if mask_name in globals() else 0

        # 只要字段有效，就置相应位
        for field, mask_name in self._MASK_BY_FIELD.items():
            opt = getattr(self, field)
            # 注意：像 create_flags / send_ops_flags 这些 OptionalValue 一定有对象
            if opt and opt.value:
                # 非零才算启用（对 flags/int）
                val = opt.value.value if hasattr(opt.value, "value") else opt.value
                if isinstance(val, (int,)) and val == 0:
                    continue
                set_bit(mask_name)

        return bit

    # ---------- 代码生成 ----------
    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_qp_init_attr_ex")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"

        enum_fields = {"qp_type": IBV_QP_TYPE_ENUM}

        # cap：单独生成一个本地变量再整体赋值（struct 赋值合法）
        if self.cap and self.cap.value:
            cap_var = varname + "_cap"
            s += self.cap.value.to_cxx(cap_var, ctx)
            s += f"    {varname}.cap = {cap_var};\n"

        # rx_hash_conf：如存在，生成临时变量并赋值
        if self.rx_hash_conf and self.rx_hash_conf.value:
            rxh_var = varname + "_rxh"
            s += self.rx_hash_conf.value.to_cxx(rxh_var, ctx)
            s += f"    {varname}.rx_hash_conf = {rxh_var};\n"

        # 基础/指针类字段统一赋值
        for field in [
            "qp_context",
            "send_cq",
            "recv_cq",
            "srq",
            "qp_type",
            "sq_sig_all",
            "pd",
            "xrcd",
            "create_flags",
            "max_tso_header",
            "rwq_ind_tbl",
            "source_qpn",
            "send_ops_flags",
        ]:
            val = getattr(self, field)
            if not val:
                continue
            s += emit_assign(varname, field, val, enums=enum_fields)

        # 最后处理 comp_mask：若用户未显式设置，则自动计算
        auto_mask = self._auto_comp_mask_value()
        if self._comp_mask_user:
            s += emit_assign(varname, "comp_mask", self.comp_mask)
        else:
            s += f"    {varname}.comp_mask = 0x{auto_mask:x};\n"

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
