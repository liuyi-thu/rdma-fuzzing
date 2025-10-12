# RDMA CM API: rdma_reg_msgs
# Semantics:
#   rdma_reg_msgs registers a buffer for message-based send/recv operations using the
#   protection domain associated with an rdma_cm_id. It's a convenience wrapper around
#   ibv_reg_mr(id->pd, addr, length, IBV_ACCESS_LOCAL_WRITE). On success, it returns
#   a pointer to an ibv_mr for the given address range; otherwise, it returns NULL.
"""
Plugin modeling for RDMA CM API rdma_reg_msgs.

This plugin wraps the rdma_reg_msgs() call into a VerbCall subclass to integrate with
the fuzzing framework. It accepts an rdma_cm_id, a buffer address, and length, and
produces an ibv_mr resource upon successful registration.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, RequireSpec, State
from lib.value import (
    IntValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaRegMsgs(VerbCall):
    """
    Model of:
        static inline struct ibv_mr * rdma_reg_msgs(struct rdma_cm_id *id, void *addr, size_t length);

    Parameters:
        id:        Name of the rdma_cm_id resource variable.
        mr:        Name of the ibv_mr output variable to hold the registered MR.
        addr:      C expression or variable name pointing to the buffer to register.
        length:    Size of the buffer (int or C expression).

    Notes:
        - The rdma_cm_id must have an associated PD (e.g., via rdma_create_qp or rdma_create_ep),
          otherwise the call will fail.
        - This wrapper implies IBV_ACCESS_LOCAL_WRITE semantics (as per rdma_reg_msgs).
    """

    MUTABLE_FIELDS = ["id", "mr", "addr", "length"]

    CONTRACT = Contract(
        requires=[
            # The cm_id must at least be allocated and valid; additionally it must have a PD associated,
            # which is typically achieved via rdma_create_qp/rdma_create_ep. We conservatively require ALLOCATED.
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
        ],
        produces=[
            # Produce an MR in ALLOCATED/REGISTERED-like state. Using ALLOCATED for generality.
            ProduceSpec(rtype="mr", state=State.ALLOCATED, name_attr="mr", metadata_fields=["id"]),
        ],
        transitions=[
            # No explicit state change for cm_id here.
        ],
    )

    def __init__(self, id: str = None, mr: str = None, addr: str = "NULL", length=None):
        if not mr:
            raise ValueError("mr must be provided for RdmaRegMsgs")

        # Inputs
        self.id = ResourceValue(resource_type="cm_id", value=id) if id else "NULL"
        self.addr = addr  # raw C expression or variable name

        # Output MR (immutable name binding)
        self.mr = ResourceValue(resource_type="mr", value=mr, mutable=False)

        # Length handling (allow raw expression or int)
        if isinstance(length, int):
            self.length = IntValue(value=length)
        elif isinstance(length, str):
            # treat as C expression
            self.length = length
        elif length is None:
            # default to 0 to keep call syntactically valid; likely to fail at runtime if used
            self.length = IntValue(value=0)
        else:
            # Already a Value type or something representing an expression
            self.length = length

        self.context = None

    def apply(self, ctx: CodeGenContext):
        self.context = ctx

        # Allocate the MR variable in the generated C code
        if self.context:
            self.context.alloc_variable(str(self.mr), "struct ibv_mr *", "NULL")

        # Apply contracts if the framework has contract handling
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext):
        id_name = str(self.id)
        mr_name = str(self.mr)
        addr_expr = self.addr if isinstance(self.addr, str) else str(self.addr)
        length_expr = str(self.length)

        return f"""
    /* rdma_reg_msgs */
    IF_OK_PTR({id_name}, {{
        {mr_name} = rdma_reg_msgs({id_name}, {addr_expr}, {length_expr});
        if (!{mr_name}) {{
            fprintf(stderr, "rdma_reg_msgs failed: id=%p addr=%p len=%zu\\n", (void*){id_name}, (void*)({addr_expr}), (size_t)({length_expr}));
        }}
    }});
"""
