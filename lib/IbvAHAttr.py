import random
try:
    from .IbvQPCap import IbvQPCap  # for package import
except ImportError:
    from IbvQPCap import IbvQPCap  # for direct script debugging

try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging

IBV_QP_STATE_ENUM = {
    0: 'IBV_QPS_RESET',
    1: 'IBV_QPS_INIT',
    2: 'IBV_QPS_RTR',
    3: 'IBV_QPS_RTS',
    4: 'IBV_QPS_SQD',
    5: 'IBV_QPS_SQE',
    6: 'IBV_QPS_ERR',
    7: 'IBV_QPS_UNKNOWN'
}
IBV_MIG_STATE_ENUM = {
    0: 'IBV_MIG_MIGRATED',
    1: 'IBV_MIG_REARM',
    2: 'IBV_MIG_ARMED'
}
IBV_MTU_ENUM = {
    1: 'IBV_MTU_256',
    2: 'IBV_MTU_512',
    3: 'IBV_MTU_1024',
    4: 'IBV_MTU_2048',
    5: 'IBV_MTU_4096'
}

class IbvGID:
    FIELD_LIST = ["raw", "src_var"]
    def __init__(self, raw=None, src_var=None):
        self.raw = raw      # 16字节list
        self.src_var = src_var  # C++已有变量名，比如 "existing_gid"

    @classmethod
    def random_mutation(cls):
        return cls(raw=[random.randint(0, 255) for _ in range(16)])

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "union ibv_gid")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        if self.src_var is not None:
            # 直接用已有变量整体赋值
            # s += f"    {varname} = {self.src_var};\n"
            s += f"    memcpy(&{varname}, &{self.src_var}, sizeof({varname}));\n"
        elif self.raw is not None:
            arr_name = varname + "_arr"
            arr_str = ', '.join(str(x) for x in self.raw)
            # s += f"    uint8_t {arr_name}[16] = {{ {arr_str} }};\n"
            if ctx:
                ctx.alloc_variable(arr_name + '[16]', "uint8_t", f"{{ {arr_str} }}")
            s += f"    memcpy({varname}.raw, {arr_name}, 16);\n"
        # 如果两个都没提供，只memset为全0（前面已做，无需再加）
        return s
    
class IbvGlobalRoute:
    FIELD_LIST = ["dgid", "flow_label", "sgid_index", "hop_limit", "traffic_class"]
    def __init__(self, dgid=None, flow_label=None, sgid_index=None, hop_limit=None, traffic_class=None):
        self.dgid = dgid
        self.flow_label = flow_label
        self.sgid_index = sgid_index
        self.hop_limit = hop_limit
        self.traffic_class = traffic_class

    @classmethod
    def random_mutation(cls):
        return cls(
            dgid=IbvGID.random_mutation(),
            flow_label=random.randint(0, 0xfffff),
            sgid_index=random.randint(0, 16),
            hop_limit=random.randint(0, 255),
            traffic_class=random.randint(0, 255)
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_global_route")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if val is None:
                continue
            if field == "dgid":
                dgid_var = varname + "_dgid"
                s += val.to_cxx(dgid_var, ctx)
                s += f"    {varname}.dgid = {dgid_var};\n"
            else:
                s += emit_assign(varname, field, val)
        return s

class IbvAHAttr:
    FIELD_LIST = ["grh", "dlid", "sl", "src_path_bits", "static_rate", "is_global", "port_num"]
    def __init__(self, grh=None, dlid=None, sl=None, src_path_bits=None, static_rate=None, is_global=None, port_num=None):
        self.grh = grh
        self.dlid = dlid
        self.sl = sl
        self.src_path_bits = src_path_bits
        self.static_rate = static_rate
        self.is_global = is_global
        self.port_num = port_num

    @classmethod
    def random_mutation(cls):
        return cls(
            grh=IbvGlobalRoute.random_mutation(),
            dlid=random.randint(0, 0xffff),
            sl=random.randint(0, 15),
            src_path_bits=random.randint(0, 7),
            static_rate=random.randint(0, 31),
            is_global=random.randint(0, 1),
            port_num=random.randint(1, 2)
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_ah_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if val is None:
                continue
            if field == "grh":
                grh_var = varname + "_grh"
                s += val.to_cxx(grh_var, ctx)
                s += f"    {varname}.grh = {grh_var};\n"
            else:
                s += emit_assign(varname, field, val)
        return s