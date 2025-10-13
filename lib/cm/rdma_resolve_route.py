# -*- coding: utf-8 -*-
"""
Modeling of RDMA CM API: rdma_resolve_route

Semantics and usage:
- rdma_resolve_route(id, timeout_ms) initiates route resolution for a previously
  address-resolved RDMA CM ID on the client side. This should be called after
  rdma_resolve_addr and before rdma_connect.
- The call returns 0 on successful initiation; completion is reported asynchronously
  via CM events (e.g., RDMA_CM_EVENT_ROUTE_RESOLVED or an error event).
- This model enforces that a valid cm_id resource exists and performs a coarse
  state transition to USED to allow subsequent operations (e.g., rdma_connect).
  Note: In a precise model, the state transition should occur upon receiving the
  corresponding CM event. For fuzzing simplicity, we advance the state here.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    IntValue,
    ResourceValue,
)
from lib.verbs import VerbCall

# Base class VerbCall is provided by the framework runtime.


class RdmaResolveRoute(VerbCall):
    """
    Python model for rdma_resolve_route:
        int rdma_resolve_route(struct rdma_cm_id *id, int timeout_ms);
    """

    MUTABLE_FIELDS = ["id", "timeout_ms"]

    # Contract:
    # - Requires a valid cm_id (created by rdma_create_id, typically associated with a client).
    # - In a coarse-grained model, we transition cm_id to USED to enable next steps like rdma_connect.
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ADDR_RESOLVED, name_attr="id"),
        ],
        produces=[],
        transitions=[
            TransitionSpec(
                rtype="cm_id", from_state=State.ADDR_RESOLVED, to_state=State.ROUTE_RESOLVED, name_attr="id"
            ),
        ],
    )

    def __init__(self, id: str = None, timeout_ms: int = 2000):
        if not id:
            raise ValueError("id (cm_id) must be provided for RdmaResolveRoute")
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)
        self.timeout_ms = IntValue(timeout_ms)

    def apply(self, ctx: CodeGenContext):
        self.context = ctx
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext):
        id_name = str(self.id)
        timeout_expr = str(self.timeout_ms)

        return f"""
    /* rdma_resolve_route */
    IF_OK_PTR({id_name}, {{
        int ret_rr = rdma_resolve_route({id_name}, {timeout_expr});
        if (ret_rr) {{
            fprintf(stderr, "rdma_resolve_route failed for id=%p: ret=%d errno=%d (%s)\\n",
                    (void*){id_name}, ret_rr, errno, strerror(errno));
        }}
    }});
"""
