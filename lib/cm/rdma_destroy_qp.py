# RDMA CM API modeling: rdma_destroy_qp
# 语义与用途：
# - rdma_destroy_qp 会销毁此前通过 rdma_create_qp 绑定到 rdma_cm_id 的 QP。
# - 应在 rdma_destroy_id 之前调用，以确保与该 ID 关联的 QP 已被释放。
# - 注意：不需要、也不应再显式调用 ibv_destroy_qp；该 API 会处理 QP 的释放。

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class RDMADestroyQP(VerbCall):
    """
    封装 rdma_destroy_qp(struct rdma_cm_id *id) 的语义模型。
    - 销毁与指定 rdma_cm_id 关联的 QP。
    - 合约层面：需要一个已分配的 cm_id，以及一个当前存在的 qp 资源；调用后使该 qp 转换为 FREED。
    - 重要：此 API 为 CM 侧销毁操作，不需要额外调用 ibv_destroy_qp。
    """

    MUTABLE_FIELDS = ["id", "qp"]

    CONTRACT = Contract(
        requires=[
            # 需要一个有效的 rdma_cm_id（已分配）
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
            # QP 已存在；在框架里，QP 初始通常为 RESET 状态（CreateQP 产出为 RESET）
            # 若框架将修改后的 QP 统一映射为 USED，也可在后续扩展此处合约
            # RequireSpec(rtype="qp", state=State.RESET, name_attr="qp"),
        ],
        produces=[
            # 不产出新资源
        ],
        transitions=[
            # QP 被销毁
            # TransitionSpec(rtype="qp", from_state=State.RESET, to_state=State.FREED, name_attr="qp"),
        ],
    )

    def __init__(self, id: str = None):
        # rdma_cm_id*，允许为 NULL（以便生成负路径/健壮性测试）
        self.id = ResourceValue(resource_type="cm_id", value=id) if id else "NULL"

        # QP 是框架中跟踪/转换状态所必需的，否则无法在状态机上标记为 FREED
        # if not qp:
        #     raise ValueError("qp must be provided for RDMADestroyQP")
        # self.qp = ResourceValue(resource_type="qp", value=qp, mutable=False)

    def apply(self, ctx: CodeGenContext):
        # 存储上下文，用于可能的绑定清理或变量分配
        self.context = ctx

        # 应用合约（状态需求与转换）
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext):
        id_name = self.id
        # qp_name = str(self.qp)

        return f"""
    /* rdma_destroy_qp */
    IF_OK_PTR({id_name}, {{
        // 通过 CM 销毁 QP，不需要显式 ibv_destroy_qp
        rdma_destroy_qp({id_name});
    }});
"""
