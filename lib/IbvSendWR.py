import random

try:
    from .attr import Attr
except ImportError:
    from attr import Attr

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

try:
    from .value import (
        ConstantValue,
        DeferredValue,
        EnumValue,
        FlagValue,
        IntValue,
        ListValue,
        OptionalValue,
        ResourceValue,
    )
except ImportError:
    from value import (
        ConstantValue,
        DeferredValue,
        EnumValue,
        FlagValue,
        IntValue,
        ListValue,
        OptionalValue,
        ResourceValue,
    )

IBV_WR_OPCODE_ENUM = {
    0: "IBV_WR_RDMA_WRITE",
    1: "IBV_WR_RDMA_WRITE_WITH_IMM",
    2: "IBV_WR_SEND",
    3: "IBV_WR_SEND_WITH_IMM",
    4: "IBV_WR_RDMA_READ",
    5: "IBV_WR_ATOMIC_CMP_AND_SWP",
    6: "IBV_WR_ATOMIC_FETCH_AND_ADD",
    7: "IBV_WR_LOCAL_INV",
    8: "IBV_WR_BIND_MW",
    9: "IBV_WR_SEND_WITH_INV",
    10: "IBV_WR_TSO",
    11: "IBV_WR_DRIVER1",
    14: "IBV_WR_FLUSH",
    15: "IBV_WR_ATOMIC_WRITE",
}


