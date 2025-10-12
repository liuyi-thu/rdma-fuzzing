# RDMA CM API modeling plugin for rdma_destroy_id.
# Semantics:
# - rdma_destroy_id releases a given rdma_cm_id and cancels any outstanding async operations.
# - Users must destroy any QP associated with the rdma_cm_id and must have acked all related CM events before calling.
# - After successful destruction, the cm_id pointer becomes invalid and should not be reused.

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class DestroyCmId(VerbCall):
    """
    Model for rdma_destroy_id(struct rdma_cm_id *id)

    Behavior:
      - Destroys the specified rdma_cm_id and cancels any outstanding async operations.
      - On success, the identifier is released; subsequent use is invalid.

    Preconditions (semantic expectations for the fuzzer):
      - Any QP associated with this rdma_cm_id must have been destroyed (rdma_destroy_qp).
      - All related CM events must have been acknowledged (rdma_ack_cm_event).

    Contract:
      - Requires the cm_id to be in an ALLOCATED/owned state.
      - Transitions the cm_id to FREED after destruction.
    """

    MUTABLE_FIELDS = ["id"]

    CONTRACT = Contract(
        requires=[
            # The cm_id must exist and be owned/allocated by us.
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
            # Note: Semantic preconditions (QP destroyed and events acked) are documented,
            # but enforced by the scenario generator; they are not hard-checked here.
        ],
        produces=[],
        transitions=[
            TransitionSpec(rtype="cm_id", from_state=State.ALLOCATED, to_state=State.FREED, name_attr="id"),
        ],
    )

    def __init__(self, id: str):
        if not id:
            raise ValueError("id must be provided for DestroyCmId")
        # cm_id resource handle to be destroyed
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

    def apply(self, ctx: CodeGenContext):
        self.context = ctx
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)

        return f"""
    /* rdma_destroy_id: release CM ID and cancel outstanding async operations.
       Precondition (semantic):
         - Associated QP must have been destroyed.
         - Related CM events must have been acked.
    */
    IF_OK_PTR({id_name}, {{
        int __ret_destroy_id = rdma_destroy_id({id_name});
        if (__ret_destroy_id) {{
            fprintf(stderr, "rdma_destroy_id({id_name}) failed: %d\\n", __ret_destroy_id);
        }} else {{
            {id_name} = NULL; /* Invalidate handle after destruction */
        }}
    }});
"""
