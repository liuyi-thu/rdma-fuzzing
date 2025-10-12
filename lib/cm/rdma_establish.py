# rdma_establish CM API modeling plugin
# 语义与用途:
# - rdma_establish 用于主动方在接收到连接响应事件后完成连接的建立过程（同时对该响应事件进行确认/ack）。
# - 只能在尚未为 rdma_cm_id 创建 QP 的情况下使用；调用后会在被动方触发 RDMA_CM_EVENT_ESTABLISHED 事件。
# - 典型流程：rdma_connect -> rdma_get_cm_event (CONNECT_RESPONSE) -> rdma_establish -> 后续建立完成。
# 参见相关 API：rdma_connect, rdma_disconnect, rdma_get_cm_event

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaEstablish(VerbCall):
    """
    Model for rdma_establish(struct rdma_cm_id *id)

    Description:
        Complete an active connection request after receiving a connection response event.
        This acknowledges the incoming connect response and finalizes the connection
        establishment. On success, the passive side will receive a connection established event.

    Notes:
        - Should ONLY be used when no QP has been created on the rdma_cm_id.
        - Typically invoked by the active side after receiving a connect response event from
          rdma_get_cm_event.
        - Using this on an rdma_cm_id that already has a QP is invalid.

    See also:
        rdma_connect, rdma_disconnect, rdma_get_cm_event
    """

    MUTABLE_FIELDS = ["id"]

    # Contract rationale:
    # - Requires: a valid cm_id pointer that has been allocated (e.g., via rdma_create_id)
    #   and has progressed far enough in the connect workflow to have received a connect
    #   response (this framework approximates with ALLOCATED as a generic pre-run check).
    # - Transition: move cm_id into a "used/established" state to reflect connection completed.
    #   (We use State.USED here as a generic "established/ready" marker.)
    # - We DO NOT create any new resources; rdma_establish only finalizes the connection.
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
            # Optionally, a response event would have been received before calling establish.
            # If the framework models cm_event explicitly, uncomment the following line:
            # RequireSpec(rtype="cm_event", state=State.RECEIVED, name_attr="id"),
        ],
        produces=[],
        transitions=[
            TransitionSpec(rtype="cm_id", from_state=State.ALLOCATED, to_state=State.USED, name_attr="id"),
        ],
    )

    def __init__(self, id: str):
        if not id:
            raise ValueError("id (rdma_cm_id variable name) must be provided for RdmaEstablish")
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

    def apply(self, ctx: CodeGenContext):
        # Apply the contract for bookkeeping in the fuzzing framework
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)
        return f"""
    /* rdma_establish: Complete active connection after receiving connect response.
     * Notes:
     *  - Must be invoked on an rdma_cm_id that does NOT have a QP created.
     *  - Typically called after rdma_get_cm_event() returns CONNECT_RESPONSE for the active side.
     *  - On success, the passive side will get RDMA_CM_EVENT_ESTABLISHED.
     */
    IF_OK_PTR({id_name}, {{
        int rc = rdma_establish({id_name});
        if (rc) {{
            fprintf(stderr, "rdma_establish({id_name}) failed: rc=%d, errno=%d (%s)\\n", rc, errno, strerror(errno));
        }} else {{
            fprintf(stderr, "rdma_establish({id_name}) succeeded (connection finalized)\\n");
        }}
    }});
"""
