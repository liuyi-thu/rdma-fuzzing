# RDMA CM API modeling plugin: rdma_free_devices
# This plugin models the semantics of rdma_free_devices, which frees the device
# array returned by rdma_get_devices. It invalidates the device list pointer and
# should be used when the device contexts are no longer needed.

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import ResourceValue
from lib.verbs import VerbCall


class RdmaFreeDevices(VerbCall):
    """
    Model for rdma_free_devices(struct ibv_context **list)

    Semantics:
    - Frees the device array returned by rdma_get_devices.
    - After calling, the pointer becomes invalid and is set to NULL in generated code to avoid double free.

    Parameters:
    - dev_list: Identifier (string) for the device list pointer resource returned from rdma_get_devices.

    Contract:
    - Requires a 'rdma_device_list' resource in ALLOCATED state.
    - Transitions the 'rdma_device_list' resource to FREED state.
    """

    MUTABLE_FIELDS = ["dev_list"]

    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="rdma_device_list", state=State.ALLOCATED, name_attr="dev_list"),
        ],
        transitions=[
            TransitionSpec(
                rtype="rdma_device_list",
                from_state=State.ALLOCATED,
                to_state=State.FREED,
                name_attr="dev_list",
            ),
        ],
    )

    def __init__(self, dev_list: str):
        if not dev_list:
            raise ValueError("dev_list must be provided for RdmaFreeDevices")
        # The device list is a tracked resource produced by rdma_get_devices
        self.dev_list = ResourceValue(resource_type="rdma_device_list", value=dev_list, mutable=True)
        self.context = None

    def apply(self, ctx: CodeGenContext):
        self.context = ctx
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        dev_list_name = str(self.dev_list)
        return f"""
    /* rdma_free_devices */
    IF_OK_PTR({dev_list_name}, {{
        rdma_free_devices({dev_list_name});
        {dev_list_name} = NULL;
    }});
"""
