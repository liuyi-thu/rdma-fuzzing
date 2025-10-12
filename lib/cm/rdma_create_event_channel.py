# RDMA CM: rdma_create_event_channel
# This API opens an event channel used to report asynchronous RDMA CM events.
# Each channel maps to a file descriptor and must be destroyed with rdma_destroy_event_channel.
# Users retrieve events via rdma_get_cm_event on this channel.

"""
Plugin modeling rdma_create_event_channel for the RDMA CM fuzzing framework.

This plugin provides a high-level semantic wrapper for creating an RDMA CM event channel.
It integrates with the framework's resource tracking and code generation system:

- Semantics:
  - rdma_create_event_channel() creates a struct rdma_event_channel *.
  - The returned channel maps to a file descriptor (ec->fd).
  - The channel must eventually be destroyed by rdma_destroy_event_channel.
  - Events are retrieved using rdma_get_cm_event.

- Contract:
  - Produces a resource of type "cm_event_channel" in ALLOCATED state.

- Code generation:
  - Declares a variable of type "struct rdma_event_channel *" initialized to NULL.
  - Emits C code to call rdma_create_event_channel() and checks for failure.

- Usage example (high level):
  - CreateEventChannel(ec="ec0")
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, State
from lib.value import ResourceValue
from lib.verbs import VerbCall


class CreateEventChannel(VerbCall):
    """
    Model for rdma_create_event_channel.

    Creates an RDMA CM event channel and registers it as a managed resource in the fuzzing framework.
    """

    MUTABLE_FIELDS = ["ec"]

    CONTRACT = Contract(
        requires=[],
        produces=[
            ProduceSpec(rtype="cm_event_channel", state=State.ALLOCATED, name_attr="ec"),
        ],
        transitions=[],
    )

    def __init__(self, ec: str = None):
        """
        Initialize the verb call.

        Parameters:
            ec: The identifier/name of the event channel resource (variable name in generated C code).
        """
        if not ec:
            raise ValueError("ec must be provided for CreateEventChannel")
        # Event channel resource (non-mutable pointer name in generated C)
        self.ec = ResourceValue(resource_type="cm_event_channel", value=ec, mutable=False)

    def apply(self, ctx: CodeGenContext):
        """
        Apply context-level side effects:
        - Allocate a C variable for the event channel.
        - Register contract semantics.
        """
        # Register the variable in the C codegen context
        ctx.alloc_variable(str(self.ec), "struct rdma_event_channel *", "NULL")

        # Apply the resource contract to the runtime contract engine (if present)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT)

    def generate_c(self, ctx: CodeGenContext) -> str:
        """
        Generate the C code that creates the event channel.

        Returns:
            C source string that calls rdma_create_event_channel and stores into the ec variable.
        """
        ec_name = str(self.ec)
        return f"""
    /* rdma_create_event_channel */
    {ec_name} = rdma_create_event_channel();
    if (!{ec_name}) {{
        fprintf(stderr, "Failed to create RDMA CM event channel {ec_name}\\n");
    }} else {{
        // The event channel maps to a file descriptor: {ec_name}->fd
        // Users should call rdma_get_cm_event on this channel and destroy it with rdma_destroy_event_channel.
    }}
"""
