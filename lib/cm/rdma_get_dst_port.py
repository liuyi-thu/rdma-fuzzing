# RDMA CM API Modeling Plugin: rdma_get_dst_port
# Semantics: rdma_get_dst_port(id) retrieves the destination (remote) TCP/UDP port associated
# with the given rdma_cm_id. The returned value is in big-endian (network) byte order (__be16).
# Usage: Typically called after address/route resolution or when the CM ID has a destination
# address set. Convert the returned port to host byte order via ntohs() before using.

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State
from lib.value import (
    LocalResourceValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaGetDstPort(VerbCall):
    """
    Model for RDMA CM API: __be16 rdma_get_dst_port(struct rdma_cm_id *id);

    This verb queries the destination port associated with a given rdma_cm_id.
    The underlying API returns a big-endian 16-bit value (__be16). This plugin
    converts the result to host byte order by default and stores it in a user-provided
    or auto-generated local variable.

    Parameters:
        id (str): Name of the rdma_cm_id pointer variable to query.
        dst_port_var (str, optional): Name of the local variable to store the result (uint16_t).
                                      If not provided, one will be generated based on id.
        to_host (bool, optional): If True, convert the result to host byte order via ntohs().
                                  If False, store the big-endian value directly. Default: True.
    """

    MUTABLE_FIELDS = ["id", "dst_port_var", "to_host"]

    CONTRACT = Contract(
        requires=[
            # Require the CM ID to be allocated/valid before querying its destination port.
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
        ],
        produces=[
            # This verb does not produce new RDMA resources; it only reads metadata.
        ],
        transitions=[
            # No state transitions for the CM ID; it's a pure query.
        ],
    )

    def __init__(self, id: str = None, dst_port_var: str = None, to_host: bool = True):
        if not id:
            raise ValueError("id (rdma_cm_id variable name) must be provided for RdmaGetDstPort")

        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

        # Create or use provided local variable name to store the resulting port.
        if dst_port_var:
            self.dst_port_var = LocalResourceValue(resource_type="port", value=dst_port_var)
        else:
            # Auto-generate a deterministic variable name based on the cm_id symbol.
            base = str(self.id).replace("cm_id[", "").replace("]", "")
            self.dst_port_var = LocalResourceValue(resource_type="port", value=f"dst_port_{base}")

        self.to_host = bool(to_host)

    def apply(self, ctx: CodeGenContext):
        self.context = ctx
        # Pre-declare the destination port variable in the code generation context.
        # We store host-order uint16_t by default; if to_host=False, it's still uint16_t but in network order.
        ctx.alloc_variable(str(self.dst_port_var), "uint16_t", "0")

        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext):
        id_name = str(self.id)
        var_name = str(self.dst_port_var)

        assign_line = (
            f"{var_name} = ntohs(rdma_get_dst_port({id_name}));"
            if self.to_host
            else f"{var_name} = rdma_get_dst_port({id_name}); /* big-endian (network order) */"
        )

        # Informational print to help trace fuzzing runs.
        fmt_suffix = "(host order)" if self.to_host else "(network order)"
        print_line = f'fprintf(stderr, "rdma_get_dst_port: {fmt_suffix} id={id_name} -> %u\\n", {var_name});'

        return f"""
    /* rdma_get_dst_port: query destination port for CM ID */
    IF_OK_PTR({id_name}, {{
        {assign_line}
        {print_line}
    }});
"""
