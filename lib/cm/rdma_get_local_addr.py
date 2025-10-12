# Modeling for RDMA CM API: rdma_get_local_addr
# This plugin models the rdma_get_local_addr API, which retrieves a pointer to the local
# sockaddr associated with an rdma_cm_id. It returns &id->route.addr.src_addr. The address
# is typically populated after rdma_bind_addr or rdma_resolve_addr and reflects the local
# source endpoint chosen/used by the CM. The returned pointer is owned by the rdma_cm_id
# and must not be freed by the user.

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, RequireSpec, State
from lib.value import (
    LocalResourceValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaGetLocalAddr(VerbCall):
    """
    Model for rdma_get_local_addr(struct rdma_cm_id *id) -> struct sockaddr *.

    Semantics:
        - Returns a pointer to the local address (source address) associated with the given
          rdma_cm_id: &id->route.addr.src_addr.
        - The pointer is valid as long as the rdma_cm_id exists; do not free it.
        - The local address is generally available after rdma_bind_addr or rdma_resolve_addr.

    Contract:
        - Requires: A valid rdma_cm_id (allocated).
        - Produces: A local sockaddr resource (pointer) that references internal memory
          of the rdma_cm_id (not owned by the caller). We model it as a LocalResourceValue.

    Parameters:
        id (str): Name of the C variable holding struct rdma_cm_id *.
        addr (str): Name of the C variable to store the resulting struct sockaddr *.

    Notes:
        - This call does not modify the state of the rdma_cm_id, it only reads from it.
        - For fuzzing/trace purposes, we also emit diagnostic printing of the resolved address.
    """

    MUTABLE_FIELDS = ["id", "addr"]

    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
        ],
        produces=[
            ProduceSpec(rtype="sockaddr", state=State.ALLOCATED, name_attr="addr", metadata_fields=["id"]),
        ],
        transitions=[],
    )

    def __init__(self, id: str, addr: str):
        if not id:
            raise ValueError("id (cm_id variable name) must be provided for RdmaGetLocalAddr")
        if not addr:
            raise ValueError("addr (sockaddr* variable name) must be provided for RdmaGetLocalAddr")

        # rdma_cm_id pointer (must already exist/allocated)
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

        # sockaddr* pointer returned by rdma_get_local_addr (local reference, not owned)
        self.addr = LocalResourceValue(resource_type="sockaddr", value=addr)

    def apply(self, ctx: CodeGenContext):
        # Allocate C variables in the harness
        ctx.alloc_variable(str(self.addr), "struct sockaddr *", "NULL")

        # Apply the contract, if the context supports it
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT)

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_var = str(self.id)
        addr_var = str(self.addr)

        # C code to interpret and print the sockaddr
        # This uses inet_ntop and standard headers; the harness should include <arpa/inet.h> and <netinet/in.h>.
        addr_dump = f"""
        if ({addr_var}) {{
            char abuf[INET6_ADDRSTRLEN] = {{0}};
            switch ({addr_var}->sa_family) {{
                case AF_INET: {{
                    struct sockaddr_in *sin = (struct sockaddr_in *){addr_var};
                    inet_ntop(AF_INET, &sin->sin_addr, abuf, sizeof(abuf));
                    fprintf(stderr, "rdma_get_local_addr({id_var}): IPv4 %s:%u\\n", abuf, ntohs(sin->sin_port));
                    break;
                }}
                case AF_INET6: {{
                    struct sockaddr_in6 *sin6 = (struct sockaddr_in6 *){addr_var};
                    inet_ntop(AF_INET6, &sin6->sin6_addr, abuf, sizeof(abuf));
                    fprintf(stderr, "rdma_get_local_addr({id_var}): IPv6 [%s]:%u\\n", abuf, ntohs(sin6->sin6_port));
                    break;
                }}
                default:
                    fprintf(stderr, "rdma_get_local_addr({id_var}): unknown sa_family=%d\\n", {addr_var}->sa_family);
                    break;
            }}
        }} else {{
            fprintf(stderr, "rdma_get_local_addr({id_var}) returned NULL\\n");
        }}
        """

        return f"""
    /* rdma_get_local_addr */
    IF_OK_PTR({id_var}, {{
        {addr_var} = rdma_get_local_addr({id_var});
        {addr_dump}
    }});
"""
