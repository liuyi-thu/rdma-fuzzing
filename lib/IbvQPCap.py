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


class IbvQPCap(Attr):
    FIELD_LIST = ["max_send_wr", "max_recv_wr", "max_send_sge", "max_recv_sge", "max_inline_data"]
    MUTABLE_FIELDS = FIELD_LIST
    EXPORT_FIELDS = ["max_send_wr", "max_recv_wr", "max_send_sge", "max_recv_sge", "max_inline_data"]

    def __init__(self, max_send_wr=None, max_recv_wr=None, max_send_sge=None, max_recv_sge=None, max_inline_data=None):
        self.max_send_wr = OptionalValue(
            IntValue(max_send_wr) if max_send_wr is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.max_recv_wr = OptionalValue(
            IntValue(max_recv_wr) if max_recv_wr is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.max_send_sge = OptionalValue(
            IntValue(max_send_sge) if max_send_sge is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.max_recv_sge = OptionalValue(
            IntValue(max_recv_sge) if max_recv_sge is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.max_inline_data = OptionalValue(
            IntValue(max_inline_data) if max_inline_data is not None else None, factory=lambda: IntValue(0)
        )

    @classmethod
    def random_mutation(cls):
        return cls(
            max_send_wr=random.choice([0, 1, 16, 1024, 2**16]),
            max_recv_wr=random.choice([0, 1, 16, 1024, 2**16]),
            max_send_sge=random.choice([0, 1, 2, 16]),
            max_recv_sge=random.choice([0, 1, 2, 16]),
            max_inline_data=random.choice([0, 1, 64, 256, 4096]),
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_qp_cap")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if val:
                s += emit_assign(varname, field, val)
        return s


if __name__ == "__main__":
    # Example usage
    qp_cap = IbvQPCap.random_mutation()
    print(qp_cap.to_cxx("qp_cap"))
    # This will print the C++ code to initialize an ibv_qp_cap structure with random values.

    for i in range(10000):
        qp_cap.mutate()
    print(qp_cap.to_cxx("qp_cap"))
