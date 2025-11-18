from lib.codegen_context import CodeGenContext
from lib.IbvAHAttr import IbvAHAttr, IbvGlobalRoute
from lib.IbvAllocDmAttr import IbvAllocDmAttr
from lib.IbvCQInitAttrEx import IbvCQInitAttrEx
from lib.IbvECE import IbvECE
from lib.IbvFlowAttr import IbvFlowAttr
from lib.IbvModifyCQAttr import IbvModifyCQAttr
from lib.IbvMwBind import IbvMwBind
from lib.IbvParentDomainInitAttr import IbvParentDomainInitAttr
from lib.IbvQPAttr import IbvQPAttr
from lib.IbvQPInitAttr import IbvQPInitAttr
from lib.IbvQPInitAttrEx import IbvQPInitAttrEx
from lib.IbvQPOpenAttr import IbvQPOpenAttr
from lib.IbvQPRateLimitAttr import IbvQPRateLimitAttr
from lib.IbvRecvWR import IbvRecvWR
from lib.IbvSendWR import IbvSendWR
from lib.IbvSge import IbvSge
from lib.IbvSrqAttr import IbvSrqAttr
from lib.IbvSrqInitAttr import IbvSrqInitAttr
from lib.IbvSrqInitAttrEx import IbvSrqInitAttrEx
from lib.IbvTdInitAttr import IbvTdInitAttr
from lib.IbvWQAttr import IbvWQAttr
from lib.IbvWQInitAttr import IbvWQInitAttr
from lib.IbvXRCDInitAttr import IbvXRCDInitAttr
from lib.value import (
    ConstantValue,
    EnumValue,
    FlagValue,
    IntValue,
    ListValue,
    LocalResourceValue,
    OptionalValue,
    ResourceValue,
)

# verbs.py 顶部新增
try:
    from ._codegen_utils import (
        coerce_bool,
        coerce_int,
        coerce_list,
        coerce_seq_of,
        coerce_str,
        ensure_identifier,
        unwrap,
        unwrap_all,
    )
except Exception:
    # 允许作为独立脚本运行时的相对导入退化
    from _codegen_utils import (
        coerce_bool,
        coerce_int,
        coerce_list,
        coerce_seq_of,
        coerce_str,
        ensure_identifier,
        unwrap,
        unwrap_all,
    )

from lib.contracts import Contract, InstantiatedContract, ProduceSpec, RequireSpec, State, TransitionSpec


def mask_fields_to_c(mask):
    """
    mask: 可以是字符串（如"IBV_QP_STATE | IBV_QP_PKEY_INDEX"）
          或list/set（如["IBV_QP_STATE", "IBV_QP_PKEY_INDEX"]）
          或int
    返回可插入C代码的字符串
    """
    if isinstance(mask, int):
        return str(mask)
    elif isinstance(mask, (list, set, tuple)):
        # 转成类似 IBV_QP_STATE | IBV_QP_PKEY_INDEX
        return " | ".join(mask)
    elif isinstance(mask, str):
        # 若全为数字直接返回
        if mask.isdigit():
            return mask
        # 若是宏名组合字符串，直接原样输出
        return mask.strip()
    else:
        raise ValueError(f"Unknown mask type: {mask}")


def _parse_kv(info: str) -> dict[str, str]:
    """Parse "k=v k2=v2" style string into dict."""
    out = {}
    for tok in info.replace(",", " ").split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k.strip()] = v.strip()
    return out


# ---------- Verb call base ----------------------------------------------------


class VerbCall:
    FIELD_LIST = []
    EXPORT_FIELDS = []

    def __init__(self):
        self.tracker = None
        self.required_resources = []  # 记录所需资源
        self.allocated_resources = []  # 记录已分配的资源

    def _contract(self):
        return None

    def get_contract(self):
        return self.CONTRACT if hasattr(self, "CONTRACT") else self._contract()

    def instantiate_contract(self):
        # print("why")
        """Instantiate the contract for this verb call."""
        # return InstantiatedContract.instantiate(self, self.get_contract())
        instantiate_contracts = [InstantiatedContract.instantiate(self, self.get_contract())]
        for field in getattr(self, "MUTABLE_FIELDS", []):
            # print(f"Checking field: {field}")
            if hasattr(self, field):
                # 递归调用
                c = getattr(self, field).instantiate_contract()
                if c:
                    instantiate_contracts.append(c)
        contract = InstantiatedContract.merge(instantiate_contracts)
        return contract

    def generate_c(self, ctx: CodeGenContext) -> str:  # pylint: disable=unused-argument
        raise NotImplementedError

    def set_resource(self, res_type: str, old_res_name: str, new_res_name: str):
        """Set a resource for this verb call, used for replacing resources."""
        # # for res in self.required_resources:
        # pass
        # for res in self.get_required_resources_recursively():
        # #     print(res)
        # # print(len(self.get_required_resources_recursively()))
        # # print()
        #     # if res.get('type') == res_type and res.get('name') == old_res_name:
        #     #     res['name'] = new_res_name
        #     #     return
        #     if res.get('type') == res_type and res.get('name') == old_res_name:
        #         position = res.get('position', 'unknown')  # 位置可能是 'cq', 'pd', 'qp' 等
        #         print("Position:", position)
        #         if position == 'unknown':
        #             # 如果位置未知，可能是因为这个资源没有被追踪
        #             # 这时我们可以选择忽略这个资源，或者抛出异常
        #             raise ValueError(f"Resource {old_res_name} of type {res_type} has unknown position.")
        #         else:
        #             setattr(self, position, new_res_name)  # 更新对应位置的资源名
        #     # 这么做没有意义，本末倒置了
        #     pass
        # pass # 有问题
        # # if hasattr(self, 'tracker') and self.tracker:
        # #     self.tracker.set_attr(res_type, old_res_name, 'name', new_res_name)
        # #     # 更新已分配资源列表
        # #     if hasattr(self, 'allocated_resources'):
        # #         self.allocated_resources.append((res_type, new_res_name))
        for res in self.get_required_resources():
            if res.get("type") == res_type and res.get("name") == old_res_name:
                # 位置可能是 'cq', 'pd', 'qp' 等
                position = res.get("position", "unknown")
                print("Position:", position)
                if position == "unknown":
                    # 如果位置未知，可能是因为这个资源没有被追踪
                    # 这时我们可以选择忽略这个资源，或者抛出异常
                    raise ValueError(f"Resource {old_res_name} of type {res_type} has unknown position.")
                else:
                    setattr(self, position, new_res_name)  # 更新对应位置的资源名

    def set_resource_recursively(self, res_type: str, old_res_name: str, new_res_name: str):
        """Set a resource for this verb call, used for replacing resources."""
        self.set_resource(res_type, old_res_name, new_res_name)

    def get_required_resources(self) -> list[dict[str, str]]:
        """Get the list of required resources for this verb call."""
        if hasattr(self, "required_resources"):
            return self.required_resources
        return []

    def get_required_resources_recursively(self) -> list[dict[str, str]]:
        """Get all required resources recursively."""
        resources = self.get_required_resources()
        # if hasattr(self, 'tracker') and self.tracker:
        #     for res in resources:
        #         # 如果资源是一个对象，递归获取其所需资源
        #         if hasattr(res, 'get_required_resources_recursively'):
        #             resources.extend(res.get_required_resources_recursively())
        return resources

    def mutable_fields(self):
        return getattr(self, "MUTABLE_FIELDS", [])

    def get_mutable_params(self):
        """返回{参数名: 参数对象}的dict"""
        return {k: getattr(self, k) for k in self.mutable_fields()}

    def apply(self, ctx: CodeGenContext):
        """Apply the context to this verb call, used for setting up resources."""
        # self.required_resources = []
        # self.allocated_resources = []
        # self.tracker = ctx.tracker if ctx else None
        # if self.tracker:
        #     # Register the resources in the tracker
        #     for res_type, res_name in self.get_mutable_params().items():
        #         if isinstance(res_name, ResourceValue):
        #             self.tracker.create(res_type, res_name.value)
        #             self.required_resources.append(
        #                 {'type': res_type, 'name': res_name.value, 'position': res_type})
        #             self.allocated_resources.append((res_type, res_name.value))
        return

    def to_dict(self):
        """Convert the verb call to a dictionary representation."""
        d = {"verb": self.__class__.__name__}
        # for field in self.FIELD_LIST:
        for field in self.EXPORT_FIELDS:
            if hasattr(self, field):
                value = getattr(self, field)
                if hasattr(value, "to_dict"):
                    d[field] = value.to_dict()
                else:
                    d[field] = value
        return d


class UtilityCall:  # 生成verbs之外的函数
    def __init__(self):
        self.tracker = None
        self.required_resources = []  # 记录所需资源
        self.allocated_resources = []  # 记录已分配的资源

    def _contract(self):
        return None

    def apply(self, ctx: CodeGenContext):
        return

    def get_contract(self):
        return self.CONTRACT if hasattr(self, "CONTRACT") else self._contract()

    def generate_c(self, ctx: CodeGenContext) -> str:  # pylint: disable=unused-argument
        raise NotImplementedError

    def get_required_resources(self) -> list[dict[str, str]]:
        """Get the list of required resources for this verb call."""
        if hasattr(self, "required_resources"):
            return self.required_resources
        return []

    def get_required_resources_recursively(self) -> list[dict[str, str]]:
        """Get all required resources recursively."""
        resources = self.get_required_resources()
        # if hasattr(self, 'tracker') and self.tracker:
        #     for res in resources:
        #         # 如果资源是一个对象，递归获取其所需资源
        #         if hasattr(res, 'get_required_resources_recursively'):
        #             resources.extend(res.get_required_resources_recursively())
        return resources


# ---------- Specific verb implementations ------------------------------------


# class AckAsyncEvent(VerbCall):
#     def __init__(self, event: str):
#         self.event = event

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         event = kv.get("event", "unknown")
#         return cls(event=event)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         return f"""
#     /* ibv_ack_async_event */
#     ibv_ack_async_event(&{self.event});
# """


class AckCQEvents(VerbCall):
    """
    AckCQEvents: Acknowledge CQ events and update object tracker usage.

    Args:
        cq (str): Address of the CQ.
        nevents (int): Number of events to acknowledge.
        tracker (ObjectTracker): The object tracker instance.
    """

    MUTABLE_FIELDS = ["cq", "nevents"]
    EXPORT_FIELDS = ["cq", "nevents"]
    CONTRACT = Contract(requires=[RequireSpec("cq", State.ALLOCATED, "cq")], produces=[], transitions=[])

    def __init__(self, cq: str | None = None, nevents: int | None = None):
        if not cq:
            raise ValueError("CQ name must be provided")
        self.cq = ResourceValue(resource_type="cq", value=cq) if cq else None
        self.nevents = IntValue(nevents or 0)
        # 是这样的，如果是None那么后面就不生成
        # 但是本函数并非如此

        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            self.tracker.use("cq", self.cq.value)  # 明确追踪这个CQ被使用了一次
            self.required_resources.append({"type": "cq", "name": self.cq.value, "position": "cq"})  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq = kv.get("cq", "unknown")
        nevents = int(kv.get("nevents", 0))
        # 通过ctx或者参数获得tracker
        return cls(cq=cq, nevents=nevents)

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_ack_cq_events */
    IF_OK_PTR({self.cq}, {{
        ibv_ack_cq_events({self.cq}, {self.nevents});
    }});
"""


class AdviseMR(VerbCall):  # TODO: 暂时用不上，没改return -1
    """
    表示 ibv_advise_mr() 调用。支持多SGE/flags/advice参数自动生成。
    参数：
        pd   -- PD 资源变量名
        advice    -- 枚举 advice 值（int 或 str）
        flags     -- flags 参数（int）
        sg_list   -- IbvSge对象列表
        num_sge   -- SGE个数（int）
    """

    MUTABLE_FIELDS = ["pd", "advice", "flags", "sg_list", "num_sge", "sg_var"]
    EXPORT_FIELDS = ["pd", "advice", "flags", "sg_list", "num_sge"]
    CONTRACT = Contract(requires=[RequireSpec("pd", State.ALLOCATED, "pd")], produces=[], transitions=[])

    # 这些参数都是必须的
    def __init__(
        self,
        pd: str = None,
        advice: int = None,
        flags: int = None,
        sg_list: list[IbvSge] = [],
        num_sge: int = None,
        sg_var: str = None,
    ):
        # sg_var 没有mutate的必要
        self.pd = ResourceValue(resource_type="pd", value=pd) if pd else ResourceValue(resource_type="pd", value="pd")
        self.advice = (
            EnumValue(advice, enum_type="IB_UVERBS_ADVISE_MR_ADVICE_ENUM")
            if advice is not None
            else EnumValue(
                "IB_UVERBS_ADVISE_MR_ADVICE_PREFETCH",
                enum_type="IB_UVERBS_ADVISE_MR_ADVICE_ENUM",
            )
        )
        self.flags = IntValue(flags or 0)  # TODO: 这个 flag 没搞清楚
        # self.sg_list = sg_list or []  # list的变异比较麻烦，得针对处理，待定
        self.sg_list = ListValue(sg_list, factory=lambda: IbvSge.random_mutation())
        self.num_sge = num_sge if num_sge is not None else len(self.sg_list)  # TODO: num_sge 是否需要和 sg_list 关联？
        # SGE数组变量名，默认为 sg_list_pd
        self.sg_var = ConstantValue(sg_var or f"sg_list_{self.pd.value}")

        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            self.tracker.use("pd", self.pd.value)
            self.required_resources.append({"type": "pd", "name": self.pd.value, "position": "pd"})  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "pd")
        advice = kv.get("advice", 0)
        flags = int(kv.get("flags", 0))
        num_sge = int(kv.get("num_sge", 1))
        # 假定 trace 传递的是已建好的 sg_list 对象列表
        sg_list = kv.get("sg_list", [IbvSge.random_mutation() for _ in range(num_sge)])
        return cls(pd, int(advice), flags, sg_list, num_sge, ctx=ctx)

    def generate_c(self, ctx):
        pd_name = coerce_str(self.pd)
        sg_var = ensure_identifier(self.sg_var)  # 标识符
        num_sge = coerce_int(self.num_sge)
        sg_list = unwrap_all(self.sg_list)  # SGE 列表的元素做一次 unwrap
        advice_macro = coerce_str(self.advice)  # 枚举值转换为字符串
        flags = coerce_int(self.flags)  # flags 转换为整数

        # 如果列表与 num_sge 不一致，用列表长度兜底，避免拼接崩溃
        if len(sg_list) != num_sge:
            num_sge = len(sg_list)

        if ctx:
            ctx.alloc_variable(f"{sg_var}[{num_sge}]", "struct ibv_sge")

        s = ""
        for idx, sge in enumerate(sg_list):
            s += sge.to_cxx(f"{sg_var}[{idx}]", ctx)

        s += f"""
    if (ibv_advise_mr({pd_name}, {advice_macro}, {flags}, {sg_var}, {num_sge}) != 0) {{
        fprintf(stderr, "ibv_advise_mr failed\\n");
        return -1;
    }}
"""
        return s


class AllocDM(VerbCall):
    MUTABLE_FIELDS = ["dm", "attr_obj", "attr_var"]
    EXPORT_FIELDS = ["dm", "attr_obj"]
    CONTRACT = Contract(
        requires=[],  # 也可把 device ctx 建模为资源
        produces=[ProduceSpec("dm", State.ALLOCATED, "dm")],
        transitions=[],
    )

    def __init__(self, ctx_name: str = None, dm: str = None, attr_obj: IbvAllocDmAttr = None):
        # ctx_name 暂时不用
        if not dm:
            raise ValueError("dm must be provided for AllocDM")
        self.dm = ResourceValue(resource_type="dm", value=dm, mutable=False)

        self.attr_obj = attr_obj
        self.attr_var = ConstantValue("dm_attr_" + self.dm.value) if dm else ConstantValue("dm_attr_dm")

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []  # 记录已分配的资源

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        if ctx:
            ctx.alloc_variable(name=self.dm.value, type="struct ibv_dm *", array_size=None)

        if self.tracker:
            # Register the DM address in the tracker
            self.tracker.create("dm", self.dm.value)

            self.allocated_resources.append(("dm", self.dm.value))  # 记录已分配的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        dm = kv.get("dm", "unknown")
        length = int(kv.get("length", 0))
        log_align_req = int(kv.get("log_align_req", 0))
        return cls(dm=dm, length=length, log_align_req=log_align_req, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        dm_name = self.dm
        ib_ctx = ctx.ib_ctx
        code = ""
        # 生成 alloc_dm_attr 结构体内容（如果有）
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        code += f"""
    {dm_name} = ibv_alloc_dm({ib_ctx}, &{self.attr_var});
    if (!{dm_name}) {{
        fprintf(stderr, "Failed to allocate device memory (DM) {dm_name}\\n");
    }}
"""
        return code


class AllocMW(VerbCall):
    MUTABLE_FIELDS = ["pd", "mw", "mw_type"]
    EXPORT_FIELDS = ["pd", "mw", "mw_type"]
    CONTRACT = Contract(
        requires=[RequireSpec("pd", State.ALLOCATED, "pd")],
        produces=[ProduceSpec("mw", State.ALLOCATED, "mw")],
        transitions=[],
    )

    def __init__(self, pd: str = None, mw: str = None, mw_type: str = None):
        self.pd = ResourceValue(resource_type="pd", value=pd) if pd else ResourceValue(resource_type="pd", value="pd")
        self.mw = (
            ResourceValue(resource_type="mw", value=mw, mutable=False)
            if mw
            else ResourceValue(resource_type="mw", value="mw", mutable=False)
        )
        self.mw_type = (
            EnumValue(mw_type, enum_type="IBV_MW_TYPE_ENUM")
            if mw_type
            else EnumValue("IBV_MW_TYPE_1", enum_type="IBV_MW_TYPE_ENUM")
        )

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        if ctx:
            ctx.alloc_variable(name=self.mw.value, type="struct ibv_mw *", array_size=None)

        if self.tracker:
            self.tracker.use("pd", self.pd.value)
            self.tracker.create("mw", self.mw.value, pd=self.pd.value)

            self.allocated_resources.append(("mw", self.mw.value))  # 记录已分配的资源
            self.required_resources.append({"type": "pd", "name": self.pd.value, "position": "pd"})  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        mw = kv.get("mw", "unknown")
        mw_type = kv.get("type", "IBV_MW_TYPE_1")
        return cls(pd=pd, mw=mw, mw_type=mw_type, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = self.pd
        mw_name = self.mw

        return f"""
    /* ibv_alloc_mw */
    IF_OK_PTR({pd_name}, {{
        {mw_name} = ibv_alloc_mw({pd_name}, {self.mw_type});
        if (!{mw_name}) {{
            fprintf(stderr, "Failed to allocate memory window {mw_name}\\n");
        }}
    }});
"""


class AllocNullMR(VerbCall):
    """Allocate a null memory region (MR) associated with a protection domain."""

    MUTABLE_FIELDS = ["pd", "mr"]
    EXPORT_FIELDS = ["pd", "mr"]
    CONTRACT = Contract(
        requires=[RequireSpec("pd", State.ALLOCATED, "pd")],
        produces=[ProduceSpec("mr", State.ALLOCATED, "mr")],
        transitions=[],
    )

    def __init__(self, pd: str = None, mr: str = None):
        self.pd = ResourceValue(resource_type="pd", value=pd) if pd else ResourceValue(resource_type="pd", value="pd")
        self.mr = ResourceValue(resource_type="mr", value=mr) if mr else ResourceValue(resource_type="mr", value="mr")

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        self.context = ctx
        if self.context:
            self.context.alloc_variable(str(self.mr), "struct ibv_mr *", "NULL")

        if self.tracker:
            self.tracker.use("pd", self.pd.value)
            self.tracker.create("mr", self.mr.value, pd=self.pd.value)

            self.allocated_resources.append(("mr", self.mr.value))
            self.required_resources.append({"type": "pd", "name": self.pd.value, "position": "pd"})
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        mr = kv.get("mr", "unknown")
        return cls(pd=pd, mr=mr, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = self.pd
        mr_name = self.mr
        return f"""
    /* ibv_alloc_null_mr */
    IF_OK_PTR({pd_name}, {{
        {mr_name} = ibv_alloc_null_mr({pd_name});
        if (!{mr_name}) {{
            fprintf(stderr, "Failed to allocate null MR {mr_name}\\n");
        }}
    }});
"""


class AllocParentDomain(VerbCall):
    """
    Allocate a new parent domain using an existing protection domain.

    Attributes:
        context (str): Associated IBV context.
        pd (str): Address of the existing protection domain.
        parent_pd (str): Address for the new parent domain.
        attr_obj (IbvParentDomainInitAttr): Optional, struct fields.
    """

    MUTABLE_FIELDS = ["context", "pd", "parent_pd", "attr_var", "attr_obj"]
    EXPORT_FIELDS = ["context", "pd", "parent_pd", "attr_obj"]
    CONTRACT = Contract(
        requires=[RequireSpec("pd", State.ALLOCATED, "pd")],
        produces=[ProduceSpec("parent_pd", State.ALLOCATED, "parent_pd")],
        transitions=[],
    )

    def __init__(
        self,
        context=None,
        pd: str = None,
        parent_pd: str = None,
        attr_var: str = None,
        attr_obj: IbvParentDomainInitAttr = None,
    ):
        self.context = context  # IBV context, e.g., ib_ctx
        self.pd = ResourceValue(resource_type="pd", value=pd) if pd else ResourceValue(resource_type="pd", value="pd")
        self.parent_pd = ResourceValue(resource_type="parent_pd", value=parent_pd)  # 新PD变量名
        self.attr_var = ConstantValue(attr_var or f"parent_pd_attr_{self.parent_pd.value}")  # 结构体变量名
        self.attr_obj = attr_obj  # 可为 None，trace replay 下只传变量名

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []  # 记录已分配的资源

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        self.context = self.context or ctx.ib_ctx
        if self.tracker:
            # Register the parent domain address in the tracker
            self.tracker.use("pd", self.pd.value)  # 确保父域的PD被使用
            self.tracker.create("parent_pd", self.parent_pd.value, pd=self.pd.value)

            self.required_resources.append({"type": "pd", "name": self.pd.value, "position": "pd"})  # 记录需要的资源
            self.allocated_resources.append(("parent_pd", self.parent_pd.value))  # 记录已分配的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        pd_new = kv.get("parent_pd", "unknown")
        attr_var = kv.get("attr_var", f"pd_attr_{pd_new}")
        attr_obj = kv.get("attr_obj")  # 可选，trace/fuzz模式灵活
        return cls(
            context=ctx.ib_ctx,
            pd=pd,
            parent_pd=pd_new,
            attr_var=attr_var,
            attr_obj=attr_obj,
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        if self.pd is None and self.attr_obj is None:
            raise ValueError("Either pd or attr_obj must be provided for AllocParentDomain")
        parent_pd_name = self.parent_pd
        code = ""
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        code += f"""
    {parent_pd_name} = ibv_alloc_parent_domain({self.context}, &{self.attr_var});
    if (!{parent_pd_name}) {{
        fprintf(stderr, "Failed to allocate parent domain {parent_pd_name}\\n");
    }}
"""
        return code


class AllocPD(VerbCall):
    """Allocate a protection domain (PD) for the RDMA device context."""

    MUTABLE_FIELDS = ["pd"]
    EXPORT_FIELDS = ["pd"]
    CONTRACT = Contract(
        requires=[], produces=[ProduceSpec(rtype="pd", state=State.ALLOCATED, name_attr="pd")], transitions=[]
    )

    def __init__(self, pd: str = None):
        if not pd:
            raise ValueError("pd must be provided for AllocPD")
        self.pd = ResourceValue(resource_type="pd", value=pd, mutable=False)

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []  # 记录已分配的资源
        self.context = None  # IBV context, e.g., ib_ctx

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        self.context = ctx  # binding context
        if self.context:
            self.context.alloc_variable(str(self.pd), "struct ibv_pd *", "NULL")

        if self.tracker:
            self.tracker.create("pd", self.pd.value)

            self.allocated_resources.append(("pd", self.pd.value))  # 记录已分配的资源

        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    """Initialize a new protection domain (PD) for the RDMA device context."""

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        return cls(pd=pd, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = self.pd
        return f"""
    /* ibv_alloc_pd */
    {pd_name} = ibv_alloc_pd({self.context.ib_ctx});
    if (!{pd_name}) {{
        fprintf(stderr, "Failed to allocate protection domain {pd_name}\\n");
    }}
