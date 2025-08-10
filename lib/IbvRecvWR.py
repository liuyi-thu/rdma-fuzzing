import random
import sys

sys.setrecursionlimit(200)

try:
    from .IbvQPCap import IbvQPCap  # for package import
except ImportError:
    from IbvQPCap import IbvQPCap  # for direct script debugging

try:
    from .IbvSge import IbvSge  # for package import
except ImportError:
    from IbvSge import IbvSge  # for direct script debugging
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
    from .value import ConstantValue, EnumValue, FlagValue, IntValue, ListValue, OptionalValue, ResourceValue
except ImportError:
    from value import ConstantValue, EnumValue, FlagValue, IntValue, ListValue, OptionalValue, ResourceValue


class IbvRecvWR(Attr):
    # FIELD_LIST = ["wr_id", "next", "sg_list", "num_sge"]
    # FIELD_LIST = ["next_wr"]
    FIELD_LIST = ["sg_list"]
    FIELD_LIST = ["next"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(self, wr_id=None, next_wr=None, sg_list=None, num_sge=None):
        self.wr_id = OptionalValue(IntValue(wr_id, 0xFFFFFFFF) if wr_id is not None else None)  # 可选的wr_id
        # self.next = next_wr  # 另一个IbvRecvWR对象或None
        # self.sg_list = sg_list if sg_list is not None else []  # list[IbvSge]
        # self.num_sge = num_sge if num_sge is not None else (len(self.sg_list) if self.sg_list else 0)
        # self.next = OptionalValue(
        #     ResourceValue(next_wr, "struct ibv_recv_wr") if next_wr is not None else None
        # )
        self.next = OptionalValue(next_wr, factory=lambda: IbvRecvWR.random_mutation())  # 另一个IbvRecvWR对象或None
        self.sg_list = OptionalValue(
            ListValue(value=sg_list, factory=lambda: IbvSge.random_mutation()) if sg_list is not None else None,
            factory=lambda: ListValue([], factory=lambda: IbvSge.random_mutation()),
        )  # list[IbvSge]
        self.num_sge = OptionalValue(
            IntValue(num_sge, 0) if num_sge is not None else (len(self.sg_list) if self.sg_list else 0)
        )

    @classmethod
    def random_mutation(cls, chain_length=1):
        # 随机生成单链表
        if chain_length <= 1:
            sges = [IbvSge.random_mutation() for _ in range(random.choice([1, 2]))]
            return cls(wr_id=random.randint(1, 0xFFFFFFFF), next_wr=None, sg_list=sges, num_sge=len(sges))
        else:
            head = None
            for _ in range(chain_length):
                head = cls(
                    wr_id=random.randint(1, 0xFFFFFFFF), next_wr=head, sg_list=[IbvSge.random_mutation()], num_sge=1
                )
            return head

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_recv_wr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        # wr_id
        if self.wr_id:
            s += emit_assign(varname, "wr_id", self.wr_id)
        # sg_list
        if self.sg_list:
            sge_array_var = varname + "_sges"
            if ctx:
                ctx.alloc_variable(sge_array_var + f"[{len(self.sg_list)}]", "struct ibv_sge")
            for idx, sge in enumerate(self.sg_list):
                s += sge.to_cxx(f"{sge_array_var}[{idx}]", ctx)
            s += f"    {varname}.sg_list = {sge_array_var};\n"
            s += f"    {varname}.num_sge = {len(self.sg_list)};\n"
        if self.num_sge:
            s += emit_assign(varname, "num_sge", self.num_sge)
        # next
        if self.next:
            next_var = varname + "_next"
            s += self.next.to_cxx(next_var, ctx)
            s += f"    {varname}.next = &{next_var};\n"
        else:
            s += f"    {varname}.next = NULL;\n"
        return s


if __name__ == "__main__":
    wr = IbvRecvWR.random_mutation(chain_length=random.randint(1, 5))
    print(wr.to_cxx("recv_wr", ctx=None))
    for i in range(1000):
        wr.mutate()
        print(wr.to_cxx(f"recv_wr_{i}", ctx=None))
        print("-----")
    # wr.mutate()
