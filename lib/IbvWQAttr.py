import random
try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging

IBV_WQ_STATE_ENUM = {
    0: 'IBV_WQS_RESET',
    1: 'IBV_WQS_RDY',
    2: 'IBV_WQS_ERR',
    3: 'IBV_WQS_UNKNOWN'
}

# 可选：也可为 attr_mask/flags/flags_mask 预设常用宏名
# 这里直接使用 int，trace/replay 可进一步增强

class IbvWQAttr:
    FIELD_LIST = ["attr_mask", "wq_state", "curr_wq_state", "flags", "flags_mask"]
    def __init__(self, attr_mask=None, wq_state=None, curr_wq_state=None, flags=None, flags_mask=None):
        self.attr_mask = attr_mask
        self.wq_state = wq_state
        self.curr_wq_state = curr_wq_state
        self.flags = flags
        self.flags_mask = flags_mask

    @classmethod
    def random_mutation(cls):
        return cls(
            attr_mask=random.choice([1, 3, 7, 15]),
            wq_state=random.choice(list(IBV_WQ_STATE_ENUM.keys())),
            curr_wq_state=random.choice(list(IBV_WQ_STATE_ENUM.keys())),
            flags=random.choice([0, 1, 2, 4, 8, 15]),
            flags_mask=random.choice([0, 1, 3, 7, 15])
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_wq_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        enum_fields = {
            'wq_state': IBV_WQ_STATE_ENUM,
            'curr_wq_state': IBV_WQ_STATE_ENUM,
        }
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is not None:
                s += emit_assign(varname, f, v, enums=enum_fields)
        return s
