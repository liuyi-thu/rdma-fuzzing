# RDMA CM rdma_disconnect plugin
# This plugin models the RDMA CM API rdma_disconnect, which disconnects an RDMA connection
# for a given rdma_cm_id. Semantics:
# - Transitions the CM ID from CONNECTED to DISCONNECTED.
# - Transitions any associated QP to the error state (handled by CM automatically).
# - Returns 0 on success or a negative errno on failure.
#
# This model captures the state transition of the CM ID and generates corresponding C code
# to invoke rdma_disconnect on the provided CM ID pointer.

"""
Plugin file that models the RDMA CM API rdma_disconnect as a VerbCall-derived class.

It provides:
- Contract definitions expressing preconditions and state transitions.
- C code generation for invoking rdma_disconnect(id).
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class RDMADisconnect(VerbCall):
    """
    Model for rdma_disconnect(struct rdma_cm_id *id).

    Usage:
        RDMADisconnect(id="cm0")

    Contract:
        - Requires the provided cm_id to be in CONNECTED state.
        - Transitions cm_id from CONNECTED to DISCONNECTED after the call.
        - The underlying RDMA CM will move any associated QP to ERROR state implicitly.
          (We don't explicitly produce/transition a QP here to avoid tight coupling;
           test orchestration may update the QP state if it tracks cm_id->qp bindings.)
    """

    # Fields that might be referenced or mutated by the framework; kept minimal.
    MUTABLE_FIELDS = ["id"]

    # Contract expressing rdma_disconnect semantics.
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.CONNECTED, name_attr="id"),
        ],
        produces=[
            # No new resources produced by rdma_disconnect.
        ],
        transitions=[
            TransitionSpec(
                rtype="cm_id", from_state=State.CONNECTED, to_state=State.DISCONNECTED, name_attr="id"
            ),  # 相当于禁止了复用 cm_id; TODO: 其实可以允许复用的
            # Note: The CM transitions any associated QP to ERROR. If your framework tracks
            # cm_id -> qp binding, it can add a corresponding transition externally.
            # Example (if supported by your State enum and binding path resolution):
            # TransitionSpec(rtype="qp", from_state=State.RTS, to_state=State.ERROR, name_attr="id.qp"),
            # TODO: 我们还没有建模 cm_id -> qp 的绑定关系
        ],
    )

    def __init__(self, id: str = None):
        """
        Initialize the rdma_disconnect verb call.

        Args:
            id: Name of the rdma_cm_id resource to disconnect.
        """
        if not id:
            raise ValueError("id must be provided for RDMADisconnect")
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)
        self.context = None

    def apply(self, ctx: CodeGenContext):
        """
        Apply any side-effect bindings and enforce contract in the orchestration context.
        """
        self.context = ctx
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext):
        """
        Generate C code that performs rdma_disconnect on the given cm_id.

        Returns:
            A C code snippet as a string.
        """
        id_name = str(self.id)

        return f"""
    /* rdma_disconnect */
    IF_OK_PTR({id_name}, {{
        int ret = rdma_disconnect({id_name});
        if (ret) {{
            fprintf(stderr, "rdma_disconnect({id_name}) failed: ret=%d errno=%s\\n",
                    ret, strerror(ret < 0 ? -ret : ret));
        }} else {{
            // rdma_disconnect succeeded; CM ID is now DISCONNECTED.
            // Any associated QP has transitioned to the ERROR state per CM semantics.
        }}
    }});
"""
