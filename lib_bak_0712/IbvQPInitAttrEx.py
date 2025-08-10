import random

from .attr import Attr

try:
    from .IbvQPCap import IbvQPCap  # for package import
except ImportError:
    from IbvQPCap import IbvQPCap  # for direct script debugging

try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging

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

    def __init__(self, rx_hash_function=None, rx_hash_key_len=None, rx_hash_key=None, rx_hash_fields_mask=None):
        self.rx_hash_function = rx_hash_function
        self.rx_hash_key_len = rx_hash_key_len
        self.rx_hash_key = rx_hash_key  # list[int] or None
        self.rx_hash_fields_mask = rx_hash_fields_mask

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
            if val is not None:
                s += emit_assign(varname, field, val)
        if self.rx_hash_key is not None:
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
        self.send_cq = send_cq
        self.recv_cq = recv_cq
        self.srq = srq
        self.cap = cap
        self.qp_type = qp_type
        self.sq_sig_all = sq_sig_all
        self.comp_mask = comp_mask
        self.pd = pd
        self.xrcd = xrcd  # 变量名
        self.create_flags = create_flags
        self.max_tso_header = max_tso_header
        self.rwq_ind_tbl = rwq_ind_tbl  # 变量名
        self.rx_hash_conf = rx_hash_conf  # IbvRxHashConf
        self.source_qpn = source_qpn
        self.send_ops_flags = send_ops_flags
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
            if self.send_cq:
                self.tracker.use("cq", self.send_cq)
                self.required_resources.append({"type": "cq", "name": self.send_cq, "position": "send_cq"})
            if self.recv_cq:
                self.tracker.use("cq", self.recv_cq)
                self.required_resources.append({"type": "cq", "name": self.recv_cq, "position": "recv_cq"})
            if self.srq:
                self.tracker.use("srq", self.srq)
                self.required_resources.append({"type": "srq", "name": self.srq, "position": "srq"})
            if self.pd:
                self.tracker.use("pd", self.pd)
                self.required_resources.append({"type": "pd", "name": self.pd, "position": "pd"})
            if self.xrcd:
                self.tracker.use("xrcd", self.xrcd)  # xrcd is INCOMPLETE, not used in verbs.py
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
            if val is None:
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
