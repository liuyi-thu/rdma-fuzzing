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
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging

try:
    from .value import (
        BoolValue,
        ConstantValue,
        DeferredValue,
        EnumValue,
        FlagValue,
        IntValue,
        OptionalValue,
        ResourceValue,
    )
except ImportError:
    from value import (
        BoolValue,
        ConstantValue,
        DeferredValue,
        EnumValue,
        FlagValue,
        IntValue,
        OptionalValue,
        ResourceValue,
    )

IBV_QP_STATE_ENUM = {
    0: "IBV_QPS_RESET",
    1: "IBV_QPS_INIT",
    2: "IBV_QPS_RTR",
    3: "IBV_QPS_RTS",
    4: "IBV_QPS_SQD",
    5: "IBV_QPS_SQE",
    6: "IBV_QPS_ERR",
    7: "IBV_QPS_UNKNOWN",
}
IBV_MIG_STATE_ENUM = {0: "IBV_MIG_MIGRATED", 1: "IBV_MIG_REARM", 2: "IBV_MIG_ARMED"}
IBV_MTU_ENUM = {1: "IBV_MTU_256", 2: "IBV_MTU_512", 3: "IBV_MTU_1024", 4: "IBV_MTU_2048", 5: "IBV_MTU_4096"}


class IbvGID(Attr):
    FIELD_LIST = ["raw", "src_var"]
    MUTABLE_FIELDS = ["raw", "src_var"]

    def __init__(self, raw=None, src_var=None):
        # raw: list[int] 长度 16, 每项 0..255；src_var: 现有 union ibv_gid 变量名（字符串）
        self.raw = raw
        self.src_var = ConstantValue(src_var) if src_var is not None else None

        # 轻量校验（不抛异常，只在 to_cxx 做最终兜底）
        if self.raw is not None and (not isinstance(self.raw, list) or len(self.raw) != 16):
            raise ValueError("IbvGID.raw must be a list of 16 integers (0..255)")

    # ---------- 便捷工厂 ----------
    @classmethod
    def zero(cls):
        return cls(raw=[0] * 16)

    @classmethod
    def from_hex(cls, hex_str: str):
        """接受 32 hex chars 或 'xxxx:...:xxxx' 形式，生成 raw。"""
        s = hex_str.replace(":", "").replace(" ", "").lower()
        if len(s) != 32 or any(c not in "0123456789abcdef" for c in s):
            raise ValueError("hex_str must be 32 hex chars for GID")
        raw = [int(s[i : i + 2], 16) for i in range(0, 32, 2)]
        return cls(raw=raw)

    @classmethod
    def random_mutation(cls):
        # 90%：在 zero 上微扰；10%：完全随机
        if random.random() < 0.9:
            base = [0] * 16
            flips = random.randint(1, 3)
            idxs = random.sample(range(16), flips)
            for i in idxs:
                base[i] = random.randint(0, 255)
            return cls(raw=base)
        else:
            return cls(raw=[random.randint(0, 255) for _ in range(16)])

    # ---------- 轻量变异（可用于 wrapper mutate） ----------
    def mutate(self, rng: random.Random):
        if self.src_var is not None and rng.random() < 0.2:
            # 小概率改成 raw，避免总是引用外部变量
            self.src_var = None
            self.raw = [rng.randint(0, 255) for _ in range(16)]
            return True
        if self.raw is None:
            # 从 src_var 转 raw 的另一种路径
            self.raw = [0] * 16
        flips = rng.randint(1, 3)
        for _ in range(flips):
            i = rng.randrange(16)
            self.raw[i] = rng.randint(0, 255)
        return True

    def to_cxx(self, varname, ctx=None):
        # 变量声明
        if ctx:
            ctx.alloc_variable(varname, "union ibv_gid")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"

        # 优先使用 src_var
        if self.src_var:
            s += f"    memcpy(&{varname}, &{self.src_var}, sizeof({varname}));\n"
            return s

        # 使用 raw
        raw = self.raw if isinstance(self.raw, list) else None
        if raw is not None and len(raw) == 16 and all(isinstance(x, int) and 0 <= x <= 255 for x in raw):
            arr_name = varname + "_arr"
            arr_str = ", ".join(str(int(x) & 0xFF) for x in raw)
            if ctx:
                ctx.alloc_variable(arr_name + "[16]", "uint8_t", f"{{ {arr_str} }}")
            s += f"    memcpy({varname}.raw, {arr_name}, 16);\n"
            return s

        # 兜底：保留全 0（已 memset）
        return s


