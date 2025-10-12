# -*- coding: utf-8 -*-
# rdma_set_local_ece: Set local ECE options on a given rdma_cm_id to be used during
# REQ/REP exchange. This models the ECE handshake configuration for connections
# initiated/accepted via the CM. It does not change the rdma_cm_id lifecycle state
# but attaches local ECE parameters that may affect the ensuing connection setup.

from typing import Optional

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaSetLocalECE(VerbCall):
    """
    Python model for CM API: int rdma_set_local_ece(struct rdma_cm_id *id, struct ibv_ece *ece);

    Semantics:
    - Configure local ECE options to be advertised and used during the REQ/REP handshake
      on a given rdma_cm_id.
    - Should be invoked prior to rdma_connect (active side) or rdma_accept (passive side)
      to ensure the options take effect during negotiation.
    - This call configures attributes but does not transition the cm_id connection state.

    Parameters:
    - id: Name of the cm_id resource.
    - ece_obj: Optional high-level object that can emit a 'struct ibv_ece' via to_cxx(var_name, ctx).
               If provided, it will be materialized into a local C variable and passed by address.
    - ece_ptr: Optional string/identifier representing an existing 'struct ibv_ece *' or '&var' to pass directly.
               If both ece_obj and ece_ptr are omitted, NULL will be passed.
    """

    MUTABLE_FIELDS = ["id", "ece_obj", "ece_ptr"]

    CONTRACT = Contract(
        requires=[
            # We require a valid cm_id handle that has been created/allocated.
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
        ],
        produces=[
            # No new resource is produced; this only configures ECE on the cm_id.
        ],
        transitions=[
            # No state transition for cm_id; it remains in the same lifecycle state.
        ],
    )

    def __init__(self, id: str, ece_obj: Optional["IbvECE"] = None, ece_ptr: Optional[str] = None):
        if not id:
            raise ValueError("id (cm_id resource name) must be provided for RdmaSetLocalECE")

        # ResourceValue ensures the resource exists and is tracked by contracts.
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

        # Two alternative ways to supply ECE:
        # - ece_obj: high-level builder object with .to_cxx(var_name, ctx)
        # - ece_ptr: direct pointer/expr to pass; if None, will pass NULL
        self.ece_obj = ece_obj
        self.ece_ptr = ece_ptr if ece_ptr else "NULL"

        # Keep context for auxiliary bindings if needed
        self.context: Optional[CodeGenContext] = None

    def apply(self, ctx: CodeGenContext):
        self.context = ctx

        # Apply contract checking/instrumentation if available
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)

        # Construct ECE parameter code if a builder object is provided.
        ece_code = ""
        ece_arg = "NULL"

        if self.ece_obj is not None:
            # Create a stable, unique-ish suffix based on cm_id variable name
            suffix = "_" + id_name.replace("id[", "").replace("]", "").replace("*", "").replace("&", "").replace(
                ".", "_"
            )
            ece_var = f"ece_params{suffix}"
            # Expect ece_obj to provide a to_cxx(var_name, ctx) -> C code that declares and fills 'struct ibv_ece'
            ece_code = self.ece_obj.to_cxx(ece_var, ctx)
            ece_arg = f"&{ece_var}"
        else:
            # If user provided a raw pointer/expression, use it verbatim; otherwise default to NULL
            ece_arg = self.ece_ptr if self.ece_ptr else "NULL"

        return f"""
    /* rdma_set_local_ece */
    IF_OK_PTR({id_name}, {{
        {ece_code}
        int rc = rdma_set_local_ece({id_name}, {ece_arg});
        if (rc) {{
            fprintf(stderr, "rdma_set_local_ece({id_name}) failed: %d\\n", rc);
        }}
    }});
"""
