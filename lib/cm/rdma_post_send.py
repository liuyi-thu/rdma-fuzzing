# Model for RDMA CM API rdma_post_send: posts a send work request on the QP associated with an rdma_cm_id.
# It uses a single SGE derived from (addr, length, mr). The 'context' is stored as the wr_id for completions.
# Typical flags include IBV_SEND_SIGNALED, IBV_SEND_SOLICITED, IBV_SEND_INLINE, IBV_SEND_FENCE, etc.

"""
Plugin modeling the RDMA CM API `rdma_post_send`.

Function prototype:
    static inline int rdma_post_send(struct rdma_cm_id *id, void *context, void *addr,
                                     size_t length, struct ibv_mr *mr, int flags);

Semantics:
- Posts a send WR to the QP associated with the given cm_id.
- A single SGE is formed using addr, length, and mr->lkey.
- The 'context' pointer is propagated as the WR ID (wr_id) for the resulting completion.
- 'flags' are standard ibverbs send flags (e.g., IBV_SEND_SIGNALED, IBV_SEND_INLINE, ...).

This plugin provides a high-level model with:
- Contract requirements on cm_id and mr resources.
- Code generation that safely defaults addr/length from mr if not explicitly provided.
- Configurable send flags for fuzzing different behaviors.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    ConstantValue,
    FlagValue,
    IntValue,
    OptionalValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaPostSend(VerbCall):
    """
    Model for rdma_post_send:
        rdma_post_send(id, context, addr, length, mr, flags)

    Parameters:
    - id: Name of the rdma_cm_id resource.
    - context: Optional user context stored as wr_id (void*). If omitted, NULL is used.
    - addr: Optional data buffer address. If omitted and mr is provided, mr->addr is used.
    - length: Optional data length. If omitted and mr is provided, mr->length is used.
    - mr: Name of the ibv_mr resource describing the buffer.
    - flags: Send flags (IBV_SEND_*). Defaults to IBV_SEND_SIGNALED.
    """

    MUTABLE_FIELDS = ["id", "context", "addr", "length", "mr", "flags"]

    # Contract:
    # - Require a connected cm_id (ready to send on its QP).
    # - Require a registered MR (buffer must be registered for posting).
    # - Transition MR to USED to indicate this operation consumes/uses the MR.
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.CONNECTED, name_attr="id"),
            RequireSpec(rtype="mr", state=State.REGISTERED, name_attr="mr"),
        ],
        produces=[],
        transitions=[
            TransitionSpec(rtype="mr", from_state=State.REGISTERED, to_state=State.USED, name_attr="mr"),
        ],
    )

    # Allowed send flags for fuzzing. This set covers common flags usable with send WRs.
    _ALLOWED_FLAGS = [
        "IBV_SEND_SIGNALED",
        "IBV_SEND_SOLICITED",
        "IBV_SEND_INLINE",
        "IBV_SEND_FENCE",
        "IBV_SEND_IP_CSUM",
        "IBV_SEND_PAD",
    ]

    def __init__(
        self,
        id: str,
        context: int | str | None = None,
        addr: str | None = None,
        length: int | None = None,
        mr: str | None = None,
        flags: int | str | list[str] | None = None,
    ):
        if not id:
            raise ValueError("id (rdma_cm_id name) must be provided for RdmaPostSend")

        # rdma_cm_id resource (must be connected)
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

        # MR resource (registered)
        self.mr = ResourceValue(resource_type="mr", value=mr) if mr else "NULL"

        # Optional context is stored as wr_id in the completion.
        # The framework will allow setting it to integers or symbolic pointers.
        self.context = (
            OptionalValue(IntValue(value=context) if isinstance(context, int) else ConstantValue(value=context))
            if context is not None
            else "NULL"
        )

        # Optional explicit addr. If not provided, will use mr->addr if available.
        self.addr = OptionalValue(ConstantValue(value=addr)) if addr is not None else None

        # Optional explicit length. If not provided, will use mr->length if available.
        self.length = OptionalValue(IntValue(value=length)) if length is not None else None

        # Flags: allow either an int, a single string, or a list of strings.
        # Default to IBV_SEND_SIGNALED to get completions for testing.
        if flags is None:
            flags = ["IBV_SEND_SIGNALED"]
        self.flags = FlagValue(flags=flags, allowed_flags=self._ALLOWED_FLAGS)

    def apply(self, ctx: CodeGenContext):
        # Apply resource contracts to ensure the operation's pre/post state is tracked
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)
        mr_name = str(self.mr) if self.mr != "NULL" else "NULL"

        # Resolve addr and length expressions.
        if self.addr is not None:
            addr_expr = str(self.addr)
        else:
            # Default: use mr->addr when MR is non-NULL, else NULL
            addr_expr = f"({mr_name} ? {mr_name}->addr : NULL)"

        if self.length is not None:
            length_expr = str(self.length)
        else:
            # Default: use mr->length when MR is non-NULL, else 0
            length_expr = f"({mr_name} ? {mr_name}->length : 0)"

        flags_expr = str(self.flags) if self.flags is not None else "0"
        context_expr = str(self.context) if self.context != "NULL" else "NULL"

        return f"""
    /* rdma_post_send */
    IF_OK_PTR({id_name}, {{
        void *wr_ctx = {context_expr};
        void *buf_addr = (void*)({addr_expr});
        size_t buf_len = (size_t)({length_expr});
        struct ibv_mr *mr_ptr = {mr_name};
        int send_flags = {flags_expr};

        int rc = rdma_post_send({id_name}, wr_ctx, buf_addr, buf_len, mr_ptr, send_flags);
        if (rc) {{
            fprintf(stderr, "rdma_post_send(id=%s) failed: %d\\n", "{id_name}", rc);
        }} else {{
            fprintf(stdout, "rdma_post_send(id=%s) posted: addr=%p len=%zu flags=0x%x\\n",
                    "{id_name}", buf_addr, buf_len, send_flags);
        }}
    }});
"""
