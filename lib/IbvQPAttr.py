import random
try:
    from .IbvQPCap import IbvQPCap  # for package import
except ImportError:
    from IbvQPCap import IbvQPCap  # for direct script debugging

try:
    from .IbvAHAttr import IbvAHAttr, IbvGID, IbvGlobalRoute
except ImportError:
    from IbvAHAttr import IbvAHAttr, IbvGID, IbvGlobalRoute

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


# class IbvGID:
#     FIELD_LIST = ["raw"]
#     def __init__(self, raw=None):
#         self.raw = raw  # 16字节list

#     @classmethod
#     def random_mutation(cls):
#         return cls(raw=[random.randint(0, 255) for _ in range(16)])

#     def to_cxx(self, varname, ctx=None):
#         if ctx:
#             ctx.alloc_variable(varname, "union ibv_gid")
#         arr = ', '.join(str(x) for x in (self.raw or [0]*16))
#         # 只有raw非None时才memcpy
#         s = f"\n    union ibv_gid {varname};\n    memset(&{varname}, 0, sizeof({varname}));\n"
#         if self.raw is not None:
#             s += f"    memcpy({varname}.raw, (uint8_t[]){{ {arr} }}, 16);\n"
#         return s

# class IbvGID:
#     FIELD_LIST = ["raw", "src_var"]
#     def __init__(self, raw=None, src_var=None):
#         self.raw = raw      # 16字节list
#         self.src_var = src_var  # C++已有变量名，比如 "existing_gid"

#     @classmethod
#     def random_mutation(cls):
#         return cls(raw=[random.randint(0, 255) for _ in range(16)])

#     def to_cxx(self, varname, ctx=None):
#         if ctx:
#             ctx.alloc_variable(varname, "union ibv_gid")
#         s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
#         if self.src_var is not None:
#             # 直接用已有变量整体赋值
#             # s += f"    {varname} = {self.src_var};\n"
#             s += f"    memcpy(&{varname}, &{self.src_var}, sizeof({varname}));\n"
#         elif self.raw is not None:
#             arr_name = varname + "_arr"
#             arr_str = ', '.join(str(x) for x in self.raw)
#             # s += f"    uint8_t {arr_name}[16] = {{ {arr_str} }};\n"
#             if ctx:
#                 ctx.alloc_variable(arr_name + '[16]', "uint8_t", f"{{ {arr_str} }}")
#             s += f"    memcpy({varname}.raw, {arr_name}, 16);\n"
#         # 如果两个都没提供，只memset为全0（前面已做，无需再加）
#         return s
    
# class IbvGlobalRoute:
#     FIELD_LIST = ["dgid", "flow_label", "sgid_index", "hop_limit", "traffic_class"]
#     def __init__(self, dgid=None, flow_label=None, sgid_index=None, hop_limit=None, traffic_class=None):
#         self.dgid = dgid
#         self.flow_label = flow_label
#         self.sgid_index = sgid_index
#         self.hop_limit = hop_limit
#         self.traffic_class = traffic_class

#     @classmethod
#     def random_mutation(cls):
#         return cls(
#             dgid=IbvGID.random_mutation(),
#             flow_label=random.randint(0, 0xfffff),
#             sgid_index=random.randint(0, 16),
#             hop_limit=random.randint(0, 255),
#             traffic_class=random.randint(0, 255)
#         )

#     def to_cxx(self, varname, ctx=None):
#         if ctx:
#             ctx.alloc_variable(varname, "struct ibv_global_route")
#         s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
#         for field in self.FIELD_LIST:
#             val = getattr(self, field)
#             if val is None:
#                 continue
#             if field == "dgid":
#                 dgid_var = varname + "_dgid"
#                 s += val.to_cxx(dgid_var, ctx)
#                 s += f"    {varname}.dgid = {dgid_var};\n"
#             else:
#                 s += emit_assign(varname, field, val)
#         return s

# class IbvAHAttr:
#     FIELD_LIST = ["grh", "dlid", "sl", "src_path_bits", "static_rate", "is_global", "port_num"]
#     def __init__(self, grh=None, dlid=None, sl=None, src_path_bits=None, static_rate=None, is_global=None, port_num=None):
#         self.grh = grh
#         self.dlid = dlid
#         self.sl = sl
#         self.src_path_bits = src_path_bits
#         self.static_rate = static_rate
#         self.is_global = is_global
#         self.port_num = port_num

#     @classmethod
#     def random_mutation(cls):
#         return cls(
#             grh=IbvGlobalRoute.random_mutation(),
#             dlid=random.randint(0, 0xffff),
#             sl=random.randint(0, 15),
#             src_path_bits=random.randint(0, 7),
#             static_rate=random.randint(0, 31),
#             is_global=random.randint(0, 1),
#             port_num=random.randint(1, 2)
#         )

#     def to_cxx(self, varname, ctx=None):
#         if ctx:
#             ctx.alloc_variable(varname, "struct ibv_ah_attr")
#         s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
#         for field in self.FIELD_LIST:
#             val = getattr(self, field)
#             if val is None:
#                 continue
#             if field == "grh":
#                 grh_var = varname + "_grh"
#                 s += val.to_cxx(grh_var, ctx)
#                 s += f"    {varname}.grh = {grh_var};\n"
#             else:
#                 s += emit_assign(varname, field, val)
#         return s

