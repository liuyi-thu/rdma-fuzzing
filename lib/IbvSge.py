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
    from .value import ConstantValue, DeferredValue, EnumValue, FlagValue, IntValue, OptionalValue, ResourceValue
except ImportError:
    from value import ConstantValue, DeferredValue, EnumValue, FlagValue, IntValue, OptionalValue, ResourceValue


class IbvSge(Attr):
    FIELD_LIST = ["addr", "length", "lkey"]
    MUTABLE_FIELDS = ["mr"]
    EXPORT_FIELDS = ["addr", "length", "lkey"]

    def __init__(self, addr=None, length=None, lkey=None, mr=None):
        self.addr = None
        self.length = length
        self.lkey = None
        if mr is not None:
            # 允许传字符串或 ResourceValue
            if isinstance(mr, ResourceValue):
                self.mr = mr
            else:
                self.mr = ResourceValue(value=str(mr), resource_type="mr")
            self.bind_local_mr(self.mr.value)
        else:
            self.mr = None  # 让上层 on_after_mutate 或 apply(ctx) 来补

    @classmethod
    def random_mutation(cls):
        return cls(
            addr=random.randint(0, 2**48), length=random.choice([0, 1, 1024, 4096]), lkey=random.randint(0, 0xFFFFFFFF)
        )

    def to_cxx(self, varname, ctx=None):
        # if ctx:
        #     ctx.alloc_variable(varname, "struct ibv_sge")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if val:
                s += emit_assign(varname, field, val)
        return s

    def bind_local_mr(self, mr):
        if not mr:
            return
        self.addr = OptionalValue(
            ConstantValue(f"(uint64_t){mr}->addr"),
            factory=lambda: ConstantValue(f"(uint64_t){mr}->addr"),
        )
        if self.length is None:
            self.length = OptionalValue(
                ConstantValue(f"{mr}->length"),
                factory=lambda: ConstantValue(f"{mr}->length"),
            )
        else:
            self.length = OptionalValue(
                ConstantValue(f"std::min<size_t>({self.length},{mr}->length)"),
                factory=lambda: ConstantValue(f"std::min<size_t>({self.length},{mr}->length)"),
            )
        self.lkey = OptionalValue(
            ConstantValue(f"{mr}->lkey"),
            factory=lambda: ConstantValue(f"{mr}->lkey"),
        )


if __name__ == "__main__":
    # For debugging purposes, you can run this file directly to see the output
    # sge = IbvSge.random_mutation()
    # print(sge.to_cxx("sge_instance", ctx=None))
    # for i in range(1000):
    #     sge.mutate()
    #     print(sge.to_cxx(f"sge_instance_{i}", ctx=None))

    sge = IbvSge(addr=0x123456, length=1024, lkey=0xABCDEF)
    print(sge.to_cxx("sge_instance", ctx=None))
