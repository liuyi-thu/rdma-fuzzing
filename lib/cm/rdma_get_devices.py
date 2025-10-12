# RDMA CM API modeling plugin: rdma_get_devices
# Semantics:
# - rdma_get_devices returns a NULL-terminated array of opened RDMA devices (struct ibv_context **).
# - If num_devices is non-NULL, it will be set to the number of devices returned.
# - The returned array must be released by rdma_free_devices.
# Usage:
# - This VerbCall models discovery of available RDMA device contexts to be shared across multiple rdma_cm_id's.

"""
Plugin that models the RDMA CM API rdma_get_devices and wraps it as a VerbCall.

This class generates C code to:
  - Allocate variables for the device list and a count of devices.
  - Call rdma_get_devices(&num_devices).
  - Print basic diagnostics and make the device list available for subsequent steps.

Contract:
  - Produces a "device_list" resource in ALLOCATED state, identified by the attribute "devices".
  - The array must later be released via a separate rdma_free_devices modeling call.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, State
from lib.value import (
    LocalResourceValue,
)
from lib.verbs import VerbCall


class RdmaGetDevices(VerbCall):
    """
    Model the librdmacm API: struct ibv_context **rdma_get_devices(int *num_devices);

    Parameters:
      - num_devices_var: Name of the C variable to hold the count of devices returned.
      - devices_var:     Name of the C variable to hold the returned struct ibv_context ** array.

    Behavior:
      - Allocates the variables in the C codegen context.
      - Invokes rdma_get_devices and logs the number of devices.
      - Produces a "device_list" resource (the pointer to the array) in ALLOCATED state.

    Notes:
      - The returned device array must be freed using rdma_free_devices.
    """

    MUTABLE_FIELDS = ["num_devices", "devices"]

    CONTRACT = Contract(
        requires=[],
        produces=[
            ProduceSpec(rtype="device_list", state=State.ALLOCATED, name_attr="devices"),
        ],
        transitions=[],
    )

    def __init__(self, num_devices_var: str = "num_devices", devices_var: str = "devices"):
        # num_devices is an integer variable; we treat it as a local resource so the framework tracks its name.
        self.num_devices = LocalResourceValue(resource_type="int", value=num_devices_var)
        # devices is the returned pointer to an array of struct ibv_context *; tracked as a local resource.
        self.devices = LocalResourceValue(resource_type="device_list", value=devices_var)

    def apply(self, ctx: CodeGenContext):
        # Make variables available for codegen and any framework bookkeeping.
        self.context = ctx
        if self.context:
            self.context.alloc_variable(str(self.num_devices.value), "int", "0")
            self.context.alloc_variable(str(self.devices.value), "struct ibv_context **", "NULL")

        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        num_name = str(self.num_devices.value)
        dev_arr = str(self.devices.value)

        # Generate C code. Iterate using num_devices (count) for reliability; array is also NULL-terminated.
        return f"""
    /* rdma_get_devices */
    {dev_arr} = rdma_get_devices(&{num_name});
    if (!{dev_arr}) {{
        fprintf(stderr, "rdma_get_devices: returned NULL device list\\n");
    }} else {{
        fprintf(stderr, "rdma_get_devices: %d device(s) available\\n", {num_name});
        for (int i = 0; i < {num_name}; ++i) {{
            struct ibv_context *ctx_i = {dev_arr}[i];
            if (ctx_i) {{
                /* Best-effort diagnostics; device name may be accessible via ctx_i->device->name */
                const char *dev_name = (ctx_i->device && ctx_i->device->name) ? ctx_i->device->name : "(unknown)";
                fprintf(stderr, "  dev[%d]: ctx=%p name=%s\\n", i, (void*)ctx_i, dev_name);
            }} else {{
                fprintf(stderr, "  dev[%d]: NULL entry\\n", i);
            }}
        }}
    }}
"""
