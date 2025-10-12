# -*- coding: utf-8 -*-
# Plugin: RDMA CM API modeling for rdma_join_multicast
# Semantics:
#   rdma_join_multicast joins an RDMA multicast group for a given rdma_cm_id and
#   multicast address (struct sockaddr). It attaches the QP associated with the
#   rdma_cm_id to the multicast group. The cm_id must have been bound to a device
#   by rdma_bind_addr or resolved via rdma_resolve_addr (and typically have a
#   QP created via rdma_create_qp). The user-defined context pointer is echoed
#   back in rdma_cm_event->private_data on multicast-related events. The caller
#   must later invoke rdma_leave_multicast to release resources.

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, RequireSpec, State, TransitionSpec
from lib.value import (
    LocalResourceValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaJoinMulticast(VerbCall):
    """
    Model for rdma_join_multicast(id, addr, context)

    This VerbCall models joining an RDMA multicast group using a cm_id and a
    multicast sockaddr. It assumes the cm_id is already bound or resolved to a
    device, and that a QP has been created and associated with the cm_id (via
    rdma_create_qp). On success, it produces a 'multicast_member' resource that
    represents the membership of (id, addr) and marks it used. The provided
    context pointer is forwarded to the kernel and returned in rdma_cm_event's
    private_data for multicast events.

    Notes:
    - The cm_id should be associated with a UD-type QP for multicast.
    - The caller must later issue rdma_leave_multicast(id, addr) to clean up.
    - addr must be a valid struct sockaddr* pointing to a multicast address.

    Fields:
    - id:        rdma_cm_id resource name (required)
    - addr:      sockaddr resource name (required)
    - qp:        qp resource name that is already associated with 'id' (optional, used for contract checking)
    - context:   a local pointer name or "NULL" to pass as user-defined context (optional)
    - member:    local resource name representing the multicast membership handle (required for tracking)
    """

    MUTABLE_FIELDS = ["id", "addr", "qp", "context", "member"]

    # Contract:
    # - Requires cm_id allocated (and implicitly bound/resolved by prior verbs).
    # - Requires addr allocated (sockaddr prepared).
    # - Optionally requires qp in RESET (created) if provided; though rdma_join_multicast uses
    #   the QP associated with cm_id, we model it for sanity checking in fuzzing.
    # - Produces a multicast_member in USED state representing the membership of (id, addr).
    # - Transitions cm_id to USED (indicating it has an active multicast membership).
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
            RequireSpec(rtype="sockaddr", state=State.ALLOCATED, name_attr="addr"),
            RequireSpec(rtype="qp", state=State.RESET, name_attr="qp"),
        ],
        produces=[
            ProduceSpec(
                rtype="multicast_member",
                state=State.USED,
                name_attr="member",
                metadata_fields=["id", "addr", "qp"],
            ),
        ],
        transitions=[
            TransitionSpec(rtype="cm_id", from_state=State.ALLOCATED, to_state=State.USED, name_attr="id"),
        ],
    )

    def __init__(
        self,
        id: str = None,
        addr: str = None,
        qp: str = None,
        context: str = None,
        member: str = None,
    ):
        if not id:
            raise ValueError("id (rdma_cm_id) must be provided for RdmaJoinMulticast")
        if not addr:
            raise ValueError("addr (sockaddr*) must be provided for RdmaJoinMulticast")
        if not member:
            raise ValueError("member (multicast_member handle name) must be provided for RdmaJoinMulticast")

        # Resource bindings
        self.id = ResourceValue(resource_type="cm_id", value=id)
        self.addr = ResourceValue(resource_type="sockaddr", value=addr)
        # qp is optional in the API; here we use it for contract validation that
        # a QP exists and is in RESET (created) state, and presumably bound via rdma_create_qp(id, qp).
        self.qp = ResourceValue(resource_type="qp", value=qp) if qp else "NULL"

        # Context pointer to be returned via rdma_cm_event->private_data
        self.context = LocalResourceValue(resource_type="ptr", value=context) if context else "NULL"

        # Local handle/resource to represent membership of (id, addr)
        self.member = LocalResourceValue(resource_type="multicast_member", value=member)

    def apply(self, ctx: CodeGenContext):
        # Contract application for resource state tracking
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

        # Optionally, register the 'member' name as a recognizable local resource in codegen context
        # (No specific allocation needed; we use it for bookkeeping and logs.)
        if hasattr(ctx, "alloc_variable"):
            # We don't allocate a C variable for 'member' since rdma_join_multicast returns int.
            # This registers the symbol for cross-plugin bookkeeping only.
            try:
                ctx.alloc_variable(str(self.member), "int", "0")
            except Exception:
                # If the context doesn't support this or already allocated, ignore.
                pass

    def generate_c(self, ctx: CodeGenContext):
        id_name = str(self.id)
        addr_name = str(self.addr)
        ctx_ptr = str(self.context) if isinstance(self.context, (LocalResourceValue, ResourceValue)) else self.context
        member_name = str(self.member)

        # When qp is provided, we can add a comment note for trace/debug.
        qp_note = ""
        if isinstance(self.qp, ResourceValue):
            qp_note = f"/* associated qp: {str(self.qp)} */"

        return f"""
    /* rdma_join_multicast: join multicast group and attach QP via cm_id */
    IF_OK_PTR({id_name}, {{
        IF_OK_PTR({addr_name}, {{
            {qp_note}
            int ret_join = rdma_join_multicast({id_name}, (struct sockaddr *){addr_name}, {ctx_ptr});
            if (ret_join) {{
                fprintf(stderr, "rdma_join_multicast(id=%s, addr=%s) failed: %d\\n", "{id_name}", "{addr_name}", ret_join);
            }} else {{
                /* Track membership handle (logical, for fuzzing bookkeeping) */
                {member_name} = 1;
                fprintf(stderr, "rdma_join_multicast(id=%s, addr=%s) succeeded, member={member_name}, ctx=%p\\n", "{id_name}", "{addr_name}", (void*){ctx_ptr});
            }}
        }});
    }});
"""
