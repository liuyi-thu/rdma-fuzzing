# -*- coding: utf-8 -*-
# rdma_migrate_id: Move an rdma_cm_id to a new rdma_event_channel.
# Semantics:
#   - Re-associates an existing RDMA CM ID with a different event channel.
#   - After migration, asynchronous CM events for the ID are delivered on the new channel.
# Typical usage:
#   - When multiplexing CM events or rebalancing event handling threads, migrate IDs to a new channel.
# Preconditions:
#   - The rdma_cm_id must be valid (allocated/created and not destroyed).
#   - The target rdma_event_channel must be valid (opened/created).
# Effects:
#   - Does not change connection state of the ID; only its event delivery channel is changed.
#   - The new channel is considered "used" after migration.

"""
Plugin class modeling rdma_migrate_id for RDMA CM, integrated with the verbs fuzzing framework.

Function prototype:

    int rdma_migrate_id(struct rdma_cm_id *id, struct rdma_event_channel *channel);

This class encapsulates the migration operation as a VerbCall, allowing the fuzzing framework
to schedule and generate the corresponding C code, manage resource contracts, and update
bookkeeping for event channel associations.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaMigrateId(VerbCall):
    """
    Model for rdma_migrate_id:

    Move an rdma_cm_id to a new event channel.

    Parameters:
        id (str): Name of the rdma_cm_id resource variable to migrate.
        channel (str): Name of the rdma_event_channel resource variable to migrate to.

    Contract:
        - Requires:
            * id: cm_id in ALLOCATED state.
            * channel: event_channel in ALLOCATED state.
        - Produces:
            * No new resources; cm_id remains in its current state.
        - Transitions:
            * event_channel: ALLOCATED -> USED (it's now associated with an active cm_id).
    """

    MUTABLE_FIELDS = ["id", "channel"]

    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
            RequireSpec(rtype="event_channel", state=State.ALLOCATED, name_attr="channel"),
        ],
        produces=[
            # No new resource is created; metadata/binding is updated internally.
        ],
        transitions=[
            TransitionSpec(rtype="event_channel", from_state=State.ALLOCATED, to_state=State.USED, name_attr="channel"),
        ],
    )

    def __init__(self, id: str = None, channel: str = None):
        if not id:
            raise ValueError("id (cm_id) must be provided for RdmaMigrateId")
        if not channel:
            raise ValueError("channel (event_channel) must be provided for RdmaMigrateId")

        # Existing resources: both cm_id and event_channel should already exist.
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)
        self.channel = ResourceValue(resource_type="event_channel", value=channel, mutable=False)

    def apply(self, ctx: CodeGenContext):
        # Register contract effects
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

        # Update bookkeeping: associate cm_id to new event channel, if the context supports it.
        # This mirrors the semantic effect of rdma_migrate_id.
        if hasattr(ctx, "make_cm_id_channel_binding"):
            ctx.make_cm_id_channel_binding(str(self.id), str(self.channel))
        elif hasattr(ctx, "note_event_channel_migration"):
            # Alternate naming fallback if the framework uses a different helper.
            ctx.note_event_channel_migration(str(self.id), str(self.channel))

    def generate_c(self, ctx: CodeGenContext):
        id_name = str(self.id)
        ch_name = str(self.channel)
        return f"""
    /* rdma_migrate_id: move CM ID to a new event channel */
    IF_OK_PTR({id_name}, {{
        IF_OK_PTR({ch_name}, {{
            int __ret_migrate = rdma_migrate_id({id_name}, {ch_name});
            if (__ret_migrate) {{
                fprintf(stderr, "rdma_migrate_id({id_name} -> {ch_name}) failed: %d\\n", __ret_migrate);
            }} else {{
                // Successfully migrated: events for {id_name} will now arrive on {ch_name}.
            }}
        }});
    }});
"""
