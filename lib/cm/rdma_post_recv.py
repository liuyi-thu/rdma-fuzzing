# RDMA CM API modeling plugin: rdma_post_recv
# This plugin models rdma_post_recv, which posts a receive buffer to the QP associated
# with a given rdma_cm_id. It wraps the API to integrate with the fuzzing framework,
# handling resource contracts and C code generation. The call enqueues a receive WR
# using the provided memory region (mr), buffer pointer (addr), and length. The user
# context (wr_context) is stored as the wr_id for CQ completions.

"""
Plugin for modeling the RDMA CM API rdma_post_recv:

    int rdma_post_recv(struct rdma_cm_id *id, void *context, void *addr, size_t length, struct ibv_mr *mr);

Semantics:
- Posts a receive work request to the receive queue of the QP associated with the rdma_cm_id.
- 'context' (wr_context) is an opaque pointer stored as wr_id, retrievable upon CQ completion.
- 'addr' must point to a buffer registered by 'mr', and 'length' must not exceed the MR's size.
- Requires that an RDMA QP has been created and associated with the cm_id (e.g., via rdma_create_qp).
- Typically used before connecting/accepting to ensure receives are available for incoming messages.

Contract assumptions for fuzzing:
- cm_id and mr must be allocated/valid in the framework.
- This call does not create new resources; it transitions cm_id and mr into a "used" state to reflect activity.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    IntValue,
    LocalResourceValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaPostRecv(VerbCall):
    """
    Model of rdma_post_recv:
        rdma_post_recv(id, wr_context, addr, length, mr)

    Parameters:
    - id: name of the rdma_cm_id resource (string)
    - wr_context: a local identifier/pointer used as wr_id for CQE context (string or None)
    - addr: C identifier to a buffer pointer (string), must be in the range of 'mr'
    - length: integer bytes to receive
    - mr: name of the ibv_mr resource (string)
    """

    MUTABLE_FIELDS = ["id", "wr_context", "addr", "length", "mr"]

    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
            RequireSpec(rtype="mr", state=State.ALLOCATED, name_attr="mr"),
        ],
        produces=[],
        transitions=[
            TransitionSpec(rtype="cm_id", from_state=State.ALLOCATED, to_state=State.USED, name_attr="id"),
            TransitionSpec(rtype="mr", from_state=State.ALLOCATED, to_state=State.USED, name_attr="mr"),
        ],
    )

    def __init__(
        self,
        id: str,
        wr_context: str = None,
        addr: str = None,
        length: int = None,
        mr: str = None,
    ):
        if not id:
            raise ValueError("id (cm_id resource name) must be provided for RdmaPostRecv")
        if not addr:
            raise ValueError("addr (buffer pointer identifier) must be provided for RdmaPostRecv")
        if length is None:
            raise ValueError("length must be provided for RdmaPostRecv")
        if not mr:
            raise ValueError("mr (ibv_mr resource name) must be provided for RdmaPostRecv")

        # Resource bindings
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)
        # wr_context is a local pointer-like value; NULL if not provided
        self.wr_context = LocalResourceValue(resource_type="wr_context", value=wr_context) if wr_context else "NULL"
        # addr is a local pointer into registered memory
        self.addr = LocalResourceValue(resource_type="buffer", value=addr)
        self.length = IntValue(length)
        self.mr = ResourceValue(resource_type="mr", value=mr, mutable=False)

    def apply(self, ctx: CodeGenContext):
        # Contract application and any context bookkeeping hooks
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

        # Optional: track that a receive was posted for this cm_id (if the context supports it)
        if hasattr(ctx, "on_post_recv"):
            try:
                ctx.on_post_recv(str(self.id), str(self.addr), int(str(self.length)), str(self.mr))
            except Exception:
                pass  # Best-effort: context may not implement this hook

    def generate_c(self, ctx: CodeGenContext):
        id_name = str(self.id)
        mr_name = str(self.mr)
        addr_expr = str(self.addr)
        len_expr = str(self.length)
        wr_ctx_expr = str(self.wr_context) if isinstance(self.wr_context, LocalResourceValue) else "NULL"

        return f"""
    /* rdma_post_recv */
    IF_OK_PTR({id_name}, {{
        IF_OK_PTR({mr_name}, {{
            int rc = rdma_post_recv({id_name}, {wr_ctx_expr}, {addr_expr}, (size_t){len_expr}, {mr_name});
            if (rc) {{
                fprintf(stderr, "rdma_post_recv failed: id={id_name}, length=%zu\\n", (size_t){len_expr});
            }} else {{
                /* Successfully posted a receive WR on id={id_name} (len=%zu) */ 
            }}
        }});
    }});
"""
