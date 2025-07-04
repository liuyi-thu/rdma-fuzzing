import random
try:
    from .IbvQPCap import IbvQPCap  # for package import
except ImportError:
    from IbvQPCap import IbvQPCap  # for direct script debugging

try:
    from .IbvSge import IbvSge  # for package import
except ImportError:
    from IbvSge import IbvSge  # for direct script debugging

try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging

class IbvRecvWR:
    FIELD_LIST = ["wr_id", "next", "sg_list", "num_sge"]

    def __init__(self, wr_id=None, next_wr=None, sg_list=None, num_sge=None):
        self.wr_id = wr_id
        self.next = next_wr  # 另一个IbvRecvWR对象或None
        self.sg_list = sg_list if sg_list is not None else []  # list[IbvSge]
        self.num_sge = num_sge if num_sge is not None else (len(self.sg_list) if self.sg_list else 0)

    @classmethod
    def random_mutation(cls, chain_length=1):
        # 随机生成单链表
        if chain_length <= 1:
            sges = [IbvSge.random_mutation() for _ in range(random.choice([1, 2]))]
            return cls(
                wr_id=random.randint(1, 0xffffffff),
                next_wr=None,
                sg_list=sges,
                num_sge=len(sges)
            )
        else:
            head = None
            for _ in range(chain_length):
                head = cls(
                    wr_id=random.randint(1, 0xffffffff),
                    next_wr=head,
                    sg_list=[IbvSge.random_mutation()],
                    num_sge=1
                )
            return head

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_recv_wr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        # wr_id
        if self.wr_id is not None:
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
        elif self.num_sge is not None:
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
    wr = IbvRecvWR.random_mutation(chain_length=1)
    print(wr.to_cxx("recv_wr"))