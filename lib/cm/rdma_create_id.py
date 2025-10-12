# RDMA CM: rdma_create_id
# 语义与用途：
# - rdma_create_id 用于分配一个 RDMA 通信标识符（rdma_cm_id），其概念上相当于用于 RDMA 的“socket”。
# - 该 id 上产生的所有通信事件会通过关联的 rdma_event_channel 报告（用户通常通过 rdma_create_event_channel 创建 channel）。
# - 成功后需在合适时机调用 rdma_destroy_id 释放。
# - 该调用需要选择 RDMA 端口空间（ps），常见为 RDMA_PS_TCP、RDMA_PS_IB 等。
#
# 本插件对该 CM API 进行建模，提供类 RdmaCreateId 以用于 fuzz 框架：
# - 资源与状态建模：要求 event_channel 已分配，产出 cm_id 处于 ALLOCATED 状态。
# - 支持上下文（void *context）与端口空间（enum rdma_port_space）参数的设置或突变。
# - 生成对应的 C 代码进行实际调用，并在 CodeGenContext 中注册变量。

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, RequireSpec, State
from lib.value import (
    ConstantValue,
    EnumValue,
    OptionalValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaCreateId(VerbCall):
    """
    模型 rdma_create_id:
        int rdma_create_id(struct rdma_event_channel *channel,
                           struct rdma_cm_id **id, void *context,
                           enum rdma_port_space ps);

    - channel: 事件通道，rdma_cm_id 上的事件将报告到该通道。
    - id: 输出参数，返回已分配的 rdma_cm_id。
    - context: 用户指定的上下文指针（void*），框架可传入 NULL 或任意常量指针值。
    - ps: 端口空间（enum rdma_port_space），如 RDMA_PS_TCP / RDMA_PS_IB 等。

    合约（Contract）：
    - requires:
        * cm_event_channel in ALLOCATED（需要已有事件通道）
    - produces:
        * cm_id in ALLOCATED（创建成功后，cm_id 进入已分配状态）
    - transitions: 无

    代码生成：
    - 在 CodeGenContext 中为 cm_id 分配变量：struct rdma_cm_id *<id> = NULL
    - 生成调用 rdma_create_id(channel, &id, context, ps) 的 C 代码，并输出错误信息。
    """

    MUTABLE_FIELDS = ["channel", "context", "ps"]
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_event_channel", state=State.ALLOCATED, name_attr="channel"),
        ],
        produces=[
            ProduceSpec(
                rtype="cm_id",
                state=State.ALLOCATED,
                name_attr="id",
                metadata_fields=["channel", "ps", "context"],
            ),
        ],
        transitions=[
            # rdma_create_id 不改变其他资源的状态
        ],
    )

    def __init__(self, channel: str = None, id: str = None, context: str = None, ps: str = "RDMA_PS_TCP"):
        # 事件通道（可为 NULL 以进行边界场景 fuzz）
        self.channel = ResourceValue(resource_type="cm_event_channel", value=channel) if channel else "NULL"

        # cm_id 必须指定变量名（资源名）
        if not id:
            raise ValueError("id must be provided for RdmaCreateId")
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

        # 用户上下文指针，可选；默认 NULL
        self.context_ptr = OptionalValue(ConstantValue(context)) if context else ConstantValue("NULL")

        # 端口空间枚举，默认 RDMA_PS_TCP
        self.ps = (
            EnumValue(enum_type="rdma_port_space", value=ps)
            if ps
            else EnumValue(enum_type="rdma_port_space", value="RDMA_PS_TCP")
        )

    def apply(self, ctx: CodeGenContext):
        # 在上下文中声明 rdma_cm_id 指针变量
        ctx.alloc_variable(str(self.id), "struct rdma_cm_id *", "NULL")

        # 合约应用（资源状态变更）
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext):
        channel_expr = str(self.channel)
        id_name = str(self.id)
        context_expr = str(self.context_ptr)
        ps_expr = str(self.ps)

        # 这是一种很巧妙的方法，用于规避重复定义的问题
        return f"""
    /* rdma_create_id */
    {{
        int ret_create_id = rdma_create_id({channel_expr}, &{id_name}, {context_expr}, {ps_expr});
        if (ret_create_id) {{
            fprintf(stderr, "rdma_create_id failed (id={id_name}, ps={ps_expr}): %d\\n", ret_create_id);
        }}
    }}
"""
