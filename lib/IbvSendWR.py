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
    
IBV_WR_OPCODE_ENUM = {
    0: 'IBV_WR_RDMA_WRITE',
    1: 'IBV_WR_RDMA_WRITE_WITH_IMM',
    2: 'IBV_WR_SEND',
    3: 'IBV_WR_SEND_WITH_IMM',
    4: 'IBV_WR_RDMA_READ',
    5: 'IBV_WR_ATOMIC_CMP_AND_SWP',
    6: 'IBV_WR_ATOMIC_FETCH_AND_ADD',
    7: 'IBV_WR_LOCAL_INV',
    8: 'IBV_WR_BIND_MW',
    9: 'IBV_WR_SEND_WITH_INV',
    10: 'IBV_WR_TSO',
    11: 'IBV_WR_DRIVER1',
    14: 'IBV_WR_FLUSH',
    15: 'IBV_WR_ATOMIC_WRITE'
}

    
class IbvRdmaInfo:
    FIELD_LIST = ["remote_addr", "rkey"]
    def __init__(self, remote_addr=None, rkey=None):
        self.remote_addr = remote_addr
        self.rkey = rkey

    @classmethod
    def random_mutation(cls):
        return cls(remote_addr=random.randint(0, 2**64-1), rkey=random.randint(0, 0xffffffff))

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct { uint64_t remote_addr; uint32_t rkey; }")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is not None:
                s += emit_assign(varname, f, v)
        return s

