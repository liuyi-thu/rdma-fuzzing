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
# IBV_QP_TYPE_ENUM maps integer values to string representations of QP types

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
    def __init__(self, comp_mask=None, qp_num=None, xrcd=None, qp_context=None, qp_type=None):
        self.comp_mask = comp_mask
        self.qp_num = qp_num
        self.xrcd = xrcd  # 可为已有 xrcd 变量名
        self.qp_context = qp_context  # C 层 void*，你可指定如 "NULL"
        self.qp_type = qp_type
        self.tracker = None
        self.required_resources = []       # 用于跟踪所需的资源

    @classmethod
    def random_mutation(cls):
        return cls(
            comp_mask=random.choice([0, 1]),
            qp_num=random.randint(0, 0xffffff),
            xrcd=None,  # trace/replay下由变量池决定
            qp_context="NULL",
            qp_type=random.choice(list(IBV_QP_TYPE_ENUM.keys())),
        )
    
    def apply(self, ctx: CodeGenContext):
        """Apply this QP open attr to the context, allocating a new variable if needed."""
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            if self.xrcd:
                self.tracker.use("xrcd", self.xrcd)
                self.required_resources.append({'type': 'xrcd', 'name': self.xrcd, 'position': 'xrcd'})
            # # Register the QP open attributes variable
            # ctx.alloc_variable("qp_open_attr", "struct ibv_qp_open_attr")
            # self.tracker.create('qp_open_attr', "qp_open_attr", qp=self.qp_num)

    def to_cxx(self, varname, ctx : CodeGenContext =None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_qp_open_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        enum_fields = {
            "qp_type": IBV_QP_TYPE_ENUM,
        }
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is None:
                continue
            if f == "xrcd":
                # v = ctx.get_xrcd(v) if isinstance(v, str) else v
                s += f"    {varname}.xrcd = {v};\n"
            else:
                s += emit_assign(varname, f, v, enums=enum_fields)
        return s


# enum ibv_qp_open_attr_mask {
# 	IBV_QP_OPEN_ATTR_NUM		= 1 << 0,
# 	IBV_QP_OPEN_ATTR_XRCD	        = 1 << 1,
# 	IBV_QP_OPEN_ATTR_CONTEXT	= 1 << 2,
# 	IBV_QP_OPEN_ATTR_TYPE		= 1 << 3,
# 	IBV_QP_OPEN_ATTR_RESERVED	= 1 << 4
# };