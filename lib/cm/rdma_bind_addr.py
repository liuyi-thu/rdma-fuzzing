# rdma_bind_addr plugin
# This plugin models the RDMA CM API rdma_bind_addr, which binds an rdma_cm_id to a local source address.
# Semantics:
# - Associates a source address (possibly wildcard) with a cm_id.
# - If binding to a specific local address, the cm_id will be bound to a local RDMA device.
# - Commonly called before rdma_listen (passive side), or before rdma_resolve_addr (active side).
# - This call mutates the cm_id by configuring its local address binding; it does not create new resources.

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    LocalResourceValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaBindAddr(VerbCall):
    """
    Model for CM API: rdma_bind_addr(struct rdma_cm_id *id, struct sockaddr *addr)

    Parameters:
    - id: Name of an existing RDMA CM ID (C variable), e.g., "cm_id".
    - addr: Name of a C variable of type 'struct sockaddr *' or concrete struct address lvalue.
            May be None to pass NULL (for fuzzing). Wildcard values permitted by the API.

    Contract:
    - Requires the cm_id to be allocated (created via rdma_create_id or equivalent).
    - Transitions cm_id state from ALLOCATED to USED upon successful binding.
      (Note: This general "USED" state reflects that the cm_id has been configured/bound.)
    """

    MUTABLE_FIELDS = ["id", "addr"]

    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
            # 'addr' is optional/wildcard; we do not require it to be allocated.
        ],
        produces=[],
        transitions=[
            TransitionSpec(rtype="cm_id", from_state=State.ALLOCATED, to_state=State.USED, name_attr="id"),
        ],
    )

    def __init__(self, id: str, addr: str | None = None):
        if not id:
            raise ValueError("id must be provided for RdmaBindAddr")
        # RDMA cm_id resource; we assume it exists in C as a pointer variable.
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)
        # Address may be a local sockaddr resource or NULL.
        self.addr = LocalResourceValue(resource_type="sockaddr", value=addr) if addr else "NULL"

    def apply(self, ctx: CodeGenContext):
        # Store context if needed for later codegen decisions.
        self.context = ctx
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext):
        id_name = str(self.id)
        addr_expr = self.addr if isinstance(self.addr, str) else str(self.addr)

        return f"""
    /* rdma_bind_addr */
    IF_OK_PTR({id_name}, {{
        int ret = rdma_bind_addr({id_name}, {addr_expr});
        if (ret) {{
            fprintf(stderr, "rdma_bind_addr failed for {id_name}: ret=%d errno=%d (%s)\\n", ret, errno, strerror(errno));
        }}
    }});
"""