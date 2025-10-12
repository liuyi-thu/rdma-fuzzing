# rdma_post_write plugin
# Semantic overview:
#   rdma_post_write posts an RDMA Write work request on the QP associated with a given rdma_cm_id.
#   It is a convenience helper from librdmacm that wraps ibv_post_send with IBV_WR_RDMA_WRITE.
#   Parameters:
#     - id: RDMA CM identifier which has an associated QP in RTS/connected state
#     - context: user context passed back in CQEs
#     - addr/length/mr: local buffer, length, and registered MR (lkey from mr is used)
#     - flags: ibv_send_flags (e.g., IBV_SEND_SIGNALED | IBV_SEND_INLINE | IBV_SEND_FENCE | IBV_SEND_SOLICITED)
#     - remote_addr/rkey: remote virtual address and rkey describing the remote MR to write into
#   Returns 0 on success, or -1 with errno set on failure.

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    ConstantValue,
    FlagValue,
    IntValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaPostWrite(VerbCall):
    """
    Python wrapper for librdmacm rdma_post_write, generating corresponding C code.

    static inline int rdma_post_write(struct rdma_cm_id *id,
                                      void *context,
                                      void *addr,
                                      size_t length,
                                      struct ibv_mr *mr,
                                      int flags,
                                      uint64_t remote_addr,
                                      uint32_t rkey);
    """

    MUTABLE_FIELDS = ["id", "context_ptr", "addr", "length", "mr", "flags", "remote_addr", "rkey"]

    # Contract assumptions:
    # - cm_id exists (ALLOCATED) and is associated with a QP in a usable state (not modeled here beyond ALLOCATED)
    # - mr is registered to the device (REGISTERED) when provided
    # - posting a write "uses" the MR (transition to USED) to reflect that it has been referenced by a WR
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
            RequireSpec(rtype="mr", state=State.REGISTERED, name_attr="mr"),
        ],
        produces=[
            # rdma_post_write does not produce new resources
        ],
        transitions=[
            TransitionSpec(rtype="mr", from_state=State.REGISTERED, to_state=State.USED, name_attr="mr"),
        ],
    )

    def __init__(
        self,
        id: str,
        context_ptr: str = None,
        addr: str = None,
        length: int = None,
        mr: str = None,
        flags=None,
        remote_addr: int = None,
        rkey: int = None,
    ):
        """
        Parameters:
          - id: resource name of rdma_cm_id
          - context_ptr: C expression for void* user context (default NULL)
          - addr: C expression for local buffer pointer; if None, mr->addr will be used
          - length: size_t length; if None, mr->length will be used
          - mr: resource name of ibv_mr used for lkey and optionally addr/length
          - flags: iterable or expression for ibv_send_flags; default IBV_SEND_SIGNALED
          - remote_addr: uint64_t remote VA
          - rkey: uint32_t remote key
        """
        if not id:
            raise ValueError("id (cm_id resource name) must be provided for RdmaPostWrite")

        # Resources and values
        self.id = ResourceValue(resource_type="cm_id", value=id)

        self.context_ptr = ConstantValue("NULL") if context_ptr is None else IntValue(value=context_ptr, ctype="void*")

        # addr and length default to MR's addr/length if not explicitly provided
        self.addr = None if addr is None else IntValue(value=addr, ctype="void*")
        self.length = None if length is None else IntValue(value=length, ctype="size_t")

        # MR is generally required for lkey; make optional in Python but contract expects REGISTERED
        if not mr:
            raise ValueError("mr (ibv_mr resource name) must be provided for RdmaPostWrite")
        self.mr = ResourceValue(resource_type="mr", value=mr)

        # Flags default to IBV_SEND_SIGNALED to ensure CQE generation
        allowed_flags = {
            "IBV_SEND_FENCE",
            "IBV_SEND_SIGNALED",
            "IBV_SEND_SOLICITED",
            "IBV_SEND_INLINE",
        }
        if flags is None:
            self.flags = FlagValue(enum_name="ibv_send_flags", value=["IBV_SEND_SIGNALED"], allowed=allowed_flags)
        else:
            # Allow either an iterable of flags or a raw expression
            if isinstance(flags, (list, tuple, set)):
                self.flags = FlagValue(enum_name="ibv_send_flags", value=list(flags), allowed=allowed_flags)
            else:
                # treat as raw C expression
                self.flags = IntValue(value=str(flags), ctype="int")

        # Remote addressing
        if remote_addr is None:
            self.remote_addr = IntValue(value="0ULL", ctype="uint64_t")
        else:
            self.remote_addr = IntValue(value=remote_addr, ctype="uint64_t")

        if rkey is None:
            self.rkey = IntValue(value="0u", ctype="uint32_t")
        else:
            self.rkey = IntValue(value=rkey, ctype="uint32_t")

    def apply(self, ctx: CodeGenContext):
        # No local allocations required for rdma_post_write; just enforce contracts
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext):
        id_name = str(self.id)
        mr_name = str(self.mr)

        # Build expressions for addr and length with sensible defaults to MR fields
        if self.addr is None:
            addr_expr = f"({mr_name} ? {mr_name}->addr : NULL)"
        else:
            addr_expr = str(self.addr)

        if self.length is None:
            length_expr = f"({mr_name} ? {mr_name}->length : 0)"
        else:
            length_expr = str(self.length)

        flags_expr = str(self.flags)
        context_expr = str(self.context_ptr)
        remote_addr_expr = str(self.remote_addr)
        rkey_expr = str(self.rkey)

        return f"""
    /* rdma_post_write */
    IF_OK_PTR({id_name}, {{
        int rc_rpw = rdma_post_write({id_name},
                                     (void*)({context_expr}),
                                     (void*)({addr_expr}),
                                     (size_t)({length_expr}),
                                     {mr_name},
                                     {flags_expr},
                                     (uint64_t)({remote_addr_expr}),
                                     (uint32_t)({rkey_expr}));
        if (rc_rpw) {{
            fprintf(stderr, "rdma_post_write(id={id_name}) failed: %s\\n", strerror(errno));
        }} else {{
            VERBOSE_LOG("rdma_post_write(id={id_name}, addr=%p, len=%zu, raddr=0x%lx, rkey=0x%x, flags=0x%x) posted",
                        (void*)({addr_expr}), (size_t)({length_expr}),
                        (unsigned long)({remote_addr_expr}), (unsigned)({rkey_expr}), (unsigned)({flags_expr}));
        }}
    }});
"""
