# -*- coding: utf-8 -*-
"""
Model for rdma_post_read CM API.

Semantics:
- rdma_post_read posts an RDMA READ work request on the QP associated with a given rdma_cm_id.
- It reads data from the remote memory region (specified via remote_addr and rkey) into a local
  buffer (addr, length) which must be covered by a registered local MR (mr).
- This helper wraps the construction of an RDMA READ send WR and posts it via the CM-managed QP.
- Requires a connected rdma_cm_id (QP in RTS and CM connection established) and a valid local MR.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State
from lib.value import (
    ConstantValue,
    IntValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaPostRead(VerbCall):
    """
    Python modeling for the CM API:
      int rdma_post_read(struct rdma_cm_id *id, void *context, void *addr, size_t length,
                         struct ibv_mr *mr, int flags, uint64_t remote_addr, uint32_t rkey);

    Notes:
    - If addr is not provided, it defaults to mr->addr.
    - If length is not provided, it defaults to mr->length.
    - flags can include standard ibv_send_flags (e.g., IBV_SEND_SIGNALED, IBV_SEND_INLINE, etc.).
    """

    MUTABLE_FIELDS = ["id", "user_context", "addr", "length", "mr", "flags", "remote_addr", "rkey"]

    # Conservative contract: requires a CM ID and a registered MR to back the local buffer.
    # We use generic states that are likely present in the harness; adjust as your framework evolves.
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.USED, name_attr="id"),
            RequireSpec(rtype="mr", state=State.ALLOCATED, name_attr="mr"),
        ],
        produces=[],
        transitions=[],
    )

    def __init__(
        self,
        id: str = None,
        user_context=None,
        addr=None,
        length: int | None = None,
        mr: str | None = None,
        flags=None,
        remote_addr=None,
        rkey=None,
    ):
        """
        Parameters:
        - id: variable name of struct rdma_cm_id* resource (string). Required for this call to be meaningful.
        - user_context: opaque void* work request context; can be an integer address or a C identifier string.
        - addr: local buffer pointer; if None, defaults to mr->addr.
        - length: local buffer size; if None, defaults to mr->length.
        - mr: variable name of struct ibv_mr* resource for local buffer. Required by rdma_post_read.
        - flags: send flags (int or C expression string).
        - remote_addr: 64-bit remote virtual address (int or C expression string).
        - rkey: 32-bit remote rkey (int or C expression string).
        """
        # CM ID resource
        self.id = ResourceValue(resource_type="cm_id", value=id) if id else "NULL"

        # Opaque context pointer for WR
        if user_context is None:
            self.user_context = ConstantValue("NULL")
        elif isinstance(user_context, str):
            self.user_context = ConstantValue(user_context)
        else:
            # Treat numeric as integer literal
            self.user_context = IntValue(user_context)

        # Local buffer pointer; may be None -> mr->addr
        if addr is None:
            self.addr = None
        elif isinstance(addr, str):
            self.addr = ConstantValue(addr)
        else:
            self.addr = IntValue(addr)

        # Local buffer length; may be None -> mr->length
        self.length = (
            IntValue(length)
            if isinstance(length, int)
            else (ConstantValue(length) if isinstance(length, str) else None)
        )

        # Local MR resource
        self.mr = ResourceValue(resource_type="mr", value=mr) if mr else "NULL"

        # Send flags
        if flags is None:
            self.flags = IntValue(0)
        elif isinstance(flags, int):
            self.flags = IntValue(flags)
        else:
            self.flags = ConstantValue(flags)

        # Remote address and rkey
        if remote_addr is None:
            self.remote_addr = IntValue(0)
        elif isinstance(remote_addr, int):
            self.remote_addr = IntValue(remote_addr)
        else:
            self.remote_addr = ConstantValue(remote_addr)

        if rkey is None:
            self.rkey = IntValue(0)
        elif isinstance(rkey, int):
            self.rkey = IntValue(rkey)
        else:
            self.rkey = ConstantValue(rkey)

    def apply(self, ctx: CodeGenContext):
        # No specific local bindings are needed, but we respect the contract system if enabled.
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext):
        id_name = str(self.id)
        mr_name = str(self.mr)
        # Default expressions for addr/length if not explicitly provided
        addr_expr = str(self.addr) if self.addr is not None else f"({mr_name} ? {mr_name}->addr : NULL)"
        length_expr = str(self.length) if self.length is not None else f"({mr_name} ? {mr_name}->length : 0)"
        ctx_expr = str(self.user_context)
        flags_expr = str(self.flags)
        remote_addr_expr = str(self.remote_addr)
        rkey_expr = str(self.rkey)

        return f"""
    /* rdma_post_read */
    IF_OK_PTR({id_name}, {{
        void * __rdma_read_addr = {addr_expr};
        size_t __rdma_read_len = {length_expr};
        int __rdma_read_rc = -1;

        if (__rdma_read_addr && __rdma_read_len > 0 && {mr_name}) {{
            __rdma_read_rc = rdma_post_read(
                                {id_name},
                                {ctx_expr},
                                __rdma_read_addr,
                                __rdma_read_len,
                                {mr_name},
                                {flags_expr},
                                (uint64_t){remote_addr_expr},
                                (uint32_t){rkey_expr});
            if (__rdma_read_rc) {{
                fprintf(stderr, "rdma_post_read failed: rc=%d (id=%p, addr=%p, len=%zu, mr=%p, raddr=0x%lx, rkey=0x%x)\\n",
                        __rdma_read_rc, (void*){id_name}, __rdma_read_addr, __rdma_read_len,
                        (void*){mr_name}, (unsigned long){remote_addr_expr}, (unsigned int){rkey_expr});
            }}
        }} else {{
            fprintf(stderr, "rdma_post_read skipped: invalid local buffer or MR (addr=%p, len=%zu, mr=%p)\\n",
                    __rdma_read_addr, __rdma_read_len, (void*){mr_name});
        }}
    }});
"""
