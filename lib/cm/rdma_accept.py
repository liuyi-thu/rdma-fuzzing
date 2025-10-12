# -*- coding: utf-8 -*-
# 本插件对 RDMA CM API 的 rdma_accept 进行建模。
# 语义与用途：
# - 该调用在监听端接收到连接请求事件（RDMA_CM_EVENT_CONNECT_REQUEST）后，
#   针对事件中携带的“新” rdma_cm_id 调用，用于接受该连接请求。
# - conn_param 可选，用于覆盖默认连接参数并携带私有数据。
# - 成功返回 0，失败返回 -1 并设置 errno。
# 注意：与 socket 的 accept 不同，rdma_accept 并非对“监听的” id 调用，而是对事件中新建的 id 调用。

from typing import Any, Optional

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaAccept(VerbCall):
    """
    建模 rdma_accept:
        int rdma_accept(struct rdma_cm_id *id, struct rdma_conn_param *conn_param);

    典型时序：
      - 监听端调用 rdma_listen。
      - 通过 rdma_get_cm_event 收到 RDMA_CM_EVENT_CONNECT_REQUEST，事件携带一个“新”的 id。
      - 对该“新” id 调用 rdma_accept(id, conn_param)。

    建模约束（保守）：
      - 需要一个已分配的 cm_id（通常来自 CONNECT_REQUEST 事件）。
      - 调用后将 cm_id 状态从 ALLOCATED 迁移到 USED（抽象为已进行接受流程）。
      - conn_param 为可选对象；若提供，需能生成 C 侧的 struct rdma_conn_param。
    """

    MUTABLE_FIELDS = ["id", "conn_param_obj"]

    CONTRACT = Contract(
        requires=[
            # 要求：id 存在且处于已分配态（具体事件态在更细粒度模型中区分）
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
        ],
        produces=[
            # 不新建资源，仅改变 cm_id 的状态
        ],
        transitions=[
            # 抽象地从 ALLOCATED -> USED，表示已发起接受流程（后续连接建立由事件驱动）
            TransitionSpec(rtype="cm_id", from_state=State.ALLOCATED, to_state=State.USED, name_attr="id"),
        ],
    )

    def __init__(self, id: str, conn_param_obj: Optional[Any] = None):
        """
        参数:
          - id: 必填，事件中新建出来的 rdma_cm_id 的变量名。
          - conn_param_obj: 可选。应当是能提供 to_cxx(var_name, ctx) 方法的对象，
                            以在 C 侧生成并初始化 struct rdma_conn_param。
                            若为 None，则传递 NULL。
        """
        if not id:
            raise ValueError("id (cm_id variable name) must be provided for RdmaAccept")
        # cm_id 是受资源跟踪的对象
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)
        # 连接参数对象（非资源，仅用于生成 C 结构体）
        self.conn_param_obj = conn_param_obj

    def apply(self, ctx: CodeGenContext):
        # 存档上下文，以便 generate_c 使用上下文工具（若需要）
        self.context = ctx

        # 应用合约（资源状态检查与迁移）
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)

        # 为 conn_param 生成本地变量名（若提供）
        suffix = "_" + id_name.replace("[", "_").replace("]", "_")
        param_name = f"conn_param{suffix}"
        code_param = ""
        param_ptr_expr = "NULL"

        if self.conn_param_obj is not None:
            # 期望 conn_param_obj 提供 to_cxx(var_name, ctx)，生成形如：
            #   struct rdma_conn_param <var>;
            #   <var>.<fields> = ...;
            code_param = self.conn_param_obj.to_cxx(param_name, ctx)
            param_ptr_expr = f"&{param_name}"

        return f"""
    /* rdma_accept */
    IF_OK_PTR({id_name}, {{
        {code_param}
        int __rc_accept = rdma_accept({id_name}, {param_ptr_expr});
        if (__rc_accept) {{
            fprintf(stderr, "rdma_accept failed on {id_name}: %s\\n", strerror(errno));
        }}
    }});
"""
