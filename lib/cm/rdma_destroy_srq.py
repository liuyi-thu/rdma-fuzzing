# rdma_destroy_srq plugin
# Semantics: rdma_destroy_srq() destroys the shared receive queue (SRQ) associated with a given rdma_cm_id.
# Usage: Call after rdma_create_srq() on the same rdma_cm_id and ensure no outstanding Work Requests and no QPs still attached to the SRQ.
# On success, the SRQ becomes invalid and must not be used. Returns 0 on success or a negative errno on failure.

"""
Python plugin that models the RDMA CM API rdma_destroy_srq, abstracted as a VerbCall-derived class.

This class encapsulates the operation of destroying an SRQ associated with an rdma_cm_id. It enforces
simple preconditions via the contract system and generates corresponding C code to invoke rdma_destroy_srq(id).

Key points:
- Requires the cm_id to be allocated.
- Optionally models an SRQ resource; if provided, transitions it from ALLOCATED to FREED.
- Generates C code calling rdma_destroy_srq(id) and, if an SRQ variable is tracked, sets it to NULL on success.
"""

from typing import Optional

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class DestroySRQ(VerbCall):
    """
    Model for rdma_destroy_srq(struct rdma_cm_id *id)

    Parameters:
    - id: name of the rdma_cm_id resource (required).
    - srq: optional name of the SRQ resource tracked by the framework. If provided, the contract
           will enforce its ALLOCATED state and transition it to FREED upon successful destroy.

    Contract semantics:
    - Requires:
        * cm_id in ALLOCATED state.
        * srq in ALLOCATED state (only if srq is provided).
    - Transitions:
        * srq ALLOCATED -> FREED (only if srq is provided).
    """

    MUTABLE_FIELDS = ["id", "srq"]

    def __init__(self, id: str, srq: Optional[str] = None):
        if not id:
            raise ValueError("id must be provided for DestroySRQ")
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)
        self.srq = ResourceValue(resource_type="srq", value=srq, mutable=True) if srq else None
        self.context: Optional[CodeGenContext] = None

    def _contract(self) -> Contract:
        requires = [
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
        ]
        transitions = []
        if self.srq is not None:
            requires.append(RequireSpec(rtype="srq", state=State.ALLOCATED, name_attr="srq"))
            transitions.append(
                TransitionSpec(rtype="srq", from_state=State.ALLOCATED, to_state=State.FREED, name_attr="srq")
            )

        return Contract(
            requires=requires,
            produces=[],
            transitions=transitions,
        )

    def apply(self, ctx: CodeGenContext):
        self.context = ctx
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)
        srq_stmt = ""
        if self.srq is not None:
            srq_name = str(self.srq)
            srq_stmt = f"""
        /* Mark local SRQ pointer as invalid after successful destroy */
        {srq_name} = NULL;"""

        return f"""
    /* rdma_destroy_srq */
    IF_OK_PTR({id_name}, {{
        int ret = rdma_destroy_srq({id_name});
        if (ret) {{
            fprintf(stderr, "rdma_destroy_srq failed for id=%s: %d (%s)\\n", "{id_name}", ret, strerror(-ret));
        }} else {{{srq_stmt}
        }}
    }});
"""
