# -*- coding: utf-8 -*-
# rdma_resolve_addr modeling.
# Semantics:
#   rdma_resolve_addr maps a destination IP address (and optional source) to an RDMA device address.
#   On success, the rdma_cm_id becomes bound to a local RDMA device, and an address resolution event
#   (RDMA_CM_EVENT_ADDR_RESOLVED) will be generated asynchronously. This is typically followed by
#   rdma_resolve_route and rdma_connect on the active side.

"""
Python plugin modeling for RDMA CM API: rdma_resolve_addr

This plugin wraps rdma_resolve_addr into a VerbCall, integrates with the fuzzing framework's
resource state machine and emits C code to perform the operation.

Usage semantics:
- Requires a valid rdma_cm_id (created by rdma_create_id).
- Requires a destination sockaddr (IPv4/IPv6). Source sockaddr is optional (can be NULL).
- Binds the cm_id to a suitable RDMA device on success and triggers an async CM event.

Contract summary:
- Requires: cm_id in ALLOCATED, dst_addr (sockaddr) available.
- Transitions: cm_id from ALLOCATED -> USED (representing "bound to device / addr resolved submitted").

C generation:
- Emits a guarded call:
    IF_OK_PTR(cm_id, {
        int ret = rdma_resolve_addr(cm_id, src, dst, timeout_ms);
        if (ret) { ... }
    });
- src may be NULL; dst must be a valid struct sockaddr*.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    ConstantValue,
    IntValue,
    LocalResourceValue,
    OptionalValue,
    ResourceValue,
)
from lib.verbs import VerbCall


# Note: VerbCall is provided by the framework runtime.
class RdmaResolveAddr(VerbCall):
    MUTABLE_FIELDS = ["cm_id", "src_addr", "dst_addr", "timeout_ms"]

    # Contract:
    # - We require a cm_id that has been created (ALLOCATED).
    # - We require a destination sockaddr resource.
    # - Source sockaddr is optional (NULL allowed), so we do not require it.
    # - After submission, we consider the cm_id "USED" (bound to device / resolution started).
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="cm_id"),
            RequireSpec(rtype="sockaddr", state=State.ALLOCATED, name_attr="dst_addr"),
        ],
        produces=[],
        transitions=[
            TransitionSpec(
                rtype="cm_id",
                from_state=State.ALLOCATED,
                to_state=State.ADDR_RESOLVED,
                name_attr="cm_id",
            ),
        ],
    )

    def __init__(self, cm_id: str = None, dst_addr: str = None, src_addr: str = None, timeout_ms: int = 2000):
        """
        Args:
          cm_id: variable name of struct rdma_cm_id* (resource type: cm_id).
          dst_addr: variable name or expression of struct sockaddr* (resource type: sockaddr), destination address.
          src_addr: optional variable name or expression of struct sockaddr* (resource type: sockaddr), source address.
          timeout_ms: integer timeout for resolution.
        """
        if not cm_id:
            raise ValueError("cm_id must be provided for RdmaResolveAddr")
        if not dst_addr:
            raise ValueError("dst_addr must be provided for RdmaResolveAddr")

        # CM ID resource
        self.cm_id = ResourceValue(resource_type="cm_id", value=cm_id, mutable=False)  # 是否应该 mutable

        # Sockaddr resources. src is optional (NULL allowed).
        self.dst_addr = LocalResourceValue(resource_type="sockaddr", value=dst_addr)
        if src_addr:
            self.src_addr = OptionalValue(LocalResourceValue(resource_type="sockaddr", value=src_addr))
        else:
            self.src_addr = ConstantValue("NULL")

        # Timeout
        self.timeout_ms = IntValue(timeout_ms)

    def apply(self, ctx: CodeGenContext):
        # If any context-specific side effects are needed (like bindings), do them here.
        # For now, just apply the contract state changes.
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def _as_sockaddr_ptr(self, expr) -> str:
        s = str(expr)
        # Preserve NULL, otherwise cast to struct sockaddr*
        if s.strip() == "NULL":
            return "NULL"
        return f"(struct sockaddr*)({s})"

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.cm_id)
        src_expr = self._as_sockaddr_ptr(self.src_addr)
        dst_expr = self._as_sockaddr_ptr(self.dst_addr)
        timeout = str(self.timeout_ms)

        return f"""
    /* rdma_resolve_addr */
    IF_OK_PTR({id_name}, {{
        int ret_resolve_addr = rdma_resolve_addr({id_name}, {src_expr}, {dst_expr}, {timeout});
        if (ret_resolve_addr) {{
            fprintf(stderr, "rdma_resolve_addr failed for {id_name}: ret=%d errno=%d (%s)\\n",
                    ret_resolve_addr, errno, strerror(errno));
        }} else {{
            fprintf(stderr, "rdma_resolve_addr submitted for {id_name}, timeout={timeout} ms\\n");
        }}
    }});
"""
