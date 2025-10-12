# -*- coding: utf-8 -*-
"""
Model for RDMA CM API: rdma_post_readv

Semantics and usage:
- rdma_post_readv posts an RDMA READ work request on the QP associated with a given rdma_cm_id.
- It takes an array of local scatter-gather entries (struct ibv_sge), the number of SGEs, and send flags.
- The operation reads from the remote memory address (remote_addr) with the provided rkey into the local SGEs.
- Requirements:
  * The rdma_cm_id must have an associated QP in an operational state (typically RTS) and be connected to a remote peer.
  * The local buffers described by SGEs must be registered (have valid lkey) and accessible for local read.
  * The remote address and rkey must refer to a valid remote MR with sufficient access rights.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State
from lib.value import (
    ConstantValue,
    IntValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaPostReadv(VerbCall):
    """
    Python-side model for rdma_post_readv:
        static inline int rdma_post_readv(struct rdma_cm_id *id, void *context,
                                          struct ibv_sge *sgl, int nsge, int flags,
                                          uint64_t remote_addr, uint32_t rkey);

    Notes:
    - This wrapper expects that the rdma_cm_id is connected and has a valid QP bound.
    - You may pass a symbol for 'sgl' that refers to an existing 'struct ibv_sge []' in generated C,
      or leave it as None/"NULL" for fuzzing invalid inputs.
    - 'flags' should be a combination of IBV_SEND_* flags (e.g., IBV_SEND_SIGNALED, IBV_SEND_FENCE, IBV_SEND_SOLICITED, IBV_SEND_INLINE).
    """

    MUTABLE_FIELDS = ["id", "context", "sgl", "nsge", "flags", "remote_addr", "rkey"]

    # Build the contract dynamically to tolerate environments without a CONNECTED state constant.
    @staticmethod
    def _contract() -> Contract:
        connected_state = getattr(State, "CONNECTED", getattr(State, "USED", State.ALLOCATED))
        return Contract(
            requires=[
                # rdma_cm_id must be connected (or at least 'used' if CONNECTED isn't available in this environment)
                RequireSpec(rtype="cm_id", state=connected_state, name_attr="id"),
                # Optional: local memory registration requirements would apply to SGEs, but are not enforced here
                # because SGE arrays are typically plain C structs rather than tracked resources.
            ],
            produces=[
                # Posting a READ does not create new tracked resources.
            ],
            transitions=[
                # No resource state transitions are modeled for posting a read work request.
            ],
        )

    def __init__(
        self,
        id: str = None,
        context: str | int | None = None,
        sgl: str | None = None,
        nsge: int | None = None,
        flags: int | None = None,
        remote_addr: int | None = None,
        rkey: int | None = None,
    ):
        # rdma_cm_id resource (must be provided for a valid call; "NULL" allowed for fuzzing)
        self.id = ResourceValue(resource_type="cm_id", value=id) if id else "NULL"

        # opaque completion context cookie (void *). Allow integers or identifiers; default to NULL.
        if context is None:
            self.context = ConstantValue("NULL")
        else:
            # Let the underlying value system stringify properly; keep integers as immediates.
            self.context = IntValue(context) if isinstance(context, int) else ConstantValue(str(context))

        # SGE array symbol or NULL
        self.sgl = ConstantValue(str(sgl)) if sgl else ConstantValue("NULL")

        # Number of SGEs
        self.nsge = IntValue(nsge if nsge is not None else 0)

        # Send flags (IBV_SEND_*). Use IntValue for maximal flexibility in fuzzing.
        self.flags = IntValue(flags if flags is not None else 0)

        # Remote address and rkey
        self.remote_addr = IntValue(remote_addr if remote_addr is not None else 0)
        self.rkey = IntValue(rkey if rkey is not None else 0)

    def apply(self, ctx: CodeGenContext):
        # Register/prepare any contextual metadata if needed.
        # For now, there is nothing specific beyond contract application.
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_expr = str(self.id)
        context_expr = str(self.context)
        sgl_expr = str(self.sgl)
        nsge_expr = str(self.nsge)
        flags_expr = str(self.flags)
        remote_addr_expr = str(self.remote_addr)
        rkey_expr = str(self.rkey)

        # If the context is not NULL and looks like a small integer, cast it to a pointer-sized integer to void*
        # Otherwise pass it directly (e.g., a symbol or NULL).
        context_arg = f"(void*)(uintptr_t)({context_expr})" if context_expr not in ("NULL",) else "NULL"

        return f"""
    /* rdma_post_readv */
    IF_OK_PTR({id_expr}, {{
        int __rc = rdma_post_readv({id_expr}, {context_arg}, {sgl_expr}, {nsge_expr}, {flags_expr}, (uint64_t)({remote_addr_expr}), (uint32_t)({rkey_expr}));
        if (__rc) {{
            fprintf(stderr, "rdma_post_readv failed (rc=%d) id=%p nsge=%d flags=0x%x raddr=0x%lx rkey=0x%x\\n",
                    __rc, (void*){id_expr}, {nsge_expr}, {flags_expr}, (unsigned long){remote_addr_expr}, (unsigned){rkey_expr});
        }}
    }});
"""
