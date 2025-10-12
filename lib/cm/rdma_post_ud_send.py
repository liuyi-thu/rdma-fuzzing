# RDMA CM API modeling plugin for rdma_post_ud_send
# This plugin models the rdma_post_ud_send API, which posts a single Unreliable Datagram (UD) send
# on the QP associated with a given rdma_cm_id. It constructs and posts a send work request with
# a single SGE backed by the provided memory region (mr), and targets a destination via ibv_ah
# (address handle) and remote_qpn (remote queue pair number). Flags control send behavior
# (e.g., IBV_SEND_SIGNALED, IBV_SEND_INLINE).

"""
Plugin: RdmaPostUdSend
This file defines a Python class that models the RDMA CM API function:

    static inline int rdma_post_ud_send(struct rdma_cm_id *id,
                                        void *context,
                                        void *addr,
                                        size_t length,
                                        struct ibv_mr *mr,
                                        int flags,
                                        struct ibv_ah *ah,
                                        uint32_t remote_qpn);

Semantics:
- Posts a UD send WQE on the QP attached to the given rdma_cm_id.
- The WQE uses a single SGE described by (addr, length, mr).
- The destination is specified via an address handle (ah) and the remote QPN (remote_qpn).
- 'context' is an opaque pointer returned in CQE, and 'flags' are ibv send flags.

Usage:
- Requires a valid cm_id with a UD QP bound and in RTS state (semantically).
- Requires a registered memory region (mr) that covers the buffer [addr, addr+length).
- Requires a valid ibv_ah that resolves to the destination.
- remote_qpn must specify the destination UD QP number.

Contracts:
- This class integrates with the framework’s resource/state tracking to ensure preconditions
  (cm_id usable, mr registered, ah allocated) before generating C code that calls rdma_post_ud_send.
"""

from typing import Optional, Union

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State
from lib.value import (
    ConstantValue,
    FlagValue,
    IntValue,
    OptionalValue,
    ResourceValue,
)
from lib.verbs import VerbCall


# Note: VerbCall base is provided by the framework runtime.
class RdmaPostUdSend(VerbCall):
    """
    Model for rdma_post_ud_send:
    Posts a UD send WR using the cm_id's QP with the given SGE and destination information.

    Parameters:
    - id: resource name of struct rdma_cm_id * (must reference a cm_id with a UD QP)
    - context: optional opaque pointer for CQE completion context (any pointer or NULL)
    - addr: pointer to the buffer to send (must be within mr)
    - length: size_t number of bytes to send
    - mr: resource name of struct ibv_mr * (registered memory region for addr)
    - flags: ibv send flags (e.g., IBV_SEND_SIGNALED | IBV_SEND_INLINE)
    - ah: resource name of struct ibv_ah * (destination address handle)
    - remote_qpn: uint32_t remote QP number (destination UD QP)

    Contract requirements (semantic):
    - id: cm_id usable (has an associated QP; UD QP expected and in RTS)
    - mr: registered
    - ah: allocated
    """

    MUTABLE_FIELDS = ["id", "context", "addr", "length", "mr", "flags", "ah", "remote_qpn"]

    CONTRACT = Contract(
        requires=[
            # The cm_id should be allocated/usable; in practice, it should have a bound UD QP in RTS.
            RequireSpec(rtype="cm_id", state=State.USED, name_attr="id"),
            # Memory region must be registered (to back the SGE during send).
            RequireSpec(rtype="mr", state=State.REGISTERED, name_attr="mr"),
            # Address handle must be allocated/resolved.
            RequireSpec(rtype="ah", state=State.ALLOCATED, name_attr="ah"),
        ],
        produces=[
            # No new resources are produced by posting a send.
        ],
        transitions=[
            # Typically does not transition resource states; send uses existing resources.
        ],
    )

    def __init__(
        self,
        id: str,
        context: Optional[Union[str, int]] = None,
        addr: Optional[str] = None,
        length: Union[int, IntValue] = 0,
        mr: Optional[str] = None,
        flags: Optional[Union[int, str, FlagValue]] = 0,
        ah: Optional[str] = None,
        remote_qpn: Union[int, IntValue] = 0,
    ):
        if not id:
            raise ValueError("id (cm_id) must be provided for RdmaPostUdSend")
        if mr is None:
            raise ValueError("mr (memory region) must be provided for RdmaPostUdSend")
        if ah is None:
            raise ValueError("ah (address handle) must be provided for RdmaPostUdSend")
        if addr is None:
            raise ValueError("addr (data buffer pointer) must be provided for RdmaPostUdSend")
        if remote_qpn is None:
            raise ValueError("remote_qpn (destination QPN) must be provided for RdmaPostUdSend")

        # Resource bindings
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)
        self.mr = ResourceValue(resource_type="mr", value=mr)
        self.ah = ResourceValue(resource_type="ah", value=ah)

        # Data buffer and length
        # 'addr' is expected to be a C pointer expression or a variable name (e.g., buf_ptr).
        self.addr = ConstantValue(value=addr) if isinstance(addr, str) else ConstantValue(value="NULL")
        self.length = IntValue(value=length if isinstance(length, int) else int(str(length)))

        # Context is optional pointer passed back in completion; model as OptionalValue.
        if context is None:
            self.context = OptionalValue(None)
        else:
            # Allow passing either a variable name or integer castable to pointer.
            self.context = ConstantValue(value=str(context))

        # Flags can be integer or a FlagValue constructed elsewhere.
        if isinstance(flags, FlagValue):
            self.flags = flags
        elif isinstance(flags, int):
            self.flags = IntValue(value=flags)
        elif isinstance(flags, str):
            # Treat as raw C expression (e.g., "IBV_SEND_SIGNALED | IBV_SEND_INLINE")
            self.flags = ConstantValue(value=flags)
        else:
            self.flags = IntValue(value=0)

        # Destination QPN
        if isinstance(remote_qpn, IntValue):
            self.remote_qpn = remote_qpn
        elif isinstance(remote_qpn, int):
            self.remote_qpn = IntValue(value=remote_qpn)
        else:
            # Fallback: string/expression
            self.remote_qpn = ConstantValue(value=str(remote_qpn))

    def apply(self, ctx: CodeGenContext):
        # Bind into the generation context as needed; primary action is contract enforcement.
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)
        mr_name = str(self.mr)
        ah_name = str(self.ah)

        context_expr = (
            "NULL" if (isinstance(self.context, OptionalValue) and self.context.value is None) else str(self.context)
        )
        addr_expr = str(self.addr) if self.addr else "NULL"
        length_expr = str(self.length)
        flags_expr = str(self.flags)
        remote_qpn_expr = str(self.remote_qpn)

        return f"""
    /* rdma_post_ud_send */
    IF_OK_PTR({id_name}, {{
        IF_OK_PTR({mr_name}, {{
            IF_OK_PTR({ah_name}, {{
                int rc = rdma_post_ud_send({id_name}, {context_expr}, {addr_expr}, {length_expr}, {mr_name}, {flags_expr}, {ah_name}, {remote_qpn_expr});
                if (rc) {{
                    fprintf(stderr, "rdma_post_ud_send failed (id=%s, rc=%d)\\n", "{id_name}", rc);
                }}
            }});
        }});
    }});
"""
