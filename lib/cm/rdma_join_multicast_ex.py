# -*- coding: utf-8 -*-
# RDMA CM modeling plugin: rdma_join_multicast_ex
# Semantics:
#   rdma_join_multicast_ex joins a multicast group with options described by
#   rdma_cm_join_mc_attr_ex (e.g., join flags). The CM ID must be bound to an
#   RDMA device via rdma_bind_addr or rdma_resolve_addr before joining. The QP
#   may be attached to the multicast group depending on the provided flags.
#   The user-defined context is returned via the private_data field in the
#   rdma_cm_event. Leaving the group must be done via rdma_leave_multicast.

"""
Python plugin that models the RDMA CM API rdma_join_multicast_ex as a VerbCall.

This class wraps the CM API call:
    int rdma_join_multicast_ex(struct rdma_cm_id *id,
                               struct rdma_cm_join_mc_attr_ex *mc_join_attr,
                               void *context);

Usage:
- id: a tracked cm_id resource (created via rdma_create_id and bound/resolved).
- mc_join_attr: a local variable name (struct rdma_cm_join_mc_attr_ex *) prepared
  elsewhere that encodes the multicast parameters (address, join_flags, etc.).
- context: an optional user pointer; returned through rdma_cm_event.private_data.

Contract (approximation for fuzzing purposes):
- Requires: id present (ALLOCATED).
- Requires: mc_join_attr prepared (ALLOCATED as a local resource).
- Produces/Transitions: id marked as USED (it initiated a multicast join).

Notes:
- The actual join behavior (QP attach, message flags) depends on the fields in
  rdma_cm_join_mc_attr_ex, which should be prepared in prior steps.
- On success, the RDMA CM will later deliver an RDMA_CM_EVENT_MULTICAST_JOIN event.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    LocalResourceValue,
    OptionalValue,
    ResourceValue,
)

# Fallback import if the framework exposes VerbCall differently
from lib.verbs import VerbCall


class JoinMulticastEx(VerbCall):
    """
    Model for rdma_join_multicast_ex.

    Parameters:
        id (str): variable name of struct rdma_cm_id *.
        mc_join_attr (str): variable name of struct rdma_cm_join_mc_attr_ex *.
        context (str | None): variable name for user context pointer (void *) or None/NULL.
    """

    MUTABLE_FIELDS = ["id", "mc_join_attr", "context"]

    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
            # mc_join_attr is modeled as a local resource (prepared elsewhere)
            RequireSpec(rtype="rdma_cm_join_mc_attr_ex", state=State.ALLOCATED, name_attr="mc_join_attr"),
        ],
        produces=[],
        transitions=[
            TransitionSpec(rtype="cm_id", from_state=State.ALLOCATED, to_state=State.USED, name_attr="id"),
        ],
    )

    def __init__(self, id: str, mc_join_attr: str, context: str = None):
        if not id:
            raise ValueError("id must be provided for JoinMulticastEx")
        if not mc_join_attr:
            raise ValueError("mc_join_attr must be provided for JoinMulticastEx")

        # Tracked resource: rdma_cm_id
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

        # Local resource: rdma_cm_join_mc_attr_ex (prepared elsewhere)
        self.mc_join_attr = LocalResourceValue(resource_type="rdma_cm_join_mc_attr_ex", value=mc_join_attr)

        # Optional user context pointer
        self.context = OptionalValue(value=context if context else "NULL")

    def apply(self, ctx: CodeGenContext):
        # Register variables with the codegen context if needed
        # (We assume id and mc_join_attr are already declared in previous steps.)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT)

    def generate_c(self, ctx: CodeGenContext):
        id_name = str(self.id)
        mc_attr_name = str(self.mc_join_attr)
        user_ctx = str(self.context) if self.context is not None else "NULL"

        return f"""
    /* rdma_join_multicast_ex */
    IF_OK_PTR({id_name}, {{
        int ret = rdma_join_multicast_ex({id_name}, {mc_attr_name}, {user_ctx});
        if (ret) {{
            fprintf(stderr, "rdma_join_multicast_ex(id={id_name}) failed: ret=%d\\n", ret);
        }} else {{
            fprintf(stdout, "rdma_join_multicast_ex(id={id_name}) succeeded\\n");
        }}
    }});
"""