class IbvRdmaInfo(Attr):
    FIELD_LIST = ["remote_addr", "rkey"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(self, remote_addr=None, rkey=None):
        # self.remote_addr = IntValue(remote_addr, 2**64 - 1) if remote_addr is not None else None
        # self.rkey = IntValue(rkey, 0xFFFFFFFF) if rkey is not None else None
        self.remote_addr = (
            DeferredValue.from_id("remote.MR", remote_addr, "addr", "uint64_t") if remote_addr is not None else None
        )
        self.rkey = DeferredValue.from_id("remote.MR", rkey, "rkey", "uint32_t") if rkey is not None else None
        # TODO: 这里没使用OptionalValue

    @classmethod
    def random_mutation(cls):
        return cls(remote_addr=random.randint(0, 2**64 - 1), rkey=random.randint(0, 0xFFFFFFFF))

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct { uint64_t remote_addr; uint32_t rkey; }")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v:
                s += emit_assign(varname, f, v)
        return s


class IbvAtomicInfo(Attr):
    FIELD_LIST = ["remote_addr", "compare_add", "swap", "rkey"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(self, remote_addr=None, compare_add=None, swap=None, rkey=None):
        self.compare_add = IntValue(compare_add, 2**64 - 1) if compare_add is not None else None
        self.swap = IntValue(swap, 2**64 - 1) if swap is not None else None
        self.remote_addr = (
            DeferredValue.from_id("remote.MR", remote_addr, "addr", "uint64_t") if remote_addr is not None else None
        )
        self.rkey = DeferredValue.from_id("remote.MR", rkey, "rkey", "uint32_t") if rkey is not None else None

    @classmethod
    def random_mutation(cls):
        return cls(
            remote_addr=random.randint(0, 2**64 - 1),
            compare_add=random.randint(0, 2**64 - 1),
            swap=random.randint(0, 2**64 - 1),
            rkey=random.randint(0, 0xFFFFFFFF),
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(
                varname, "struct { uint64_t remote_addr; uint64_t compare_add; uint64_t swap; uint32_t rkey; }"
            )
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v:
                s += emit_assign(varname, f, v)
        return s


class IbvUdInfo(Attr):
    FIELD_LIST = ["ah", "remote_qpn", "remote_qkey"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(self, ah=None, remote_qpn=None, remote_qkey=None):
        self.ah = ResourceValue(ah, "ah") if ah is not None else None  # 可适配为现有ah变量
        self.remote_qpn = IntValue(remote_qpn, 2**24 - 1) if remote_qpn is not None else None
        self.remote_qkey = IntValue(remote_qkey, 2**32 - 1) if remote_qkey is not None else None

    @classmethod
    def random_mutation(cls):
        return cls(
            ah=None,  # 可适配为现有ah变量
            remote_qpn=random.randint(0, 2**24 - 1),
            remote_qkey=random.randint(0, 2**32 - 1),
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct { struct ibv_ah* ah; uint32_t remote_qpn; uint32_t remote_qkey; }")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is not None:
                s += emit_assign(varname, f, v)
        return s


class IbvBindMwInfo(Attr):
    FIELD_LIST = ["mw", "rkey", "bind_info"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(self, mw=None, rkey=None, bind_info=None):
        self.mw = ResourceValue(mw, "struct ibv_mw") if mw is not None else None  # 可适配为现有mw变量
        self.rkey = IntValue(rkey, 0xFFFFFFFF) if rkey is not None else None
        self.bind_info = bind_info  # 可进一步建模成IbvMwBindInfo

    @classmethod
    def random_mutation(cls):
        return cls(
            mw=None,  # 或者 f"mw_{random.randint(0,100)}"
            rkey=random.randint(0, 0xFFFFFFFF),
            bind_info=None,
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(
                varname, "struct { struct ibv_mw* mw; uint32_t rkey; struct ibv_mw_bind_info bind_info; }"
            )
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v:
                if f == "bind_info":
                    bind_info_var = varname + "_bind_info"
                    s += v.to_cxx(bind_info_var, ctx)
                    s += f"    {varname}.bind_info = {bind_info_var};\n"
                else:
                    s += emit_assign(varname, f, v)
        return s


# 进一步建模struct ibv_mw_bind_info:
# class IbvMwBindInfo(Attr):
#     FIELD_LIST = ["addr", "length", "mw_access_flags"]
#     MUTABLE_FIELDS = FIELD_LIST

#     def __init__(self, addr=None, length=None, mw_access_flags=None):
#         self.addr = IntValue(addr, 2**64 - 1) if addr is not None else None
#         self.length = IntValue(length, 2**32 - 1) if length is not None else None
#         self.mw_access_flags = (
#             FlagValue(mw_access_flags, "IBV_ACCESS_FLAGS_ENUM") if mw_access_flags is not None else None
#         )

#     @classmethod
#     def random_mutation(cls):
#         return cls(
#             addr=random.randint(0, 2**64 - 1),
#             length=random.randint(0, 2**32 - 1),
#             mw_access_flags=random.randint(0, 0xFFFF),
#         )

#     def to_cxx(self, varname, ctx=None):
#         if ctx:
#             ctx.alloc_variable(varname, "struct ibv_mw_bind_info")
#         s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
#         for f in self.FIELD_LIST:
#             v = getattr(self, f)
#             if v is not None:
#                 s += emit_assign(varname, f, v)
#         return s


class IbvMwBindInfo(Attr):
    FIELD_LIST = ["mr", "addr", "length", "mw_access_flags"]
    MUTABLE_FIELDS = ["mr", "addr", "length", "mw_access_flags"]

    def __init__(self, mr=None, addr=None, length=None, mw_access_flags=None):
        self.mr = OptionalValue(
            # ConstantValue(mr) if mr is not None else None, factory=lambda: ConstantValue("NULL")
            ResourceValue(mr, resource_type="mr") if mr is not None else None,
        )  # C++已有变量名或NULL
        self.addr = OptionalValue(
            IntValue(addr) if addr is not None else None, factory=lambda: IntValue(random.randint(0x1000, 0xFFFFF000))
        )
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
            if not v:
                continue
            else:
                s += emit_assign(varname, f, v)
        return s


class IbvTsoInfo(Attr):
    FIELD_LIST = ["hdr", "hdr_sz", "mss"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(self, hdr=None, hdr_sz=None, mss=None):
        self.hdr = ResourceValue(hdr, "void*") if hdr is not None else None  # 可适配为现有hdr变量
        self.hdr_sz = IntValue(hdr_sz, 4096) if hdr_sz is not None else None
        self.mss = IntValue(mss, 0xFFFF) if mss is not None else None

    @classmethod
    def random_mutation(cls):
        return cls(
            hdr=None,  # 或 f"tso_hdr_{random.randint(0,100)}"
            hdr_sz=random.randint(0, 4096),
            mss=random.choice([1460, 9000, 4096, 512]),
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct { void* hdr; uint16_t hdr_sz; uint16_t mss; }")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is not None:
                s += emit_assign(varname, f, v)
        return s


class IbvXrcInfo(Attr):
    FIELD_LIST = ["remote_srqn"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(self, remote_srqn=None):
        self.remote_srqn = IntValue(remote_srqn, 2**32 - 1) if remote_srqn is not None else None

    @classmethod
    def random_mutation(cls):
        return cls(remote_srqn=random.randint(0, 2**32 - 1))

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct { uint32_t remote_srqn; }")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is not None:
                s += emit_assign(varname, f, v)
        return s


class IbvSendWR(Attr):
    FIELD_LIST = [
        "wr_id",
        "next",
        "sg_list",
        "num_sge",
        "opcode",
        "send_flags",
        "imm_data",
        "invalidate_rkey",
        "rdma",
        "atomic",
        "ud",
        "xrc",
        "bind_mw",
        "tso",
    ]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(
        self,
        wr_id=None,
        next_wr=None,
        sg_list=None,
        num_sge=None,
        opcode=None,
        send_flags=None,
        imm_data=None,
        invalidate_rkey=None,
        rdma=None,
        atomic=None,
        ud=None,
        xrc=None,
        bind_mw=None,
        tso=None,
    ):
        self.wr_id = OptionalValue(IntValue(wr_id, 0xFFFFFFFF) if wr_id is not None else None)
        self.next = OptionalValue(next_wr, factory=lambda: IbvSendWR.random_mutation())  # 另一个IbvSendWR对象或None
        self.sg_list = OptionalValue(
            ListValue(value=sg_list, factory=lambda: IbvSge.random_mutation()) if sg_list is not None else None
        )  # list[IbvSge]
        self.num_sge = OptionalValue(
            IntValue(num_sge, 0) if num_sge is not None else (len(self.sg_list) if self.sg_list else 0)
        )
        self.opcode = OptionalValue(EnumValue(opcode, "IBV_WR_OPCODE_ENUM") if opcode is not None else None)
        self.send_flags = OptionalValue(
            FlagValue(send_flags, "IBV_SEND_FLAGS_ENUM") if send_flags is not None else None
        )
        # union
        self.imm_data = OptionalValue(IntValue(imm_data, 0xFFFFFFFF) if imm_data is not None else None)
        self.invalidate_rkey = OptionalValue(
            IntValue(invalidate_rkey, 0xFFFFFFFF) if invalidate_rkey is not None else None
        )
        self.rdma = OptionalValue(rdma, factory=lambda: IbvRdmaInfo.random_mutation())
        self.atomic = OptionalValue(atomic, factory=lambda: IbvAtomicInfo.random_mutation())
        self.ud = OptionalValue(ud, factory=lambda: IbvUdInfo.random_mutation())
        self.xrc = OptionalValue(xrc, factory=lambda: IbvXrcInfo.random_mutation())
        self.bind_mw = OptionalValue(bind_mw, factory=lambda: IbvBindMwInfo.random_mutation())
        self.tso = OptionalValue(tso, factory=lambda: IbvTsoInfo.random_mutation())

    @classmethod
    def random_mutation(cls, chain_length=1):
        if chain_length <= 1:
            sg_list = [IbvSge.random_mutation() for _ in range(random.choice([0, 1, 2, 4]))]
            opcode_val = random.choice(list(IBV_WR_OPCODE_ENUM.values()))
            fields = {}
            # 1. opcode驱动的union分支
            if opcode_val in (1, 3):  # *_WITH_IMM
                fields["imm_data"] = random.randint(0, 0xFFFFFFFF)
            if opcode_val == 7:  # *_INV
                fields["invalidate_rkey"] = random.randint(0, 0xFFFFFFFF)
            if opcode_val in (0, 1, 4):  # RDMA相关
                fields["rdma"] = IbvRdmaInfo.random_mutation()
            if opcode_val in (5, 6, 15):  # ATOMIC
                fields["atomic"] = IbvAtomicInfo.random_mutation()
            if opcode_val == 2:  # UD
                fields["ud"] = IbvUdInfo.random_mutation()
            # XRC通常是QP类型相关，但也可混淆
            if random.random() < 0.2:
                fields["xrc"] = IbvXrcInfo.random_mutation()
            # bind_mw
            if opcode_val == 8 or random.random() < 0.1:
                fields["bind_mw"] = IbvBindMwInfo.random_mutation()
            # TSO
            if opcode_val == 10 or random.random() < 0.05:
                fields["tso"] = IbvTsoInfo.random_mutation()

            # 支持链表式WR
            next_wr = None
            # if random.random() < 0.15:
            #     next_wr = f"wr_{random.randint(1,9999)}"  # 这里给变量名占位，真正链表拼接时可递归生成

            return cls(
                wr_id=random.randint(0, 2**64 - 1),
                next_wr=next_wr,
                sg_list=sg_list,
                num_sge=len(sg_list),
                opcode=opcode_val,
                send_flags=random.randint(0, 0xFFFF),
                **fields,
            )
        else:
            head = None
            for _ in range(chain_length):
                sg_list = [IbvSge.random_mutation() for _ in range(random.choice([0, 1, 2, 4]))]
                opcode_val = random.choice(list(IBV_WR_OPCODE_ENUM.values()))
                fields = {}
                # 1. opcode驱动的union分支
                if opcode_val in (1, 3):  # *_WITH_IMM
                    fields["imm_data"] = random.randint(0, 0xFFFFFFFF)
                if opcode_val == 7:  # *_INV
                    fields["invalidate_rkey"] = random.randint(0, 0xFFFFFFFF)
                if opcode_val in (0, 1, 4):  # RDMA相关
                    fields["rdma"] = IbvRdmaInfo.random_mutation()
                if opcode_val in (5, 6, 15):  # ATOMIC
                    fields["atomic"] = IbvAtomicInfo.random_mutation()
                if opcode_val == 2:  # UD
                    fields["ud"] = IbvUdInfo.random_mutation()
                # XRC通常是QP类型相关，但也可混淆
                if random.random() < 0.2:
                    fields["xrc"] = IbvXrcInfo.random_mutation()
                # bind_mw
                if opcode_val == 8 or random.random() < 0.1:
                    fields["bind_mw"] = IbvBindMwInfo.random_mutation()
                # TSO
                if opcode_val == 10 or random.random() < 0.05:
                    fields["tso"] = IbvTsoInfo.random_mutation()
                head = cls(
                    wr_id=random.randint(0, 2**64 - 1),
                    next_wr=head,
                    sg_list=sg_list,
                    num_sge=1,
                    opcode=opcode_val,
                    send_flags=random.randint(0, 0xFFFF),
                    **fields,
                )
            return head

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_send_wr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        enum_fields = {"opcode": IBV_WR_OPCODE_ENUM}
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if not val:
                continue
            if field == "sg_list":
                if len(val) > 0:
                    # 生成sge数组
                    for idx, sge in enumerate(val):
                        sge_var = f"{varname}_sge_{idx}"
                        s += sge.to_cxx(sge_var, ctx)
                    s += f"    {varname}.sg_list = &{varname}_sge_0;\n"
                continue
            # union/struct字段
            if field == "rdma":
                rdma_var = varname + "_rdma"
                s += val.to_cxx(rdma_var, ctx)
                for f in IbvRdmaInfo.FIELD_LIST:
                    s += f"    {varname}.wr.rdma.{f} = {rdma_var}.{f};\n"
            elif field == "atomic":
                atomic_var = varname + "_atomic"
                s += val.to_cxx(atomic_var, ctx)
                for f in IbvAtomicInfo.FIELD_LIST:
                    s += f"    {varname}.wr.atomic.{f} = {atomic_var}.{f};\n"
            elif field == "ud":
                ud_var = varname + "_ud"
                s += val.to_cxx(ud_var, ctx)
                for f in IbvUdInfo.FIELD_LIST:
                    s += f"    {varname}.wr.ud.{f} = {ud_var}.{f};\n"
            elif field == "xrc":
                xrc_var = varname + "_xrc"
                s += val.to_cxx(xrc_var, ctx)
                for f in IbvXrcInfo.FIELD_LIST:
                    s += f"    {varname}.qp_type.xrc.{f} = {xrc_var}.{f};\n"
            elif field == "bind_mw":
                bind_mw_var = varname + "_bind_mw"
                s += val.to_cxx(bind_mw_var, ctx)
                for f in IbvBindMwInfo.FIELD_LIST:
                    s += f"    {varname}.bind_mw.{f} = {bind_mw_var}.{f};\n"
            elif field == "tso":
                tso_var = varname + "_tso"
                s += val.to_cxx(tso_var, ctx)
                for f in IbvTsoInfo.FIELD_LIST:
                    s += f"    {varname}.tso.{f} = {tso_var}.{f};\n"
            elif field in ["imm_data", "invalidate_rkey"]:
                # union: 直接赋值即可，假定调用方保证只有一个有效
                s += emit_assign(varname, field, val)
            elif field == "next_wr":
                # 假设 next 是下一个wr的变量名
                s += f"    {varname}.next = {val};\n"
            else:
                s += emit_assign(varname, field, val, enum_fields)
        return s


if __name__ == "__main__":
    wr = IbvSendWR.random_mutation(chain_length=random.randint(1, 5))
    print(wr.to_cxx("recv_wr", ctx=None))
    for i in range(1000):
        wr.mutate()
        print(wr.to_cxx(f"recv_wr_{i}", ctx=None))
        print("-----")
    # wr.mutate()