"""


class AllocTD(VerbCall):
    """
    Represents ibv_alloc_td() verb call to allocate a thread domain object.
    """

    MUTABLE_FIELDS = ["td", "attr_var", "attr_obj"]
    EXPORT_FIELDS = ["td", "attr_obj"]
    CONTRACT = Contract(  # TODO: 改为动态
        requires=[],  # 也可把 device ctx 建模为资源
        produces=[ProduceSpec("td", State.ALLOCATED, "td")],
        transitions=[],
    )

    def __init__(self, td: str = None, attr_var: str = None, attr_obj: IbvTdInitAttr = None):
        if not td:
            raise ValueError("td must be provided for AllocTD")
        self.td = ResourceValue(resource_type="td", value=td)
        self.attr_var = ConstantValue(attr_var or f"td_init_attr_{self.td.value}")  # 结构体变量名
        self.attr_obj = attr_obj  # IbvTdInitAttr对象，若有则生成内容

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        self.context = ctx
        if self.context:
            self.context.alloc_variable(name=self.td.value, type="struct ibv_td *", array_size=None)
        if self.tracker:
            self.tracker.create("td", self.td.value)

            self.allocated_resources.append(("td", self.td.value))
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        td = kv.get("td", "td")
        attr_var = kv.get("attr_var", "td_attr")
        attr_obj = kv.get("attr_obj")  # 若trace记录了具体结构体内容
        return cls(td=td, attr_var=attr_var, attr_obj=attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        td_name = self.td
        code = ""
        # 若结构体对象不为None，自动生成初始化内容
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            code += f"\n    struct ibv_td_init_attr {self.attr_var} = {{0}};\n"
        code += f"""
    {td_name} = ibv_alloc_td({ctx.ib_ctx}, &{self.attr_var});
    if (!{td_name}) {{
        fprintf(stderr, "Failed to allocate thread domain {td_name}\\n");
        return -1;
    }}
"""
        return code


class AttachMcast(VerbCall):
    MUTABLE_FIELDS = ["qp", "gid", "lid"]
    CONTRACT = Contract(
        requires=[RequireSpec("qp", None, "qp", exclude_states=[State.DESTROYED])], produces=[], transitions=[]
    )

    def __init__(self, qp: str = None, gid: str = None, lid: int = None):
        # 注意gid需要是变量，不然无法传参 # TODO: gid这种类型如何处理
        self.qp = ResourceValue(resource_type="qp", value=qp) if qp else ResourceValue(resource_type="qp", value="qp")
        self.gid = ConstantValue(gid or "gid")  # GID变量名，默认为"gid"
        self.lid = IntValue(lid or 0)  # LID值，默认为0

        self.tracker = None
        self.required_resources = []

    """Attach a multicast group to a queue pair (QP) using the specified GID and LID."""

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            self.tracker.use("qp", self.qp.value)

            self.required_resources.append({"type": "qp", "name": self.qp.value, "position": "qp"})

        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        gid = kv.get("gid", "unknown")
        lid = int(kv.get("lid", "0"))
        return cls(qp=qp, gid=gid, lid=lid)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = str(self.qp)
        gid_value = f"{self.gid}"
        return f"""
    /* ibv_attach_mcast */
    IF_OK_PTR({qp_name}, {{
        if (ibv_attach_mcast({qp_name}, &{gid_value}, {self.lid})) {{
            fprintf(stderr, "Failed to attach multicast group {qp_name}\\n");
        }}
    }});
"""


class BindMW(VerbCall):
    MUTABLE_FIELDS = ["qp", "mw", "mw_bind_var", "mw_bind_obj"]
    # CONTRACT = Contract(  # TODO: 改为动态（其实有办法筛选）
    #     requires=[RequireSpec("qp", None, "qp"), RequireSpec("mr", None, "mw_bind_obj.bind_info.mr")],
    #     produces=[ProduceSpec("mw", State.ALLOCATED, "mw")],
    #     transitions=[],
    # )

    # CONTRACT = Contract(  # TODO: 改为动态（其实有办法筛选）
    #     requires=[
    #         RequireSpec("qp", None, "qp", exclude_states=[State.DESTROYED]),
    #         RequireSpec("mr", State.ALLOCATED, "mw_bind_obj.bind_info.mr"),
    #         RequireSpec("mw", State.ALLOCATED, "mw"),
    #     ],
    #     produces=[],
    #     transitions=[
    #         TransitionSpec(
    #             "buf", from_state=State.ALLOCATED, to_state=State.USED, name_attr="mw_bind_obj.bind_info.addr"
    #         )
    #     ],
    # )

    def __init__(
        self,
        qp: str = None,
        mw: str = None,
        mw_bind_var: str = None,
        mw_bind_obj: IbvMwBind = None,
    ):
        self.qp = ResourceValue(resource_type="qp", value=qp) if qp else None
        self.mw = ResourceValue(resource_type="mw", value=mw) if mw else None
        # 默认生成 mw_bind_<mw>
        self.mw_bind_var = ConstantValue(mw_bind_var or f"mw_bind_{self.mw.value}")  # MW bind variable name
        self.mw_bind_obj = mw_bind_obj

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    def _contract(self):
        reqs = [
            RequireSpec("qp", None, "qp", exclude_states=[State.DESTROYED]),
            RequireSpec("mw", State.ALLOCATED, "mw"),
        ]
        trans = []
        if self.mw_bind_obj is not None and self.mw_bind_obj.bind_info is not None:
            reqs.append(RequireSpec("mr", State.ALLOCATED, "mw_bind_obj.bind_info.mr"))
            # trans.append(
            #     TransitionSpec(
            #         "buf", from_state=State.ALLOCATED, to_state=State.USED, name_attr="mw_bind_obj.bind_info.addr"
            #     )
            # )

        return Contract(
            requires=reqs,
            produces=[],
            transitions=trans,
        )

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            self.tracker.use("qp", self.qp.value)
            # self.tracker.create("mw", self.mw.value, qp=self.qp.value)
            self.tracker.use("mw", self.mw.value)  # 确保MW被使用

            self.required_resources.append({"type": "qp", "name": self.qp.value, "position": "qp"})
            self.allocated_resources.append(("mw", self.mw.value))  # 记录已分配的资源
            if self.mw_bind_obj is not None:
                self.mw_bind_obj.apply(ctx)  # 确保结构体对象被追踪
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def get_required_resources_recursively(self) -> list[dict[str, str]]:
        """Get all required resources recursively."""
        resources = self.get_required_resources()
        resources.extend(self.mw_bind_obj.get_required_resources_recursively() if self.mw_bind_obj else [])
        return resources

    def set_resource_recursively(self, res_type: str, old_res_name: str, new_res_name: str):
        """Set the resource name recursively in the MW bind object."""
        self.set_resource(res_type, old_res_name, new_res_name)
        if self.mw_bind_obj is not None:
            self.mw_bind_obj.set_resource_recursively(res_type, old_res_name, new_res_name)
        # Update the MW bind variable name
        # if res_type == 'mw_bind' and self.mw_bind_var == old_res_name:
        #     self.mw_bind_var = new_res_name

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        mw = kv.get("mw", "unknown")
        mw_bind_var = kv.get("mw_bind_var", f"mw_bind_{mw}")
        mw_bind_obj = kv.get("mw_bind_obj")  # 可选，支持结构体对象
        return cls(qp=qp, mw=mw, mw_bind_var=mw_bind_var, mw_bind_obj=mw_bind_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = str(self.qp)
        mw_name = self.mw
        mw_bind_var = str(self.mw_bind_var)
        code = ""
        if self.mw_bind_obj is not None:
            code += self.mw_bind_obj.to_cxx(mw_bind_var, ctx)

        code += f"""
    IF_OK_PTR({qp_name}, {{
        IF_OK_PTR({mw_name}, {{
            if (ibv_bind_mw({qp_name}, {mw_name}, &{mw_bind_var}) != 0) {{
                fprintf(stderr, "Failed to bind MW {mw_name}, {qp_name}\\n");
            }}
        }});
    }});
"""
        return code


class CloseDevice(VerbCall):
    """Close the RDMA device context. This does not release all resources allocated using the context.
    Make sure to release all associated resources before closing."""

    MUTABLE_FIELDS = []
    EXPORT_FIELDS = []

    def __init__(self):
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        return cls()

    def generate_c(self, ctx: CodeGenContext) -> str:
        context_name = ctx.ib_ctx
        return f"""
    /* ibv_close_device */
    IF_OK_PTR({context_name}, {{
        if (ibv_close_device({context_name})) {{
            fprintf(stderr, "Failed to close device {context_name}\\n");
            }}
        }}
    );
"""


class CloseXRCD(VerbCall):
    """Close an XRC domain."""

    MUTABLE_FIELDS = ["xrcd"]
    EXPORT_FIELDS = ["xrcd"]
    CONTRACT = Contract(
        requires=[RequireSpec("xrcd", State.ALLOCATED, "xrcd")],
        produces=[],
        transitions=[],
    )

    def __init__(self, xrcd: str = None):
        if not xrcd:
            raise ValueError("xrcd must be provided for CloseXRCD")
        self.xrcd = ResourceValue(resource_type="xrcd", value=xrcd)

        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the XRCD address in the tracker
            self.tracker.use("xrcd", self.xrcd.value)
            self.required_resources.append({"type": "xrcd", "name": self.xrcd.value, "position": "xrcd"})
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        xrcd = kv.get("xrcd", "unknown")
        return cls(xrcd=xrcd)

    def generate_c(self, ctx: CodeGenContext) -> str:
        xrcd_name = self.xrcd
        return f"""
    /* ibv_close_xrcd */
    IF_OK_PTR({xrcd_name}, {{
        if (ibv_close_xrcd({xrcd_name})) {{
            fprintf(stderr, "Failed to close XRCD {xrcd_name}\\n");
        }}
    }});
"""


class CreateAH(VerbCall):
    """
    ibv_create_ah() - 创建 address handle。
    参数：
        pd    -- PD变量名（如"pd1"）
        attr_var   -- 结构体变量名（如"ah_attr1"）
        attr_obj   -- IbvAHAttr对象（可选，自动生成结构体内容）
        ret_var    -- 返回的 ibv_ah* 变量名（如"ah1"）
    """

    MUTABLE_FIELDS = ["pd", "attr_var", "ah", "attr_obj"]
    EXPORT_FIELDS = ["pd", "ah", "attr_obj"]
    CONTRACT = Contract(
        requires=[RequireSpec("pd", State.ALLOCATED, "pd")],
        produces=[ProduceSpec("ah", State.ALLOCATED, "ah")],
        transitions=[],
    )

    def __init__(
        self,
        pd: str = None,
        attr_var: str = None,
        ah: str = None,
        attr_obj: IbvAHAttr = None,
    ):
        self.pd = ResourceValue(resource_type="pd", value=pd) if pd else ResourceValue(resource_type="pd", value="pd")
        # 默认生成 ah_attr_<pd>
        self.attr_var = ConstantValue(attr_var or f"ah_attr_{self.pd.value}")
        self.ah = (
            ResourceValue(resource_type="ah", value=ah)
            if ah
            else ResourceValue(resource_type="ah", value=f"ah_{self.pd.value}")
        )
        self.attr_obj = attr_obj

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            self.tracker.use("pd", self.pd.value)
            self.tracker.create("ah", self.ah.value, pd=self.pd.value)

            self.required_resources.append({"type": "pd", "name": self.pd.value, "position": "pd"})
            self.allocated_resources.append(("ah", self.ah.value))
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "pd")
        attr_var = kv.get("attr", "ah_attr")
        ret_var = kv.get("ret_var", "ah")
        attr_obj = kv.get("attr_obj")  # trace 里若含结构体内容
        return cls(pd, attr_var, ret_var, attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = self.pd
        ah_var = self.ah
        code = ""
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        code += f"""
    IF_OK_PTR({pd_name}, {{
        {ah_var} = ibv_create_ah({pd_name}, &{self.attr_var});
        if (!{ah_var}) {{
            fprintf(stderr, "ibv_create_ah failed {ah_var}\\n");
        }}
    }});
