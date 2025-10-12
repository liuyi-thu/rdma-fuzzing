# Plugin modeling rdma_destroy_ep: destroys an rdma_cm_id and any QP created on that ID.
# Semantics:
# - Input: a valid rdma_cm_id pointer.
# - Action: rdma_destroy_ep(id) deallocates the cm_id and destroys any associated QP.
# - Post: The cm_id becomes invalid. Any QP created on this id is also destroyed by the provider.
# Notes:
# - This class models the teardown of a CM ID. It transitions the cm_id resource to DESTROYED.
# - Associated QP teardown is implicit at the provider; frameworks may optionally track and
#   update QP state elsewhere if bindings are available.

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import ResourceValue
from lib.verbs import VerbCall


class RdmaDestroyEp(VerbCall):
    """
    Model for rdma_destroy_ep(struct rdma_cm_id *id).

    This call deallocates the specified rdma_cm_id and destroys any QP created on that id.

    Constructor parameters:
    - id: Name of the cm_id resource to destroy (must refer to an existing cm_id resource).

    Contract:
    - Requires: cm_id is in ALLOCATED (or otherwise valid/active) state.
    - Transitions: cm_id -> DESTROYED.
      Note: QP destruction is implicit; if test harness tracks a binding from cm_id to qp,
      it may update qp state separately.
    """

    MUTABLE_FIELDS = ["id"]

    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
        ],
        produces=[],
        transitions=[
            TransitionSpec(rtype="cm_id", from_state=State.ALLOCATED, to_state=State.DESTROYED, name_attr="id"),
        ],
    )

    def __init__(self, id: str):
        if not id:
            raise ValueError("id must be provided for RdmaDestroyEp")
        # cm_id to destroy
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

    def apply(self, ctx: CodeGenContext):
        self.context = ctx
        # If the framework tracks contracts, apply them
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT)

        # Optionally, the framework could clear internal bindings here
        # e.g., if ctx has something like ctx.clear_cm_id_bindings(str(self.id))
        # We avoid making assumptions about ctx's API.

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)
        return f"""
    /* rdma_destroy_ep */
    IF_OK_PTR({id_name}, {{
        rdma_destroy_ep({id_name});
        {id_name} = NULL; /* mark as invalid after destroy */
    }});
"""