class IbvAtomicInfo:
    FIELD_LIST = ["remote_addr", "compare_add", "swap", "rkey"]
    def __init__(self, remote_addr=None, compare_add=None, swap=None, rkey=None):
        self.remote_addr = remote_addr
        self.compare_add = compare_add
        self.swap = swap
        self.rkey = rkey

    @classmethod
    def random_mutation(cls):
        return cls(
            remote_addr=random.randint(0, 2**64-1),
            compare_add=random.randint(0, 2**64-1),
            swap=random.randint(0, 2**64-1),
            rkey=random.randint(0, 0xffffffff)
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct { uint64_t remote_addr; uint64_t compare_add; uint64_t swap; uint32_t rkey; }")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is not None:
                s += emit_assign(varname, f, v)
        return s

class IbvUdInfo:
    FIELD_LIST = ["ah", "remote_qpn", "remote_qkey"]
    def __init__(self, ah=None, remote_qpn=None, remote_qkey=None):
        self.ah = ah
        self.remote_qpn = remote_qpn
        self.remote_qkey = remote_qkey

    @classmethod
    def random_mutation(cls):
        return cls(
            ah=None,  # 可适配为现有ah变量
            remote_qpn=random.randint(0, 2**24-1),
            remote_qkey=random.randint(0, 2**32-1)
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

class IbvBindMwInfo:
    FIELD_LIST = ["mw", "rkey", "bind_info"]
    def __init__(self, mw=None, rkey=None, bind_info=None):
        self.mw = mw          # C++已有变量名或者None
        self.rkey = rkey
        self.bind_info = bind_info  # 可进一步建模成IbvMwBindInfo

    @classmethod
    def random_mutation(cls):
        return cls(
            mw=None,  # 或者 f"mw_{random.randint(0,100)}"
            rkey=random.randint(0, 0xffffffff),
            bind_info=None
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct { struct ibv_mw* mw; uint32_t rkey; struct ibv_mw_bind_info bind_info; }")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is not None:
                if f == "bind_info" and v is not None:
                    bind_info_var = varname + "_bind_info"
                    s += v.to_cxx(bind_info_var, ctx)
                    s += f"    {varname}.bind_info = {bind_info_var};\n"
                else:
                    s += emit_assign(varname, f, v)
        return s

# 进一步建模struct ibv_mw_bind_info:
class IbvMwBindInfo:
    FIELD_LIST = ["addr", "length", "mw_access_flags"]
    def __init__(self, addr=None, length=None, mw_access_flags=None):
        self.addr = addr
        self.length = length
        self.mw_access_flags = mw_access_flags

    @classmethod
    def random_mutation(cls):
        return cls(
            addr=random.randint(0, 2**64-1),
            length=random.randint(0, 2**32-1),
            mw_access_flags=random.randint(0, 0xffff)
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_mw_bind_info")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is not None:
                s += emit_assign(varname, f, v)
        return s

class IbvTsoInfo:
    FIELD_LIST = ["hdr", "hdr_sz", "mss"]
    def __init__(self, hdr=None, hdr_sz=None, mss=None):
        self.hdr = hdr       # 通常是C++已有变量指针名
        self.hdr_sz = hdr_sz
        self.mss = mss

    @classmethod
    def random_mutation(cls):
        return cls(
            hdr=None,  # 或 f"tso_hdr_{random.randint(0,100)}"
            hdr_sz=random.randint(0, 4096),
            mss=random.choice([1460, 9000, 4096, 512])
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

class IbvXrcInfo:
    FIELD_LIST = ["remote_srqn"]
    def __init__(self, remote_srqn=None):
        self.remote_srqn = remote_srqn

    @classmethod
    def random_mutation(cls):
        return cls(remote_srqn=random.randint(0, 2**32-1))

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct { uint32_t remote_srqn; }")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for f in self.FIELD_LIST:
            v = getattr(self, f)
            if v is not None:
                s += emit_assign(varname, f, v)
        return s
    
class IbvSendWR:
    FIELD_LIST = [
        "wr_id", "next", "sg_list", "num_sge", "opcode", "send_flags",
        "imm_data", "invalidate_rkey", "rdma", "atomic", "ud",
        "xrc", "bind_mw", "tso"
    ]

    def __init__(
        self, wr_id=None, next=None, sg_list=None, num_sge=None, opcode=None, send_flags=None,
        imm_data=None, invalidate_rkey=None, rdma=None, atomic=None, ud=None, xrc=None,
        bind_mw=None, tso=None
    ):
        self.wr_id = wr_id
        self.next = next              # 下一个IbvSendWR变量名或None
        self.sg_list = sg_list        # list of IbvSge 或 None
        self.num_sge = num_sge
        self.opcode = opcode
        self.send_flags = send_flags
        # union
        self.imm_data = imm_data
        self.invalidate_rkey = invalidate_rkey
        self.rdma = rdma              # IbvRdmaInfo
        self.atomic = atomic          # IbvAtomicInfo
        self.ud = ud                  # IbvUdInfo
        self.xrc = xrc                # IbvXrcInfo
        self.bind_mw = bind_mw        # IbvBindMwInfo
        self.tso = tso                # IbvTsoInfo
    @classmethod
    def random_mutation(cls):
        sg_list = [IbvSge.random_mutation() for _ in range(random.choice([0, 1, 2, 4]))]
        opcode_val = random.choice(list(IBV_WR_OPCODE_ENUM.keys()))
        fields = {}
        # 1. opcode驱动的union分支
        if opcode_val in (1, 3):  # *_WITH_IMM
            fields['imm_data'] = random.randint(0, 0xffffffff)
        if opcode_val == 7:  # *_INV
            fields['invalidate_rkey'] = random.randint(0, 0xffffffff)
        if opcode_val in (0, 1, 4):  # RDMA相关
            fields['rdma'] = IbvRdmaInfo.random_mutation()
        if opcode_val in (5, 6, 15):  # ATOMIC
            fields['atomic'] = IbvAtomicInfo.random_mutation()
        if opcode_val == 2:  # UD
            fields['ud'] = IbvUdInfo.random_mutation()
        # XRC通常是QP类型相关，但也可混淆
        if random.random() < 0.2:
            fields['xrc'] = IbvXrcInfo.random_mutation()
        # bind_mw
        if opcode_val == 8 or random.random() < 0.1:
            fields['bind_mw'] = IbvBindMwInfo.random_mutation()
        # TSO
        if opcode_val == 10 or random.random() < 0.05:
            fields['tso'] = IbvTsoInfo.random_mutation()

        # 支持链表式WR
        next_wr = None
        # if random.random() < 0.15:
        #     next_wr = f"wr_{random.randint(1,9999)}"  # 这里给变量名占位，真正链表拼接时可递归生成

        return cls(
            wr_id=random.randint(0, 2**64-1),
            next=next_wr,
            sg_list=sg_list,
            num_sge=len(sg_list),
            opcode=opcode_val,
            send_flags=random.randint(0, 0xffff),
            **fields
        )
    
    # @classmethod
    # def random_mutation(cls):
    #     sg_list = [IbvSge.random_mutation() for _ in range(random.choice([0, 1, 2, 4]))]
    #     opcode_val = random.choice(list(IBV_WR_OPCODE_ENUM.keys()))
    #     # 针对opcode生成相应union字段
    #     fields = {}
    #     if opcode_val in (1, 3):  # *_WITH_IMM
    #         fields['imm_data'] = random.randint(0, 0xffffffff)
    #     if opcode_val == 7:  # *_INV
    #         fields['invalidate_rkey'] = random.randint(0, 0xffffffff)
    #     if opcode_val in (0, 1, 4):  # RDMA相关
    #         fields['rdma'] = IbvRdmaInfo.random_mutation()
    #     if opcode_val in (5, 6, 15):  # ATOMIC
    #         fields['atomic'] = IbvAtomicInfo.random_mutation()
    #     if opcode_val == 2:  # UD
    #         fields['ud'] = IbvUdInfo.random_mutation()
    #     # 其他union略
    #     return cls(
    #         wr_id=random.randint(0, 2**64-1),
    #         sg_list=sg_list,
    #         num_sge=len(sg_list),
    #         opcode=opcode_val,
    #         send_flags=random.randint(0, 0xffff),
    #         **fields
    #     )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_send_wr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        enum_fields = {"opcode": IBV_WR_OPCODE_ENUM}
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if val is None:
                continue
            if field == "sg_list":
                if isinstance(val, list) and len(val) > 0:
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
            elif field == "next":
                # 假设 next 是下一个wr的变量名
                s += f"    {varname}.next = {val};\n"
            else:
                s += emit_assign(varname, field, val, enum_fields)
        return s

if __name__ == "__main__":
    wr = IbvSendWR.random_mutation()
    print(wr.to_cxx("send_wr"))
