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
    

class IbvCQInitAttrEx(Attr):
    FIELD_LIST = [
        "cqe", "cq_context", "channel", "comp_vector", "wc_flags",
        "comp_mask", "flags", "parent_domain"
    ]
    def __init__(self, cqe=None, cq_context=None, channel=None, comp_vector=None,
                 wc_flags=None, comp_mask=None, flags=None, parent_domain=None):
        self.cqe = cqe
        self.cq_context = cq_context      # 可设为NULL或已有context指针名
        self.channel = channel            # ibv_comp_channel*，变量名或NULL
        self.comp_vector = comp_vector
        self.wc_flags = wc_flags
        self.comp_mask = comp_mask
        self.flags = flags
        self.parent_domain = parent_domain # 直接为指针变量名，如 "pd1"
        self.required_resources = []
        self.tracker = None  # 用于跟踪资源依赖 

    @classmethod
    def random_mutation(cls, pd_var="pd1", channel_var="NULL"):
        return cls(
            cqe=random.choice([1, 16, 128, 1024]),
            cq_context="NULL",
            channel=channel_var,
            comp_vector=random.choice([0, 1, 2]),
            wc_flags=random.choice([0, 1, 0xf, 0x1f]),
            comp_mask=random.choice([0, 1, 0x100]),
            flags=random.choice([0, 1, 0xf]),
            parent_domain=pd_var
        )

    def apply(self, ctx: CodeGenContext):
        """Apply this CQ init attr to the context, allocating a new variable if needed."""
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # self.tracker.use("cq", self.cq_context)
            # if self.channel:
            #     self.tracker.use("channel", self.channel)
            if self.parent_domain:
                self.tracker.use("pd", self.parent_domain)
            # 记录所需资源
            # self.required_resources.append({'type': 'cq', 'name': self.cq_context, 'position': 'cq'})
            # if self.channel:
            #     self.required_resources.append({'type': 'channel', 'name': self.channel, 'position': 'channel'})
            if self.parent_domain:
                self.required_resources.append({'type': 'pd', 'name': self.parent_domain, 'position': 'parent_domain'})

            
    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_cq_init_attr_ex")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if val is not None:
                s += emit_assign(varname, field, val)
        return s
