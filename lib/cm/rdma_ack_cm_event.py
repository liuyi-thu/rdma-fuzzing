# RDMA CM API modeling plugin: rdma_ack_cm_event
# This plugin models the RDMA CM API rdma_ack_cm_event, which acknowledges and frees
# a communication event obtained by rdma_get_cm_event. Each successfully received event
# must be matched with exactly one ack; after ack, the event object is no longer valid.

"""
Plugin: AckCmEvent
Purpose:
  Model rdma_ack_cm_event() as a VerbCall for the RDMA verbs fuzzing framework.
  This call acknowledges (frees) a CM event previously acquired by rdma_get_cm_event.

Semantics:
  - Input: a valid struct rdma_cm_event * (obtained via rdma_get_cm_event).
  - Effect: releases the event back to the CM. The event pointer becomes invalid after ack.
  - Constraints: There must be a one-to-one mapping between successful rdma_get_cm_event
    calls and their corresponding rdma_ack_cm_event calls.

Contracts:
  - Requires: cm_event in ALLOCATED state.
  - Transitions: cm_event moves to FREED after acknowledgement.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class AckCmEvent(VerbCall):
    """
    Acknowledge and free a CM event.

    Corresponding C API:
      int rdma_ack_cm_event(struct rdma_cm_event *event);

    Usage notes:
      - The event must have been obtained via rdma_get_cm_event.
      - After ack, the event is invalid and should not be used again.
      - Framework contract transitions the event resource to FREED state.
    """

    MUTABLE_FIELDS = ["event"]

    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_event", state=State.ALLOCATED, name_attr="event"),
        ],
        produces=[
            # No new resources are produced; this call frees the event.
        ],
        transitions=[
            TransitionSpec(rtype="cm_event", from_state=State.ALLOCATED, to_state=State.FREED, name_attr="event"),
        ],
    )

    def __init__(self, event: str = None):
        if not event:
            raise ValueError("event must be provided for AckCmEvent")
        # CM event pointer/resource obtained via rdma_get_cm_event
        self.event = ResourceValue(resource_type="cm_event", value=event, mutable=False)

    def apply(self, ctx: CodeGenContext):
        # Apply resource state contract
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext):
        event_name = str(self.event)
        return f"""
    /* rdma_ack_cm_event */
    IF_OK_PTR({event_name}, {{
        int rc = rdma_ack_cm_event({event_name});
        if (rc) {{
            fprintf(stderr, "rdma_ack_cm_event({event_name}) failed: rc=%d\\n", rc);
        }} else {{
            /* Event successfully acknowledged; invalidate the pointer to prevent reuse. */
            {event_name} = NULL;
        }}
    }});
"""
