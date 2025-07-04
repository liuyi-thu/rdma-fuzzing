import random
try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging

IBV_WQ_TYPE_ENUM = {
    0: 'IBV_WQT_RQ',       # Receive Queue
    1: 'IBV_WQT_RQ_WITH_SRQ',  # Receive Queue with SRQ
    2: 'IBV_WQT_SRQ',      # Shared Receive Queue
    # 若有更多类型可补充
}


class IbvWQInitAttr:
    FIELD_LIST = [
        "wq_context", "wq_type", "max_wr", "max_sge",
        "pd", "cq", "comp_mask", "create_flags"
    ]
    def __init__(self, wq_context=None, wq_type=None, max_wr=None, max_sge=None,
                 pd=None, cq=None, comp_mask=None, create_flags=None):
        self.wq_context = wq_context
        self.wq_type = wq_type
        self.max_wr = max_wr
        self.max_sge = max_sge
        self.pd = pd
        self.cq = cq
        self.comp_mask = comp_mask
        self.create_flags = create_flags

    @classmethod
    def random_mutation(cls):
        return cls(
            wq_context="NULL",
            wq_type=random.choice(list(IBV_WQ_TYPE_ENUM.keys())),
            max_wr=random.choice([1, 8, 64, 1024]),
            max_sge=random.choice([1, 2, 16]),
            pd="pd1",
            cq="cq1",
            comp_mask=random.choice([0, 1]),
            create_flags=random.choice([0, 1, 0x10])
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_wq_init_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        enum_fields = {"wq_type": IBV_WQ_TYPE_ENUM}
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if val is not None:
                s += emit_assign(varname, field, val, enums=enum_fields)
        return s
