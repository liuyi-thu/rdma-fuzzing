# -*- coding: utf-8 -*-
# 语义说明：
# rdma_create_srq 用于在指定的 rdma_cm_id 上创建一个共享接收队列（SRQ），并与给定的 PD 关联。
# 调用成功后，SRQ 会绑定到 cm_id（通常通过 id->srq 访问）。该 SRQ 可供后续创建的 QP 共享以接收数据。
# 该插件对该 CM API 进行建模，生成对应的 C 代码序列，并在资源图中产出一个 srq 资源。

"""
Plugin: RDMA CM - rdma_create_srq
本插件将 RDMA CM API rdma_create_srq 抽象为一个 VerbCall 子类，
用于由 Python 端生成对应的 C 调用代码以及维护资源与状态机契约信息。

函数原型：
int rdma_create_srq(struct rdma_cm_id *id, struct ibv_pd *pd, struct ibv_srq_init_attr *attr);

语义要点：
- 在指定的 rdma_cm_id 上创建 SRQ，关联到传入的 PD。
- 成功返回 0，失败返回负值或错误码；成功后 cm_id->srq 指向新创建的 SRQ。
- 后续使用该 SRQ 可在多个 QP 间共享接收队列。

使用约束（建模）：
- 需要 cm_id 和 pd 已分配（ALLOCATED）。
- 产出 srq 资源，状态为 ALLOCATED。
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, RequireSpec, State, TransitionSpec
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class IbvSRQInitAttr:
    """
    轻量封装 ibv_srq_init_attr，用于生成 C 端结构体初始化代码。
    字段说明（常用子集）：
      - max_wr: SRQ 最大可挂载的 WR 数（attr.max_wr）
      - max_sge: 每个 WR 可包含的最大 SGE 数（attr.max_sge）
      - srq_limit: SRQ 的通知阈值（attr.srq_limit），可选
      - srq_context_ptr: SRQ 上下文指针（srq_context），可选；默认使用 cm_id 作为上下文
    """

    def __init__(self, max_wr: int = 32, max_sge: int = 1, srq_limit: int = 0, srq_context_ptr: str = None):
        self.max_wr = max_wr
        self.max_sge = max_sge
        self.srq_limit = srq_limit
        self.srq_context_ptr = srq_context_ptr  # C 代码中的指针表达式字符串，如 "(void*)id"

    def to_cxx(self, var_name: str, ctx: CodeGenContext, cm_id_expr: str = None) -> str:
        """
        生成 ibv_srq_init_attr 的 C 初始化代码。
        var_name: 目标 C 变量名
        cm_id_expr: 可选，作为默认 srq_context
        """
        srq_ctx_expr = self.srq_context_ptr or (("(void*)" + str(cm_id_expr)) if cm_id_expr else "NULL")

        code = []
        code.append(f"struct ibv_srq_init_attr {var_name};")
        code.append(f"memset(&{var_name}, 0, sizeof({var_name}));")
        code.append(f"{var_name}.srq_context = {srq_ctx_expr};")
        code.append(f"{var_name}.attr.max_wr = {int(self.max_wr)};")
        code.append(f"{var_name}.attr.max_sge = {int(self.max_sge)};")
        code.append(f"{var_name}.attr.srq_limit = {int(self.srq_limit)};")
        # 保留 srq_type 的默认值（0 或 IBV_SRQT_BASIC），不同平台定义差异较大，这里不主动设置。
        return "\n        ".join(code)


class RdmaCreateSRQ(VerbCall):
    """
    建模 rdma_create_srq 的调用节点。
    """

    MUTABLE_FIELDS = ["id", "pd", "srq", "init_attr_obj"]

    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
            RequireSpec(rtype="pd", state=State.ALLOCATED, name_attr="pd"),
        ],
        produces=[
            ProduceSpec(rtype="srq", state=State.ALLOCATED, name_attr="srq", metadata_fields=["pd", "id"]),
        ],
        transitions=[
            # 创建 SRQ 后，cm_id 仍可继续使用；视框架策略，也可标注为 USED。
            TransitionSpec(rtype="cm_id", from_state=State.ALLOCATED, to_state=State.USED, name_attr="id"),
        ],
    )

    def __init__(self, id: str = None, pd: str = None, srq: str = None, init_attr_obj: IbvSRQInitAttr = None):
        if not id:
            raise ValueError("id (cm_id) must be provided for RdmaCreateSRQ")
        if not pd:
            raise ValueError("pd must be provided for RdmaCreateSRQ")
        if not srq:
            raise ValueError("srq must be provided for RdmaCreateSRQ")

        # 资源包装
        self.id = ResourceValue(resource_type="cm_id", value=id)
        self.pd = ResourceValue(resource_type="pd", value=pd)
        self.srq = ResourceValue(resource_type="srq", value=srq, mutable=False)

        # SRQ 初始化属性（可选），默认会使用一个保守配置
        self.init_attr_obj = init_attr_obj

    def apply(self, ctx: CodeGenContext):
        # 注册生成的 SRQ 变量
        ctx.alloc_variable(str(self.srq), "struct ibv_srq *", "NULL")

        # 应用契约（状态与资源生产）
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT)

    def _default_attr(self) -> IbvSRQInitAttr:
        # 提供一个相对保守且多平台兼容的默认配置
        return IbvSRQInitAttr(max_wr=32, max_sge=1, srq_limit=0)

    def generate_c(self, ctx: CodeGenContext) -> str:
        srq_name = str(self.srq)
        id_name = str(self.id)
        pd_name = str(self.pd)

        # 生成属性变量名（带后缀避免冲突）
        attr_suffix = "_" + srq_name.replace("srq[", "").replace("]", "")
        attr_name = f"srq_attr_init{attr_suffix}"

        # 生成 attr 初始化代码
        if self.init_attr_obj is not None:
            attr_code = self.init_attr_obj.to_cxx(attr_name, ctx, cm_id_expr=id_name)
        else:
            default_attr = self._default_attr()
            attr_code = default_attr.to_cxx(attr_name, ctx, cm_id_expr=id_name)

        # 生成 C 调用代码
        return f"""
    /* rdma_create_srq */
    IF_OK_PTR({id_name}, {{
        IF_OK_PTR({pd_name}, {{
            {attr_code}
            int ret_create_srq = rdma_create_srq({id_name}, {pd_name}, &{attr_name});
            if (ret_create_srq) {{
                fprintf(stderr, "Failed to rdma_create_srq on id=%p, pd=%p: %d\\n", (void*){id_name}, (void*){pd_name}, ret_create_srq);
            }} else {{
                {srq_name} = {id_name}->srq;
                if (!{srq_name}) {{
                    fprintf(stderr, "rdma_create_srq succeeded but id->srq is NULL (unexpected)\\n");
                }}
            }}
        }});
    }});
"""
