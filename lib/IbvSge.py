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
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(self, addr=None, length=None, lkey=None, local_mr_id=None):
        # self.addr = OptionalValue(IntValue(addr) if addr is not None else None, factory=lambda: IntValue(0))
        self.addr = OptionalValue(
            DeferredValue.from_id("local.MR", addr, "addr", "uint64_t") if addr is not None else None,
            factory=lambda: DeferredValue.from_id("local.MR", None, "addr", "uint64_t"),
        )  # TODO: may cause errors
        self.length = OptionalValue(IntValue(length) if length is not None else None, factory=lambda: IntValue(0))
        # self.length = OptionalValue(
        #     DeferredValue.from_id("local.MR", length, "length", "uint32_t") if length is not None else None,
        #     factory=lambda: DeferredValue.from_id("local.MR", None, "length", "uint32_t"),
        # )
        # self.lkey = OptionalValue(IntValue(lkey) if lkey is not None else None, factory=lambda: IntValue(0))
        self.lkey = OptionalValue(
            DeferredValue.from_id("local.MR", lkey, "lkey", "uint32_t") if lkey is not None else None,
            factory=lambda: DeferredValue.from_id("local.MR", None, "lkey", "uint32_t"),
        )
        self.local_mr_id = local_mr_id  # for resolving addr/length/lkey from MR # TODO: 还没有改成Value

    @classmethod
    def random_mutation(cls):
        return cls(
            addr=random.randint(0, 2**48), length=random.choice([0, 1, 1024, 4096]), lkey=random.randint(0, 0xFFFFFFFF)
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_sge")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if val:
                s += emit_assign(varname, field, val)
        return s


if __name__ == "__main__":
    # For debugging purposes, you can run this file directly to see the output
    # sge = IbvSge.random_mutation()
    # print(sge.to_cxx("sge_instance", ctx=None))
    # for i in range(1000):
    #     sge.mutate()
    #     print(sge.to_cxx(f"sge_instance_{i}", ctx=None))

    sge = IbvSge(addr=0x123456, length=1024, lkey=0xABCDEF)
    print(sge.to_cxx("sge_instance", ctx=None))