# class IbvGID(Attr):
#     FIELD_LIST = ["raw", "src_var"]
#     MUTABLE_FIELDS = ["raw", "src_var"]

#     def __init__(self, raw=None, src_var=None):
#         self.raw = raw  # 16字节list， list后面需要想想能不能mutate
#         self.src_var = ConstantValue(src_var)  # C++已有变量名，比如 "existing_gid"

#     @classmethod
#     def random_mutation(cls):
#         return cls(raw=[random.randint(0, 255) for _ in range(16)])

#     def to_cxx(self, varname, ctx=None):
#         if ctx:
#             ctx.alloc_variable(varname, "union ibv_gid")
#         s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
#         if self.src_var:
#             # 直接用已有变量整体赋值
#             # s += f"    {varname} = {self.src_var};\n"
#             s += f"    memcpy(&{varname}, &{self.src_var}, sizeof({varname}));\n"
#         elif self.raw:
#             arr_name = varname + "_arr"
#             arr_str = ", ".join(str(x) for x in self.raw)
#             # s += f"    uint8_t {arr_name}[16] = {{ {arr_str} }};\n"
#             if ctx:
#                 ctx.alloc_variable(arr_name + "[16]", "uint8_t", f"{{ {arr_str} }}")
#             s += f"    memcpy({varname}.raw, {arr_name}, 16);\n"
#         # 如果两个都没提供，只memset为全0（前面已做，无需再加）
#         return s


