# RDMA CM API modeling plugin: rdma_leave_multicast
# This plugin models the rdma_leave_multicast CM API, which leaves a multicast group
# for a given rdma_cm_id and detaches any associated QP from that group. If called
# before a join completes, it cancels the pending join. Note that completions from
# the multicast group may still be queued immediately after leaving. Destroying
# an rdma_cm_id will automatically leave all multicast groups.

from typing import Optional

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, InstantiatedContract, RequireSpec, State
from lib.value import (
    LocalResourceValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaLeaveMulticast(VerbCall):
    """
    VerbCall wrapper for rdma_leave_multicast(id, addr).

    Semantics:
    - Leaves a multicast group identified by 'addr' for the given rdma_cm_id 'id'.
    - Detaches any associated QP from that multicast group.
    - If invoked before the join completes, this cancels the pending join.
    - Completions from the multicast group may still be queued immediately after leaving.
    - Destroying the rdma_cm_id will implicitly leave any joined multicast groups.

    Arguments:
    - id: Name of a rdma_cm_id resource in the framework (Resource type: "cm_id").
    - addr: Name of a sockaddr resource (Resource type: "sockaddr") identifying the multicast group.

    Contract:
    - Requires:
        * cm_id in ALLOCATED (or a compatible state indicating a valid rdma_cm_id).
        * sockaddr in ALLOCATED (a valid multicast address to leave).
    - Produces: None.
    - Transitions: None (membership bookkeeping is left to higher-level orchestration;
      join/leave tracking may be handled by separate plugins/resources).
    """

    MUTABLE_FIELDS = ["id", "addr"]

    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
            RequireSpec(rtype="sockaddr", state=State.ALLOCATED, name_attr="addr"),
        ],
        produces=[],
        transitions=[],
    )

    def __init__(self, id: str, addr: str):
        if not id:
            raise ValueError("id (cm_id name) must be provided for RdmaLeaveMulticast")
        if not addr:
            raise ValueError("addr (sockaddr name) must be provided for RdmaLeaveMulticast")

        # rdma_cm_id handle name tracked by the resource system
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

        # The multicast address variable name (struct sockaddr *)
        # Using LocalResourceValue since addr is typically a locally managed sockaddr instance.
        self.addr = LocalResourceValue(resource_type="sockaddr", value=addr)

        # Internal context reference (optional)
        self.context: Optional[CodeGenContext] = None

    def apply(self, ctx: CodeGenContext):
        self.context = ctx
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def _contract(self) -> InstantiatedContract:
        # Fallback if framework expects an instantiated contract
        return self.CONTRACT

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)
        addr_name = str(self.addr)

        # Generate C code to invoke rdma_leave_multicast.
        # Both id and addr must be valid pointers; we guard them via IF_OK_PTR.
        # Note: Leaving may cancel a pending join and completions may still be queued after return.
        return f"""
    /* rdma_leave_multicast */
    IF_OK_PTR({id_name}, {{
        IF_OK_PTR({addr_name}, {{
            int ret = rdma_leave_multicast({id_name}, (struct sockaddr *){addr_name});
            if (ret) {{
                fprintf(stderr, "rdma_leave_multicast(id={id_name}, addr={addr_name}) failed: %d\\n", ret);
            }} else {{
                /* Left multicast group successfully.
                 * Completion entries from the group may still be queued immediately after leaving.
                 */
            }}
        }});
    }});
"""
