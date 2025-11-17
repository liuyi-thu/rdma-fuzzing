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
    from .value import ConstantValue, EnumValue, FlagValue, IntValue, LocalResourceValue, OptionalValue, ResourceValue
except ImportError:
    from value import ConstantValue, EnumValue, FlagValue, IntValue, LocalResourceValue, OptionalValue, ResourceValue


class IbvMwBindInfo(Attr):
    FIELD_LIST = ["mr", "addr", "length", "mw_access_flags"]
    MUTABLE_FIELDS = ["mr", "addr", "length", "mw_access_flags"]
    EXPORT_FIELDS = ["mr", "addr", "length", "mw_access_flags"]

    def __init__(self, mr=None, addr=None, length=None, mw_access_flags=None):
        self.mr = OptionalValue(
            # ConstantValue(mr) if mr is not None else None, factory=lambda: ConstantValue("NULL")
            ResourceValue(mr, resource_type="mr") if mr is not None else None,
        )  # C++已有变量名或NULL
        # self.addr = OptionalValue(
        #     IntValue(addr) if addr is not None else None, factory=lambda: IntValue(random.randint(0x1000, 0xFFFFF000))
        # )
        if not addr:
            raise ValueError("IbvMwBindInfo requires a valid addr")
        # 应该不能为 NULL，否则会直接挂掉
        # self.addr = LocalResourceValue(value=addr or "buf", resource_type="buf")
        self.addr = f"(uint64_t){self.mr}->addr"  # 直接用 mr 的 addr
        self.length = OptionalValue(
            IntValue(length) if length is not None else None,
            factory=lambda: IntValue(random.choice([0x1000, 0x2000, 0x8000])),
        )
        self.mw_access_flags = OptionalValue(
            FlagValue(mw_access_flags, flag_type="IBV_ACCESS_FLAGS_ENUM") if mw_access_flags is not None else None,
            factory=lambda: FlagValue(random.choice([0, 1, 0xF, 0x1F]), flag_type="IBV_ACCESS_FLAGS_ENUM"),
        )
        self.tracker = None
        self.required_resources = []  # 用于跟踪所需的资源

    @classmethod
    def random_mutation(cls):
        return cls(
            mr=None,  # 实际上应该从mr_map中随机获取一个，不然100%要挂
            addr=random.randint(0x1000, 0xFFFFF000),
            length=random.choice([0x1000, 0x2000, 0x8000]),
            mw_access_flags=random.choice([0, 1, 0xF, 0x1F]),
        )

    def apply(self, ctx: CodeGenContext):
        """Apply this bind info to the context, allocating a new variable if needed."""
        self.required_resources = []
        self.tracker = ctx.tracker if ctx is not None else None
        if self.tracker:
            self.tracker.use("mr", self.mr.get_value())
            self.required_resources.append({"type": "mr", "name": self.mr.get_value(), "position": "mr"})

    def get_required_resources_recursively(self) -> list[dict[str, str]]:
        """Get all required resources recursively."""
        resources = self.required_resources.copy()
        return resources

    def to_cxx(self, varname, ctx: CodeGenContext = None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_mw_bind_info")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in ["addr", "length", "mw_access_flags", "mr"]:
            v = getattr(self, f)
            # print(f"DEBUG: IbvMwBindInfo.to_cxx field={f} value={v}")
            if not v:
                continue
            else:
                # if f == "addr":
                #     # addr 需要取地址符
                #     s += emit_assign(varname, f, v, add_address_symbol=True)
                s += emit_assign(varname, f, v)
        return s


class IbvMwBind(Attr):
    FIELD_LIST = ["wr_id", "send_flags", "bind_info"]
    MUTABLE_FIELDS = ["wr_id", "send_flags", "bind_info"]
    EXPORT_FIELDS = ["wr_id", "send_flags", "bind_info"]

    def __init__(self, wr_id=None, send_flags=None, bind_info=None):
        self.wr_id = OptionalValue(
            IntValue(wr_id) if wr_id is not None else None,
            factory=lambda: IntValue(random.randint(0, 0xFFFFFFFFFFFFFFFF)),
        )
        self.send_flags = OptionalValue(
            FlagValue(send_flags, flag_type="IBV_SEND_FLAGS_ENUM") if send_flags is not None else None,
            factory=lambda: FlagValue(random.choice([0, 1, 2, 0xF, 0x1F]), flag_type="IBV_SEND_FLAGS_ENUM"),
        )
        self.bind_info = OptionalValue(
            bind_info if bind_info is not None else None, factory=lambda: IbvMwBindInfo.random_mutation()
        )
        self.required_resources = []  # 用于跟踪所需的资源

    @classmethod
    def random_mutation(cls):
        return cls(
            wr_id=random.randint(0, 0xFFFFFFFFFFFFFFFF),
            send_flags=random.choice([0, 1, 2, 0xF, 0x1F]),
            bind_info=IbvMwBindInfo.random_mutation(),
        )

    def apply(self, ctx: CodeGenContext):
        """Apply this bind to the context, allocating a new variable if needed."""
        self.required_resources = []
        if self.bind_info:
            self.bind_info.apply(ctx)
            # if ctx:
            #     ctx.alloc_variable("mw_bind_info", "struct ibv_mw_bind_info")
            #     ctx.alloc_variable("mw_bind", "struct ibv_mw_bind")
            #     ctx.tracker.create("mw_bind", "mw_bind", mw_bind=self.bind_info.mr)

    def get_required_resources_recursively(self) -> list[dict[str, str]]:
        """Get all required resources recursively."""
        resources = self.required_resources.copy()
        if self.bind_info:
            resources.extend(self.bind_info.get_required_resources_recursively())
        return resources

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_mw_bind")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        if self.wr_id:
            s += emit_assign(varname, "wr_id", self.wr_id)
        if self.send_flags:
            s += emit_assign(varname, "send_flags", self.send_flags)
        if self.bind_info:
            bind_info_var = varname + "_bind_info"
            s += self.bind_info.to_cxx(bind_info_var, ctx)
            s += f"    {varname}.bind_info = {bind_info_var};\n"
        return s


if __name__ == "__main__":
    bind = IbvMwBind.random_mutation()
    print(bind.to_cxx("mw_bind"))

    for i in range(10000):
        bind.mutate()
    print(bind.to_cxx("mw_bind_mutated"))
    # ctx = CodeGenContext()
    # bind.apply(ctx)
    # print(ctx.get_code())