class IbvGlobalRoute(Attr):
    FIELD_LIST = ["dgid", "flow_label", "sgid_index", "hop_limit", "traffic_class"]
    MUTABLE_FIELDS = ["dgid", "flow_label", "sgid_index", "hop_limit", "traffic_class"]

    def __init__(self, dgid=None, flow_label=None, sgid_index=None, hop_limit=None, traffic_class=None):
        # self.dgid = OptionalValue(dgid, factory=lambda: IbvGID())  # IbvGID instance, can be mutated
        self.dgid = OptionalValue(
            DeferredValue.from_id("remote.QP", dgid, "gid", "const char *"),
            factory=DeferredValue.from_id("remote.QP", None, "gid", "const char *"),
        )  # TODO: may cause bugs; and gid cannot be assigned directly, to be fixed.
        self.flow_label = OptionalValue(
            IntValue(flow_label) if flow_label is not None else None, factory=lambda: IntValue()
        )  # not necessary
        self.sgid_index = OptionalValue(
            IntValue(sgid_index) if sgid_index is not None else None, factory=lambda: IntValue()
        )  # not necessary
        # hop_limit and traffic_class are usually set to 0, but can be mutated
        self.hop_limit = OptionalValue(
            IntValue(hop_limit) if hop_limit is not None else None, factory=lambda: IntValue()
        )
        self.traffic_class = OptionalValue(
            IntValue(traffic_class) if traffic_class is not None else None, factory=lambda: IntValue()
        )

    @classmethod
    def random_mutation(cls):
        return cls(
            dgid=IbvGID.random_mutation(),
            flow_label=random.randint(0, 0xFFFFF),
            sgid_index=random.randint(0, 16),
            hop_limit=random.randint(0, 255),
            traffic_class=random.randint(0, 255),
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_global_route")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if not val:
                continue
            if field == "dgid":
                # dgid_var = varname + "_dgid"
                # s += val.to_cxx(dgid_var, ctx)
                # s += f"    {varname}.dgid = {dgid_var};\n"
                # s += f"    memcpy({varname}.dgid, {val}, sizeof({varname}.dgid));\n"
                s += f"    parse_gid_str({val}, {varname}.dgid);\n"
            else:
                s += emit_assign(varname, field, val)
        return s


class IbvAHAttr(Attr):
    FIELD_LIST = ["grh", "dlid", "sl", "src_path_bits", "static_rate", "is_global", "port_num"]
    MUTABLE_FIELDS = ["grh", "dlid", "sl", "src_path_bits", "static_rate", "is_global", "port_num"]

    def __init__(
        self, grh=None, dlid=None, sl=None, src_path_bits=None, static_rate=None, is_global=None, port_num=None
    ):
        self.grh = OptionalValue(grh, factory=lambda: IbvGlobalRoute())  # Global Route Header, can be mutated
        # self.dlid = OptionalValue(
        #     IntValue(dlid) if dlid is not None else None, factory=lambda: IntValue()
        # )  # dlid is usually an integer
        self.dlid = OptionalValue(
            DeferredValue.from_id("remote.QP", dlid, "lid", "uint32_t"),
            factory=DeferredValue.from_id("remote.QP", None, "lid", "uint32_t"),
        )  # dlid is usually an integer # TODO: may cause bugs
        self.sl = OptionalValue(
            IntValue(sl) if sl is not None else None, factory=lambda: IntValue()
        )  # Service Level, can be mutated
        self.src_path_bits = OptionalValue(
            IntValue(src_path_bits) if src_path_bits is not None else None, factory=lambda: IntValue()
        )  # Source Path Bits, can be mutated
        self.static_rate = OptionalValue(
            IntValue(static_rate) if static_rate is not None else None, factory=lambda: IntValue()
        )  # Static Rate, can be mutated
        self.is_global = OptionalValue(
            BoolValue(is_global) if is_global is not None else None, factory=lambda: BoolValue(False)
        )  # Is Global, default is False
        # self.port_num = OptionalValue(
        #     IntValue(port_num) if port_num is not None else None, factory=lambda: IntValue(1)
        # )  # Port Number, default is 1
        self.port_num = OptionalValue(
            DeferredValue.from_id("remote.QP", dlid, "port_num", "uint32_t"),
            factory=DeferredValue.from_id("remote.QP", None, "port_num", "uint32_t"),
        )

    @classmethod
    def random_mutation(cls):
        return cls(
            grh=IbvGlobalRoute.random_mutation(),
            dlid=random.randint(0, 0xFFFF),
            sl=random.randint(0, 15),
            src_path_bits=random.randint(0, 7),
            static_rate=random.randint(0, 31),
            is_global=random.randint(0, 1),
            port_num=random.randint(1, 2),
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_ah_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if not val:
                continue
            if field == "grh":
                grh_var = varname + "_grh"
                s += val.to_cxx(grh_var, ctx)
                s += f"    {varname}.grh = {grh_var};\n"
            else:
                s += emit_assign(varname, field, val)
        return s


if __name__ == "__main__":
    # Example usage
    # ah_attr = IbvAHAttr(
    #     grh=IbvGlobalRoute(dgid=IbvGID(raw=[0] * 16), flow_label=0, sgid_index=0, hop_limit=0, traffic_class=0),
    #     dlid=1,
    #     sl=2,
    #     src_path_bits=3,
    #     static_rate=4,
    #     is_global=True,
    #     port_num=1,
    # )
    # print(ah_attr.to_cxx("my_ah_attr"))  # This will generate the C++ code for the AH attribute
    # ah_attr.mutate()  # Mutate the attributes
    # print(ah_attr.to_cxx("my_ah_attr_mutated"))  # This
    # # print(IbvAHAttr.random_mutation().to_cxx("random_ah_attr"))
    # grh = IbvGlobalRoute(
    #     dgid=IbvGID(raw=[0] * 16, src_var="existing_gid"), flow_label=0, sgid_index=0, hop_limit=0, traffic_class=0
    # )
    # print(grh.to_cxx("grh"))  # This will generate the C++ code after mutation
    # grh.mutate()  # Mutate the grh
    # print(grh.to_cxx("grh_mutated"))  # This will generate the

    # ah_attr = IbvAHAttr.random_mutation()
    # print(ah_attr.to_cxx("my_ah_attr_random"))
    # for i in range(10000):
    #     ah_attr.mutate()  # Mutate the attributes
    # print("after mutation:")
    # print(ah_attr.to_cxx("my_ah_attr_random_mutated"))  #

    globalRoute = IbvGlobalRoute(dgid="abc", flow_label=0, sgid_index=0, hop_limit=0, traffic_class=0)
    print(globalRoute.to_cxx("my_global_route"))
