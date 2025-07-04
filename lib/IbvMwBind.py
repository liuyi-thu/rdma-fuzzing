import random
try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging

# class IbvMr:
#     FIELD_LIST = ["context", "pd", "addr", "length", "handle", "lkey", "rkey"]
#     def __init__(self, context=None, pd=None, addr=None, length=None, handle=None, lkey=None, rkey=None):
#         self.context = context
#         self.pd = pd
#         self.addr = addr
#         self.length = length
#         self.handle = handle
#         self.lkey = lkey
#         self.rkey = rkey

#     @classmethod
#     def random_mutation(cls):
#         return cls(
#             context=None,
#             pd=None,
#             addr=random.randint(0x1000, 0xFFFFF000),
#             length=random.choice([0x1000, 0x2000, 0x8000]),
#             handle=random.randint(0, 0xFFFF),
#             lkey=random.randint(0, 0xFFFFFF),
#             rkey=random.randint(0, 0xFFFFFF)
#         )

#     def to_cxx(self, varname, ctx=None):
#         if ctx:
#             ctx.alloc_variable(varname, "struct ibv_mr")
#         s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
#         for f in self.FIELD_LIST:
#             v = getattr(self, f)
#             if v is not None:
#                 s += emit_assign(varname, f, v)
#         return s
    
class IbvMwBindInfo:
    FIELD_LIST = ["mr", "addr", "length", "mw_access_flags"]
    def __init__(self, mr=None, addr=None, length=None, mw_access_flags=None, ctx: CodeGenContext = None):
        self.mr = mr   # IbvMr实例 或 已有变量名
        self.addr = addr
        self.length = length
        self.mw_access_flags = mw_access_flags

    @classmethod
    def random_mutation(cls):
        return cls(
            mr=None, # 实际上应该从mr_map中随机获取一个，不然100%要挂
            addr=random.randint(0x1000, 0xFFFFF000),
            length=random.choice([0x1000, 0x2000, 0x8000]),
            mw_access_flags=random.choice([0, 1, 0xf, 0x1f])
        )

    def to_cxx(self, varname, ctx: CodeGenContext = None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_mw_bind_info")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        if self.mr is not None:
            mr_var = ctx.get_mr(self.mr)
            s += f"    {varname}.mr = &{mr_var};\n"
        for f in ["addr", "length", "mw_access_flags"]:
            v = getattr(self, f)
            if v is not None:
                s += emit_assign(varname, f, v)
        return s
    
class IbvMwBind:
    FIELD_LIST = ["wr_id", "send_flags", "bind_info"]
    def __init__(self, wr_id=None, send_flags=None, bind_info=None):
        self.wr_id = wr_id
        self.send_flags = send_flags
        self.bind_info = bind_info  # IbvMwBindInfo实例

    @classmethod
    def random_mutation(cls):
        return cls(
            wr_id=random.randint(0, 0xffffffffffffffff),
            send_flags=random.choice([0, 1, 2, 0xf, 0x1f]),
            bind_info=IbvMwBindInfo.random_mutation()
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_mw_bind")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        if self.wr_id is not None:
            s += emit_assign(varname, "wr_id", self.wr_id)
        if self.send_flags is not None:
            s += emit_assign(varname, "send_flags", self.send_flags)
        if self.bind_info is not None:
            bind_info_var = varname + "_bind_info"
            s += self.bind_info.to_cxx(bind_info_var, ctx)
            s += f"    {varname}.bind_info = {bind_info_var};\n"
        return s