# RDMA CM API modeling plugin for rdma_get_remote_ece
# This plugin models the rdma_get_remote_ece API, which retrieves remote ECE
# (Explicit Congestion Control Extensions) parameters received in REQ/REP events.
# It is used to implement the ECE handshake for external QPs during RDMA CM
# connection establishment. The call fills a struct ibv_ece with parameters
# negotiated/advertised by the remote side.

"""
Plugin that models rdma_get_remote_ece(id, ece) for the RDMA verbs fuzzing framework.

Semantics:
- rdma_get_remote_ece extracts the remote ECE parameters associated with a given rdma_cm_id.
- ECE parameters are available when the CM has processed REQ/REP events during connection setup.
- The API returns 0 on success, and a non-zero error code otherwise.

This class encapsulates the call for code generation and contract/state tracking,
allocating a local struct ibv_ece unless the caller provides a variable name.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, RequireSpec, State
from lib.value import (
    LocalResourceValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class GetRemoteECE(VerbCall):
    MUTABLE_FIELDS = ["id", "ece"]
    CONTRACT = Contract(
        requires=[
            # rdma_cm_id must exist and be usable (REQ/REP processed)
            RequireSpec(rtype="cm_id", state=State.USED, name_attr="id"),
        ],
        produces=[
            # Produce an 'ece' resource representing a filled ibv_ece structure.
            ProduceSpec(rtype="ece", state=State.USED, name_attr="ece"),
        ],
        transitions=[
            # No state transition for cm_id; it remains usable.
        ],
    )

    def __init__(self, id: str = None, ece: str = None):
        if not id:
            raise ValueError("id (rdma_cm_id variable name) must be provided for GetRemoteECE")
        # cm_id pointer held by the framework
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

        # 'ece' is a local struct ibv_ece variable to be filled by rdma_get_remote_ece.
        # If not provided, we will auto-derive a name from the id.
        if ece:
            self.ece = LocalResourceValue(resource_type="ece", value=ece)
        else:
            # The actual variable name will be finalized in apply() using context.
            self.ece = LocalResourceValue(resource_type="ece", value=None)

    def apply(self, ctx: CodeGenContext):
        self.context = ctx
        # Determine a stable local variable name if not provided
        if not self.ece.value:
            id_name = str(self.id)
            suffix = "_" + id_name.replace("cm_id[", "").replace("]", "")
            self.ece.value = f"ece{suffix}"

        # Allocate the local struct ibv_ece variable
        ctx.alloc_variable(self.ece.value, "struct ibv_ece")

        # Apply contract bookkeeping
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext):
        id_name = str(self.id)
        ece_name = self.ece.value

        return f"""
    /* rdma_get_remote_ece */
    IF_OK_PTR({id_name}, {{
        memset(&{ece_name}, 0, sizeof({ece_name}));
        int ret_ece = rdma_get_remote_ece({id_name}, &{ece_name});
        if (ret_ece) {{
            fprintf(stderr, "rdma_get_remote_ece({id_name}) failed: %d\\n", ret_ece);
        }} else {{
            // Remote ECE parameters fetched and stored in {ece_name}
        }}
    }});
"""
