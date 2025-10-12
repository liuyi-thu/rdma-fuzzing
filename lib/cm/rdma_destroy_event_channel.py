# RDMA CM plugin: rdma_destroy_event_channel
# Semantics:
#   rdma_destroy_event_channel closes an RDMA CM event channel and releases all
#   associated resources. All rdma_cm_id objects tied to this channel must be
#   destroyed and all retrieved events must be acknowledged before calling it.
# Usage:
#   This model requires a previously created event channel resource and will
#   transition it to a destroyed state after invoking the API.

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import ResourceValue
from lib.verbs import VerbCall


class DestroyEventChannel(VerbCall):
    """
    Model for rdma_destroy_event_channel.

    C prototype:
        void rdma_destroy_event_channel(struct rdma_event_channel *channel);

    Description:
        Release all resources associated with an event channel and close the
        associated file descriptor.

    Notes:
        - All rdma_cm_id's associated with the event channel must be destroyed.
        - All returned CM events must be acknowledged via rdma_ack_cm_event.
        - After destruction, the channel pointer is no longer valid.

    Contract:
        Requires:
            - A cm_event_channel resource in ALLOCATED state.
        Transitions:
            - cm_event_channel: ALLOCATED -> DESTROYED
    """

    MUTABLE_FIELDS = ["channel"]

    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_event_channel", state=State.ALLOCATED, name_attr="channel"),
        ],
        produces=[],
        transitions=[
            TransitionSpec(
                rtype="cm_event_channel",
                from_state=State.ALLOCATED,
                to_state=State.DESTROYED,
                name_attr="channel",
            ),
        ],
    )

    def __init__(self, channel: str = None):
        if not channel:
            raise ValueError("channel must be provided for DestroyEventChannel")
        # Resource type name aligns with rdma_create_event_channel model
        self.channel = ResourceValue(resource_type="cm_event_channel", value=channel, mutable=False)

    def apply(self, ctx: CodeGenContext):
        # Bind context and apply contracts
        self.context = ctx
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        ch = str(self.channel)
        return f"""
    /* rdma_destroy_event_channel */
    IF_OK_PTR({ch}, {{
        /* Precondition (by contract): all cm_id on this channel destroyed, all events acked */
        rdma_destroy_event_channel({ch});
        {ch} = NULL;
    }});
"""
