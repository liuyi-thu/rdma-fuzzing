import random
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

class IbvQpInitAttr:
    FIELD_LIST = [
        "qp_context", "send_cq", "recv_cq", "srq",
        "cap", "qp_type", "sq_sig_all"
    ]
    def __init__(self, qp_context=None, send_cq=None, recv_cq=None, srq=None,
                 cap=None, qp_type=None, sq_sig_all=None):
        self.qp_context = qp_context      # C++变量名/trace名/None
        self.send_cq = send_cq            # C++变量名/trace名/None
        self.recv_cq = recv_cq            # C++变量名/trace名/None
        self.srq = srq                    # C++变量名/trace名/None
        self.cap = cap                    # IbvQPCap 对象/None
        self.qp_type = qp_type            # int（需用枚举）
        self.sq_sig_all = sq_sig_all      # int

    @classmethod
    def random_mutation(cls):
        return cls(
            qp_context=None,
            send_cq="send_cq_0",
            recv_cq="recv_cq_0",
            srq=None,
            cap=IbvQPCap.random_mutation(),
            qp_type=random.choice(list(IBV_QP_TYPE_ENUM.keys())),
            sq_sig_all=random.choice([0, 1])
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_qp_init_attr")
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
            else:
                s += emit_assign(varname, field, val, enum_fields)
        return s
    
if __name__ == "__main__":
    init_attr = IbvQpInitAttr.random_mutation()
    print(init_attr.to_cxx("init_attr"))