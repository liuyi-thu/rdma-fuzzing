try:
    from .IbvQPCap import IbvQPCap  # for package import
except ImportError:
    from IbvQPCap import IbvQPCap  # for direct script debugging

try:
    from .IbvAHAttr import IbvAHAttr, IbvGID, IbvGlobalRoute
except ImportError:
    from IbvAHAttr import IbvAHAttr, IbvGID, IbvGlobalRoute

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


class IbvQPAttr(Attr):
    FIELD_LIST = [
        "qp_state",
        "cur_qp_state",
        "path_mtu",
        "path_mig_state",
        "qkey",
        "rq_psn",
        "sq_psn",
        "dest_qp_num",
        "qp_access_flags",
        "cap",
        "ah_attr",
        "alt_ah_attr",
        "pkey_index",
        "alt_pkey_index",
        "en_sqd_async_notify",
        "sq_draining",
        "max_rd_atomic",
        "max_dest_rd_atomic",
        "min_rnr_timer",
        "port_num",
        "timeout",
        "retry_cnt",
        "rnr_retry",
        "alt_port_num",
        "alt_timeout",
        "rate_limit",
    ]
    MUTABLE_FIELD_LIST = [
        "qp_state",
        "cur_qp_state",
        "path_mtu",
        "path_mig_state",
        "qkey",
        "rq_psn",
        "sq_psn",
        "dest_qp_num",
        "qp_access_flags",
        "cap",
        "ah_attr",
        "alt_ah_attr",
        "pkey_index",
        "alt_pkey_index",
        "en_sqd_async_notify",
        "sq_draining",
        "max_rd_atomic",
        "max_dest_rd_atomic",
        "min_rnr_timer",
        "port_num",
        "timeout",
        "retry_cnt",
        "rnr_retry",
        "alt_port_num",
        "alt_timeout",
        "rate_limit",
    ]

    def __init__(
        self,
        qp_state=None,
        cur_qp_state=None,
        path_mtu=None,
        path_mig_state=None,
        qkey=None,
        rq_psn=None,
        sq_psn=None,
        dest_qp_num=None,
        qp_access_flags=None,
        cap=None,
        ah_attr=None,
        alt_ah_attr=None,
        pkey_index=None,
        alt_pkey_index=None,
        en_sqd_async_notify=None,
        sq_draining=None,
        max_rd_atomic=None,
        max_dest_rd_atomic=None,
        min_rnr_timer=None,
        port_num=None,
        timeout=None,
        retry_cnt=None,
        rnr_retry=None,
        alt_port_num=None,
        alt_timeout=None,
        rate_limit=None,
    ):
        self.qp_state = OptionalValue(
            EnumValue(qp_state, enum_type="IBV_QP_STATE_ENUM") if qp_state is not None else None,
            factory=lambda: EnumValue(0, enum_type="IBV_QP_STATE_ENUM"),
        )  # 默认值为IBV_QPS_RESET
        self.cur_qp_state = OptionalValue(
            EnumValue(cur_qp_state, enum_type="IBV_QP_STATE_ENUM") if cur_qp_state is not None else None,
            factory=lambda: EnumValue(0, enum_type="IBV_QP_STATE_ENUM"),
        )  # 默认值为IBV_QPS_RESET
        self.path_mtu = OptionalValue(
            EnumValue(path_mtu, enum_type="IBV_MTU_ENUM") if path_mtu is not None else None,
            factory=lambda: EnumValue(1, enum_type="IBV_MTU_ENUM"),
        )  # 默认值为256
        self.path_mig_state = OptionalValue(
            EnumValue(path_mig_state, enum_type="IBV_MIG_STATE_ENUM") if path_mig_state is not None else None,
            factory=lambda: EnumValue(0, enum_type="IBV_MIG_STATE_ENUM"),
        )  # 默认值为IBV_MIG_MIGRATED
        self.qkey = OptionalValue(
            IntValue(qkey) if qkey is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.rq_psn = OptionalValue(
            IntValue(rq_psn) if rq_psn is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.sq_psn = OptionalValue(
            IntValue(sq_psn) if sq_psn is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0zx
        self.dest_qp_num = OptionalValue(
            IntValue(dest_qp_num) if dest_qp_num is not None else None, factory=lambda: IntValue(0)
        )
        self.qp_access_flags = OptionalValue(
            FlagValue(qp_access_flags, flag_type="IBV_ACCESS_FLAGS_ENUM") if qp_access_flags is not None else None,
            factory=lambda: FlagValue(0, flag_type="IBV_ACCESS_FLAGS_ENUM"),
        )  # 默认值为0
        self.cap = OptionalValue(cap if cap is not None else None, factory=lambda: IbvQPCap.random_mutation())
        self.ah_attr = OptionalValue(
            ah_attr if ah_attr is not None else None, factory=lambda: IbvAHAttr.random_mutation()
        )
        self.alt_ah_attr = OptionalValue(
            alt_ah_attr if alt_ah_attr is not None else None, factory=lambda: IbvAHAttr.random_mutation()
        )
        self.pkey_index = OptionalValue(
            IntValue(pkey_index) if pkey_index is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.alt_pkey_index = OptionalValue(
            IntValue(alt_pkey_index) if alt_pkey_index is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.en_sqd_async_notify = OptionalValue(
            IntValue(en_sqd_async_notify) if en_sqd_async_notify is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.sq_draining = OptionalValue(
            IntValue(sq_draining) if sq_draining is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.max_rd_atomic = OptionalValue(
            IntValue(max_rd_atomic) if max_rd_atomic is not None else None, factory=lambda: IntValue(1)
        )  # 默认值为1
        self.max_dest_rd_atomic = OptionalValue(
            IntValue(max_dest_rd_atomic) if max_dest_rd_atomic is not None else None, factory=lambda: IntValue(1)
        )  # 默认值为1
        self.min_rnr_timer = OptionalValue(
            IntValue(min_rnr_timer) if min_rnr_timer is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.port_num = OptionalValue(
            IntValue(port_num) if port_num is not None else None, factory=lambda: IntValue(1)
        )  # 默认值为1
        self.timeout = OptionalValue(
            IntValue(timeout) if timeout is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.retry_cnt = OptionalValue(
            IntValue(retry_cnt) if retry_cnt is not None else None, factory=lambda: IntValue(7)
        )  # 默认值为7
        self.rnr_retry = OptionalValue(
            IntValue(rnr_retry) if rnr_retry is not None else None, factory=lambda: IntValue(7)
        )  # 默认值为7
        self.alt_port_num = OptionalValue(
            IntValue(alt_port_num) if alt_port_num is not None else None, factory=lambda: IntValue(1)
        )  # 默认值为1
        self.alt_timeout = OptionalValue(
            IntValue(alt_timeout) if alt_timeout is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0
        self.rate_limit = OptionalValue(
            IntValue(rate_limit) if rate_limit is not None else None, factory=lambda: IntValue(0)
        )  # 默认值为0

    @classmethod
    def random_mutation(cls):
        return cls(
            qp_state=random.choice([0, 1, 2, 3, 4, 5]),
            cur_qp_state=random.choice([0, 1, 2, 3, 4, 5]),
            path_mtu=random.choice([1, 2, 3, 4, 5]),
            path_mig_state=random.choice([0, 1, 2]),
            qkey=random.randint(0, 2**32 - 1),
            rq_psn=random.randint(0, 2**24 - 1),
            sq_psn=random.randint(0, 2**24 - 1),
            dest_qp_num=random.randint(0, 2**24 - 1),
            qp_access_flags=random.choice([0, 1, 7, 0xDEADBEEF]),
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
            rate_limit=random.randint(0, 0xFFFFF),
        )

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_qp_attr")
        # s = f"\n    struct ibv_qp_attr {varname};\n    memset(&{varname}, 0, sizeof({varname}));\n"
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        # enum_fields = {
        #     'qp_state': IBV_QP_STATE_ENUM,
        #     'cur_qp_state': IBV_QP_STATE_ENUM,
        #     'path_mtu': IBV_MTU_ENUM,
        #     'path_mig_state': IBV_MIG_STATE_ENUM,
        #     # ...如有其它枚举类型
        # }
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if not val:
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
                # s += emit_assign(varname, field, val, enums=enum_fields)
                s += emit_assign(varname, field, val)
        return s


if __name__ == "__main__":
    attr = IbvQPAttr.random_mutation()
    print(attr.to_cxx("qp_attr"))
    for i in range(10000):
        attr = IbvQPAttr.random_mutation()
        print(attr.to_cxx(f"qp_attr_{i}"))
        if i % 1000 == 0:
            print(f"Generated {i} random QP attributes.")
