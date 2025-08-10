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

IBV_WQ_TYPE_ENUM = {
    0: "IBV_WQT_RQ",  # Receive Queue
    1: "IBV_WQT_RQ_WITH_SRQ",  # Receive Queue with SRQ
    2: "IBV_WQT_SRQ",  # Shared Receive Queue
    # 若有更多类型可补充
}


class IbvWQInitAttr(Attr):
    FIELD_LIST = ["wq_context", "wq_type", "max_wr", "max_sge", "pd", "cq", "comp_mask", "create_flags"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(
        self,
        wq_context=None,
        wq_type=None,
        max_wr=None,
        max_sge=None,
        pd=None,
        cq=None,
        comp_mask=None,
        create_flags=None,
    ):
        self.wq_context = OptionalValue(
            ConstantValue(wq_context) if wq_context is not None else None, factory=lambda: ConstantValue("NULL")
        )
        self.wq_type = OptionalValue(
            EnumValue(wq_type, enum_type="IBV_WQ_TYPE_ENUM") if wq_type is not None else None,
            factory=lambda: EnumValue(0, enum_type="IBV_WQ_TYPE_ENUM"),
        )
        self.max_wr = OptionalValue(IntValue(max_wr) if max_wr is not None else None, factory=lambda: IntValue(1))
        self.max_sge = OptionalValue(IntValue(max_sge) if max_sge is not None else None, factory=lambda: IntValue(1))
        self.pd = OptionalValue(
            ResourceValue(value=pd, resource_type="pd") if pd is not None else None,
            factory=lambda: ResourceValue(value="pd1", resource_type="pd"),
        )
        self.cq = OptionalValue(
            ResourceValue(value=cq, resource_type="cq") if cq is not None else None,
            factory=lambda: ResourceValue(value="cq1", resource_type="cq"),
        )
        self.comp_mask = OptionalValue(
            IntValue(comp_mask) if comp_mask is not None else None, factory=lambda: IntValue(0)
        )
        self.create_flags = OptionalValue(
            FlagValue(create_flags, flag_type="IBV_WQ_FLAGS") if create_flags is not None else None,
            factory=lambda: FlagValue(0, flag_type="IBV_WQ_FLAGS"),
        )

        self.tracker = None
        self.required_resources = []  # 用于跟踪所需的资源

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
            create_flags=random.choice([0, 1, 0x10]),
        )

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            if self.pd.is_not_none():
                self.tracker.use("pd", self.pd.get_value())
                self.required_resources.append({"type": "pd", "name": self.pd.get_value(), "position": "pd"})
            if self.cq.is_not_none():
                self.tracker.use("cq", self.cq.get_value())
                self.required_resources.append({"type": "cq", "name": self.cq.get_value(), "position": "cq"})
            # 记录所需资源
            # self.required_resources.append({'type': 'wq', 'name': self.wq_context, 'position': 'wq_context'})

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_wq_init_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        enum_fields = {"wq_type": IBV_WQ_TYPE_ENUM}
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if val:
                # s += emit_assign(varname, field, val, enums=enum_fields)
                s += emit_assign(varname, field, val)
        return s


if __name__ == "__main__":
    # For debugging purposes, you can run this file directly
    attr = IbvWQInitAttr.random_mutation()
    print(attr.to_cxx("wq_init_attr", CodeGenContext()))
    # This will generate a random IbvWQInitAttr and print its C++ representation
    for i in range(1000):
        attr = IbvWQInitAttr.random_mutation()
        print(attr.to_cxx(f"wq_init_attr_{i}", CodeGenContext()))
        print("\n")
