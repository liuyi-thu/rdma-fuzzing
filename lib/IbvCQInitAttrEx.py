import random

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


class IbvCQInitAttrEx(Attr):
    FIELD_LIST = ["cqe", "cq_context", "channel", "comp_vector", "wc_flags", "comp_mask", "flags", "parent_domain"]
    MUTABLE_FIELDS = ["cqe", "cq_context", "channel", "comp_vector", "wc_flags", "comp_mask", "flags", "parent_domain"]

    def __init__(
        self,
        cqe=None,
        cq_context=None,
        channel=None,
        comp_vector=None,
        wc_flags=None,
        comp_mask=None,
        flags=None,
        parent_domain=None,
    ):
        self.cqe = OptionalValue(
            IntValue(cqe) if cqe is not None else None, factory=lambda: IntValue(random.choice([1, 16, 128, 1024]))
        )
        self.cq_context = OptionalValue(
            ConstantValue(cq_context) if cq_context is not None else None, factory=lambda: ConstantValue("NULL")
        )  # C++已有变量名或NULL
        self.channel = OptionalValue(
            ConstantValue(channel) if channel is not None else None, factory=lambda: ConstantValue("NULL")
        )
        # 这里使用 IntValue 包装 comp_vector，确保它是一个整数值
        # 如果 comp_vector 为 None，则使用 factory 生成一个随机整数
        # 这里的 factory 函数返回一个 IntValue 实例，确保类型一致
        # 注意：如果 comp_vector 是一个变量名（字符串），则需要在使用时转换为 IntValue
        # 例如：如果 comp_vector 是 "0" 或 "1" 等字符串，则需要转换为 IntValue(0) 或 IntValue(1)
        self.comp_vector = OptionalValue(
            IntValue(comp_vector) if comp_vector is not None else None,
            factory=lambda: IntValue(random.choice([0, 1, 2])),
        )
        self.wc_flags = OptionalValue(
            IntValue(wc_flags) if wc_flags is not None else None,
            factory=lambda: IntValue(random.choice([0, 1, 0xF, 0x1F])),
        )
        self.comp_mask = OptionalValue(
            IntValue(comp_mask) if comp_mask is not None else None,
            factory=lambda: IntValue(random.choice([0, 1, 0x100])),
        )
        self.flags = OptionalValue(
            IntValue(flags) if flags is not None else None, factory=lambda: IntValue(random.choice([0, 1, 0xF]))
        )
        # self.parent_domain = ConstantValue(parent_domain)  # C++已有变量名，如 "pd1"
        self.parent_domain = OptionalValue(
            ConstantValue(parent_domain) if parent_domain is not None else None, factory=lambda: ConstantValue("pd1")
        )  # 默认父域为 "pd1"

        self.required_resources = []
        self.tracker = None  # 用于跟踪资源依赖

    @classmethod
    def random_mutation(cls, pd_var="pd1", channel_var="NULL"):
        return cls(
            cqe=random.choice([1, 16, 128, 1024]),
            cq_context="NULL",
            channel=channel_var,
            comp_vector=random.choice([0, 1, 2]),
            wc_flags=random.choice([0, 1, 0xF, 0x1F]),
            comp_mask=random.choice([0, 1, 0x100]),
            flags=random.choice([0, 1, 0xF]),
            parent_domain=pd_var,
        )

    def apply(self, ctx: CodeGenContext):
        """Apply this CQ init attr to the context, allocating a new variable if needed."""
        self.required_resources = []
        self.tracker = ctx.tracker if ctx is not None else None
        if self.tracker:
            # self.tracker.use("cq", self.cq_context)
            # if self.channel:
            #     self.tracker.use("channel", self.channel)
            if self.parent_domain.is_not_none():
                self.tracker.use("pd", self.parent_domain.get_value())
            # 记录所需资源
            # self.required_resources.append({'type': 'cq', 'name': self.cq_context, 'position': 'cq'})
            # if self.channel:
            #     self.required_resources.append({'type': 'channel', 'name': self.channel, 'position': 'channel'})
            if self.parent_domain.is_not_none():
                self.required_resources.append(
                    {"type": "pd", "name": self.parent_domain.get_value(), "position": "parent_domain"}
                )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_cq_init_attr_ex")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if not val:
                continue
            else:
                s += emit_assign(varname, field, val)
        return s


if __name__ == "__main__":
    attr = IbvCQInitAttrEx.random_mutation()
    print(attr.to_cxx("cq_attr"))
    for i in range(10000):
        attr.mutate()
    print(attr.to_cxx("cq_attr"))
