# RDMA CM API modeling for rdma_reg_write
# Semantics:
#   rdma_reg_write(id, addr, length) registers a memory region on the
#   protection domain associated with the given rdma_cm_id, with access flags
#   suitable for remote write operations (typically IBV_ACCESS_REMOTE_WRITE
#   plus IBV_ACCESS_LOCAL_WRITE). The returned ibv_mr can be used by the peer
#   to perform RDMA WRITEs to the registered memory.
#
# Usage in fuzzing:
#   - Requires a valid rdma_cm_id that has an associated PD (e.g., via rdma_create_qp).
#   - Produces an MR resource in REGISTERED state, bound to the passed addr/length.

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, RequireSpec, State
from lib.value import (
    IntValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaRegWrite(VerbCall):
    """
    Model of rdma_reg_write:
        static inline struct ibv_mr * rdma_reg_write(struct rdma_cm_id *id, void *addr, size_t length);

    Registers a memory region for remote WRITE access on the PD associated with the
    specified rdma_cm_id. Returns a pointer to ibv_mr on success, NULL on failure.

    Contract:
      - Requires:
          * A valid cm_id (id) that is allocated and has a PD (id.pd) allocated.
          * Optionally, a buffer resource (addr) allocated, if modeled as a resource.
      - Produces:
          * An MR in REGISTERED state.
    """

    MUTABLE_FIELDS = ["id", "addr", "length", "mr"]

    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
            # rdma_reg_* helpers use the PD bound to the cm_id
            RequireSpec(rtype="pd", state=State.ALLOCATED, name_attr="id.pd"),
            # If the framework tracks buffers as resources, ensure it's allocated
            RequireSpec(rtype="buf", state=State.ALLOCATED, name_attr="addr", optional=True),
        ],
        produces=[
            ProduceSpec(
                rtype="mr",
                state=State.REGISTERED,
                name_attr="mr",
                metadata_fields=["id", "addr", "length"],
            ),
        ],
        transitions=[
            # No resource state transitions beyond producing the MR.
        ],
    )

    def __init__(self, id: str = None, mr: str = None, addr: str = None, length: int = None):
        if not id:
            raise ValueError("id (rdma_cm_id variable name) must be provided for RdmaRegWrite")
        if not mr:
            raise ValueError("mr (ibv_mr variable name) must be provided for RdmaRegWrite")

        # rdma_cm_id bound to a PD
        self.id = ResourceValue(resource_type="cm_id", value=id)

        # Destination MR pointer variable to receive the returned ibv_mr*
        self.mr = ResourceValue(resource_type="mr", value=mr, mutable=False)

        # Address and length to register
        # If the framework models buffers as resources, use ResourceValue; otherwise pass-through string.
        self.addr = ResourceValue(resource_type="buf", value=addr) if addr else "NULL"
        self.length = IntValue(length) if length is not None else "0"

    def apply(self, ctx: CodeGenContext):
        self.context = ctx
        if self.context:
            # Allocate the MR pointer in C
            self.context.alloc_variable(str(self.mr), "struct ibv_mr *", "NULL")

            # If context supports bindings/metadata for MR, attempt to record them (best-effort)
            if hasattr(self.context, "set_metadata"):
                try:
                    self.context.set_metadata(
                        str(self.mr),
                        {
                            "addr": str(self.addr),
                            "length": str(self.length),
                            "by": "rdma_reg_write",
                            "cm_id": str(self.id),
                        },
                    )
                except Exception:
                    pass

        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx):
        id_name = str(self.id)
        mr_name = str(self.mr)
        addr_expr = str(self.addr)
        length_expr = str(self.length)

        return f"""
    /* rdma_reg_write */
    IF_OK_PTR({id_name}, {{
        {mr_name} = rdma_reg_write({id_name}, {addr_expr}, (size_t){length_expr});
        if (!{mr_name}) {{
            fprintf(stderr, "rdma_reg_write failed: id=%s addr=%p len=%zu\\n", "{id_name}", (void*){addr_expr}, (size_t){length_expr});
        }} else {{
            fprintf(stderr, "rdma_reg_write OK: mr=%s lkey=0x%x rkey=0x%x addr=%p len=%zu\\n",
                    "{mr_name}", {mr_name}->lkey, {mr_name}->rkey, (void*){addr_expr}, (size_t){length_expr});
        }}
    }});
"""
