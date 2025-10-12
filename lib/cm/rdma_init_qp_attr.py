# -*- coding: utf-8 -*-
# 语义说明：
# rdma_init_qp_attr 用于基于 rdma_cm_id 中的已解析路由/连接上下文，生成一份 ibv_qp_attr 及其掩码 qp_attr_mask。
# 这些信息通常用于后续调用 ibv_modify_qp 将 QP 迁移到合适的状态（如 RTR/RTS）或完成连接建立/接受的必要配置。
# 该调用不创建或销毁任何资源，仅产生可供后续步骤使用的属性数据。

from typing import Optional

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State
from lib.value import ResourceValue
from lib.verbs import VerbCall


class RdmaInitQPAttr(VerbCall):
    """
    对 rdma_cm API: rdma_init_qp_attr 的建模。

    原型:
        int rdma_init_qp_attr(struct rdma_cm_id *id,
                              struct ibv_qp_attr *qp_attr,
                              int *qp_attr_mask);

    作用:
        - 基于指定的 rdma_cm_id，填充一份 ibv_qp_attr 以及对应的掩码 qp_attr_mask。
        - 常用于根据 CM 路由/连接信息准备后续 ibv_modify_qp 所需的参数。

    约束/副作用:
        - 不创建/销毁资源，也不改变 cm_id 的生命周期状态，仅依赖其为有效状态（通常需要地址/路由已解析或收到连接请求）。
    """

    MUTABLE_FIELDS = ["id", "qp_attr_var", "qp_attr_mask_var"]

    CONTRACT = Contract(
        requires=[
            # cm_id 至少需要处于“已分配/有效”的状态；更严格的状态（如 ROUTE_RESOLVED/CONNECTED）由上层场景保证
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
        ],
        produces=[],
        transitions=[],
    )

    def __init__(
        self,
        id: str,
        qp_attr_var: Optional[str] = None,
        qp_attr_mask_var: Optional[str] = None,
    ):
        """
        参数:
            id: cm_id 资源名称（必须）。
            qp_attr_var: 生成的 ibv_qp_attr 变量名；若未提供则基于 id 自动生成。
            qp_attr_mask_var: 生成的掩码变量名；若未提供则基于 id 自动生成。
        """
        if not id:
            raise ValueError("id (cm_id) must be provided for RdmaInitQPAttr")

        self.id = ResourceValue(resource_type="cm_id", value=id)
        self.qp_attr_var = qp_attr_var  # 在 generate_c 中按需推导
        self.qp_attr_mask_var = qp_attr_mask_var  # 在 generate_c 中按需推导

    def apply(self, ctx: CodeGenContext):
        # 保存上下文（若后续需要在代码生成阶段引用）
        self.context = ctx
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else None)

    def _derive_names(self):
        # 基于 cm_id 名称派生出稳定的局部变量名
        id_name = str(self.id)
        safe_suffix = id_name.replace("[", "_").replace("]", "").replace(".", "_")
        attr_name = self.qp_attr_var or f"qp_attr_{safe_suffix}"
        mask_name = self.qp_attr_mask_var or f"qp_attr_mask_{safe_suffix}"
        return id_name, attr_name, mask_name

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name, attr_name, mask_name = self._derive_names()

        # 在上下文中声明需要的局部变量
        ctx.alloc_variable(attr_name, "struct ibv_qp_attr")
        ctx.alloc_variable(mask_name, "int", "0")

        code = f"""
    /* rdma_init_qp_attr */
    IF_OK_PTR({id_name}, {{
        int rc_rdma_init_qp_attr = rdma_init_qp_attr({id_name}, &{attr_name}, &{mask_name});
        if (rc_rdma_init_qp_attr) {{
            fprintf(stderr, "rdma_init_qp_attr({id_name}) failed: %d\\n", rc_rdma_init_qp_attr);
        }} else {{
            /* Successfully initialized QP attributes into {attr_name}, mask in {mask_name} */
        }}
    }});
"""
        return code