"""
        return code


class CreateAHFromWC(VerbCall):
    MUTABLE_FIELDS = ["pd", "wc", "grh", "port_num", "ah"]
    EXPORT_FIELDS = ["pd", "wc", "grh", "port_num", "ah"]
    CONTRACT = Contract(
        requires=[
            RequireSpec("pd", State.ALLOCATED, "pd"),
            RequireSpec("wc", State.ALLOCATED, "wc"),
            # RequireSpec("grh", State.ALLOCATED, "grh"),
        ],
        produces=[ProduceSpec("ah", State.ALLOCATED, "ah")],
        transitions=[],
    )

    def __init__(
        self,
        pd: str = None,
        wc: str = None,
        grh: IbvGlobalRoute = None,
        port_num: int = None,
        ah: str = None,
    ):
        self.pd = ResourceValue(resource_type="pd", value=pd) if pd else None
        self.wc = ResourceValue(resource_type="wc", value=wc) if wc else None
        self.grh = grh
        self.port_num = IntValue(port_num or 1)  # 默认端口号为1
        self.ah = ResourceValue(resource_type="ah", value=ah) if ah else None  # Variable name for the created AH

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the PD, WC, and AH addresses in the tracker
            self.tracker.use("pd", self.pd.value)
            self.tracker.use("wc", self.wc.value)
            self.tracker.use("grh", self.grh.value)
            self.tracker.create("ah", self.ah.value, pd=self.pd.value)

            self.required_resources.append({"type": "pd", "name": self.pd.value, "position": "pd"})  # 记录需要的资源
            self.required_resources.append({"type": "wc", "name": self.wc.value, "position": "wc"})
            self.required_resources.append({"type": "grh", "name": self.grh.value, "position": "grh"})  # 记录需要的资源
            self.allocated_resources.append(("ah", self.ah.value))
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        wc = kv.get("wc", "unknown")
        grh = kv.get("grh", "unknown")
        port_num = int(kv.get("port_num", 1))
        return cls(pd=pd, wc=wc, grh=grh, port_num=port_num)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = self.pd
        wc_name = self.wc
        grh_name = self.grh
        port_num = self.port_num

        return f"""
    /* ibv_create_ah_from_wc */
    IF_OK_PTR({pd_name}, {{
        IF_OK_PTR({wc_name}, {{
            {self.ah} = ibv_create_ah_from_wc({pd_name}, &{wc_name}, &{grh_name}, {port_num});
            if (!{self.ah}) {{
                fprintf(stderr, "Failed to create AH from work completion {self.ah}\\n");
            }}
        }}
    }});
"""


class CreateCompChannel(VerbCall):
    MUTABLE_FIELDS = ["channel"]
    EXPORT_FIELDS = ["channel"]
    CONTRACT = Contract(requires=[], produces=[ProduceSpec("channel", State.ALLOCATED, "channel")], transitions=[])

    def __init__(self, channel: str = None):
        self.channel = (
            ResourceValue(resource_type="channel", value=channel)
            if channel
            else ResourceValue(resource_type="channel", value="channel")
        )

        self.tracker = None
        # self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            self.tracker.create("channel", self.channel.value)

            self.allocated_resources.append(("channel", self.channel.value))
        ctx.alloc_variable(str(self.channel), "struct ibv_comp_channel *", "NULL")
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        channel = kv.get("channel", "unknown")
        return cls(channel=channel)

    def generate_c(self, ctx: CodeGenContext) -> str:
        channel_name = self.channel
        ib_ctx = ctx.ib_ctx
        return f"""
    /* ibv_create_comp_channel */
    {channel_name} = ibv_create_comp_channel({ib_ctx});
    if (!{channel_name}) {{
        fprintf(stderr, "Failed to create completion channel {channel_name}\\n");
    }}
"""


class CreateCQ(VerbCall):
    MUTABLE_FIELDS = ["cqe", "cq_context", "channel", "comp_vector", "cq"]
    EXPORT_FIELDS = ["cqe", "cq_context", "channel", "comp_vector", "cq"]
    CONTRACT = Contract(requires=[], produces=[ProduceSpec("cq", State.ALLOCATED, "cq")], transitions=[])

    def __init__(
        self,
        cqe: int = 32,
        cq_context: str = "NULL",
        channel: str = "NULL",
        comp_vector: int = 0,
        cq: str = None,
    ):
        # TODO: channel 是否需要关联
        self.cqe = IntValue(cqe)
        self.cq_context = ConstantValue(cq_context)
        self.channel = ConstantValue(channel)
        self.comp_vector = IntValue(comp_vector)
        if not cq:
            raise ValueError("cq must be provided for CreateCQ")
        self.cq = ResourceValue(resource_type="cq", value=cq, mutable=False)
        self.tracker = None
        self.context = None
        self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        self.context = ctx  # TEMP

        if self.context:
            self.context.alloc_variable(str(self.cq), "struct ibv_cq *", "NULL")

        if self.tracker:
            # self.tracker.create('cq', cq, context=ctx)
            self.tracker.create("cq", self.cq.value)

            self.allocated_resources.append(("cq", self.cq.value))

        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        context = kv.get("context", ctx.ib_ctx)
        cqe = int(kv.get("cqe", 32))
        cq_context = kv.get("cq_context", "NULL")
        channel = kv.get("channel", "NULL")
        comp_vector = int(kv.get("comp_vector", 0))
        cq = kv.get("cq", "unknown")
        # ctx.alloc_cq(cq)
        return cls(
            context=context,
            cqe=cqe,
            cq_context=cq_context,
            channel=channel,
            comp_vector=comp_vector,
            cq=cq,
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = coerce_str(self.cq)
        cqe = coerce_int(self.cqe)
        comp_vector = coerce_int(self.comp_vector)
        channel = coerce_str(self.channel)
        cq_context = coerce_str(self.cq_context)
        return f"""
    /* ibv_create_cq */
    {cq_name} = ibv_create_cq({self.context.ib_ctx}, {cqe}, 
                              {cq_context}, {channel}, 
                              {comp_vector});
    if (!{cq_name}) {{
        fprintf(stderr, "Failed to create completion queue {cq_name}\\n");
    }}
"""


class CreateCQEx(VerbCall):
    """
    表示 ibv_create_cq_ex() 调用，自动生成/重放 cq_ex 的初始化与调用。
    参数：
        ctx_name      -- IBV context 变量名（如"ctx"）
        cq_var        -- 返回 CQ_EX 变量名（如"cq_ex1"）
        cq_attr_var   -- cq_attr 结构体变量名（如"cq_attr1"）
        cq_attr_obj   -- IbvCQInitAttrEx对象（可选，自动生成结构体内容）
    """

    MUTABLE_FIELDS = ["cq_ex", "cq_attr_var", "cq_attr_obj"]
    EXPORT_FIELDS = ["cq_ex", "cq_attr_obj"]
    CONTRACT = Contract(
        requires=[],  # 也可以把 ctx（device context）建模为资源；先省略
        produces=[ProduceSpec("cq", State.ALLOCATED, "cq_ex")],  # 归一到 'cq' 类型
        transitions=[],
    )

    def __init__(
        self,
        # ctx_name: str = None,
        cq_ex: str = None,
        cq_attr_var: str = None,
        cq_attr_obj: IbvCQInitAttrEx = None,
    ):
        # IBV context variable name, default is "ctx"
        # self.ctx_name = ConstantValue(ctx_name or "ctx")
        if not cq_ex:
            raise ValueError("cq_ex must be provided for CreateCQEx")
        self.cq_ex = ResourceValue(resource_type="cq_ex", value=cq_ex)
        # 默认生成 cq_attr_<cq_var>
        self.cq_attr_var = ConstantValue(cq_attr_var or f"cq_attr_{self.cq_ex.value}")
        self.cq_attr_obj = cq_attr_obj

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        self.ctx_name = ctx.ib_ctx
        if ctx:
            ctx.alloc_variable(name=self.cq_ex.value, type="struct ibv_cq_ex *", array_size=None)
        if self.tracker:
            # Register the CQ_EX address in the tracker
            self.tracker.create("cq_ex", self.cq_ex.value)
            self.allocated_resources.append(("cq_ex", self.cq_ex.value))
            if self.cq_attr_obj is not None:
                # Register the CQ_EX attribute object in the tracker
                self.cq_attr_obj.apply(ctx)
            # if self.cq_attr_obj.parent_domain:
            #     # Register the parent domain address in the tracker
            #     self.tracker.use('pd', self.cq_attr_obj.parent_domain)
            #     self.required_resources.append(('pd', self.cq_attr_obj.parent_domain))
            # # 记录需要的资源 # to be recursive 标记
            # # Register the CQ_EX attribute variable
            # self.tracker.create('cq_attr', self.cq_attr_var, cq_ex=cq_ex)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def get_required_resources_recursively(self) -> list[dict[str, str]]:
        """Get all required resources recursively."""
        resources = self.get_required_resources()
        if self.cq_attr_obj is not None:
            resources.extend(self.cq_attr_obj.get_required_resources_recursively())
        return resources

    def set_resource_recursively(self, res_type: str, old_res_name: str, new_res_name: str):
        """Set the resource name recursively in the MW bind object."""
        self.set_resource(res_type, old_res_name, new_res_name)
        if self.cq_attr_obj is not None:
            self.cq_attr_obj.set_resource_recursively(res_type, old_res_name, new_res_name)

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ctx_name = kv.get("ctx", "ctx")
        cq_var = kv.get("cq_var", "cq_ex")
        cq_attr_var = kv.get("cq_attr_var", "cq_attr")
        cq_attr_obj = kv.get("cq_attr_obj")  # 若trace含结构体内容
        return cls(ctx_name, cq_var, cq_attr_var, cq_attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        code = ""
        # 自动生成结构体内容
        if self.cq_attr_obj is not None:
            code += self.cq_attr_obj.to_cxx(self.cq_attr_var, ctx)
        code += f"""
    {self.cq_ex} = ibv_create_cq_ex({self.ctx_name}, &{self.cq_attr_var});
    if (!{self.cq_ex}) {{
        fprintf(stderr, "ibv_create_cq_ex failed {self.cq_ex}\\n");
    }}
"""
        return code


class CreateFlow(VerbCall):
    """
    表示 ibv_create_flow() 调用，自动生成/重放 flow_attr 的初始化与调用。
    参数：
        qp      -- QP变量名（如"qp1"）
        flow_var     -- 返回 flow 变量名（如"flow1"）
        flow_attr_var-- flow_attr 结构体变量名（如"flow_attr1"）
        flow_attr_obj-- IbvFlowAttr对象（可选，自动生成结构体内容）
    """

    MUTABLE_FIELDS = ["qp", "flow", "flow_attr_var", "flow_attr_obj"]
    EXPORT_FIELDS = ["qp", "flow", "flow_attr_obj"]
    CONTRACT = Contract(
        requires=[RequireSpec("qp", None, "qp", exclude_states=[State.DESTROYED])],
        produces=[ProduceSpec("flow", State.ALLOCATED, "flow")],
        transitions=[],
    )

    def __init__(
        self,
        qp: str = None,
        flow: str = None,
        flow_attr_var: str = None,
        flow_attr_obj: IbvFlowAttr = None,
    ):
        if not flow:
            raise ValueError("flow must be provided for CreateFlow")
        self.qp = ResourceValue(resource_type="qp", value=qp) if qp else None
        self.flow = ResourceValue(resource_type="flow", value=flow) if flow else None
        # 默认生成 flow_attr_<qp>
        self.flow_attr_var = ConstantValue(
            flow_attr_var or f"flow_attr_{self.qp.value}"
        )  # Flow attribute variable name
        self.flow_attr_obj = flow_attr_obj  # None时仅生成结构体声明

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        if ctx:
            ctx.alloc_variable(name=self.flow.value, type="struct ibv_flow *", array_size=None)
        if self.tracker:
            # Register the QP address in the tracker
            self.tracker.use("qp", self.qp.value)
            self.required_resources.append({"type": "qp", "name": self.qp.value, "position": "qp"})  # 记录需要的资源
            # Register the flow address in the tracker
            self.tracker.create("flow", self.flow.value, qp=self.qp.value)
            # Register the flow attribute variable
            # self.tracker.create('flow_attr', self.flow_attr_var, flow=flow)
            self.allocated_resources.append(("flow", self.flow.value))  # 记录已分配的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "qp")
        flow_var = kv.get("flow_var", "flow")
        flow_attr_var = kv.get("flow_attr_var", "flow_attr")
        flow_attr_obj = kv.get("flow_attr_obj")  # 若trace含结构体内容
        return cls(qp, flow_var, flow_attr_var, flow_attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = str(self.qp)
        flow_var = self.flow
        flow_attr_var = self.flow_attr_var
        code = ""
        if self.flow_attr_obj is not None:
            code += self.flow_attr_obj.to_cxx(flow_attr_var, ctx)
        code += f"""
    IF_OK_PTR({qp_name}, {{
        {flow_var} = ibv_create_flow({qp_name}, &{flow_attr_var});
        if (!{flow_var}) {{
            fprintf(stderr, "ibv_create_flow failed {flow_var}\\n");
        }}
    }});
"""
        return code


class CreateQP(VerbCall):
    MUTABLE_FIELDS = ["pd", "qp", "init_attr_obj", "remote_qp"]
    EXPORT_FIELDS = ["pd", "qp", "init_attr_obj", "remote_qp"]
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="pd", state=State.ALLOCATED, name_attr="pd"),
            RequireSpec(rtype="cq", state=State.ALLOCATED, name_attr="init_attr_obj.send_cq"),
            RequireSpec(rtype="cq", state=State.ALLOCATED, name_attr="init_attr_obj.recv_cq"),
            RequireSpec(rtype="srq", state=State.ALLOCATED, name_attr="init_attr_obj.srq"),
            RequireSpec(rtype="remote_qp", state=State.ALLOCATED, name_attr="remote_qp"),
        ],
        produces=[
            # ProduceSpec(rtype="qp", state=State.ALLOCATED, name_attr="qp"),
            ProduceSpec(rtype="qp", state=State.RESET, name_attr="qp", metadata_fields=["pd"]),
        ],
        transitions=[
            TransitionSpec(rtype="remote_qp", from_state=State.ALLOCATED, to_state=State.USED, name_attr="remote_qp"),
        ],
    )

    def __init__(self, pd: str = None, qp: str = None, init_attr_obj: IbvQPInitAttr = None, remote_qp: str = None):
        self.pd = ResourceValue(resource_type="pd", value=pd) if pd else "NULL"
        if not qp:
            raise ValueError("qp must be provided for CreateQP")
        self.qp = ResourceValue(resource_type="qp", value=qp, mutable=False)
        # QP变量名
        self.init_attr_obj = init_attr_obj  # IbvQPInitAttr实例（如自动生成/trace重放）
        self.remote_qp = LocalResourceValue(resource_type="remote_qp", value=remote_qp)

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    # def _contract(self) -> Contract:
    #     """Generate the contract for this verb call."""
    #     return self._contract_for_this_call()

    # def _contract_for_this_call(self) -> Contract:
    #     # 读取本次期望目标状态
    #     return

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        self.context = ctx  # TEMP
        if self.context:
            self.context.alloc_variable(str(self.qp), "struct ibv_qp *", "NULL")

            # self.srv_name = self.context.gen_var_name("srv", "")
            # qp_name = str(self.qp)
            # self.context.make_qp_binding(qp_name, self.srv_name)
            self.context.make_qp_binding(str(self.qp), self.remote_qp.value)
            self.context.make_qp_recv_cq_binding(
                str(self.qp), self.init_attr_obj.recv_cq if self.init_attr_obj else "NULL"
            )
            self.context.make_qp_send_cq_binding(
                str(self.qp), self.init_attr_obj.send_cq if self.init_attr_obj else "NULL"
            )

        if self.tracker:
            # Register the PD and QP addresses in the tracker
            self.tracker.use("pd", self.pd.value)
            self.tracker.create("qp", self.qp.value, pd=self.pd.value)
            self.allocated_resources.append(("qp", self.qp.value))  # 记录已分配的资源
            self.required_resources.append({"type": "pd", "name": self.pd.value, "position": "pd"})  # 记录需要的资源
            if self.init_attr_obj:
                self.init_attr_obj.apply(ctx)
                # # # Register the SRQ if it exists
                # if self.init_attr_obj.srq:
                #     self.tracker.use('srq', self.init_attr_obj.srq)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def get_required_resources_recursively(self) -> list[dict[str, str]]:
        """Get all required resources recursively."""
        resources = self.get_required_resources().copy()  # this is a bug!
        if self.init_attr_obj is not None:
            resources.extend(self.init_attr_obj.get_required_resources_recursively())
        return resources

    def set_resource_recursively(self, res_type: str, old_res_name: str, new_res_name: str):
        """Set the resource name recursively in the MW bind object."""
        self.set_resource(res_type, old_res_name, new_res_name)
        if self.init_attr_obj is not None:
            self.init_attr_obj.set_resource_recursively(res_type, old_res_name, new_res_name)

    @classmethod
    def from_trace(cls, info, ctx):
        kv = _parse_kv(info)
        return cls(
            pd=kv.get("pd"),
            init_attr_var=kv.get("init_attr"),
            qp=kv.get("qp"),
            init_attr_obj=kv.get("init_attr_obj"),  # 若trace包含IbvQPInitAttr对象
        )

    def generate_c(self, ctx):
        qp_name = str(self.qp)
        pd_name = self.pd
        attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
        attr_name = f"attr_init{attr_suffix}"
        # ctx.alloc_variable(attr_name, "struct ibv_qp_init_attr")  # Register the attribute name in the context
        code = ""
        # 1. 生成/声明init_attr结构体
        if self.init_attr_obj is not None:
            code += self.init_attr_obj.to_cxx(attr_name, ctx)
        # 2. 声明QP变量

        return f"""
    /* ibv_create_qp */
    IF_OK_PTR({pd_name}, {{
        {code}
        {qp_name} = ibv_create_qp({pd_name}, &{attr_name});
        if (!{qp_name}) {{
            fprintf(stderr, "Failed to create QP {qp_name}\\n");
        }}
        
        IF_OK_PTR({qp_name}, {{
            qps[qps_size++] = (PR_QP){{
                .id = "{qp_name}",
                .qpn = {qp_name}->qp_num,
                .psn = 0,
                .port = 1,
                .lid = 0,
                .gid = "" // will set below
            }};
            
            snprintf(qps[qps_size-1].gid, sizeof(qps[qps_size-1].gid),
                        "%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x",
                        {self.context.gid_var}.raw[0], {self.context.gid_var}.raw[1], {self.context.gid_var}.raw[2], {self.context.gid_var}.raw[3], {self.context.gid_var}.raw[4], {self.context.gid_var}.raw[5], {self.context.gid_var}.raw[6], {self.context.gid_var}.raw[7], {self.context.gid_var}.raw[8], {self.context.gid_var}.raw[9], {self.context.gid_var}.raw[10], {self.context.gid_var}.raw[11], {self.context.gid_var}.raw[12], {self.context.gid_var}.raw[13], {self.context.gid_var}.raw[14], {self.context.gid_var}.raw[15]);
                        
            prs[prs_size++] = (PR_Pair){{
                .id = "pair-{qp_name}-{self.remote_qp}",
                .cli_id = "{qp_name}",
                .srv_id = "{self.remote_qp}"
            }};
            
            pr_write_client_update_claimed(CLIENT_UPDATE_PATH, qps, qps_size, mrs, mrs_size, prs, prs_size);
        }});
    }});
"""


class CreateQPEx(VerbCall):
    """
    表示 ibv_create_qp_ex() 调用，自动生成/重放 qp_init_attr_ex 的初始化与调用。
    参数：
        ctx_name        -- IBV context 变量名（如"ctx"）
        qp_var          -- 返回 QP 变量名（如"qp1"）
        qp_attr_var     -- qp_init_attr_ex 结构体变量名（如"qp_init_attr_ex1"）
        qp_attr_obj     -- IbvQPInitAttrEx对象（可选，自动生成结构体内容）
    """

    MUTABLE_FIELDS = ["qp", "qp_attr_var", "qp_attr_obj"]
    EXPORT_FIELDS = ["qp", "qp_attr_obj"]
    CONTRACT = Contract(
        requires=[
            RequireSpec("pd", State.ALLOCATED, "qp_attr_obj.pd"),
            RequireSpec("cq", State.ALLOCATED, "qp_attr_obj.send_cq"),
            RequireSpec("cq", State.ALLOCATED, "qp_attr_obj.recv_cq"),
            RequireSpec(rtype="srq", state=State.ALLOCATED, name_attr="init_attr_obj.srq"),
            RequireSpec(rtype="remote_qp", state=State.ALLOCATED, name_attr="remote_qp"),
        ],
        produces=[ProduceSpec("qp", State.RESET, "qp")],
        transitions=[],
    )

    def __init__(
        self,
        # ctx_name: str = None,
        qp: str = None,
        qp_attr_var: str = None,
        qp_attr_obj: IbvQPInitAttrEx = None,
        remote_qp: str = None,
    ):
        # IBV context variable name, default is "ctx"
        # self.ctx_name = ConstantValue(ctx_name or "ctx")
        if not qp:
            raise ValueError("qp must be provided for CreateQPEx")
        self.qp = (
            ResourceValue(resource_type="qp", value=qp) if qp else ResourceValue(resource_type="qp", value="qp")
        )  # QP variable name, default is "qp"
        # 默认生成 qp_init_attr_ex_<qp_var>
        self.qp_attr_var = ConstantValue(
            qp_attr_var or f"qp_init_attr_ex_{self.qp.value}"
        )  # QP attribute variable name
        self.qp_attr_obj = qp_attr_obj  # 若为None仅生成结构体声明
        self.remote_qp = LocalResourceValue(resource_type="remote_qp", value=remote_qp)

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        self.ctx_name = ctx.ib_ctx
        self.context = ctx  # TEMP
        if ctx:
            ctx.alloc_variable(name=self.qp.value, type="struct ibv_qp *", array_size=None)
            self.context.make_qp_binding(str(self.qp), self.remote_qp.value)
            self.context.make_qp_recv_cq_binding(str(self.qp), self.qp_attr_obj.recv_cq if self.qp_attr_obj else "NULL")
            self.context.make_qp_send_cq_binding(str(self.qp), self.qp_attr_obj.send_cq if self.qp_attr_obj else "NULL")
        if self.tracker:
            # Register the QP address in the tracker
            self.tracker.create("qp", self.qp.value)
            self.allocated_resources.append(("qp", self.qp.value))  # 记录已分配的资源
            if self.qp_attr_obj:
                self.qp_attr_obj.apply(ctx)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def get_required_resources_recursively(self) -> list[dict[str, str]]:
        """Get all required resources recursively."""
        resources = self.get_required_resources().copy()
        if self.qp_attr_obj is not None:
            resources.extend(self.qp_attr_obj.get_required_resources_recursively())
        return resources

    def set_resource_recursively(self, res_type: str, old_res_name: str, new_res_name: str):
        """Set the resource name recursively in the MW bind object."""
        self.set_resource(res_type, old_res_name, new_res_name)
        if self.qp_attr_obj is not None:
            self.qp_attr_obj.set_resource_recursively(res_type, old_res_name, new_res_name)

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ctx_name = kv.get("ctx", "ctx")
        qp_var = kv.get("qp_var", "qp")
        qp_attr_var = kv.get("qp_attr_var", "qp_init_attr_ex")
        qp_attr_obj = kv.get("qp_attr_obj")  # 若trace含结构体内容
        return cls(ctx_name, qp_var, qp_attr_var, qp_attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = self.qp
        pd_name = self.qp_attr_obj.pd if self.qp_attr_obj else "NULL"
        attr_name = self.qp_attr_var
        code = ""
        # 自动生成结构体内容
        if self.qp_attr_obj is not None:
            code += self.qp_attr_obj.to_cxx(str(self.qp_attr_var), ctx)
        #         code += f"""
        #     {qp_name} = ibv_create_qp_ex({self.ctx_name}, &{self.qp_attr_var});
        #     if (!{qp_name}) {{
        #         fprintf(stderr, "ibv_create_qp_ex failed {qp_name}\\n");
        #     }}
        # """
        return f"""
    /* ibv_create_qp */
    IF_OK_PTR({pd_name}, {{
        {code}
        {qp_name} = ibv_create_qp_ex({self.ctx_name}, &{self.qp_attr_var});
        if (!{qp_name}) {{
            fprintf(stderr, "ibv_create_qp_ex failed {qp_name}\\n");
        }}
        
        IF_OK_PTR({qp_name}, {{
            qps[qps_size++] = (PR_QP){{
                .id = "{qp_name}",
                .qpn = {qp_name}->qp_num,
                .psn = 0,
                .port = 1,
                .lid = 0,
                .gid = "" // will set below
            }};
            
            snprintf(qps[qps_size-1].gid, sizeof(qps[qps_size-1].gid),
                        "%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x",
                        {self.context.gid_var}.raw[0], {self.context.gid_var}.raw[1], {self.context.gid_var}.raw[2], {self.context.gid_var}.raw[3], {self.context.gid_var}.raw[4], {self.context.gid_var}.raw[5], {self.context.gid_var}.raw[6], {self.context.gid_var}.raw[7], {self.context.gid_var}.raw[8], {self.context.gid_var}.raw[9], {self.context.gid_var}.raw[10], {self.context.gid_var}.raw[11], {self.context.gid_var}.raw[12], {self.context.gid_var}.raw[13], {self.context.gid_var}.raw[14], {self.context.gid_var}.raw[15]);
                        
            prs[prs_size++] = (PR_Pair){{
                .id = "pair-{qp_name}-{self.remote_qp}",
                .cli_id = "{qp_name}",
                .srv_id = "{self.remote_qp}"
            }};
            
            pr_write_client_update_claimed(CLIENT_UPDATE_PATH, qps, qps_size, mrs, mrs_size, prs, prs_size);
        }});
    }});
"""


# class CreateRWQIndTable(VerbCall):
#     def __init__(self, context: str, log_ind_tbl_size: int = 0, ind_tbls: list = []):
#         self.context = context
#         self.log_ind_tbl_size = log_ind_tbl_size
#         self.ind_tbls = ind_tbls or []

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         context = kv.get("context", "unknown")
#         ctx.use_context(context)
#         log_size = int(kv.get("log_ind_tbl_size", 0))
#         ind_tbls = kv.get("ind_tbl", "").split()
#         return cls(context=context, log_ind_tbl_size=log_size, ind_tbls=ind_tbls)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         context_name = ctx.get_context(self.context)
#         ind_tbl_name = f"ind_tbl[{len(self.ind_tbls)}]"
#         init_attr_name = f"init_attr_{self.context}"

#         ind_tbl_entries = ", ".join(f"wq[{i}]" for i in range(len(self.ind_tbls)))
#         init_attr_struct = f"""
#     struct ibv_rwq_ind_table_init_attr {init_attr_name};
#     {init_attr_name}.log_ind_tbl_size = {self.log_ind_tbl_size};
#     {init_attr_name}.ind_tbl = {ind_tbl_name};
#     {init_attr_name}.comp_mask = 0; // Comp mask can be modified based on requirements
# """

#         return f"""
#     /* ibv_create_rwq_ind_table */
#     struct ibv_rwq_ind_table *rwq_ind_table;
#     struct ibv_wq *{ind_tbl_name}[] = {{{ind_tbl_entries}}};
#     {init_attr_struct}
#     rwq_ind_table = ibv_create_rwq_ind_table({context_name}, &{init_attr_name});
#     if (!rwq_ind_table) {{
#         fprintf(stderr, "Failed to create RWQ indirection table\\n");
#         return -1;
#     }}
# """


class CreateSRQ(VerbCall):
    """Create a shared receive queue (SRQ)"""

    MUTABLE_FIELDS = ["pd", "srq", "srq_init_obj"]
    EXPORT_FIELDS = ["pd", "srq", "srq_init_obj"]
    CONTRACT = Contract(
        requires=[RequireSpec("pd", State.ALLOCATED, "pd")],
        produces=[ProduceSpec("srq", State.ALLOCATED, "srq")],
        transitions=[],
    )

    def __init__(self, pd: str = None, srq: str = None, srq_init_obj: IbvSrqInitAttr = None):
        self.pd = ResourceValue(resource_type="pd", value=pd) if pd else "NULL"
        if not srq:
            raise ValueError("srq must be provided for CreateSRQ")
        self.srq = ResourceValue(resource_type="srq", value=srq, mutable=False)
        self.srq_init_obj = srq_init_obj

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        if ctx:
            ctx.alloc_variable(name=self.srq.value, type="struct ibv_srq *", array_size=None)

        if self.tracker:
            # Register the PD and SRQ addresses in the tracker
            self.tracker.use("pd", self.pd.value)
            self.tracker.create("srq", self.srq.value, pd=self.pd.value)
            self.required_resources.append({"type": "pd", "name": self.pd.value, "position": "pd"})  # 记录需要的资源
            self.allocated_resources.append(("srq", self.srq.value))
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        srq = kv.get("srq", "unknown")
        srq_attr_keys = {"max_wr", "max_sge", "srq_limit"}
        srq_attr_params = {k: kv[k] for k in srq_attr_keys if k in kv}
        return cls(pd=pd, srq=srq, srq_attr_params=srq_attr_params, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = self.pd
        srq_name = str(self.srq)

        code = ""
        attr_name = f"srq_init_attr_{srq_name.replace('srq', '').replace('[', '').replace(']', '')}"
        if self.srq_init_obj is not None:
            code += self.srq_init_obj.to_cxx(attr_name, ctx)

        return f"""
    /* ibv_create_srq */
    IF_OK_PTR({pd_name}, {{
        {code}
        {srq_name} = ibv_create_srq({pd_name}, &{attr_name});
        if (!{srq_name}) {{
            fprintf(stderr, "Failed to create SRQ {srq_name}\\n");
        }}
    }});
"""


class CreateSRQEx(VerbCall):  # TODO: 暂时不用，没改return -1
    """
    表示 ibv_create_srq_ex() 调用，自动生成/重放 srq_init_attr_ex 的初始化与调用。
    参数：
        ctx_name      -- IBV context 变量名（如"ctx"）
        srq_var       -- 返回 SRQ 变量名（如"srq1"）
        srq_attr_var  -- srq_init_attr_ex 结构体变量名（如"srq_attr_ex1"）
        srq_attr_obj  -- IbvSrqInitAttrEx对象（可选，自动生成结构体内容）
    """

    MUTABLE_FIELDS = ["srq", "srq_attr_var", "srq_attr_obj"]
    EXPORT_FIELDS = ["srq", "srq_attr_obj"]
    CONTRACT = Contract(
        requires=[RequireSpec("pd", State.ALLOCATED, "srq_attr_obj.pd")],
        produces=[ProduceSpec("srq", State.ALLOCATED, "srq")],
        transitions=[],
    )

    def __init__(
        self,
        ctx_name: str = None,
        srq: str = None,
        srq_attr_var: str = None,
        srq_attr_obj: "IbvSrqInitAttrEx" = None,
    ):
        # IBV context variable name, default is "ctx"
        self.ctx_name = ConstantValue(ctx_name or "ctx")
        self.srq = (
            ResourceValue(resource_type="srq", value=srq) if srq else ResourceValue(resource_type="srq", value="srq")
        )  # SRQ variable name, default is "srq"
        # 默认生成 srq_attr_ex_<srq_var>
        self.srq_attr_var = ConstantValue(
            srq_attr_var or f"srq_attr_ex_{self.srq.value}"
        )  # SRQ attribute variable name
        self.srq_attr_obj = srq_attr_obj  # 若为None仅生成结构体声明

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            self.tracker.create("srq_ex", self.srq.value)
            self.allocated_resources.append(("srq_ex", self.srq.value))
            if self.srq_attr_obj is not None:
                self.srq_attr_obj.apply(ctx)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def get_required_resources_recursively(self) -> list[dict[str, str]]:
        """Get all required resources recursively."""
        resources = self.get_required_resources().copy()
        if self.srq_attr_obj is not None:
            resources.extend(self.srq_attr_obj.get_required_resources_recursively())
        return resources

    def set_resource_recursively(self, res_type: str, old_res_name: str, new_res_name: str):
        """Set the resource name recursively in the MW bind object."""
        self.set_resource(res_type, old_res_name, new_res_name)
        if self.srq_attr_obj is not None:
            self.srq_attr_obj.set_resource_recursively(res_type, old_res_name, new_res_name)

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ctx_name = kv.get("ctx", "ctx")
        srq_var = kv.get("srq_var", "srq")
        srq_attr_var = kv.get("srq_attr_var", "srq_attr_ex")
        srq_attr_obj = kv.get("srq_attr_obj")  # 若trace含结构体内容
        return cls(ctx_name, srq_var, srq_attr_var, srq_attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        if self.ctx_name is None:
            self.ctx_name = ctx.ib_ctx  # Default to ib_ctx if ctx_name is not provided
        self.srq_var = self.srq
        code = ""
        # 自动生成结构体内容
        if self.srq_attr_obj is not None:
            code += self.srq_attr_obj.to_cxx(self.srq_attr_var, ctx)
        code += f"""
    {self.srq_var} = ibv_create_srq_ex({self.ctx_name}, &{self.srq_attr_var});
    if (!{self.srq_var}) {{
        fprintf(stderr, "ibv_create_srq_ex failed {self.srq_var}\\n");
    }}
"""
        return code


class CreateWQ(VerbCall):  # TODO: 暂时不用，没改return -1
    """
    表示 ibv_create_wq() 调用，自动生成/重放 wq_init_attr 的初始化与调用。
    参数：
        ctx_name     -- IBV context 变量名（如"ctx"）
        wq_var       -- 返回 WQ 变量名（如"wq1"）
        wq_attr_var  -- wq_init_attr 结构体变量名（如"wq_attr1"）
        wq_attr_obj  -- IbvWQInitAttr对象（可选，自动生成结构体内容）
    """

    MUTABLE_FIELDS = ["wq", "wq_attr_var", "wq_attr_obj"]
    EXPORT_FIELDS = ["wq", "wq_attr_obj"]
    # CONTRACT = Contract(
    #     requires=[],
    #     produces=[ProduceSpec("wq", state=State.ALLOCATED, name_attr="wq")],
    #     transitions=[],
    # )

    def _contract(self):
        reqs = [
            RequireSpec("pd", State.ALLOCATED, "wq_attr_obj.pd"),
            RequireSpec("cq", State.ALLOCATED, "wq_attr_obj.cq"),
        ]
        return Contract(requires=reqs, produces=[ProduceSpec("wq", State.ALLOCATED, "wq")], transitions=[])

    def __init__(
        self,
        ctx_name: str = None,
        wq: str = None,
        wq_attr_var: str = None,
        wq_attr_obj: "IbvWQInitAttr" = None,
    ):
        # IBV context variable name, default is "ctx"
        self.ctx_name = ConstantValue(ctx_name or "ctx")
        self.wq = (
            ResourceValue(resource_type="wq", value=wq) if wq else ResourceValue(resource_type="wq", value="wq")
        )  # WQ variable name, default is "wq"
        # 默认生成 wq_attr_<wq_var>
        self.wq_attr_var = ConstantValue(wq_attr_var or f"wq_attr_{self.wq.value}")  # WQ attribute variable name
        self.wq_attr_obj = wq_attr_obj  # 若为None仅生成结构体声明

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            self.tracker.create("wq", self.wq.value)
            self.allocated_resources.append(("wq", self.wq.value))
            if self.wq_attr_obj is not None:
                self.wq_attr_obj.apply(ctx)

        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def get_required_resources_recursively(self) -> list[dict[str, str]]:
        """Get all required resources recursively."""
        resources = self.get_required_resources().copy()
        if self.wq_attr_obj is not None:
            resources.extend(self.wq_attr_obj.get_required_resources_recursively())
        return resources

    def set_resource_recursively(self, res_type: str, old_res_name: str, new_res_name: str):
        """Set the resource name recursively in the MW bind object."""
        self.set_resource(res_type, old_res_name, new_res_name)
        if self.wq_attr_obj is not None:
            self.wq_attr_obj.set_resource_recursively(res_type, old_res_name, new_res_name)

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ctx_name = kv.get("ctx", "ctx")
        wq_var = kv.get("wq_var", "wq")
        wq_attr_var = kv.get("wq_attr_var", "wq_attr")
        wq_attr_obj = kv.get("wq_attr_obj")  # 若trace含结构体内容
        return cls(ctx_name, wq_var, wq_attr_var, wq_attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        self.wq_var = self.wq
        if self.ctx_name is None:
            self.ctx_name = ctx.ib_ctx
        code = ""
        # 自动生成结构体内容
        if self.wq_attr_obj is not None:
            code += self.wq_attr_obj.to_cxx(self.wq_attr_var, ctx)
        code += f"""
    {self.wq_var} = ibv_create_wq({self.ctx_name}, &{self.wq_attr_var});
    if (!{self.wq_var}) {{
        fprintf(stderr, "ibv_create_wq failed {self.wq_var}\\n");
    }}
"""
        return code


class DeallocMW(VerbCall):
    """Deallocate a Memory Window (MW)."""

    MUTABLE_FIELDS = ["mw"]
    EXPORT_FIELDS = ["mw"]
    CONTRACT = Contract(
        requires=[RequireSpec("mw", State.ALLOCATED, "mw")],
        produces=[],
        transitions=[TransitionSpec("mw", State.ALLOCATED, State.DESTROYED, "mw")],
    )

    def __init__(self, mw: str = None):
        self.mw = ResourceValue(resource_type="mw", value=mw) if mw else ResourceValue(resource_type="mw", value="mw")
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            self.tracker.use("mw", self.mw.value)
            self.tracker.destroy("mw", self.mw.value)
            self.required_resources.append({"type": "mw", "name": self.mw.value, "position": "mw"})
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        mw = kv.get("mw", "unknown")
        return cls(mw=mw)

    def generate_c(self, ctx: CodeGenContext) -> str:
        mw_name = self.mw
        return f"""
    /* ibv_dealloc_mw */
    IF_OK_PTR({mw_name}, {{
        if (ibv_dealloc_mw({mw_name})) {{
            fprintf(stderr, "Failed to deallocate MW {mw_name}\\n");
        }}
    }});
"""


class DeallocPD(VerbCall):
    """Deallocate a protection domain (PD)."""

    MUTABLE_FIELDS = ["pd"]
    EXPORT_FIELDS = ["pd"]
    CONTRACT = Contract(
        requires=[RequireSpec("pd", state=State.ALLOCATED, name_attr="pd")],
        produces=[],
        transitions=[TransitionSpec("pd", from_state=State.ALLOCATED, to_state=State.DESTROYED, name_attr="pd")],
    )

    def __init__(self, pd: str = None):
        if not pd:
            raise ValueError("pd must be provided for DeallocPD")
        self.pd = ResourceValue(resource_type="pd", value=pd)
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the PD address in the tracker
            self.tracker.use("pd", self.pd.value)
            self.tracker.destroy("pd", self.pd.value)
            self.required_resources.append({"type": "pd", "name": self.pd.value, "position": "pd"})  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        return cls(pd=pd)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = self.pd
        return f"""
    /* ibv_dealloc_pd */
    IF_OK_PTR({pd_name}, {{
        if (ibv_dealloc_pd({pd_name})) {{
            fprintf(stderr, "Failed to deallocate PD {pd_name}\\n");
        }}
    }});
"""


class DeallocTD(VerbCall):
    """Deallocate an RDMA thread domain (TD) object."""

    MUTABLE_FIELDS = ["td"]
    EXPORT_FIELDS = ["td"]
    CONTRACT = Contract(
        requires=[RequireSpec("td", State.ALLOCATED, "td")],
        produces=[],
        transitions=[TransitionSpec("td", State.ALLOCATED, State.DESTROYED, "td")],
    )

    def __init__(self, td: str = None):
        self.td = (
            ResourceValue(resource_type="td", value=td) if td else ResourceValue(resource_type="td", value="td")
        )  # 默认生成 td
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the TD address in the tracker
            self.tracker.use("td", self.td.value)
            self.tracker.destroy("td", self.td.value)
            self.required_resources.append({"type": "td", "name": self.td.value, "position": "td"})
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        td = kv.get("td", "unknown")
        return cls(td=td)

    def generate_c(self, ctx: CodeGenContext) -> str:
        td_name = self.td
        return f"""
    /* ibv_dealloc_td */
    IF_OK_PTR({td_name}, {{
        if (ibv_dealloc_td({td_name})) {{
            fprintf(stderr, "Failed to deallocate TD {td_name}\\n");
        }}
    }});
"""


class DeregMR(VerbCall):
    """Deregister a Memory Region."""

    MUTABLE_FIELDS = ["mr"]
    EXPORT_FIELDS = ["mr"]
    CONTRACT = Contract(
        requires=[RequireSpec("mr", State.ALLOCATED, "mr")],
        produces=[],
        transitions=[TransitionSpec("mr", State.ALLOCATED, State.DESTROYED, "mr")],
    )

    def __init__(self, mr: str = None):
        if not mr:
            raise ValueError("mr must be provided for DeregMR")
        self.mr = ResourceValue(resource_type="mr", value=mr)
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the MR address in the tracker
            self.tracker.use("mr", self.mr.value)
            self.tracker.destroy("mr", self.mr.value)
            self.required_resources.append({"type": "mr", "name": self.mr.value, "position": "mr"})
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        mr = kv.get("mr", "unknown")
        return cls(mr=mr)

    def generate_c(self, ctx: CodeGenContext) -> str:
        mr_name = self.mr
        return f"""
    /* ibv_dereg_mr */
    IF_OK_PTR({mr_name}, {{
        if (ibv_dereg_mr({mr_name})) {{
            fprintf(stderr, "Failed to deregister MR {mr_name}\\n");
        }}
    }});
"""


class DestroyAH(VerbCall):
    """Destroy an Address Handle (AH)."""

    MUTABLE_FIELDS = ["ah"]
    EXPORT_FIELDS = ["ah"]
    CONTRACT = Contract(
        requires=[RequireSpec("pd", State.ALLOCATED, "pd")],
        produces=[],
        transitions=[TransitionSpec("ah", State.ALLOCATED, State.DESTROYED, "ah")],
    )

    def __init__(self, ah: str = None):
        self.ah = (
            ResourceValue(resource_type="ah", value=ah) if ah else ResourceValue(resource_type="ah", value="ah")
        )  # 默认生成 ah
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the AH address in the tracker
            self.tracker.use("ah", self.ah.value)
            self.tracker.destroy("ah", self.ah.value)
            self.required_resources.append({"type": "ah", "name": self.ah.value, "position": "ah"})  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ah = kv.get("ah", "unknown")
        return cls(ah=ah)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ah_name = self.ah
        return f"""
    /* ibv_destroy_ah */
    IF_OK_PTR({ah_name}, {{
        if (ibv_destroy_ah({ah_name})) {{
            fprintf(stderr, "Failed to destroy AH {ah_name}\\n");
        }}
    }})
"""


class DestroyCompChannel(VerbCall):
    """Destroy a completion event channel."""

    MUTABLE_FIELDS = ["channel"]
    EXPORT_FIELDS = ["channel"]
    CONTRACT = Contract(
        requires=[RequireSpec("channel", State.ALLOCATED, "channel")],
        produces=[],
        transitions=[TransitionSpec("channel", State.ALLOCATED, State.DESTROYED, "channel")],
    )

    def __init__(self, channel: str = None):
        self.channel = (
            ResourceValue(resource_type="channel", value=channel)
            if channel
            else ResourceValue(resource_type="channel", value="channel")
        )  # 默认生成 channel
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the completion channel address in the tracker
            self.tracker.use("channel", self.channel.value)
            self.tracker.destroy("channel", self.channel.value)
            self.required_resources.append(
                {
                    "type": "channel",
                    "name": self.channel.value,
                    "position": "channel",
                }
            )  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        channel = kv.get("channel", "unknown")
        return cls(channel=channel)

    def generate_c(self, ctx: CodeGenContext) -> str:
        channel_name = self.channel
        return f"""
    /* ibv_destroy_comp_channel */
    IF_OK_PTR({channel_name}, {{
        if (ibv_destroy_comp_channel({channel_name})) {{
            fprintf(stderr, "Failed to destroy completion channel {channel_name}\\n");
        }}
    }});
"""


class DestroyCQ(VerbCall):
    """Destroy a Completion Queue."""

    MUTABLE_FIELDS = ["cq"]
    EXPORT_FIELDS = ["cq"]
    CONTRACT = Contract(
        requires=[RequireSpec("cq", State.ALLOCATED, "cq")],
        produces=[],
        transitions=[TransitionSpec("cq", State.ALLOCATED, State.DESTROYED, "cq")],
    )

    def __init__(self, cq: str = None):
        if not cq:
            raise ValueError("cq must be provided for DestroyCQ")
        self.cq = ResourceValue(resource_type="cq", value=cq)
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the CQ address in the tracker
            self.tracker.use("cq", self.cq.value)
            self.tracker.destroy("cq", self.cq.value)
            self.required_resources.append({"type": "cq", "name": self.cq.value, "position": "cq"})  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq = kv.get("cq", "unknown")
        return cls(cq=cq)

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = self.cq
        return f"""
    /* ibv_destroy_cq */
    IF_OK_PTR({cq_name}, {{
        if (ibv_destroy_cq({cq_name})) {{
            fprintf(stderr, "Failed to destroy CQ {cq_name}\\n");
        }}
    }});
"""


class DestroyFlow(VerbCall):
    """Destroy a flow steering rule."""

    MUTABLE_FIELDS = ["flow"]
    EXPORT_FIELDS = ["flow"]
    CONTRACT = Contract(
        requires=[RequireSpec("flow", State.ALLOCATED, "flow")],
        produces=[],
        transitions=[TransitionSpec("flow", State.ALLOCATED, State.DESTROYED, "flow")],
    )

    def __init__(self, flow: str = None):
        self.flow = (
            ResourceValue(resource_type="flow", value=flow)
            if flow
            else ResourceValue(resource_type="flow", value="flow")
        )  # 默认生成 flow
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the flow address in the tracker
            self.tracker.use("flow", self.flow.value)
            self.tracker.destroy("flow", self.flow.value)
            self.required_resources.append(
                {"type": "flow", "name": self.flow.value, "position": "flow"}
            )  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        flow = kv.get("flow", "unknown")
        return cls(flow=flow)

    def generate_c(self, ctx: CodeGenContext) -> str:
        flow_name = self.flow
        return f"""
    /* ibv_destroy_flow */
    IF_OK_PTR({flow_name}, {{
        if (ibv_destroy_flow({flow_name})) {{
            fprintf(stderr, "Failed to destroy flow {flow_name}\\n");
        }}
    }});
"""


class DestroyQP(VerbCall):
    """Destroy a Queue Pair (QP)."""

    MUTABLE_FIELDS = ["qp"]
    EXPORT_FIELDS = ["qp"]
    CONTRACT = Contract(
        requires=[RequireSpec("qp", None, "qp", exclude_states=[State.DESTROYED])],
        produces=[],
        transitions=[TransitionSpec("qp", None, State.DESTROYED, "qp")],
    )

    def __init__(self, qp: str = None):
        if not qp:
            raise ValueError("qp must be provided for DestroyQP")
        self.qp = ResourceValue(resource_type="qp", value=qp)
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the QP address in the tracker
            self.tracker.use("qp", self.qp.value)
            self.tracker.destroy("qp", self.qp.value)
            self.required_resources.append({"type": "qp", "name": self.qp.value, "position": "qp"})  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        return cls(qp=qp)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = str(self.qp)
        return f"""
    /* ibv_destroy_qp */
    IF_OK_PTR({qp_name}, {{
        if (ibv_destroy_qp({qp_name})) {{
            fprintf(stderr, "Failed to destroy QP {qp_name}\\n");
        }}
    }});
"""


# class DestroyRWQIndTable(VerbCall):
#     """Destroy a Receive Work Queue Indirection Table (RWQ IND TBL)."""

#     def __init__(self, rwq_ind_table: str):
#         self.rwq_ind_table = rwq_ind_table

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         rwq_ind_table = kv.get("rwq_ind_table", "unknown")
#         # Ensure the RWQ IND TBL is used before generating code
#         ctx.use_rwq_ind_table(rwq_ind_table)
#         return cls(rwq_ind_table=rwq_ind_table)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         rwq_ind_table_name = ctx.get_rwq_ind_table(self.rwq_ind_table)
#         return f"""
#     /* ibv_destroy_rwq_ind_table */
#     if (ibv_destroy_rwq_ind_table({rwq_ind_table_name})) {{
#         fprintf(stderr, "Failed to destroy RWQ IND TBL\\n");
#         return -1;
#     }}
# """


class DestroySRQ(VerbCall):
    """Destroy a Shared Receive Queue (SRQ)."""

    MUTABLE_FIELDS = ["srq"]
    EXPORT_FIELDS = ["srq"]
    CONTRACT = Contract(
        requires=[RequireSpec("srq", State.ALLOCATED, "srq")],
        produces=[],
        transitions=[TransitionSpec("srq", State.ALLOCATED, State.DESTROYED, "srq")],
    )

    def __init__(self, srq: str = None):
        if not srq:
            raise ValueError("srq must be provided for DestroySRQ")
        self.srq = ResourceValue(resource_type="srq", value=srq)
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the SRQ address in the tracker
            self.tracker.use("srq", self.srq.value)
            self.tracker.destroy("srq", self.srq.value)
            self.required_resources.append({"type": "srq", "name": self.srq.value, "position": "srq"})  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        srq = kv.get("srq", "unknown")
        return cls(srq=srq)

    def generate_c(self, ctx: CodeGenContext) -> str:
        srq_name = self.srq
        return f"""
    /* ibv_destroy_srq */
    IF_OK_PTR({srq_name}, {{
        if (ibv_destroy_srq({srq_name}) != 0) {{
            fprintf(stderr, "Failed to destroy SRQ {srq_name}\\n");
        }}
    }});
"""


class DestroyWQ(VerbCall):
    """Destroy a Work Queue (WQ)."""

    MUTABLE_FIELDS = ["wq"]
    EXPORT_FIELDS = ["wq"]
    CONTRACT = Contract(
        requires=[RequireSpec("wq", State.ALLOCATED, "wq")],
        produces=[],
        transitions=[TransitionSpec("wq", from_state=State.ALLOCATED, to_state=State.DESTROYED, name_attr="wq")],
    )

    def __init__(self, wq: str = None):
        self.wq = (
            ResourceValue(resource_type="wq", value=wq) if wq else ResourceValue(resource_type="wq", value="wq")
        )  # 默认生成 wq
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the WQ address in the tracker
            self.tracker.use("wq", self.wq.value)
            self.tracker.destroy("wq", self.wq.value)
            self.required_resources.append({"type": "wq", "name": self.wq.value, "position": "wq"})  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        wq = kv.get("wq", "unknown")
        return cls(wq=wq)

    def generate_c(self, ctx: CodeGenContext) -> str:
        wq_name = self.wq
        return f"""
    /* ibv_destroy_wq */
    IF_OK_PTR({wq_name}, {{
        if (ibv_destroy_wq({wq_name})) {{
            fprintf(stderr, "Failed to destroy WQ {wq_name}\\n");
        }}
    }});
"""


class DetachMcast(VerbCall):  # TODO: gid 需要是变量名
    """Detach a QP from a multicast group."""

    MUTABLE_FIELDS = ["qp", "gid", "lid"]
    EXPORT_FIELDS = ["qp", "gid", "lid"]
    CONTRACT = Contract(
        requires=[RequireSpec("qp", None, "qp", exclude_states=[State.DESTROYED])], produces=[], transitions=[]
    )

    def __init__(self, qp: str = None, gid: str = None, lid: int = None):
        self.qp = (
            ResourceValue(resource_type="qp", value=qp) if qp else ResourceValue(resource_type="qp", value="qp")
        )  # 默认生成 qp
        # Multicast group address, default is "unknown"
        self.gid = ConstantValue(gid or "unknown")
        # LID of the multicast group, default is 0
        self.lid = IntValue(lid or 0)
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the QP address in the tracker
            self.tracker.use("qp", self.qp.value)
            self.required_resources.append({"type": "qp", "name": self.qp.value, "position": "qp"})  # 记录需要的资源
            # Register the multicast group address
            # self.tracker.use('gid', gid)
            # self.tracker.use('lid', str(lid))
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        gid = kv.get("gid", "unknown")
        lid = int(kv.get("lid", "0"))
        return cls(qp=qp, gid=gid, lid=lid)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = str(self.qp)
        return f"""
    /* ibv_detach_mcast */
    IF_OK_PTR({qp_name}, {{
        if (ibv_detach_mcast({qp_name}, &{self.gid}, {self.lid})) {{
            fprintf(stderr, "Failed to detach multicast group {qp_name}\\n");
        }}
    }});
"""


# class EventTypeStr(VerbCall): # 这个感觉没什么用
#     """Generate code for ibv_event_type_str.

#     Returns a string describing the enum value for the given event type."""

#     def __init__(self, event: str):
#         self.event = event

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         event = kv.get("event", "IBV_EVENT_COMM_EST")
#         return cls(event=event)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         return f"""
#     /* ibv_event_type_str */
#     const char *event_desc = ibv_event_type_str({self.event});
#     fprintf(stdout, "Event description: %s\\n", event_desc);
# """

# class FlowActionESP(VerbCall): # 意义不明
#     def __init__(self, ctx: str = "ctx", esp_params: dict[str, any] = {}):
#         self.ctx = ctx
#         self.esp_params = esp_params

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext = None):
#         kv = _parse_kv(info)
#         esp_params = {
#             "esp_attr": kv.get("esp_attr"),
#             "keymat_proto": kv.get("keymat_proto"),
#             "keymat_len": kv.get("keymat_len"),
#             "keymat_ptr": kv.get("keymat_ptr"),
#             "replay_proto": kv.get("replay_proto"),
#             "replay_len": kv.get("replay_len"),
#             "replay_ptr": kv.get("replay_ptr"),
#             "esp_encap": kv.get("esp_encap"),
#             "comp_mask": kv.get("comp_mask"),
#             "esn": kv.get("esn")
#         }
#         return cls(ctx=ctx.ib_ctx, esp_params=esp_params)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         esp_var = "esp_params"
#         esp_lines = "\n    ".join(
#             f"{esp_var}.{key} = {value};" for key, value in self.esp_params.items()
#         )

#         return f"""
#     struct ibv_flow_action_esp {esp_var};
#     memset(&{esp_var}, 0, sizeof({esp_var}));
#     {esp_lines}
#     struct ibv_flow_action *esp_action = `ibv_create_flow_action_esp({self.ctx}, &{esp_var})`;
#     if (!esp_action) {{
#         fprintf(stderr, "Failed to create ESP flow action\\n");
#         return -1;
#     }}
# """


class ForkInit(VerbCall):
    MUTABLE_FIELDS = []
    EXPORT_FIELDS = []

    def __init__(self):
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        return cls()

    def generate_c(self, ctx: CodeGenContext) -> str:
        return """
    /* ibv_fork_init */
    if (ibv_fork_init()) {
        fprintf(stderr, "Failed to initialize fork support\\n");
        return -1;
    }
"""


class FreeDeviceList(VerbCall):
    """Release the array of RDMA devices obtained from ibv_get_device_list."""

    MUTABLE_FIELDS = []
    EXPORT_FIELDS = []

    def __init__(self, dev_list: str = None):
        self.dev_list = ConstantValue(dev_list or "dev_list")
        pass

    @classmethod  # dummy function
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        return cls()

    def apply(self, ctx: CodeGenContext):
        self.context = ctx
        # self.context.dev_list = None

    def generate_c(self, ctx: CodeGenContext) -> str:
        dev_list = self.dev_list
        return f"""
    /* ibv_free_device_list */
    ibv_free_device_list({dev_list});
"""


class FreeDM(VerbCall):
    """Release a device memory buffer (DM)."""

    MUTABLE_FIELDS = ["dm"]
    EXPORT_FIELDS = ["dm"]
    CONTRACT = Contract(
        requires=[RequireSpec("dm", State.ALLOCATED, "dm")],
        produces=[],
        transitions=[TransitionSpec("dm", State.ALLOCATED, State.DESTROYED, "dm")],
    )

    def __init__(self, dm: str = None):
        self.dm = (
            ResourceValue(resource_type="dm", value=dm) if dm else ResourceValue(resource_type="dm", value="dm")
        )  # 默认生成 dm
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the DM address in the tracker
            self.tracker.use("dm", self.dm.value)
            self.tracker.destroy("dm", self.dm.value)
            self.required_resources.append({"type": "dm", "name": self.dm.value, "position": "dm"})  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        dm = kv.get("dm", "unknown")
        return cls(dm=dm)

    def generate_c(self, ctx: CodeGenContext) -> str:
        dm_name = self.dm
        return f"""
    /* ibv_free_dm */
    IF_OK_PTR({dm_name}, {{
        if (ibv_free_dm({dm_name})) {{
            fprintf(stderr, "Failed to free device memory (DM) {dm_name}\\n");
        }}
    }});
"""


# class GetAsyncEvent(VerbCall):  # 意义不明
#     MUTABLE_FIELDS = []

#     def __init__(self):
#         pass

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext = None):
#         kv = _parse_kv(info)
#         return cls()

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         return f"""
#     /* ibv_get_async_event */
#     struct ibv_async_event async_event;
#     if (ibv_get_async_event({ctx.ib_ctx}, &async_event)) {{
#         fprintf(stderr, "Failed to get async_event\\n");
#         return -1;
#     }}

#     /* Process the async event */
#     switch (async_event.event_type) {{
#         case IBV_EVENT_CQ_ERR:
#             fprintf(stderr, "CQ error\\n");
#             break;
#         case IBV_EVENT_QP_FATAL:
#             fprintf(stderr, "QP fatal error\\n");
#             break;
#         case IBV_EVENT_QP_REQ_ERR:
#             fprintf(stderr, "QP request error\\n");
#             break;
#         case IBV_EVENT_QP_ACCESS_ERR:
#             fprintf(stderr, "QP access error\\n");
#             break;
#         case IBV_EVENT_COMM_EST:
#             fprintf(stderr, "Communication established\\n");
#             break;
#         case IBV_EVENT_SQ_DRAINED:
#             fprintf(stderr, "Send Queue drained\\n");
#             break;
#         case IBV_EVENT_PATH_MIG:
#             fprintf(stderr, "Path migrated\\n");
#             break;
#         case IBV_EVENT_PATH_MIG_ERR:
#             fprintf(stderr, "Path migration error\\n");
#             break;
#         case IBV_EVENT_DEVICE_FATAL:
#             fprintf(stderr, "Device fatal error\\n");
#             break;
#         case IBV_EVENT_PORT_ACTIVE:
#             fprintf(stderr, "Port active\\n");
#             break;
#         case IBV_EVENT_PORT_ERR:
#             fprintf(stderr, "Port error\\n");
#             break;
#         case IBV_EVENT_LID_CHANGE:
#             fprintf(stderr, "LID changed\\n");
#             break;
#         case IBV_EVENT_PKEY_CHANGE:
#             fprintf(stderr, "P_Key table changed\\n");
#             break;
#         case IBV_EVENT_SM_CHANGE:
#             fprintf(stderr, "SM changed\\n");
#             break;
#         case IBV_EVENT_SRQ_ERR:
#             fprintf(stderr, "SRQ error\\n");
#             break;
#         case IBV_EVENT_SRQ_LIMIT_REACHED:
#             fprintf(stderr, "SRQ limit reached\\n");
#             break;
#         case IBV_EVENT_QP_LAST_WQE_REACHED:
#             fprintf(stderr, "Last WQE reached\\n");
#             break;
#         case IBV_EVENT_CLIENT_REREGISTER:
#             fprintf(stderr, "Client re-register request\\n");
#             break;
#         case IBV_EVENT_GID_CHANGE:
#             fprintf(stderr, "GID table changed\\n");
#             break;
#         case IBV_EVENT_WQ_FATAL:
#             fprintf(stderr, "WQ fatal error\\n");
#             break;
#         default:
#             fprintf(stderr, "Unknown event type\\n");
#             break;
#     }}

#     /* Acknowledge the async event */
#     ibv_ack_async_event(&async_event);
# """


# class GetCQEvent(VerbCall):  # 意义不明，暂时不用
#     MUTABLE_FIELDS = ["channel", "cq", "cq_context"]

#     def __init__(self, channel: str, cq: str, cq_context: str):
#         self.channel = channel
#         self.cq = cq
#         self.cq_context = cq_context

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         channel = kv.get("channel", "unknown")
#         cq = kv.get("cq", "unknown")
#         cq_context = kv.get("cq_context", "unknown")
#         return cls(channel=channel, cq=cq, cq_context=cq_context)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         # Assume context resolves object names
#         channel_name = self.chanel
#         cq_name = self.cq
#         return f"""
#     /* ibv_get_cq_event */
#     if (ibv_get_cq_event({channel_name}, &{cq_name}, &{self.cq_context})) {{
#         fprintf(stderr, "Failed to get CQ event\\n");
#         return -1;
#     }}
#     /* Acknowledge the event */
#     ibv_ack_cq_events({cq_name}, 1);
# """


class GetDeviceGUID(VerbCall):
    """Get the Global Unique Identifier (GUID) of the RDMA device."""

    MUTABLE_FIELDS = ["device", "output"]
    EXPORT_FIELDS = ["device", "output"]

    def __init__(self, device: str = None, output: str = None):
        # Default device is the first in the list
        self.device = ConstantValue(device or "dev_list[0]")
        # Default output variable name
        if output:
            self.output = ConstantValue(output)
        else:
            # random name
            import uuid

            self.output = ConstantValue("device_guid_" + str(uuid.uuid4()).replace("-", "_")[:10])

    def apply(self, ctx: CodeGenContext):
        if ctx:
            # Register the output variable in context
            ctx.alloc_variable(self.output, "uint64_t")

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        device = kv.get("device", "dev_list[0]")
        return cls(device=device)

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_get_device_guid */
    {self.output} = ibv_get_device_guid({self.device});
    printf("Device GUID: %llx\\n", (unsigned long long)be64toh({self.output}));
"""


class GetDeviceIndex(VerbCall):
    """Retrieve the device index for the specified IB device."""

    MUTABLE_FIELDS = ["device_name", "output"]
    EXPORT_FIELDS = ["device_name", "output"]

    def __init__(self, device_name: str = None, output: str = None):
        # Default device is the first in the list
        self.device_name = ConstantValue(device_name or "dev_list[0]")
        # Default output variable name
        if output:
            self.output = ConstantValue(output)
        else:
            # random name
            import uuid

            self.output = ConstantValue("device_index_" + str(uuid.uuid4()).replace("-", "_")[:10])

    def apply(self, ctx: CodeGenContext):
        if ctx:
            # Register the output variable in context
            ctx.alloc_variable(self.output, "int")
            # Register the device name in context
            # ctx.use_device(self.device_name)

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        device_name = kv.get("device", "unknown")
        return cls(device_name=device_name)

    def generate_c(self, ctx: CodeGenContext) -> str:
        # device = ctx.get_device(self.device_name)
        # index_var = f"device_index_{self.device_name}"
        device = self.device_name
        index_var = self.output
        return f"""
    /* Retrieve IB device index */
    {index_var} = ibv_get_device_index({device});
    if ({index_var} < 0) {{
        fprintf(stderr, "Failed to get device index for {device}\\n");
    }}
"""


class GetDeviceList(VerbCall):
    """Fetch the list of available RDMA devices.

    This verb generates the C code to retrieve a list of RDMA devices currently
    available on the system using ibv_get_device_list(). If successful, a
    NULL-terminated array of available devices is returned. This is typically
    the first step in setting up RDMA resources.

    Errors:
    - EPERM: Permission denied.
    - ENOSYS: Function not implemented.
    """

    MUTABLE_FIELDS = []
    EXPORT_FIELDS = []

    def __init__(self, dev_list: str = "dev_list"):
        self.dev_list = ConstantValue(dev_list or "dev_list")
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        """Create an instance based on a parsed JSON trace line."""
        kv = _parse_kv(info)
        return cls()

    def apply(self, ctx: CodeGenContext):
        if ctx:
            # Register the device list variable in context
            ctx.alloc_variable(self.dev_list, "struct ibv_device **")
            ctx.dev_list = self.dev_list

    def generate_c(self, ctx: CodeGenContext) -> str:
        # num_devices = "num_devices"
        return f"""
    /* ibv_get_device_list */
    {self.dev_list} = ibv_get_device_list(NULL);
    if (!{self.dev_list}) {{
        fprintf(stderr, "Failed to get device list: %s\\n", strerror(errno));
        return -1;
    }}
"""


class GetDeviceName(VerbCall):
    EXPORT_FIELDS = ["device", "output"]

    def __init__(self, device: str = "dev_list[0]", output: str = None):
        self.device = ConstantValue(device or "dev_list[0]")
        if output:
            self.output = ConstantValue(output)
        else:
            import uuid

            self.output = ConstantValue("device_name_" + str(uuid.uuid4()).replace("-", "_")[:10])

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        device = kv.get("device", "dev_list[0]")
        return cls(device=device)

    def apply(self, ctx: CodeGenContext):
        if ctx:
            ctx.alloc_variable(self.output, "const char *")

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_get_device_name */
    {self.output} = ibv_get_device_name({self.device});
    if (!{self.output}) {{
        fprintf(stderr, "Failed to get device name\\n");
    }} else {{
        printf("Device name: %s\\n", {self.output});
    }}
"""


class GetPKeyIndex(VerbCall):
    MUTABLE_FIELDS = ["port_num", "pkey", "output"]
    EXPORT_FIELDS = ["port_num", "pkey", "output"]

    def __init__(self, port_num: int = None, pkey: int = None, output: str = None):
        self.port_num = IntValue(port_num or 1)  # Default port number is 1
        self.pkey = IntValue(pkey or 0)  # Default P_Key is 0
        # Variable name to store the P_Key index
        if output:
            self.output = ConstantValue(output)
        else:
            import uuid

            self.output = ConstantValue("pkey_index_" + str(uuid.uuid4()).replace("-", "_")[:10])

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        port_num = int(kv.get("port_num", 1))
        pkey = int(kv.get("pkey", 0))
        return cls(port_num=port_num, pkey=pkey)

    def apply(self, ctx: CodeGenContext):
        if ctx:
            # Register the P_Key index variable in context
            ctx.alloc_variable(self.output, "int")
            # # Register the port number and P_Key in context
            # ctx.use_port(self.port_num)
            # ctx.use_pkey(self.pkey)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = ctx.ib_ctx
        pkey_index = self.output  # Use the output variable name for the P_Key index
        return f"""
    /* ibv_get_pkey_index */
    if (({pkey_index} = ibv_get_pkey_index({ib_ctx}, {self.port_num}, {self.pkey})) < 0) {{
        fprintf(stderr, "Failed to get P_Key index\\n");
        return -1;
    }}
"""


class GetSRQNum(VerbCall):
    MUTABLE_FIELDS = ["srq", "srq_num_var"]
    EXPORT_FIELDS = ["srq"]
    CONTRACT = Contract(
        requires=[RequireSpec("srq", State.ALLOCATED, "srq")],
        produces=[],
        transitions=[],
    )

    def __init__(self, srq: str = None, srq_num_var: str = None):
        # self.srq = srq  # Shared Receive Queue address
        self.srq = (
            ResourceValue(resource_type="srq", value=srq) if srq else ResourceValue(resource_type="srq", value="srq")
        )  # 默认生成 srq
        if srq_num_var:
            self.srq_num_var = ConstantValue(srq_num_var)
        else:
            import uuid

            self.srq_num_var = ConstantValue("srq_num_" + str(uuid.uuid4()).replace("-", "_")[:10])

        self.tracker = None
        # self.srq_num_var = srq_num_var  # Variable name to store the SRQ number
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the SRQ address in the tracker
            self.tracker.use("srq", self.srq.value)
            # Register the SRQ number variable in the tracker
            # self.tracker.create('srq_num', self.srq_num_var.value)
            self.required_resources.append({"type": "srq", "name": self.srq.value, "position": "srq"})
        if ctx:
            ctx.alloc_variable(self.srq_num_var, "uint32_t")
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        srq = kv.get("srq", "unknown")
        srq_num_var = kv.get("srq_num", "srq_num")
        return cls(srq=srq, srq_num_var=srq_num_var)

    def generate_c(self, ctx: CodeGenContext) -> str:
        srq_name = self.srq
        # Register the SRQ number variable in context
        # ctx.alloc_variable(self.srq_num_var, "uint32_t")
        return f"""
    /* ibv_get_srq_num */
    IF_OK_PTR({srq_name}, {{
        if (ibv_get_srq_num({srq_name}, &{self.srq_num_var})) {{
            fprintf(stderr, "Failed to get SRQ number {srq_name}\\n");
        }}
    }});
"""


# class ImportDevice(VerbCall):  # 意义不明
#     MUTABLE_FIELDS = ["cmd_fd", "ctx_var"]

#     def __init__(self, cmd_fd: int = None, ctx_var: str = None):
#         self.ctx_var = ctx_var  # Variable name for the context
#         self.cmd_fd = cmd_fd

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         cmd_fd = int(kv.get("cmd_fd", "-1"))  # Default to -1 if not found
#         return cls(cmd_fd=cmd_fd)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         return f"""
#     /* ibv_import_device */
#     {self.ctx_var} = ibv_import_device({self.cmd_fd});
#     if (!{self.ctx_var}) {{
#         fprintf(stderr, "Failed to import device\\n");
#         return -1;
#     }}
# """


class ImportDM(VerbCall):
    MUTABLE_FIELDS = ["dm_handle", "dm"]
    EXPORT_FIELDS = ["dm_handle", "dm"]
    CONTRACT = Contract(
        requires=[RequireSpec("dm", State.ALLOCATED, "dm")],
        produces=[],
        transitions=[],
    )

    def __init__(self, dm_handle: int = None, dm: str = None):
        # Default to 0 if not provided
        # TODO: 似乎应该是变量名
        self.dm_handle = IntValue(dm_handle or 0)
        self.dm = (
            ResourceValue(resource_type="dm", value=dm) if dm else ResourceValue(resource_type="dm", value="dm")
        )  # Variable name for the imported device memory
        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []  # Track allocated resources

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []  # Track allocated resources
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the DM address in the tracker
            self.tracker.create("dm", self.dm.value)
            self.allocated_resources.append(("dm", self.dm.value))  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        dm_handle = int(kv.get("dm_handle", "0"))
        return cls(dm_handle=dm_handle)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = ctx.ib_ctx
        # Get the DM variable name from context
        self.dm_var = self.dm
        # ctx.alloc_variable(self.dm_var, "struct ibv_dm *")  # Register the DM variable in context
        return f"""
    /* ibv_import_dm */
    {self.dm_var} = ibv_import_dm({ib_ctx}, {self.dm_handle});
    if (!{self.dm_var}) {{
        fprintf(stderr, "Failed to import device memory {self.dm_var}\\n");
    }}
"""


class ImportMR(VerbCall):
    MUTABLE_FIELDS = ["pd", "mr_handle", "mr"]
    EXPORT_FIELDS = ["pd", "mr_handle", "mr"]
    CONTRACT = Contract(
        requires=[RequireSpec("pd", State.ALLOCATED, "pd")],
        produces=[ProduceSpec("mr", State.ALLOCATED, "mr")],
        transitions=[],
    )

    def __init__(self, pd: str = None, mr_handle: int = None, mr: str = None):
        self.pd = ResourceValue(resource_type="pd", value=pd) if pd else ResourceValue(resource_type="pd", value="pd")
        # Default to 0 if not provided
        self.mr_handle = IntValue(mr_handle or 0)
        # TODO: 似乎应该是变量名
        self.mr = (
            ResourceValue(resource_type="mr", value=mr) if mr else ResourceValue(resource_type="mr", value="mr")
        )  # Variable name for the imported memory region

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []  # Track allocated resources

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []  # Track allocated resources
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the PD address in the tracker
            self.tracker.use("pd", self.pd.value)
            # Register the MR address in the tracker
            self.tracker.create("mr", self.mr.value)
            self.allocated_resources.append(("mr", self.mr.value))  # 记录需要的资源
            self.required_resources.append({"type": "pd", "name": self.pd.value, "position": "pd"})  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        mr_handle = int(kv.get("mr_handle", 0))
        mr = kv.get("mr", "unknown")
        return cls(pd=pd, mr_handle=mr_handle, mr=mr, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = self.pd
        mr_name = self.mr
        return f"""
    /* ibv_import_mr */
    {mr_name} = ibv_import_mr({pd_name}, {self.mr_handle});
    if (!{mr_name}) {{
        fprintf(stderr, "Failed to import MR {mr_name}\\n");
    }}
"""


class ImportPD(VerbCall):
    MUTABLE_FIELDS = ["pd", "pd_handle"]
    EXPORT_FIELDS = ["pd", "pd_handle"]
    CONTRACT = Contract(
        requires=[],
        produces=[ProduceSpec("pd", State.ALLOCATED, "pd")],
        transitions=[TransitionSpec("pd", from_state=None, to_state=State.IMPORTED, name_attr="pd")],
    )

    def __init__(self, pd: str = None, pd_handle: int = None):
        self.pd = (
            ResourceValue(resource_type="pd", value=pd) if pd else ResourceValue(resource_type="pd", value="pd")
        )  # Variable name for the imported protection domain
        # Default to 0 if not provided
        self.pd_handle = IntValue(pd_handle or 0)  # TODO: 似乎应该是变量名

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []  # Track allocated resources

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []  # Track allocated resources
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the PD address in the tracker
            self.tracker.create("pd", self.pd.value)
            self.allocated_resources.append(("pd", self.pd.value))  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        pd_handle = int(kv.get("pd_handle", 0))
        return cls(pd=pd, pd_handle=pd_handle, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = self.pd
        return f"""
    /* ibv_import_pd */
    {pd_name} = ibv_import_pd({ctx.ib_ctx}, {self.pd_handle});
    if (!{pd_name}) {{
        fprintf(stderr, "Failed to import PD {pd_name}\\n");
    }}
"""


# class IncRKey(VerbCall):  # 意义不明
#     """Verb to increment the rkey value."""

#     def __init__(self, rkey: str = None, new_rkey: str = None):
#         self.rkey = rkey
#         self.new_rkey = new_rkey  # Variable name for the new rkey

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         rkey = kv.get("rkey", "unknown")
#         return cls(rkey=rkey)

#     def apply(self, ctx: CodeGenContext):
#         if ctx:
#             # # Register the rkey variable in context
#             # ctx.alloc_variable(self.rkey, "uint32_t")
#             # Register the new_rkey variable in context
#             ctx.alloc_variable(self.new_rkey, "uint32_t")

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         return f"""
#     /* ibv_inc_rkey */
#     {self.new_rkey} = ibv_inc_rkey({self.rkey});
#     fprintf(stdout, "Old RKey: %u, New RKey: %u\\n", {self.rkey}, {self.new_rkey});
# """


# class InitAHFromWC(VerbCall):  # 意义不明
#     def __init__(self, context: str, port_num: int, wc: str, grh: str, ah_attr: str):
#         self.context = context
#         self.port_num = port_num
#         self.wc = wc
#         self.grh = grh
#         self.ah_attr = ah_attr

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         context = kv.get("context", "ctx")
#         port_num = int(kv.get("port_num", 1))
#         wc = kv.get("wc", "wc")
#         grh = kv.get("grh", "grh")
#         ah_attr = kv.get("ah_attr", "ah_attr")
#         return cls(context=context, port_num=port_num, wc=wc, grh=grh, ah_attr=ah_attr)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         return f"""
#     /* ibv_init_ah_from_wc */
#     if (ibv_init_ah_from_wc({self.context}, {self.port_num}, &{self.wc}, &{self.grh}, &{self.ah_attr})) {{
#         fprintf(stderr, "Failed to initialize AH from WC\\n");
#         return -1;
#     }}
# """


# class IsForkInitialized(VerbCall):  # 意义不明
#     """Check if fork support is enabled using ibv_is_fork_initialized."""

#     def __init__(self, output: str = None):
#         self.output = output or 'fork_status'
#         pass

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext = None):
#         return cls()

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         # Register the fork status variable in context
#         ctx.alloc_variable(self.output, "enum ibv_fork_status")
#         return f"""
#     /* Check if fork support is initialized */
#     {self.output} = ibv_is_fork_initialized();
#     switch ({self.output}) {{
#         case IBV_FORK_DISABLED:
#             fprintf(stdout, "Fork support is disabled\\n");
#             break;
#         case IBV_FORK_ENABLED:
#             fprintf(stdout, "Fork support is enabled\\n");
#             break;
#         case IBV_FORK_UNNEEDED:
#             fprintf(stdout, "Fork support is unneeded\\n");
#             break;
#         default:
#             fprintf(stdout, "Unknown fork status\\n");
#             break;
#     }}
# """


class MemcpyFromDM(VerbCall):
    MUTABLE_FIELDS = ["host", "dm", "dm_offset", "length"]
    EXPORT_FIELDS = ["host", "dm", "dm_offset", "length"]
    CONTRACT = Contract(
        requires=[RequireSpec("dm", State.ALLOCATED, "dm")],
        produces=[],
        transitions=[],
    )

    def __init__(
        self,
        host: str = None,
        dm: str = None,
        dm_offset: int = None,
        length: int = None,
    ):
        self.host = ConstantValue(host or "host_buf")  # Host memory address
        self.dm = (
            ResourceValue(resource_type="dm", value=dm) if dm else ResourceValue(resource_type="dm", value="dm")
        )  # Device memory address
        # Offset in the device memory
        self.dm_offset = IntValue(dm_offset or 0)
        self.length = IntValue(length or 0)  # Length of data to copy
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the device memory and host addresses in the tracker
            self.tracker.use("dm", self.dm.value)
            # self.tracker.use('host', host)
            self.required_resources.append({"type": "dm", "name": self.dm.value, "position": "dm"})  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        host = kv.get("host", "unknown")
        dm = kv.get("dm", "unknown")
        dm_offset = int(kv.get("dm_offset", 0))
        length = int(kv.get("length", 0))
        return cls(host=host, dm=dm, dm_offset=dm_offset, length=length)

    def generate_c(self, ctx: CodeGenContext) -> str:
        dm_name = self.dm
        return f"""
    /* ibv_memcpy_from_dm */
    IF_OK_PTR({dm_name}, {{
        if (ibv_memcpy_from_dm({self.host}, {dm_name}, {self.dm_offset}, {self.length}) != 0) {{
            fprintf(stderr, "Failed to copy from device memory {dm_name}\\n");
        }}
    }});
"""


class MemcpyToDM(VerbCall):
    MUTABLE_FIELDS = ["dm", "dm_offset", "host", "length"]
    EXPORT_FIELDS = ["dm", "dm_offset", "host", "length"]
    CONTRACT = Contract(
        requires=[RequireSpec("dm", State.ALLOCATED, "dm")],
        produces=[],
        transitions=[],
    )

    def __init__(
        self,
        dm: str = None,
        dm_offset: int = None,
        host: str = None,
        length: int = None,
    ):
        self.dm = (
            ResourceValue(resource_type="dm", value=dm) if dm else ResourceValue(resource_type="dm", value="dm")
        )  # Device memory address
        # Offset in the device memory
        self.dm_offset = IntValue(dm_offset or 0)
        self.host = ConstantValue(host or "host_buf")  # Host memory address
        self.length = IntValue(length or 0)  # Length of data to copy
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the device memory and host addresses in the tracker
            self.tracker.use("dm", self.dm.value)
            self.required_resources.append({"type": "dm", "name": self.dm.value, "position": "dm"})  # 记录需要的资源
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())
            # self.tracker.use('host', host)

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        dm = kv.get("dm", "unknown")
        return cls(
            dm=dm,
            dm_offset=int(kv.get("dm_offset", 0)),
            host=kv.get("host", "host_buf"),
            length=int(kv.get("length", 0)),
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        dm_name = self.dm
        return f"""
    /* ibv_memcpy_to_dm */
    IF_OK_PTR({dm_name}, {{
        if (ibv_memcpy_to_dm({dm_name}, {self.dm_offset}, {self.host}, {self.length}) != 0) {{
            fprintf(stderr, "Failed to copy to device memory {dm_name}\\n");
        }}
    }});
"""


class ModifyCQ(VerbCall):
    """Modify a Completion Queue (CQ) attributes.

    This verb modifies a CQ with new moderation attributes
    like number of completions per event and period in microseconds.
    The `attr_mask` field in `ibv_modify_cq_attr` specifies which
    attributes to modify.
    """

    MUTABLE_FIELDS = ["cq", "attr_obj", "attr_var"]
    EXPORT_FIELDS = ["cq", "attr_obj"]
    CONTRACT = Contract(requires=[RequireSpec("cq", State.ALLOCATED, "cq")], produces=[], transitions=[])

    def __init__(self, cq: str = None, attr_obj: IbvModifyCQAttr = None, attr_var: str = None):
        if not cq:
            raise ValueError("CQ name must be provided")
        self.cq = ResourceValue(resource_type="cq", value=cq)
        self.attr_obj = attr_obj  # This can be a dict or an object with attributes
        # Default variable name for the CQ attributes
        # Variable name for the CQ attributes
        self.attr_var = ConstantValue(attr_var or "modify_cq_attr")

        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the CQ address in the tracker
            self.tracker.use("cq", self.cq.value)
            self.required_resources.append({"type": "cq", "name": self.cq.value, "position": "cq"})  # 记录需要的资源
            # # Register the CQ attributes variable in the tracker
            # self.tracker.create('attr_var', self.attr_var)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq_var = kv.get("cq", "cq")
        attr_var = kv.get("attr_var", "modify_cq_attr")
        attr_obj = kv.get("attr_obj")  # trace中如含结构体内容
        return cls(cq_var, attr_var, attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        # Get the CQ variable name from context
        cq_name = self.cq
        code = ""
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            code += f"\n    struct ibv_modify_cq_attr {self.attr_var} = {{0}};\n"
        code += f"""
    IF_OK_PTR({cq_name}, {{
        if (ibv_modify_cq({cq_name}, &{self.attr_var}) != 0) {{
            fprintf(stderr, "ibv_modify_cq failed {cq_name}\\n");
        }}
    }});
"""
        return code


_QP_ENUM_TO_STATE = {
    "IBV_QPS_RESET": State.RESET,
    "IBV_QPS_INIT": State.INIT,
    "IBV_QPS_RTR": State.RTR,
    "IBV_QPS_RTS": State.RTS,
}

_PREV_STATE = {
    State.RESET: None,
    State.INIT: State.RESET,
    State.RTR: State.INIT,
    State.RTS: State.RTR,
}


class ModifyQP(VerbCall):
    MUTABLE_FIELDS = ["qp", "attr_obj", "attr_mask"]
    EXPORT_FIELDS = ["qp", "attr_obj", "attr_mask"]
    # CONTRACT = Contract(
    #     requires=[RequireSpec("qp", None, "qp")],
    #     produces=[],  # 不新建资源
    #     transitions=[TransitionSpec("qp", from_state=State.RESET, to_state=State.INIT, name_attr="qp")],
    # )

    def __init__(self, qp: str = None, attr_obj: IbvQPAttr = None, attr_mask: str = None):  # TODO: attr 需要检查
        if not qp:
            raise ValueError("QP name must be provided")
        self.qp = ResourceValue(resource_type="qp", value=qp, mutable=False)  # 以免破坏FSM链
        self.attr_obj = attr_obj
        # e.g., "IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS"
        self.attr_mask = FlagValue(
            attr_mask or "IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS",
            flag_type="IBV_QP_ATTR_MASK_ENUM",
        )  # Variable name for the attribute mask
        self.tracker = None
        self.required_resources = []

    def _contract(self) -> Contract:
        """Generate the contract for this verb call."""
        return self._contract_for_this_call()

    def _contract_for_this_call(self) -> Contract:
        # 读取本次期望目标状态
        target = None
        ao = getattr(self, "attr_obj", None) or getattr(self, "attr", None)
        if ao is not None and hasattr(ao, "qp_state"):
            qs = getattr(ao, "qp_state")
            qs = getattr(qs, "value", qs)
            target = _QP_ENUM_TO_STATE.get(str(qs))

        # 只要求 qp 存在；迁移到“本次 attr 指定的状态”
        if target is None:
            return Contract(
                requires=[RequireSpec("qp", None, "qp")],
                produces=[],
                transitions=[],
            )
        return Contract(
            # requires=[RequireSpec("qp", _PREV_STATE[target], "qp")],
            requires=[RequireSpec("qp", _PREV_STATE[target], "qp")],
            produces=[],
            # from_state=None = 放宽来源，避免你这种二次调用还要求 RESET 的情况
            transitions=[TransitionSpec("qp", from_state=_PREV_STATE[target], to_state=target, name_attr="qp")],
        )

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the QP address in the tracker
            self.tracker.use("qp", self.qp.value)
            self.required_resources.append({"type": "qp", "name": self.qp.value, "position": "qp"})  # 记录需要的资源
            # # Register the attribute variable in the tracker
            # self.tracker.create('attr_modify_qp', f"qp_attr_{qp}")
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())
        # 如果有 attr_obj，尝试替换其中的 remote 信息为 DeferredValue
        if self.attr_obj:
            self.attr_obj.bind_remote_qp(ctx.get_peer_qp_num(self.qp.value))

        self.context = ctx

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        attr_keys = {
            "qp_state",
            "pkey_index",
            "port_num",
            "qp_access_flags",
            "path_mtu",
            "dest_qp_num",
            "rq_psn",
            "max_dest_rd_atomic",
            "min_rnr_timer",
            "ah_attr.is_global",
            "ah_attr.dlid",
            "ah_attr.sl",
            "ah_attr.src_path_bits",
            "ah_attr.port_num",
            #  "ah_attr.grh.dgid",
            "ah_attr.grh.flow_label",
            "ah_attr.grh.hop_limit",
            "ah_attr.grh.sgid_index",
            "ah_attr.grh.traffic_class",
            "timeout",
            "retry_cnt",
            "rnr_retry",
            "sq_psn",
            "max_rd_atomic",
        }
        attr_params = {k: kv[k] for k in attr_keys if k in kv}
        attr_mask = kv.get(
            "attr_mask",
            "IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS",
        )
        return cls(qp=qp, attr=attr_params, attr_mask=attr_mask)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = str(self.qp)
        # e.g., "_0" for qp[0]
        attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
        # attr_name = f"attr_modify_rtr{attr_suffix}"
        attr_name = f"qp_attr{attr_suffix}"
        # Convert the attr dict to C++ code
        attr_lines = self.attr_obj.to_cxx(attr_name, ctx)
        # mask_code = mask_fields_to_c(self.attr_mask)
        mask_code = str(self.attr_mask)
        wait_code = ""
        target = None
        ao = getattr(self, "attr_obj", None) or getattr(self, "attr", None)
        if ao is not None and hasattr(ao, "qp_state"):
            qs = getattr(ao, "qp_state")
            qs = getattr(qs, "value", qs)
            target = _QP_ENUM_TO_STATE.get(str(qs))
        if target == State.RTR:
            wait_code = f'pr_wait_pair_state(BUNDLE_ENV, "pair-{self.qp}-{self.context.get_peer_qp_num(qp_name)}", "BOTH_RTS", /*timeout_ms=*/15000);'
        return f"""
    IF_OK_PTR({qp_name}, {{
        {wait_code}
        memset(&{attr_name}, 0, sizeof({attr_name}));
        {attr_lines}
        if (ibv_modify_qp({qp_name}, &{attr_name}, {mask_code})) {{
            fprintf(stderr, "Failed to modify QP {qp_name}\\n");
        }}
    }});
        """


class ModifyQPRateLimit(VerbCall):
    """
    表示 ibv_modify_qp_rate_limit() 调用，自动生成/重放 ibv_qp_rate_limit_attr 的初始化与调用。
    参数：
        qp_var      -- QP 变量名（如"qp1"）
        attr_var    -- qp_rate_limit_attr 结构体变量名（如"rate_limit_attr1"）
        attr_obj    -- IbvQPRateLimitAttr对象（可选，自动生成结构体内容）
    """

    MUTABLE_FIELDS = ["qp", "attr_var", "attr_obj"]
    EXPORT_FIELDS = ["qp", "attr_obj"]
    CONTRACT = Contract(requires=[RequireSpec("qp", State.ALLOCATED, "qp")], produces=[], transitions=[])

    def __init__(
        self,
        qp: str = None,
        attr_var: str = None,
        attr_obj: "IbvQPRateLimitAttr" = None,
    ):
        self.qp = (
            ResourceValue(resource_type="qp", value=qp) if qp else ResourceValue(resource_type="qp", value="qp")
        )  # QP address
        # Default variable name for the rate limit attributes
        # Variable name for the rate limit attributes
        self.attr_var = ConstantValue(attr_var or f"rate_limit_attr_{qp}")
        self.attr_obj = attr_obj

        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the QP address in the tracker
            self.tracker.use("qp", self.qp.value)
            self.required_resources.append({"type": "qp", "name": self.qp.value, "position": "qp"})  # 记录需要的资源
            # # Register the rate limit attributes variable in the tracker
            # self.tracker.create('attr_var', self.attr_var)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp_var = kv.get("qp", "qp")
        attr_var = kv.get("attr_var", "rate_limit_attr")
        attr_obj = kv.get("attr_obj")  # 若trace含结构体内容
        return cls(qp_var, attr_var, attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        # Get the QP variable name from context
        qp_name = self.qp
        code = ""
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            code += f"\n    struct ibv_qp_rate_limit_attr {self.attr_var} = {{0}};\n"
        code += f"""
    IF_OK_PTR({qp_name}, {{
        if (ibv_modify_qp_rate_limit({qp_name}, &{self.attr_var}) != 0) {{
            fprintf(stderr, "ibv_modify_qp_rate_limit failed {qp_name}\\n");
        }}
    }});
"""
        return code


class ModifySRQ(VerbCall):
    """
    表示 ibv_modify_srq() 调用，自动生成/重放 srq_attr 的初始化与调用。
    参数：
        srq_var      -- SRQ 变量名（如"srq1"）
        attr_var     -- srq_attr 结构体变量名（如"srq_attr1"）
        attr_obj     -- IbvSrqAttr对象（可选，自动生成结构体内容）
        attr_mask    -- int，传递给 C API 的 srq_attr_mask
    """

    MUTABLE_FIELDS = ["srq", "attr_var", "attr_obj", "attr_mask"]
    EXPORT_FIELDS = ["srq", "attr_obj", "attr_mask"]
    CONTRACT = Contract(requires=[RequireSpec("srq", State.ALLOCATED, "srq")], produces=[], transitions=[])

    def __init__(
        self,
        srq: str = None,
        attr_var: str = None,
        attr_obj: IbvSrqAttr = None,
        attr_mask: int = 0,
    ):
        if not srq:
            raise ValueError("SRQ name must be provided")
        self.srq = ResourceValue(resource_type="srq", value=srq)
        # Default variable name for the SRQ attributes
        # Variable name for the SRQ attributes
        self.attr_var = ConstantValue(attr_var or f"srq_attr_{srq}")
        # attr_obj is an instance of IbvSrqAttr or similar, containing the attributes
        self.attr_obj = attr_obj
        # Mask for the attributes to modify
        self.attr_mask = FlagValue(attr_mask or 0, flag_type="IBV_SRQ_ATTR_MASK_ENUM")
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the SRQ address in the tracker
            self.tracker.use("srq", self.srq.value)
            self.required_resources.append({"type": "srq", "name": self.srq.value, "position": "srq"})
            # # Register the SRQ attributes variable in the tracker
            # self.tracker.create('attr_var', self.attr_var)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        srq_var = kv.get("srq", "srq")
        attr_var = kv.get("attr_var", "srq_attr")
        attr_obj = kv.get("attr_obj")  # 若trace含结构体内容
        attr_mask = int(kv.get("attr_mask", 0))
        return cls(srq_var, attr_var, attr_obj, attr_mask)

    def generate_c(self, ctx: CodeGenContext) -> str:
        srq_name = self.srq
        code = ""
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            code += f"\n    struct ibv_srq_attr {self.attr_var} = {{0}};\n"
        code += f"""
    IF_OK_PTR({srq_name}, {{
        if (ibv_modify_srq({srq_name}, &{self.attr_var}, {self.attr_mask}) != 0) {{
            fprintf(stderr, "ibv_modify_srq failed {srq_name}\\n");
        }}
    }});
"""
        return code


class ModifyWQ(VerbCall):
    """
    表示 ibv_modify_wq() 调用，自动生成/重放 wq_attr 的初始化与调用。
    参数：
        wq_var      -- WQ 变量名（如"wq1"）
        attr_var    -- wq_attr 结构体变量名（如"wq_attr1"）
        attr_obj    -- IbvWQAttr对象（可选，自动生成结构体内容）
    """

    MUTABLE_FIELDS = ["wq", "attr_var", "attr_obj"]
    EXPORT_FIELDS = ["wq", "attr_obj"]
    CONTRACT = Contract(
        requires=[RequireSpec("wq", State.ALLOCATED, "wq")],
        produces=[],
        transitions=[],  # 若你有 WQ 状态机，可加 transitions
    )

    def __init__(self, wq: str = None, attr_var: str = None, attr_obj: "IbvWQAttr" = None):
        self.wq = (
            ResourceValue(resource_type="wq", value=wq) if wq else ResourceValue(resource_type="wq", value="wq")
        )  # WQ address
        # Default variable name for the WQ attributes
        # Variable name for the WQ attributes
        self.attr_var = ConstantValue(attr_var or f"wq_attr_{wq}")
        self.attr_obj = attr_obj
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the WQ address in the tracker
            self.tracker.use("wq", self.wq.value)
            self.required_resources.append({"type": "wq", "name": self.wq.value, "position": "wq"})  # 记录需要的资源
            # # Register the WQ attributes variable in the tracker
            # self.tracker.create('attr_var', self.attr_var)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        wq_var = kv.get("wq", "wq")
        attr_var = kv.get("attr_var", "wq_attr")
        attr_obj = kv.get("attr_obj")  # trace中如含结构体内容
        return cls(wq_var, attr_var, attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        # Get the WQ variable name from context
        wq_name = self.wq
        code = ""
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            code += f"\n    struct ibv_wq_attr {self.attr_var} = {{0}};\n"
        code += f"""
    IF_OK_PTR({wq_name}, {{
        if (ibv_modify_wq({wq_name}, &{self.attr_var}) != 0) {{
            fprintf(stderr, "ibv_modify_wq failed {wq_name}\\n");
        }}
    }});
"""
        return code


class OpenDevice(VerbCall):
    """Open an RDMA device and create a context for use."""

    MUTABLE_FIELDS = ["device"]
    EXPORT_FIELDS = ["device"]

    def __init__(self, device: str = None, ctx_name: str = None):
        # Device name or variable, e.g., "dev_list[
        self.device = ConstantValue(device or "dev_list")
        self.ctx_name = ConstantValue(ctx_name or "ctx")
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        return cls()  # No special initialization needed from trace

    def apply(self, ctx: CodeGenContext):
        self.context = ctx
        self.context.ib_ctx = self.ctx_name if ctx else "ctx"
        self.context.alloc_variable(self.context.ib_ctx, "struct ibv_context *")

    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = self.context.ib_ctx if self.context else "ctx"
        dev_list = self.context.dev_list  # Assuming correct allocation of device list
        return f"""
    /* ibv_open_device */
    {ib_ctx} = ibv_open_device({dev_list}[0]);
    if (!{ib_ctx}) {{
        fprintf(stderr, "Failed to open device {dev_list}\\n");
    }}
"""


class OpenQP(VerbCall):
    """
    表示 ibv_open_qp() 调用。
    参数：
        ctx_var      -- ibv_context 变量名（如"ctx"）
        qp_var       -- QP 变量名（如"qp1"）
        attr_var     -- qp_open_attr 结构体变量名（如"qp_open_attr1"）
        attr_obj     -- IbvQPOpenAttr对象（可选，自动生成结构体内容）
    """

    MUTABLE_FIELDS = ["ctx_var", "qp", "attr_var", "attr_obj"]
    EXPORT_FIELDS = ["ctx_var", "qp", "attr_var", "attr_obj"]
    CONTRACT = Contract(requires=[RequireSpec("qp", State.ALLOCATED, "qp")], produces=[], transitions=[])

    def __init__(
        self,
        ctx_var=None,
        qp: str = None,
        attr_var: str = None,
        attr_obj: IbvQPOpenAttr = None,
    ):
        # Context variable name, e.g., "ctx"
        self.ctx_var = ConstantValue(ctx_var or "ctx")
        self.qp = (
            ResourceValue(resource_type="qp", value=qp) if qp else ResourceValue(resource_type="qp", value="qp")
        )  # QP address
        # Default variable name for the QP open attributes
        # Variable name for the QP open attributes
        self.attr_var = ConstantValue(attr_var or f"qp_open_attr_{qp}")
        self.attr_obj = attr_obj
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        self.ctx_var = self.ctx_var or ctx.ib_ctx if ctx else "ctx"
        if self.tracker:
            # # Register the context variable in the tracker
            # self.tracker.use('ctx', ctx_var)
            # Register the QP address in the tracker
            self.tracker.use("qp", self.qp.value)
            # self.tracker.use(
            #     'xrcd', self.attr_obj.xrcd if self.attr_obj else None)
            self.required_resources.append({"type": "qp", "name": self.qp.value, "position": "qp"})  # 记录需要的资源
            # self.required_resources.append(('xrcd', self.attr_obj.xrcd if self
            #     .attr_obj else None))  # to be recursive 标记
            # # Register the context variable in the tracker
            # # Register the QP open attributes variable in the tracker
            # self.tracker.create('attr_var', self.attr_var)
            if self.attr_obj is not None:
                # Register the attribute object in the tracker
                self.attr_obj.apply(ctx)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ctx_var = kv.get("ctx", "ctx")
        qp_var = kv.get("qp", "qp")
        attr_var = kv.get("attr_var", "qp_open_attr")
        attr_obj = kv.get("attr_obj")  # 若trace中含结构体内容
        return cls(ctx_var, qp_var, attr_var, attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        self.qp_var = self.qp
        code = ""
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            code += f"\n    struct ibv_qp_open_attr {self.attr_var} = {{0}};\n"
        code += f"""
    {self.qp_var} = ibv_open_qp({self.ctx_var}, &{self.attr_var});
    if (!{self.qp_var}) {{
        fprintf(stderr, "ibv_open_qp failed {self.qp_var}\\n");
    }}
"""
        return code


class OpenXRCD(VerbCall):
    """
    表示 ibv_open_xrcd() 调用，自动生成 struct ibv_xrcd_init_attr 初始化与调用。
    参数：
        ctx_var     -- ibv_context 变量名（如"ctx"）
        xrcd_var    -- XRC Domain 变量名（如"xrcd1"）
        attr_var    -- xrcd_init_attr 结构体变量名（如"xrcd_init_attr1"）
        attr_obj    -- IbvXRCDInitAttr对象（可选，自动生成结构体内容）
    """

    MUTABLE_FIELDS = ["ctx_var", "xrcd", "attr_var", "attr_obj"]
    EXPORT_FIELDS = ["ctx_var", "xrcd", "attr_var", "attr_obj"]
    CONTRACT = Contract(requires=[RequireSpec("xrcd", State.ALLOCATED, "xrcd")], produces=[], transitions=[])

    def __init__(
        self,
        ctx_var: str = None,
        xrcd: str = None,
        attr_var: str = None,
        attr_obj: IbvXRCDInitAttr = None,
    ):
        # Context variable name, e.g., "ctx"
        self.ctx_var = ConstantValue(ctx_var or "ctx")
        self.xrcd = (
            ResourceValue(resource_type="xrcd", value=xrcd)
            if xrcd
            else ResourceValue(resource_type="xrcd", value="xrcd")
        )  # XRC Domain address
        # Default variable name for the XRC Domain attributes
        # Variable name for the XRC Domain attributes
        self.attr_var = ConstantValue(attr_var or f"xrcd_init_attr_{xrcd}")
        self.attr_obj = attr_obj
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # # Register the context variable in the tracker
            # self.tracker.use('ctx', ctx_var)
            # Register the XRC Domain address in the tracker
            self.tracker.use("xrcd", self.xrcd.value)
            self.required_resources.append(
                {"type": "xrcd", "name": self.xrcd.value, "position": "xrcd"}
            )  # 记录需要的资源
            # # Register the XRC Domain attributes variable in the tracker
            # self.tracker.create('attr_var', self.attr_var)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ctx_var = kv.get("ctx", "ctx")
        xrcd_var = kv.get("xrcd", "xrcd")
        attr_var = kv.get("attr_var", "xrcd_init_attr")
        attr_obj = kv.get("attr_obj")  # 若trace含结构体内容
        return cls(ctx_var, xrcd_var, attr_var, attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        # Get the XRC Domain variable name from context
        code = ""
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            code += f"\n    struct ibv_xrcd_init_attr {self.attr_var} = {{0}};\n"
        code += f"""
    {self.xrcd_var} = ibv_open_xrcd({self.ctx_var}, &{self.attr_var});
    if (!{self.xrcd_var}) {{
        fprintf(stderr, "ibv_open_xrcd failed {self.xrcd_var}\\n");
    }}
"""
        return code


class PollCQ(VerbCall):  # TODO: 这个非常特殊，是一个compound的函数，待改
    MUTABLE_FIELDS = ["cq"]
    EXPORT_FIELDS = ["cq"]
    CONTRACT = Contract(requires=[RequireSpec("cq", State.ALLOCATED, "cq")], produces=[], transitions=[])

    def __init__(self, cq: str = None):
        if not cq:
            raise ValueError("CQ name must be provided")
        self.cq = ResourceValue(resource_type="cq", value=cq)
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the CQ address in the tracker
            self.tracker.use("cq", self.cq.value)
            self.required_resources.append({"type": "cq", "name": self.cq.value, "position": "cq"})  # 记录需要的资源
            # # Register the CQ variable in the tracker
            # self.tracker.create('cq_var', cq)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq = kv.get("cq", "unknown")
        return cls(cq=cq)

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = str(self.cq)
        return f"""
        /* ibv_poll_cq — self-contained minimal polling */
        IF_OK_PTR({cq_name}, {{
            {{
                struct ibv_wc wc;
                int n = 0;
                int attempts = 100;   /* ~100 * 100us ≈ 10ms */
                while (attempts-- > 0) {{
                    n = ibv_poll_cq({cq_name}, 1, &wc);
                    if (n < 0) {{
                        fprintf(stderr, "ibv_poll_cq failed {cq_name}\\n");
                    }}
                    if (n == 1) {{
                        if (wc.status != IBV_WC_SUCCESS) {{
                            fprintf(stderr, "**bad** completion: status=0x%x vendor=0x%x cq={cq_name}\\n",
                                    wc.status, wc.vendor_err);
                        }}
                        /* success – got one completion */
                        printf("got one completion: wr_id=%lu opcode=%u byte_len=%u\\n",
                               wc.wr_id, wc.opcode, wc.byte_len);
                        break;
                    }}
                    /* n == 0: no CQE yet, back off briefly */
                    usleep(100); /* 100us */
                }}
                if (n == 0) {{
                    fprintf(stderr, "no completion within budget\\n");
                }}
            }}
        }});

    """


class PostRecv(VerbCall):
    """
    表示 ibv_post_recv() 调用，自动生成 recv_wr 链与调用代码。
    参数：
        qp   -- QP 资源变量名/trace名
        wr_obj    -- IbvRecvWR对象（支持链表）
        wr_var    -- recv_wr 结构体变量名
        bad_wr_var-- bad_wr 结构体指针变量名
    """

    MUTABLE_FIELDS = ["qp", "wr_obj", "wr_var", "bad_wr_var"]
    EXPORT_FIELDS = ["qp", "wr_obj", "wr_var", "bad_wr_var"]

    CONTRACT = Contract(
        requires=[
            # 需要 QP 存在（状态可不限制）
            RequireSpec("qp", State.RTS, "qp", exclude_states=[State.DESTROYED]),
            # 需要 WR 链里每个 SGE 的 MR 存在（未销毁即可）
            # wr_obj**   ：遍历整条 RecvWR 链
            # sg_list[*]：每个 WR 的所有 SGE
            # .mr       ：取出 ResourceValue("mr", <name>) → 名字
            RequireSpec("mr", State.ALLOCATED, "wr_obj.**.sg_list[*].mr"),
        ],
        produces=[],
        transitions=[],
    )

    def __init__(
        self,
        qp: str = None,
        wr_obj: IbvRecvWR = None,
        wr_var: str = None,
        bad_wr_var: str = None,
    ):
        if not qp:
            raise ValueError("QP name must be provided")
        self.qp = ResourceValue(resource_type="qp", value=qp)
        self.wr_obj = wr_obj
        self.wr_var = ConstantValue(wr_var or f"recv_wr_{qp}")
        self.bad_wr_var = ConstantValue(bad_wr_var or f"bad_recv_wr_{qp}")
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the QP address in the tracker
            self.tracker.use("qp", self.qp.value)
            self.required_resources.append({"type": "qp", "name": self.qp.value, "position": "qp"})  # 记录需要的资源
            # # Register the WR variable in the tracker
            # self.tracker.create('wr_var', self.wr_var)
            # # Register the bad WR variable in the tracker
            # self.tracker.create('bad_wr_var', self.bad_wr_var)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "qp")
        # 假设 trace 提供 wr 对象（或需自己构造/解析）
        wr_obj = kv.get("wr_obj")
        wr_var = kv.get("wr_var", "recv_wr")
        bad_wr_var = kv.get("bad_wr_var", "bad_recv_wr")
        return cls(qp, wr_obj, wr_var, bad_wr_var)

    # ---------- 辅助：递归收集 WR 链里所有 SGE 的 MR 名 ----------
    @staticmethod
    def _collect_mr_names_from_wr_head(wr_head) -> list[str]:
        """
        遍历 wr_head 整条链（通过 .next），把每个 WR 的 sg_list[*].mr 的 ResourceValue.name 收集（去重，保序）。
        """
        seen = set()
        order = []

        def add(name: str):
            if name not in seen:
                seen.add(name)
                order.append(name)

        cur = wr_head
        while cur is not None:
            # sg_list
            try:
                sg_lv = getattr(cur, "sg_list", None)
                if isinstance(sg_lv, OptionalValue):
                    sg_list = sg_lv.value
                else:
                    sg_list = sg_lv
                if isinstance(sg_list, list) or isinstance(sg_list, ListValue):
                    for sge in sg_list:
                        mr_val = getattr(sge, "mr", None)
                        if isinstance(mr_val, ResourceValue) and mr_val.resource_type == "mr":
                            if isinstance(mr_val.value, str) and mr_val.value:
                                add(mr_val.value)
            except Exception:
                pass

            # next
            nxt = None
            try:
                nxt_ov = getattr(cur, "next", None)
                if isinstance(nxt_ov, OptionalValue):
                    nxt = nxt_ov.value
                else:
                    nxt = nxt_ov
            except Exception:
                nxt = None
            cur = nxt

        return order

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = coerce_str(self.qp)
        wr = unwrap(self.wr_obj)
        wr_var = str(self.wr_var)  # e.g., "recv_wr_qp1"
        bad_wr_var = str(self.bad_wr_var)  # e.g., "bad_recv
        wr_name = str(self.wr_var)  # e.g., "recv_wr_qp1"
        bad_wr_name = str(self.bad_wr_var)  # e.g., "bad_recv
        # 构造 WR 结构体（链表/单个）
        code_wr = ""
        if self.wr_obj is not None:
            code_wr += self.wr_obj.to_cxx(wr_var, ctx)
        # bad_wr 定义

        ctx.alloc_variable(bad_wr_var, "struct ibv_recv_wr *", "NULL")

        mr_names = self._collect_mr_names_from_wr_head(wr)
        ptrs = [qp_name] + mr_names

        guard_open = []
        guard_close = []
        for i, p in enumerate(ptrs):
            guard_open.append(f"    IF_OK_PTR({p}, {{\n")
            guard_close.append("    });\n")

        guard_prefix = "".join(guard_open)
        guard_suffix = "".join(reversed(guard_close))

        body = f"""\
    if (ibv_post_recv({qp_name}, &{wr_name}, &{bad_wr_name}) != 0) {{
        fprintf(stderr, "[warn] ibv_post_recv failed {qp_name}\\n");
    }}"""
        return f"""
    /* ibv_post_recv (fuzz-friendly guarded) */
{guard_prefix}{code_wr}{body}
{guard_suffix}
"""


class PostSend(VerbCall):
    MUTABLE_FIELDS = ["qp", "wr_obj"]
    EXPORT_FIELDS = ["qp", "wr_obj"]

    # 要求 RTS 的 QP + 全链路 SGE 所用的 MR 已分配
    CONTRACT = Contract(
        requires=[
            RequireSpec("qp", State.RTS, "qp", exclude_states=[State.DESTROYED]),
            RequireSpec("mr", State.ALLOCATED, "wr_obj.**.sg_list[*].mr"),
        ],
        produces=[],
        transitions=[],
    )

    def __init__(self, qp: str = None, wr_obj: IbvSendWR = None, wr_var=None, bad_wr_var=None):
        if not qp:
            raise ValueError("QP name must be provided")
        self.qp = ResourceValue(resource_type="qp", value=qp)
        self.wr_obj = wr_obj  # IbvSendWR（可为链表头）
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            self.tracker.use("qp", self.qp.value)
            self.required_resources.append({"type": "qp", "name": self.qp.value, "position": "qp"})
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    # ---------- 辅助：递归收集 WR 链里所有 SGE 的 MR 名 ----------
    @staticmethod
    def _collect_mr_names_from_wr_head(wr_head) -> list[str]:
        """
        遍历 wr_head 整条链（通过 .next），把每个 WR 的 sg_list[*].mr 的 ResourceValue.name 收集（去重，保序）。
        """
        seen = set()
        order = []

        def add(name: str):
            if name not in seen:
                seen.add(name)
                order.append(name)

        cur = wr_head
        while cur is not None:
            # sg_list
            try:
                sg_lv = getattr(cur, "sg_list", None)
                if isinstance(sg_lv, OptionalValue):
                    sg_list = sg_lv.value
                else:
                    sg_list = sg_lv
                if isinstance(sg_list, list) or isinstance(sg_list, ListValue):
                    for sge in sg_list:
                        mr_val = getattr(sge, "mr", None)
                        if isinstance(mr_val, ResourceValue) and mr_val.resource_type == "mr":
                            if isinstance(mr_val.value, str) and mr_val.value:
                                add(mr_val.value)
            except Exception:
                pass

            # next
            nxt = None
            try:
                nxt_ov = getattr(cur, "next", None)
                if isinstance(nxt_ov, OptionalValue):
                    nxt = nxt_ov.value
                else:
                    nxt = nxt_ov
            except Exception:
                nxt = None
            cur = nxt

        return order

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = coerce_str(self.qp)
        wr = unwrap(self.wr_obj)
        suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
        wr_name = f"wr{suffix}"
        bad_wr_name = f"bad_wr{suffix}"

        # 1) 铺 WR 结构体
        code_wr = ""
        if self.wr_obj is not None:
            code_wr += self.wr_obj.to_cxx(wr_name, ctx)

        # 2) 声明 bad_wr 指针
        ctx.alloc_variable(bad_wr_name, "struct ibv_send_wr *", "NULL")

        # 3) 找出这次调用所依赖的指针：QP + WR 链里的所有 MR 指针名
        mr_names = self._collect_mr_names_from_wr_head(wr)
        ptrs = [qp_name] + mr_names  # 守卫顺序：先 QP，再 MRs

        # 4) 生成嵌套 IF_OK_PTR 守卫
        guard_open = []
        guard_close = []
        for i, p in enumerate(ptrs):
            guard_open.append(f"    IF_OK_PTR({p}, {{\n")
            guard_close.append("    });\n")

        guard_prefix = "".join(guard_open)
        guard_suffix = "".join(reversed(guard_close))

        # 5) 生成最终调用
        bad_wr_arg = f"&{bad_wr_name}"
        body = f"""\
    if (ibv_post_send({qp_name}, &{wr_name}, {bad_wr_arg}) != 0) {{
        fprintf(stderr, "[warn] ibv_post_send failed {qp_name}\\n");
    }}"""

        return f"""
    /* ibv_post_send (fuzz-friendly guarded) */
{guard_prefix}{code_wr}{body}
{guard_suffix}
"""


class PostSRQRecv(VerbCall):
    """
    表示 ibv_post_srq_recv() 调用，自动生成 recv_wr 链和调用代码。
    参数：
        srq   -- SRQ 资源变量名（或 trace 名）
        wr_obj     -- IbvRecvWR 对象（支持链表）
        wr_var     -- recv_wr 结构体变量名
        bad_wr_var -- bad_recv_wr 结构体指针变量名
    """

    MUTABLE_FIELDS = ["srq", "wr_obj", "wr_var", "bad_wr_var"]
    EXPORT_FIELDS = ["srq", "wr_obj", "wr_var", "bad_wr_var"]
    CONTRACT = Contract(
        requires=[
            RequireSpec("srq", State.ALLOCATED, "srq"),
            RequireSpec("mr", State.ALLOCATED, "wr_obj.**.sg_list[*].mr"),
        ],
        produces=[],
        transitions=[],
    )

    def __init__(
        self,
        srq: str = None,
        wr_obj: IbvRecvWR = None,
        wr_var: str = None,
        bad_wr_var: str = None,
    ):
        if not srq:
            raise ValueError("SRQ name must be provided")
        self.srq = ResourceValue(resource_type="srq", value=srq)
        self.wr_obj = wr_obj
        # Default variable name for the receive work request
        self.wr_var = ConstantValue(wr_var or f"recv_wr_{srq}")
        self.bad_wr_var = ConstantValue(bad_wr_var or f"bad_recv_wr_{srq}")
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the SRQ address in the tracker
            self.tracker.use("srq", self.srq.value)
            self.required_resources.append({"type": "srq", "name": self.srq.value, "position": "srq"})  # 记录需要的资源
            # # Register the WR variable in the tracker
            # self.tracker.create('wr_var', self.wr_var)
            # # Register the bad WR variable in the tracker
            # self.tracker.create('bad_wr_var', self.bad_wr_var)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        srq = kv.get("srq", "srq")
        wr_obj = kv.get("wr_obj")
        wr_var = kv.get("wr_var", "recv_wr")
        bad_wr_var = kv.get("bad_wr_var", "bad_recv_wr")
        return cls(srq, wr_obj, wr_var, bad_wr_var)

    # ---------- 辅助：递归收集 WR 链里所有 SGE 的 MR 名 ----------
    @staticmethod
    def _collect_mr_names_from_wr_head(wr_head) -> list[str]:
        """
        遍历 wr_head 整条链（通过 .next），把每个 WR 的 sg_list[*].mr 的 ResourceValue.name 收集（去重，保序）。
        """
        seen = set()
        order = []

        def add(name: str):
            if name not in seen:
                seen.add(name)
                order.append(name)

        cur = wr_head
        while cur is not None:
            # sg_list
            try:
                sg_lv = getattr(cur, "sg_list", None)
                if isinstance(sg_lv, OptionalValue):
                    sg_list = sg_lv.value
                else:
                    sg_list = sg_lv
                if isinstance(sg_list, list) or isinstance(sg_list, ListValue):
                    for sge in sg_list:
                        mr_val = getattr(sge, "mr", None)
                        if isinstance(mr_val, ResourceValue) and mr_val.resource_type == "mr":
                            if isinstance(mr_val.value, str) and mr_val.value:
                                add(mr_val.value)
            except Exception:
                pass

            # next
            nxt = None
            try:
                nxt_ov = getattr(cur, "next", None)
                if isinstance(nxt_ov, OptionalValue):
                    nxt = nxt_ov.value
                else:
                    nxt = nxt_ov
            except Exception:
                nxt = None
            cur = nxt

        return order

    def generate_c(self, ctx: CodeGenContext) -> str:
        srq_name = coerce_str(self.srq)
        wr = unwrap(self.wr_obj)
        wr_var = str(self.wr_var)  # e.g., "recv_wr_qp1"
        bad_wr_var = str(self.bad_wr_var)  # e.g., "bad_recv
        wr_name = str(self.wr_var)  # e.g., "recv_wr_qp1"
        bad_wr_name = str(self.bad_wr_var)  # e.g., "bad_recv
        # 构造 WR 结构体（链表/单个）
        code_wr = ""
        if self.wr_obj is not None:
            code_wr += self.wr_obj.to_cxx(wr_var, ctx)
        # bad_wr 定义

        ctx.alloc_variable(bad_wr_var, "struct ibv_recv_wr *", "NULL")

        mr_names = self._collect_mr_names_from_wr_head(wr)
        ptrs = [srq_name] + mr_names

        guard_open = []
        guard_close = []
        for i, p in enumerate(ptrs):
            guard_open.append(f"    IF_OK_PTR({p}, {{\n")
            guard_close.append("    });\n")

        guard_prefix = "".join(guard_open)
        guard_suffix = "".join(reversed(guard_close))

        body = f"""\
    if (ibv_post_srq_recv({srq_name}, &{wr_name}, &{bad_wr_name}) != 0) {{
        fprintf(stderr, "[warn] ibv_post_srq_recv failed {srq_name}\\n");
    }}"""
        return f"""
    /* ibv_post_srq_recv (fuzz-friendly guarded) */
{guard_prefix}{code_wr}{body}
{guard_suffix}
"""


class QueryDeviceAttr(VerbCall):
    """Query the attributes of an RDMA device using its context."""

    MUTABLE_FIELDS = ["output"]
    EXPORT_FIELDS = ["output"]

    def __init__(self, output: str = None):
        # Default output variable name
        self.output = ConstantValue(output or "dev_attr")
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        return cls()

    def apply(self, ctx: CodeGenContext):
        self.context = ctx
        if ctx:
            ctx.alloc_variable(self.output, "struct ibv_device_attr")
            ctx.dev_attr = str(self.output)  # Register in context for later use

    def generate_c(self, ctx: CodeGenContext) -> str:
        # dev_attr = ctx.dev_attr
        # if self.output is None:
        #     self.output = dev_attr  # Use the context's device attribute variable
        ib_ctx = ctx.ib_ctx
        return f"""
    /* ibv_query_device */
    if (ibv_query_device({ib_ctx}, &{self.output})) {{
        fprintf(stderr, "Failed to query device attributes\\n");
        return -1;
    }}
"""


class QueryDeviceEx(VerbCall):
    """
    表示 ibv_query_device_ex() 调用。
    参数:
        ctx_var  -- ibv_context 变量名
        attr_var -- ibv_device_attr_ex 变量名
        comp_mask -- input.comp_mask 的值
        input_var -- (可选) input 结构体变量名
    """

    MUTABLE_FIELDS = ["ctx_var", "attr_var", "comp_mask", "input_var"]
    EXPORT_FIELDS = ["ctx_var", "attr_var", "comp_mask", "input_var"]
    # CONTRACT = Contract(
    #     requires=[RequireSpec("ctx", None, "ctx")],
    #     produces=[RequireSpec("attr", None, "attr")],
    #     transitions=[],
    # )

    def __init__(
        self,
        ctx_var: str = None,
        attr_var: str = None,
        comp_mask: int = None,
        input_var: str = None,
    ):
        self.ctx_var = ConstantValue(ctx_var or "ctx")  # Context variable name
        self.attr_var = ConstantValue(attr_var or "attr")  # this is output
        self.comp_mask = IntValue(comp_mask or 0)  # Comp mask value
        self.input_var = ConstantValue(input_var or "query_input")  # Input variable name

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ctx_var = kv.get("ctx", "ctx")
        attr_var = kv.get("attr_var", "dev_attr_ex")
        comp_mask = int(kv.get("comp_mask", 0))
        input_var = kv.get("input_var", "query_input")
        return cls(ctx_var, attr_var, comp_mask, input_var)

    def apply(self, ctx: CodeGenContext):
        if ctx:
            # # Register the context variable in the context
            # ctx.alloc_variable(self.ctx_var, "struct ibv_context")
            # Register the output variable in the context
            ctx.alloc_variable(self.attr_var, "struct ibv_device_attr_ex")
            # Register the input variable in the context
            ctx.alloc_variable(self.input_var, "struct ibv_query_device_ex_input")

    def generate_c(self, ctx: CodeGenContext) -> str:
        # Register the input variable in the context
        # ctx.alloc_variable(self.input_var, "struct ibv_query_device_ex_input")
        # ctx.alloc_variable(
        #     self.attr_var, "struct ibv_device_attr_ex")  # Register
        s = f"""
    memset(&{self.input_var}, 0, sizeof({self.input_var}));
    {self.input_var}.comp_mask = {self.comp_mask};
    if (ibv_query_device_ex({self.ctx_var}, &{self.input_var}, &{self.attr_var}) != 0) {{
        fprintf(stderr, "ibv_query_device_ex failed {self.ctx_var}\\n");
        return -1;
    }}
"""
        return s


class QueryECE(VerbCall):
    MUTABLE_FIELDS = ["qp", "output"]
    EXPORT_FIELDS = ["qp", "output"]
    CONTRACT = Contract(
        requires=[RequireSpec("qp", None, "qp", exclude_states=[State.DESTROYED])],
        produces=[RequireSpec("ece_options", None, "ece_options")],
        transitions=[],
    )

    """Query the ECE options of a QP (Queue Pair) using its address."""

    def __init__(self, qp: str = None, output: str = None):
        self.qp = ResourceValue(resource_type="qp", value=qp) if qp else ResourceValue(resource_type="qp", value="qp")
        # Default output variable name
        self.output = ConstantValue(output or "ece_options")
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the QP address in the tracker
            self.tracker.use("qp", self.qp.value)
            self.required_resources.append({"type": "qp", "name": self.qp.value, "position": "qp"})  # 记录需要的资源
            # # Register the ECE options variable in the tracker
            # self.tracker.create('ece_var', self.output)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        return cls(qp=qp)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = str(self.qp)
        # Register the ECE options variable in the context
        ctx.alloc_variable(self.output, "struct ibv_ece")
        return f"""
    /* ibv_query_ece */
    IF_OK_PTR({qp_name}, {{
        if (ibv_query_ece({qp_name}, &{self.output})) {{
            fprintf(stderr, "Failed to query ECE options, error code: %d\\n", query_result);
        }}
        fprintf(stdout, "ECE options for QP: vendor_id=0x%x, options=0x%x, comp_mask=0x%x\\n",
                {self.output}.vendor_id, {self.output}.options, {self.output}.comp_mask);
    }});

"""


class QueryGID(VerbCall):
    MUTABLE_FIELDS = ["port_num", "index"]

    def __init__(self, port_num: int = None, index: int = None, gid_var: str = None):
        self.port_num = IntValue(port_num or 1)  # Default port number
        self.index = IntValue(index or 1)  # Default GID index
        self.gid_var = ConstantValue(gid_var or "gid")  # Variable name for the GID output

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        port_num = int(kv.get("port_num", "1"))
        index = int(kv.get("index", "0"))
        return cls(port_num=port_num, index=index)

    def apply(self, ctx: CodeGenContext):
        self.context = ctx
        if ctx:
            ctx.alloc_variable(self.gid_var, "union ibv_gid")
            ctx.gid_var = str(self.gid_var)  # Register in context for later use

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_query_gid */
    if (ibv_query_gid({self.context.ib_ctx}, {self.port_num}, {self.index}, &{self.gid_var})) {{
        fprintf(stderr, "Failed to query GID {self.context.ib_ctx}, {self.port_num}, {self.index}\\n");
        return -1;
    }}
"""


class QueryGIDEx(VerbCall):
    MUTATBLE_FIELDS = ["port_num", "gid_index", "flags", "output"]
    EXPORT_FIELDS = ["port_num", "gid_index", "flags", "output"]
    """Query a specific GID entry on a given port of an RDMA device."""

    def __init__(
        self,
        port_num: int = None,
        gid_index: int = None,
        flags: int = None,
        output: str = None,
    ):
        self.port_num = IntValue(port_num or 1)  # Default port number
        self.gid_index = IntValue(gid_index or 0)  # Default GID index
        self.flags = IntValue(flags or 0)  # Default flags # now must be 0
        # Variable name for the GID entry output
        self.output = ConstantValue("gid" or output)

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        port_num = int(kv.get("port_num", 1))
        gid_index = int(kv.get("gid_index", 0))
        flags = int(kv.get("flags", 0))
        return cls(port_num=port_num, gid_index=gid_index, flags=flags)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = ctx.ib_ctx
        ctx.alloc_variable(self.output, "struct ibv_gid_entry")
        return f"""
    /* ibv_query_gid_ex */
    if (ibv_query_gid_ex({ib_ctx}, {self.port_num}, {self.gid_index}, &{self.output}, {self.flags})) {{
        fprintf(stderr, "Failed to query GID {ib_ctx}, {self.port_num}, {self.gid_index}\\n");
        return -1;
    }}
"""


class QueryGIDTable(VerbCall):
    """Query GID table of a given RDMA device context."""

    MUTABLE_FIELDS = ["max_entries", "output"]
    EXPORT_FIELDS = ["max_entries", "output"]

    def __init__(self, max_entries: int = None, output: str = None):
        self.max_entries = IntValue(max_entries or 10)  # Default max entries
        # Variable name for the GID entries output
        self.output = ConstantValue(output or "gid_entries")

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        return cls(max_entries=int(kv.get("max_entries", 10)))

    def generate_c(self, ctx: CodeGenContext) -> str:
        ctx.alloc_variable(self.output, "struct ibv_gid_entry", f"entries[{self.max_entries}]")
        ib_ctx = ctx.ib_ctx
        return f"""
    /* ibv_query_gid_table */
    if (ibv_query_gid_table({ctx.ib_ctx}, {self.output}, {self.max_entries}, 0) < 0) {{
        fprintf(stderr, "Failed to query GID table {ctx.ib_ctx}, {self.output}, {self.max_entries}\\n");
        return -1;
    }}
"""


class QueryPKey(VerbCall):
    """Query an InfiniBand port's P_Key table entry."""

    MUTATBLE_FIELDS = ["port_num", "index", "pkey"]
    EXPORT_FIELDS = ["port_num", "index", "pkey"]

    def __init__(self, port_num: int = None, index: int = None, pkey: str = None):
        self.port_num = IntValue(port_num or 1)  # Default port number
        self.index = IntValue(index or 0)  # Default P_Key index
        # Variable name for the P_Key output
        self.pkey = ConstantValue(pkey or "pkey")

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        port_num = int(kv.get("port_num", "1"))
        index = int(kv.get("index", "0"))
        pkey = kv.get("pkey", "pkey")
        return cls(port_num=port_num, index=index, pkey=pkey)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pkey_name = self.pkey
        return f"""
    /* ibv_query_pkey */
    if (ibv_query_pkey({ctx.ib_ctx}, {self.port_num}, {self.index}, &{pkey_name})) {{
        fprintf(stderr, "Failed to query P_Key {ctx.ib_ctx}, {self.port_num}, {self.index}\\n");
        return -1;
    }}
"""


class QueryPortAttr(VerbCall):
    """Query the attributes of a specified RDMA port on a given device context."""

    MUTABLE_FIELDS = ["port_num"]
    EXPORT_FIELDS = ["port_num", "port_attr"]

    def __init__(self, port_num: int = None, port_attr: str = None):
        self.port_num = IntValue(port_num or 1)  # Default port number
        self.port_attr = ConstantValue(port_attr or "port_attr")  # Variable name for port attributes

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        return cls(port_num=int(kv.get("port_num", "1")))

    def apply(self, ctx: CodeGenContext):
        self.context = ctx
        if ctx:
            ctx.alloc_variable(self.port_attr, "struct ibv_port_attr")
            ctx.port_attr = str(self.port_attr)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = self.context.ib_ctx
        return f"""
    /* ibv_query_port */
    if (ibv_query_port({ib_ctx}, {self.port_num}, &{self.port_attr})) {{
        fprintf(stderr, "Failed to query port attributes {ib_ctx}, {self.port_num}\\n");
        return -1;
    }}
"""


class QueryQP(VerbCall):
    """Query the attributes of a specified Queue Pair (QP) in an RDMA context."""

    MUTABLE_FIELDS = ["qp", "attr_mask"]
    EXPORT_FIELDS = ["qp", "attr_mask"]
    CONTRACT = Contract(
        requires=[RequireSpec("qp", None, "qp", exclude_states=[State.DESTROYED])],
        produces=[],
        transitions=[],
    )

    def __init__(self, qp: str = None, attr_mask: str = None):
        self.qp = ResourceValue(resource_type="qp", value=qp) if qp else ResourceValue(resource_type="qp", value="qp")
        self.attr_mask = FlagValue(
            attr_mask or "IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS",
            flag_type="IBV_QP_ATTR_MASK_ENUM",
        )
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the QP address in the tracker
            self.tracker.use("qp", self.qp.value)
            self.required_resources.append({"type": "qp", "name": self.qp.value, "position": "qp"})  # 记录需要的资源
            # # Register the attribute mask in the tracker
            # self.tracker.create('attr_mask', attr_mask)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        mask = kv.get("attr_mask", "0")
        return cls(qp=qp, attr_mask=int(mask))

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = str(self.qp)
        # e.g., "_0" for qp[0]
        attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
        attr_name = f"attr_query{attr_suffix}"
        init_attr_name = f"init_attr{attr_suffix}"
        # Register the QP attribute variable in the context
        ctx.alloc_variable(attr_name, "struct ibv_qp_attr")
        ctx.alloc_variable(init_attr_name, "struct ibv_qp_init_attr")  #
        return f"""
    /* ibv_query_qp */
    IF_OK_PTR({qp_name}, {{
        if (ibv_query_qp({qp_name}, &{attr_name}, {self.attr_mask}, &{init_attr_name})) {{
            fprintf(stderr, "Failed to query QP {qp_name}\\n");
        }}
    }});
"""


# class QueryQPDataInOrder(VerbCall):
#     def __init__(self, qp: str, opcode: str, flags: int):
#         self.qp = qp
#         self.opcode = opcode
#         self.flags = flags

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         qp = kv.get("qp", "unknown")
#         opcode = kv.get("opcode", "IBV_WR_SEND")
#         flags = int(kv.get("flags", "0"), 0)
#         ctx.use_qp(qp)  # Ensure the QP is used before generating code
#         return cls(qp=qp, opcode=opcode, flags=flags)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         qp_name = ctx.get_qp(self.qp)
#         return f"""
#     /* ibv_query_qp_data_in_order */
#     int in_order = ibv_query_qp_data_in_order({qp_name}, {self.opcode}, {self.flags});
#     if (in_order < 0) {{
#         fprintf(stderr, "Failed to query QP data in order\\n");
#         return -1;
#     }}
#     printf("QP data in order query result: %d\\n", in_order);
# """

# class QueryRTValuesEx(VerbCall):
#     def __init__(self):
#         pass

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         return cls()

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         ib_ctx = ctx.ib_ctx
#         return f"""
#     /* ibv_query_rt_values_ex */
#     struct ibv_values_ex values;
#     values.comp_mask = IBV_VALUES_MASK_RAW_CLOCK; /* Request to query the raw clock */
#     if (ibv_query_rt_values_ex({ib_ctx}, &values)) {{
#         fprintf(stderr, "Failed to query real time values\\n");
#         return -1;
#     }}
#     fprintf(stdout, "HW raw clock queried successfully\\n");
# """


class QuerySRQ(VerbCall):
    """Query a Shared Receive Queue (SRQ) for its attributes."""

    MUTABLE_FIELDS = ["srq"]
    EXPORT_FIELDS = ["srq"]
    CONTRACT = Contract(
        requires=[RequireSpec("srq", State.ALLOCATED, "srq")],
        produces=[],
        transitions=[],
    )

    def __init__(self, srq: str = None):
        self.srq = (
            ResourceValue(resource_type="srq", value=srq) if srq else ResourceValue(resource_type="srq", value="srq")
        )
        # Default variable name for the SRQ attributes
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the SRQ address in the tracker
            self.tracker.use("srq", self.srq.value)
            self.required_resources.append({"type": "srq", "name": self.srq.value, "position": "srq"})  # 记录需要的资源
            # # Register the SRQ variable in the tracker
            # self.tracker.create('srq_var', srq)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        srq = kv.get("srq", "unknown")
        return cls(srq=srq)

    def generate_c(self, ctx: CodeGenContext) -> str:
        srq_name = str(self.srq)
        attr_name = f"srq_attr_{srq_name.replace('[', '_').replace(']', '')}"
        ctx.alloc_variable(attr_name, "struct ibv_srq_attr")
        return f"""
    /* ibv_query_srq */
    IF_OK_PTR({srq_name}, {{
        if (ibv_query_srq({srq_name}, &{attr_name})) {{
            fprintf(stderr, "Failed to query SRQ {srq_name}\\n");
        }}
        fprintf(stdout, "SRQ max_wr: %u, max_sge: %u, srq_limit: %u\\n", 
                {attr_name}.max_wr, {attr_name}.max_sge, {attr_name}.srq_limit);
    }});

"""


# class RateToMbps(VerbCall): # 意义不明，没什么用
#     """Convert IB rate enumeration to Mbps."""
#     MUTABLE_FIELDS = ['rate', 'output']
#     def __init__(self, rate: str, output: str = "mbps"):
#         self.rate = rate  # IB rate enumeration
#         self.output = output

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext = None):
#         kv = _parse_kv(info)
#         rate = kv.get("rate", "IBV_RATE_MAX")
#         return cls(rate=rate)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         # Register the output variable in the context
#         ctx.alloc_variable(self.output, "int")
#         return f"""
#     /* ibv_rate_to_mbps */
#     {self.output} = ibv_rate_to_mbps({self.rate});
#     printf("Rate: %s, Mbps: %d\\n", "{self.rate}", mbps);
# """


# class RateToMult(VerbCall):
#     """Convert IB rate enumeration to multiplier of 2.5 Gbit/sec (IBV_RATE_TO_MULT)"""

#     def __init__(self, rate: str, output: str = "mbps"):
#         self.rate = rate  # IB rate enumeration
#         self.output = output

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         rate = kv.get("rate", "IBV_RATE_MAX")
#         return cls(rate=rate)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         # Register the output variable in the context
#         ctx.alloc_variable(self.output, "int")
#         return f"""
#     /* ibv_rate_to_mult */
#     {self.output}  ibv_rate_to_mult({self.rate});
#     printf("Rate multiplier for {self.rate}: %d\\n", multiplier);
# """


class RegDmaBufMR(VerbCall):
    MUTABLE_FIELDS = ["pd", "mr", "offset", "length", "iova", "fd", "access"]
    EXPORT_FIELDS = ["pd", "mr", "offset", "length", "iova", "fd", "access"]
    CONTRACT = Contract(
        requires=[RequireSpec("pd", State.ALLOCATED, "pd")],
        produces=[ProduceSpec("mr", State.ALLOCATED, "mr")],
        transitions=[],
    )
    """Register a DMA buffer memory region (MR) with the specified protection domain (PD)."""

    def __init__(
        self,
        pd: str = None,
        mr: str = None,
        offset: int = None,
        length: int = None,
        iova: int = None,
        fd: int = None,
        access: int = None,
    ):
        self.pd = ResourceValue(resource_type="pd", value=pd) if pd else ResourceValue(resource_type="pd", value="pd")
        self.mr = ResourceValue(resource_type="mr", value=mr) if mr else ResourceValue(resource_type="mr", value="mr")
        self.offset = IntValue(offset or 0)  # Default offset
        self.length = IntValue(length or 4096)  # Default length
        self.iova = IntValue(iova or 0)  # Default IOVA
        # Default file descriptor # TODO: 注意这个可能不能变异，得做成fd变量
        self.fd = IntValue(fd or 0)
        self.access = FlagValue(
            access or "IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
            flag_type="IBV_ACCESS_FLAGS_ENUM",
        )

        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the PD and MR addresses in the tracker
            self.tracker.use("pd", self.pd.value)
            self.tracker.create("mr", self.mr.value)
            self.required_resources.append({"type": "pd", "name": self.pd.value, "position": "pd"})
            self.allocated_resources.append(("mr", self.mr.value))  # 记录需要的资源
            # # Register the MR variable in the tracker
            # self.tracker.create('mr_var', mr)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "pd[0]")
        mr = kv.get("mr", "unknown")
        offset = int(kv.get("offset", "0"))
        length = int(kv.get("length", "0"))
        iova = int(kv.get("iova", "0"))
        fd = int(kv.get("fd", "0"))
        access = int(kv.get("access", "0"))
        return cls(
            pd=pd,
            mr=mr,
            offset=offset,
            length=length,
            iova=iova,
            fd=fd,
            access=access,
            ctx=ctx,
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        mr_name = self.mr
        pd_name = self.pd
        return f"""
    /* ibv_reg_dmabuf_mr */
    {mr_name} = ibv_reg_dmabuf_mr({pd_name}, {self.offset}, {self.length}, {self.iova}, {self.fd}, {self.access});
    if (!{mr_name}) {{
        fprintf(stderr, "Failed to register dmabuf MR {mr_name}\\n");
    }}

    IF_OK_PTR({mr_name}, {{
        mrs[mrs_size++] = (PR_MR){{
            .id = "{mr_name}",
            .addr = (uint64_t)({mr_name}->addr),
            .length = {self.length},
            .lkey = {mr_name}->lkey
        }};
        pr_write_client_update_claimed(CLIENT_UPDATE_PATH, qps, qps_size, mrs, mrs_size, prs, prs_size);
    }});
"""


class RegMR(VerbCall):
    MUTABLE_FIELDS = ["pd", "mr", "addr", "length", "access"]
    EXPORT_FIELDS = ["pd", "mr", "addr", "length", "access"]
    CONTRACT = Contract(
        requires=[RequireSpec("pd", State.ALLOCATED, "pd"), RequireSpec("buf", State.ALLOCATED, "addr")],
        produces=[ProduceSpec("mr", State.ALLOCATED, "mr", metadata_fields=["pd"])],
        transitions=[
            TransitionSpec("buf", from_state=State.ALLOCATED, to_state=State.USED, name_attr="addr")
        ],  # 简单设计，禁止在同一个verb序列里重复使用，所以dereg不需要改
    )
    """Register a memory region (MR) with the specified protection domain (PD)."""

    def __init__(
        self,
        pd: str = None,
        mr: str = None,
        addr: str = None,
        length: int = None,
        access: str = None,
    ):
        # if not pd or not mr:
        #     raise ValueError("PD and MR name must be provided")
        self.pd = ResourceValue(resource_type="pd", value=pd) if pd else "NULL"
        if not mr:
            raise ValueError("MR name must be provided")
        self.mr = ResourceValue(resource_type="mr", value=mr, mutable=False)
        # self.addr = ConstantValue(addr or "buf")  # Default buffer variable name
        self.addr = LocalResourceValue(value=addr or "buf", resource_type="buf")
        self.length = IntValue(length or 4096)  # Default length
        self.access = FlagValue(access or "IBV_ACCESS_LOCAL_WRITE", flag_type="IBV_ACCESS_FLAGS_ENUM")
        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        self.context = ctx
        if self.context:
            self.context.alloc_variable(str(self.mr), "struct ibv_mr *", "NULL")

        if self.tracker:
            # Register the PD and MR addresses in the tracker
            self.tracker.use("pd", self.pd.value)
            self.tracker.create("mr", self.mr.value)
            self.required_resources.append({"type": "pd", "name": self.pd.value, "position": "pd"})
            self.allocated_resources.append(("mr", self.mr.value))  # 记录需要的资源
            # # Register the MR variable in the tracker
            # self.tracker.create('mr_var', mr)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "pd[0]")
        mr = kv.get("mr", "unknown")
        access = kv.get("access", "IBV_ACCESS_LOCAL_WRITE")
        return cls(pd=pd, mr=mr, access=access, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = coerce_str(self.pd)
        mr_name = coerce_str(self.mr)
        # addr = ensure_identifier(self.addr)  # 若当成 C 变量名使用
        addr = coerce_str(self.addr)
        length = coerce_int(self.length)
        access = coerce_str(self.access)
        return f"""
    /* ibv_reg_mr */
    {mr_name} = ibv_reg_mr({pd_name}, {addr}, {length}, {access});
    if (!{mr_name}) {{
        fprintf(stderr, "Failed to register memory region {mr_name}\\n");
    }}
    
    IF_OK_PTR({mr_name}, {{
        mrs[mrs_size++] = (PR_MR){{
            .id = "{mr_name}",
            .addr = (uint64_t)({mr_name}->addr),
            .length = {length},
            .lkey = {mr_name}->lkey
        }};
        pr_write_client_update_claimed(CLIENT_UPDATE_PATH, qps, qps_size, mrs, mrs_size, prs, prs_size);
    }});
    
"""


class RegMRIova(VerbCall):
    MUTABLE_FIELDS = ["pd", "mr", "buf", "length", "iova", "access"]
    EXPORT_FIELDS = ["pd", "mr", "buf", "length", "iova", "access"]
    CONTRACT = Contract(
        requires=[RequireSpec("pd", State.ALLOCATED, "pd")],
        produces=[ProduceSpec("mr", State.ALLOCATED, "mr")],
        transitions=[],
    )

    def __init__(
        self,
        pd: str = None,
        mr: str = None,
        buf: str = None,
        length: int = None,
        iova: int = None,
        access: str = None,
    ):
        self.pd = ResourceValue(resource_type="pd", value=pd) if pd else ResourceValue(resource_type="pd", value="pd")
        self.mr = ResourceValue(resource_type="mr", value=mr) if mr else ResourceValue(resource_type="mr", value="mr")
        self.buf = ConstantValue(buf or "buf")  # Default buffer variable name
        self.length = IntValue(length or 4096)  # Default length
        self.iova = IntValue(iova or 0)  # Default IOVA
        self.access = FlagValue(access or "IBV_ACCESS_LOCAL_WRITE", flag_type="IBV_ACCESS_FLAGS_ENUM")
        self.tracker = None
        self.required_resources = []
        self.allocated_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.allocated_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the PD and MR addresses in the tracker
            self.tracker.use("pd", self.pd.value)
            self.tracker.create("mr", self.mr.value)
            self.required_resources.append({"type": "pd", "name": self.pd.value, "position": "pd"})
            self.allocated_resources.append(("mr", self.mr.value))  # 记录需要的资源
            # # Register the MR variable in the tracker
            # self.tracker.create('mr_var', mr)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "pd[0]")
        mr = kv.get("mr", "unknown")
        return cls(
            pd=pd,
            mr=mr,
            buf=kv.get("buf", "buf"),
            length=int(kv.get("length", 4096)),
            iova=int(kv.get("iova", 0)),
            access=kv.get("access", "IBV_ACCESS_LOCAL_WRITE"),
            ctx=ctx,
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = self.pd
        mr_name = self.mr
        return f"""
    /* ibv_reg_mr_iova */
    {mr_name} = ibv_reg_mr_iova({pd_name}, {self.buf}, {self.length}, {self.iova}, {self.access});
    if (!{mr_name}) {{
        fprintf(stderr, "Failed to register memory region with IOVA {mr_name}\\n");
    }}
    
    IF_OK_PTR({mr_name}, {{
        mrs[mrs_size++] = (PR_MR){{
            .id = "{mr_name}",
            .addr = (uint64_t)({mr_name}->addr),
            .length = {self.length},
            .lkey = {mr_name}->lkey
        }};
        pr_write_client_update_claimed(CLIENT_UPDATE_PATH, qps, qps_size, mrs, mrs_size, prs, prs_size);
    }});
"""


class ReqNotifyCQ(VerbCall):
    """Request completion notification on a completion queue (CQ)."""

    MUTABLE_FIELDS = ["cq", "solicited_only"]
    EXPORT_FIELDS = ["cq", "solicited_only"]
    CONTRACT = Contract(requires=[RequireSpec("cq", State.ALLOCATED, "cq")], produces=[], transitions=[])

    def __init__(self, cq: str = None, solicited_only: int = None):
        if not cq:
            raise ValueError("CQ name must be provided")
        self.cq = ResourceValue(resource_type="cq", value=cq) if cq else None
        # Default solicited_only value
        self.solicited_only = IntValue(solicited_only or 0)
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the CQ address in the tracker
            self.tracker.use("cq", self.cq.value)
            self.required_resources.append({"type": "cq", "name": self.cq.value, "position": "cq"})  # 记录需要的资源
            # # Register the CQ variable in the tracker
            # self.tracker.create('cq_var', cq)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq = kv.get("cq", "unknown")
        solicited_only = int(kv.get("solicited_only", 0))
        return cls(cq=cq, solicited_only=solicited_only)

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = coerce_str(self.cq)
        return f"""
    /* ibv_req_notify_cq */
    IF_OK_PTR({cq_name}, {{
        if (ibv_req_notify_cq({cq_name}, {self.solicited_only})) {{
        fprintf(stderr, "Failed to request CQ notification {cq_name}\\n");
        }}
    }});

"""


class ReRegMR(VerbCall):
    MUTABLE_FIELDS = ["mr", "flags", "pd", "addr", "length", "access"]
    CONTRACT = Contract(
        requires=[
            RequireSpec("mr", None, "mr", exclude_states=[State.DESTROYED]),
            RequireSpec("pd", State.ALLOCATED, "pd"),
            RequireSpec("buf", None, "addr", exclude_states=[State.DESTROYED]),
        ],
        # produces=[ProduceSpec("mr", State.ALLOCATED, "mr")],
        produces=[],
        transitions=[TransitionSpec("buf", from_state=None, to_state=State.USED, name_attr="addr")],
    )
    """Re-register a memory region (MR) with the specified protection domain (PD)."""

    def __init__(
        self,
        mr: str = None,
        flags: int = None,
        pd: str | None = None,
        addr: str | None = None,
        length: int = 0,
        access: int = 0,
    ):
        self.mr = ResourceValue(resource_type="mr", value=mr) if mr else "NULL"
        self.flags = FlagValue(flags or 0, flag_type="IBV_REREG_MR_FLAGS_ENUM")
        self.pd = ResourceValue(resource_type="pd", value=pd) if pd else "NULL"  # Optional PD
        # Default address variable name
        self.addr = ConstantValue(addr) if addr else "NULL"
        self.length = IntValue(length or 0)  # Default length
        # Default access flags
        self.access = FlagValue(access or 0, flag_type="IBV_ACCESS_FLAGS_ENUM")
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        # if self.tracker:
        #     # Register the MR address in the tracker
        #     self.tracker.use("mr", self.mr.value)
        #     self.required_resources.append({"type": "mr", "name": self.mr.value, "position": "mr"})  # 记录需要的资源
        #     # Register the PD address if specified
        #     if self.pd:
        #         self.tracker.use("pd", self.pd.value)
        #         self.required_resources.append(
        #             {"type": "pd", "name": self.pd.value, "position": "pd"}
        #         )  # 记录需要的资源
        #     # # Register the MR variable in the tracker
        #     # self.tracker.create('mr_var', mr)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        mr = kv.get("mr", "unknown")
        flags = int(kv.get("flags", 0))
        pd = kv.get("pd")
        addr = kv.get("addr")
        length = int(kv.get("length", 0))
        access = int(kv.get("access", 0))
        return cls(mr=mr, flags=flags, pd=pd, addr=addr, length=length, access=access)

    def generate_c(self, ctx: CodeGenContext) -> str:
        mr_name = self.mr
        pd_name = self.pd if self.pd else "NULL"
        addr = self.addr if self.addr else "NULL"
        if pd_name != "NULL":
            return f"""
        /* ibv_rereg_mr */
        IF_OK_PTR({mr_name}, {{
            IF_OK_PTR({pd_name}, {{
                    if (ibv_rereg_mr({mr_name}, {self.flags}, {pd_name}, {addr}, {self.length}, {self.access}) != 0) {{
                    fprintf(stderr, "Failed to re-register MR {mr_name}\\n");
                }}
            }});
        }});
    """
        else:
            return f"""
        /* ibv_rereg_mr */
        IF_OK_PTR({mr_name}, {{
                if (ibv_rereg_mr({mr_name}, {self.flags}, NULL, {addr}, {self.length}, {self.access}) != 0) {{
                fprintf(stderr, "Failed to re-register MR {mr_name}\\n");
            }}
        }});
"""


class ResizeCQ(VerbCall):
    MUTABLE_FIELDS = ["cq", "cqe"]
    EXPORT_FIELDS = ["cq", "cqe"]
    CONTRACT = Contract(
        requires=[RequireSpec("cq", State.ALLOCATED, "cq")],
        produces=[],
        transitions=[],
    )

    """Resize a completion queue (CQ) to a new size."""

    def __init__(self, cq: str = None, cqe: int = None):
        self.cq = ResourceValue(resource_type="cq", value=cq) if cq else ResourceValue(resource_type="cq", value="cq")
        self.cqe = IntValue(cqe or 0)  # Default CQE count

        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the CQ address in the tracker
            self.tracker.use("cq", self.cq.value)
            self.required_resources.append({"type": "cq", "name": self.cq.value, "position": "cq"})  # 记录需要的资源
            # # Register the CQ variable in the tracker
            # self.tracker.create('cq_var', cq)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq = kv.get("cq", "unknown")
        cqe = int(kv.get("cqe", 0))
        return cls(cq=cq, cqe=cqe)

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = self.cq
        return f"""
    /* ibv_resize_cq */
    IF_OK_PTR({cq_name}, {{
        if (ibv_resize_cq({cq_name}, {self.cqe})) {{
        fprintf(stderr, "Failed to resize CQ {cq_name}\\n");
        }}
    }});

"""


class SetECE(VerbCall):
    """
    表示 ibv_set_ece() 调用。
    参数：
        qp    -- QP 资源变量名
        ece_obj    -- IbvECE 对象
        ece_var    -- ece 结构体变量名
    """

    MUTABLE_FIELDS = ["qp", "ece_obj", "ece_var"]
    EXPORT_FIELDS = ["qp", "ece_obj", "ece_var"]
    CONTRACT = Contract(
        requires=[RequireSpec("qp", State.ALLOCATED, "qp")],
        produces=[],
        transitions=[],
    )

    def __init__(self, qp: str = None, ece_obj: "IbvECE" = None, ece_var: str = None):
        self.qp = ResourceValue(resource_type="qp", value=qp) if qp else ResourceValue(resource_type="qp", value="qp")
        self.ece_obj = ece_obj
        # Default variable name for the ECE structure
        self.ece_var = ConstantValue(ece_var or "ece")
        # Default to None, will be set in apply()
        # 记录需要的资源

        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the QP address in the tracker
            self.tracker.use("qp", self.qp.value)
            self.required_resources.append({"type": "qp", "name": self.qp.value, "position": "qp"})  # 记录需要的资源
            # # Register the ECE options variable in the tracker
            # self.tracker.create('ece_var', ece_var)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "qp")
        # 支持 trace 中直接提供 ece_obj 或手动构造
        ece_obj = kv.get("ece_obj", IbvECE.random_mutation())
        ece_var = kv.get("ece_var", "ece")
        return cls(qp, ece_obj, ece_var)

    def generate_c(self, ctx: CodeGenContext) -> str:
        s = ""
        if self.ece_obj is not None:
            s += self.ece_obj.to_cxx(self.ece_var, ctx)
        else:
            s += f"\n    struct ibv_ece {self.ece_var} = {{0}};\n"
        qp_name = str(self.qp)
        s += f"""
    IF_OK_PTR({qp_name}, {{
        if (ibv_set_ece({qp_name}, &{self.ece_var}) != 0) {{
        fprintf(stderr, "ibv_set_ece failed {qp_name}\\n");
        }}
    }});
"""
        return s


class AbortWR(VerbCall):
    """Abort all prepared work requests since wr_start."""

    MUTABLE_FIELDS = ["qp_ex"]
    EXPORT_FIELDS = ["qp_ex"]
    CONTRACT = Contract(
        requires=[RequireSpec("qp_ex", State.ALLOCATED, "qp_ex")],
        produces=[],
        transitions=[],
    )

    def __init__(self, qp_ex: str = None):
        self.qp_ex = (
            ResourceValue(resource_type="qp_ex", value=qp_ex)
            if qp_ex
            else ResourceValue(resource_type="qp_ex", value="qp_ex")
        )
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the QP extension address in the tracker
            self.tracker.use("qp_ex", self.qp_ex.value)
            self.required_resources.append(
                {"type": "qp_ex", "name": self.qp_ex.value, "position": "qp_ex"}
            )  # 记录需要的资源
            # # Register the QP extension variable in the tracker
            # self.tracker.create('qp_ex_var', qp_ex)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        return cls(qp=qp)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_ex_name = self.qp_ex
        return f"""
    /* Abort all work requests */
    struct ibv_qp_ex *{qp_ex_name} = ibv_qp_to_qp_ex({qp_ex_name});
    ibv_wr_abort({qp_ex_name});
"""


class WRComplete(VerbCall):
    MUTABLE_FIELDS = ["qp_ex"]
    EXPORT_FIELDS = ["qp_ex"]
    CONTRACT = Contract(
        requires=[RequireSpec("qp_ex", State.ALLOCATED, "qp_ex")],
        produces=[],
        transitions=[],
    )

    def __init__(self, qp_ex: str):
        self.qp_ex = (
            ResourceValue(resource_type="qp_ex", value=qp_ex)
            if qp_ex
            else ResourceValue(resource_type="qp_ex", value="qp_ex")
        )
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the QP extension address in the tracker
            self.tracker.use("qp_ex", self.qp_ex.value)
            self.required_resources.append(
                {"type": "qp_ex", "name": self.qp_ex.value, "position": "qp_ex"}
            )  # 记录需要的资源
            # # Register the QP extension variable in the tracker
            # self.tracker.create('qp_ex_var', qp_ex)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp_ex = kv.get("qp_ex", "unknown")
        return cls(qp_ex=qp_ex)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_ex_name = self.qp_ex
        return f"""
    /* ibv_wr_complete */
    IF_OK_PTR({qp_ex_name}, {{
        if (ibv_wr_complete({qp_ex_name}) != 0) {{
        fprintf(stderr, "Failed to complete work request {qp_ex_name}\\n");
        }}
    }});

"""


class WrStart(VerbCall):
    MUTABLE_FIELDS = ["qp_ex"]
    CONTRACT = Contract(
        requires=[RequireSpec("qp_ex", State.ALLOCATED, "qp_ex")],
        produces=[],
        transitions=[],
    )

    def __init__(self, qp_ex: str = None):
        self.qp_ex = (
            ResourceValue(resource_type="qp_ex", value=qp_ex)
            if qp_ex
            else ResourceValue(resource_type="qp_ex", value="qp_ex")
        )
        self.tracker = None
        self.required_resources = []

    def apply(self, ctx: CodeGenContext):
        self.required_resources = []
        self.tracker = ctx.tracker if ctx else None
        if self.tracker:
            # Register the QP extension address in the tracker
            self.tracker.use("qp_ex", self.qp_ex.value)
            self.required_resources.append(
                {"type": "qp_ex", "name": self.qp_ex.value, "position": "qp_ex"}
            )  # 记录需要的资源
            # # Register the QP extension variable in the tracker
            # self.tracker.create('qp_ex_var', qp_ex)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp_ex = kv.get("qp_ex", "unknown")
        # Ensure the QP extension is used before generating code
        return cls(qp_ex=qp_ex)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_ex_name = self.qp_ex
        return f"""
    /* ibv_wr_start */
    ibv_wr_start({qp_ex_name});
"""


# Mapping verb -> constructor
VERB_FACTORY = {
    # "ibv_create_qp": CreateQP.from_trace,
    # "ibv_reg_mr": RegMR.from_trace,
    # "ibv_post_send": PostSend.from_trace,
    # "ibv_post_recv": PostRecv.from_trace,
    # "ibv_get_device_list": GetDeviceList.from_trace,
    # "ibv_open_device": OpenDevice.from_trace,
    # "ibv_free_device_list": FreeDeviceList.from_trace,
    # "ibv_query_device": QueryDeviceAttr.from_trace,
    # "ibv_query_port": QueryPortAttr.from_trace,
    # "ibv_query_gid": QueryGID.from_trace,
    # "ibv_alloc_pd": AllocPD.from_trace,
    # "ibv_create_cq": CreateCQ.from_trace,
    # "ibv_modify_qp": ModifyQP.from_trace,
    # # "ibv_modify_qp_rtr": ModifyQPToRTR.from_trace,
    # # "ibv_modify_qp_rts": ModifyQPToRTS.from_trace,
    # "ibv_poll_cq": PollCQ.from_trace,
    # "ibv_destroy_qp": DestroyQP.from_trace,
    # "ibv_dereg_mr": DeregMR.from_trace,
    # "ibv_destroy_cq": DestroyCQ.from_trace,
    # "ibv_dealloc_pd": DeallocPD.from_trace,
    # "ibv_close_device": CloseDevice.from_trace,
}
