# rdma_get_src_port: Retrieve the local source UDP port for a given RDMA CM ID.
# This call returns the source port in network byte order (__be16). In the generated C code,
# we convert it to host byte order (uint16_t) using ntohs and store it in a user-provided variable.

"""
Plugin that models the RDMA CM API rdma_get_src_port(id).

Semantics:
- rdma_get_src_port(struct rdma_cm_id *id) returns the local source port (UDP port) associated
  with the given CM ID in network byte order (__be16). If the CM ID has not been bound or does not
  have a source address, the returned value may be 0.
- This plugin generates C code to call rdma_get_src_port, converts the result into host byte order
  with ntohs, and saves it into a uint16_t variable for later use.

Usage within the fuzzing framework:
- Requires a valid RDMA CM ID resource (state: ALLOCATED).
- Produces no new resources; it only populates a scalar variable holding the host-endian port.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State
from lib.value import ResourceValue
from lib.verbs import VerbCall


class GetSrcPort(VerbCall):
    MUTABLE_FIELDS = ["id", "out_var"]

    CONTRACT = Contract(
        requires=[
            # Must have a valid CM ID to query its source port.
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
        ],
        produces=[],
        transitions=[],
    )

    def __init__(self, id: str, out_var: str = None):
        """
        Initialize the GetSrcPort verb call.

        Args:
            id: The name of the RDMA CM ID resource to query (e.g., "cm_id0").
            out_var: Optional name of a C variable (uint16_t) to store the host-endian port.
                     If not provided, a name will be derived from the CM ID.
        """
        if not id:
            raise ValueError("id must be provided for GetSrcPort")
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)
        self.out_var = out_var  # created/allocated in apply()

    def _default_out_var(self) -> str:
        base = str(self.id)
        # Derive a readable variable name from the CM ID token.
        suffix = base.replace("cm_id[", "").replace("]", "")
        if suffix == base:
            # No indexed form, still generate a reasonable name.
            suffix = base
        return f"src_port_{suffix}"

    def apply(self, ctx: CodeGenContext):
        self.context = ctx
        # Determine the output variable name and allocate it in the C context.
        if not self.out_var:
            self.out_var = self._default_out_var()
        # Store as host-endian uint16_t
        ctx.alloc_variable(self.out_var, "uint16_t", "0")

        # Apply resource/state contract checks if supported by the context.
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)
        out_name = self.out_var

        return f"""
    /* rdma_get_src_port */
    IF_OK_PTR({id_name}, {{
        // rdma_get_src_port returns __be16 (network byte order). Convert to host order.
        {out_name} = ntohs(rdma_get_src_port({id_name}));
        fprintf(stderr, "rdma_get_src_port({id_name}) -> %u\\n", (unsigned){out_name});
    }});
"""