class IbvQPAttr:
    FIELD_LIST = [
        'qp_state', 'cur_qp_state', 'path_mtu', 'path_mig_state', 'qkey', 'rq_psn', 'sq_psn', 'dest_qp_num',
        'qp_access_flags', 'cap', 'ah_attr', 'alt_ah_attr', 'pkey_index', 'alt_pkey_index', 'en_sqd_async_notify',
        'sq_draining', 'max_rd_atomic', 'max_dest_rd_atomic', 'min_rnr_timer', 'port_num', 'timeout', 'retry_cnt',
        'rnr_retry', 'alt_port_num', 'alt_timeout', 'rate_limit'
    ]
    def __init__(self, qp_state=None, cur_qp_state=None, path_mtu=None, path_mig_state=None, qkey=None, rq_psn=None,
                 sq_psn=None, dest_qp_num=None, qp_access_flags=None, cap=None, ah_attr=None, alt_ah_attr=None,
                 pkey_index=None, alt_pkey_index=None, en_sqd_async_notify=None, sq_draining=None, max_rd_atomic=None,
                 max_dest_rd_atomic=None, min_rnr_timer=None, port_num=None, timeout=None, retry_cnt=None,
                 rnr_retry=None, alt_port_num=None, alt_timeout=None, rate_limit=None):
        self.qp_state = qp_state
        self.cur_qp_state = cur_qp_state
        self.path_mtu = path_mtu
        self.path_mig_state = path_mig_state
        self.qkey = qkey
        self.rq_psn = rq_psn
        self.sq_psn = sq_psn
        self.dest_qp_num = dest_qp_num
        self.qp_access_flags = qp_access_flags
        self.cap = cap
        self.ah_attr = ah_attr
        self.alt_ah_attr = alt_ah_attr
        self.pkey_index = pkey_index
        self.alt_pkey_index = alt_pkey_index
        self.en_sqd_async_notify = en_sqd_async_notify
        self.sq_draining = sq_draining
        self.max_rd_atomic = max_rd_atomic
        self.max_dest_rd_atomic = max_dest_rd_atomic
        self.min_rnr_timer = min_rnr_timer
        self.port_num = port_num
        self.timeout = timeout
        self.retry_cnt = retry_cnt
        self.rnr_retry = rnr_retry
        self.alt_port_num = alt_port_num
        self.alt_timeout = alt_timeout
        self.rate_limit = rate_limit

    @classmethod
    def random_mutation(cls):
        return cls(
            qp_state=random.choice([0, 1, 2, 3, 4, 5]),
            cur_qp_state=random.choice([0, 1, 2, 3, 4, 5]),
            path_mtu=random.choice([1, 2, 3, 4, 5]),
            path_mig_state=random.choice([0, 1, 2]),
            qkey=random.randint(0, 2**32-1),
            rq_psn=random.randint(0, 2**24-1),
            sq_psn=random.randint(0, 2**24-1),
            dest_qp_num=random.randint(0, 2**24-1),
            qp_access_flags=random.choice([0, 1, 7, 0xdeadbeef]),
            cap=IbvQPCap.random_mutation(),
            ah_attr=IbvAHAttr.random_mutation(),
            alt_ah_attr=IbvAHAttr.random_mutation(),
            pkey_index=random.randint(0, 128),
            alt_pkey_index=random.randint(0, 128),
            en_sqd_async_notify=random.randint(0, 1),
            sq_draining=random.randint(0, 1),
            max_rd_atomic=random.randint(0, 16),
            max_dest_rd_atomic=random.randint(0, 16),
            min_rnr_timer=random.randint(0, 31),
            port_num=random.choice([1, 2]),
            timeout=random.choice([0, 1, 14, 30]),
            retry_cnt=random.choice([0, 1, 7]),
            rnr_retry=random.choice([0, 1, 7]),
            alt_port_num=random.choice([1, 2]),
            alt_timeout=random.choice([0, 1, 14, 30]),
            rate_limit=random.randint(0, 0xfffff)
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_qp_attr")
        # s = f"\n    struct ibv_qp_attr {varname};\n    memset(&{varname}, 0, sizeof({varname}));\n"
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        enum_fields = {
            'qp_state': IBV_QP_STATE_ENUM,
            'cur_qp_state': IBV_QP_STATE_ENUM,
            'path_mtu': IBV_MTU_ENUM,
            'path_mig_state': IBV_MIG_STATE_ENUM,
            # ...如有其它枚举类型
        }
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if val is None:
                continue
            if field == "cap":
                cap_var = varname + "_cap"
                s += val.to_cxx(cap_var, ctx)
                s += f"    {varname}.cap = {cap_var};\n"
            elif field == "ah_attr":
                ah_var = varname + "_ah"
                s += val.to_cxx(ah_var, ctx)
                s += f"    {varname}.ah_attr = {ah_var};\n"
            elif field == "alt_ah_attr":
                alt_ah_var = varname + "_alt_ah"
                s += val.to_cxx(alt_ah_var, ctx)
                s += f"    {varname}.alt_ah_attr = {alt_ah_var};\n"
            else:
                s += emit_assign(varname, field, val, enums=enum_fields)
        return s

if __name__ == "__main__":
    attr = IbvQPAttr.random_mutation()
    print(attr.to_cxx("qp_attr"))
