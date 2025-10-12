# RDMA CM API modeling: rdma_get_peer_addr
# This plugin models the rdma_get_peer_addr CM API, which returns a pointer to the peer's
# (destination) socket address associated with a given rdma_cm_id. The address is taken
# from id->route.addr.dst_addr and is valid after address/route resolution steps.
# This call does not mutate CM state; it provides read-only access to the remote address.

"""
Plugin for modeling rdma_get_peer_addr in the RDMA verbs fuzzing framework.

Semantics:
- Input: rdma_cm_id*
- Output: struct sockaddr* pointing to the peer (destination) address stored within the CM ID route.
- Preconditions: The CM ID should have a resolved address/route (typically after rdma_resolve_addr or rdma_resolve_route,
  or after an incoming connection request populates route info).
- Postconditions: No state changes to the CM ID; a local pointer variable is produced and can be inspected or used
  in subsequent operations.

Notes:
- The returned pointer refers to internal storage inside the rdma_cm_id; it must not be freed by the caller.
- The plugin emits simple C to retrieve and store the returned pointer in a generated local variable.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, RequireSpec, State
from lib.value import (
    LocalResourceValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class GetPeerAddr(VerbCall):
    """
    Model rdma_get_peer_addr(struct rdma_cm_id *id) -> struct sockaddr *.

    Produces a local pointer variable (struct sockaddr *) that references the peer (destination)
    address associated with the given CM ID. This operation does not mutate the CM ID.
    """

    MUTABLE_FIELDS = ["cm_id", "peer_addr"]

    # Contract:
    # - Require: cm_id must be in a state where route/address has been resolved (we conservatively use USED here).
    # - Produce: a local "sockaddr" resource representing the pointer to the peer address.
    CONTRACT = Contract(
        requires=[
            # We assume cm_id is usable (e.g., after resolve/route). Framework may refine to State.RESOLVED if available.
            RequireSpec(rtype="cm_id", state=State.USED, name_attr="cm_id"),
        ],
        produces=[
            # The returned pointer is a local resource pointing into id->route; no ownership transfer.
            ProduceSpec(rtype="sockaddr", state=State.USED, name_attr="peer_addr"),
        ],
        transitions=[
            # No state transitions for cm_id; read-only access.
        ],
    )

    def __init__(self, cm_id: str = None, peer_addr: str = None):
        """
        Initialize the GetPeerAddr verb.

        Args:
            cm_id: Name of the rdma_cm_id resource.
            peer_addr: Name of the local variable to hold the returned struct sockaddr*.
        """
        if not cm_id:
            raise ValueError("cm_id must be provided for GetPeerAddr")
        if not peer_addr:
            raise ValueError("peer_addr must be provided for GetPeerAddr")
        self.cm_id = ResourceValue(resource_type="cm_id", value=cm_id, mutable=False)
        # Local pointer resource to store the result; no allocation is performed, it just references internal storage.
        self.peer_addr = LocalResourceValue(resource_type="sockaddr", value=peer_addr)

    def apply(self, ctx: CodeGenContext):
        # Register local variable in codegen context
        ctx.alloc_variable(str(self.peer_addr), "struct sockaddr *", "NULL")

        # Apply contract if the system tracks/validates resource states
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        cm_id_name = str(self.cm_id)
        peer_var_name = str(self.peer_addr)

        return f"""
    /* rdma_get_peer_addr */
    IF_OK_PTR({cm_id_name}, {{
        {peer_var_name} = rdma_get_peer_addr({cm_id_name});
        if (!{peer_var_name}) {{
            fprintf(stderr, "rdma_get_peer_addr({cm_id_name}) returned NULL\\n");
        }} else {{
            // Pointer references internal storage in rdma_cm_id->route.addr.dst_addr (do not free).
            // Optionally, print family for quick diagnostics.
            fprintf(stderr, "peer addr family for %s: %d\\n", "{cm_id_name}", {peer_var_name}->sa_family);
        }}
    }});
"""
