# -*- coding: utf-8 -*-
# rdma_reject_ece CM API modeling plugin.
# Semantics: rdma_reject_ece is used by a server-side CM endpoint to reject an
# incoming connection request with ECE (Enhanced Connection Establishment) rejected reason.
# It is functionally equivalent to rdma_reject(), while marking the reject as ECE-related.
# Usage: invoke this on a cm_id that just received RDMA_CM_EVENT_CONNECT_REQUEST, optionally
# supplying small private data (<= 255 bytes) to return to the peer.

"""
Python plugin modeling rdma_reject_ece() for an RDMA verbs fuzzing framework.

This class wraps the RDMA CM API rdma_reject_ece(struct rdma_cm_id *id,
                                                 const void *private_data,
                                                 uint8_t private_data_len)
into a VerbCall-compatible object that can be sequenced by the Python layer and
emits C code to perform the actual operation at runtime.

Notes:
- private_data is optional; if provided, its length must fit in a uint8_t (<= 255).
- Intended to be used upon receiving RDMA_CM_EVENT_CONNECT_REQUEST on a passive (server) side cm_id.
"""

from typing import Optional, Union

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    IntValue,
    LocalResourceValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaRejectECE(VerbCall):
    """
    Model of rdma_reject_ece(id, private_data, private_data_len).

    Parameters:
    - id: resource name of the rdma_cm_id to reject (server-side request cm_id).
    - private_data: optional payload to send back to the peer:
        * bytes/bytearray: embedded as a static uint8_t array in generated C.
        * str: embedded as a static C string literal (sent as bytes).
        * LocalResourceValue/ResourceValue: treated as a pointer expression to an existing buffer.
        * None: no private data is sent; length=0.
    - private_data_len: optional explicit length (uint8_t). Required if private_data is a pointer
      (LocalResourceValue/ResourceValue). Ignored if private_data is bytes/str (computed automatically).

    Contract assumptions (lightweight):
    - Requires the cm_id to be allocated and to have a pending connect request (framework may refine).
    - Transitions the cm_id to a "used" state (framework can specialize to a REJECTED/ERROR state if defined).
    """

    MUTABLE_FIELDS = ["id", "private_data", "private_data_len"]

    # Minimal contract: require a cm_id allocated; mark it "used" after rejection.
    # Frameworks with richer CM states may refine from REQ_RCVD -> REJECTED.
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
        ],
        produces=[],  # rdma_reject_ece does not create new resources
        transitions=[
            TransitionSpec(rtype="cm_id", from_state=State.ALLOCATED, to_state=State.USED, name_attr="id"),
        ],
    )

    def __init__(
        self,
        id: str,
        private_data: Optional[Union[bytes, bytearray, str, LocalResourceValue, ResourceValue]] = None,
        private_data_len: Optional[int] = None,
    ):
        if not id:
            raise ValueError("id (cm_id resource name) must be provided for RdmaRejectECE")

        # cm_id resource handle (immutable by default)
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

        # Store private data and length; length is validated in generate_c()
        self.private_data = private_data
        self.private_data_len = IntValue(value=private_data_len) if private_data_len is not None else None

    def apply(self, ctx: CodeGenContext):
        # Apply contracts (state management and dependency checks)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT)

    def _c_ident_suffix(self, base_name: str) -> str:
        # Produce a sanitized suffix for C identifiers based on the resource name
        return "_" + base_name.replace("cm_id[", "").replace("]", "").replace("-", "_").replace(".", "_")

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)
        suffix = self._c_ident_suffix(id_name)

        # Determine private_data pointer expression and length expression
        init_lines = ""
        ptr_expr = "NULL"
        len_expr = "0"

        if self.private_data is None:
            # No payload
            ptr_expr = "NULL"
            len_expr = "0"

        elif isinstance(self.private_data, (LocalResourceValue, ResourceValue)):
            # Treat as pointer variable name/expression
            ptr_expr = str(self.private_data)
            if self.private_data_len is None:
                # If user didn't provide the length, default to 0 and warn in generated C
                init_lines += f"/* WARNING: private_data_len not provided for pointer {ptr_expr}; using 0 */\n"
                len_expr = "0"
            else:
                # Clamp to uint8_t range
                pd_len = int(self.private_data_len.value)
                if pd_len < 0:
                    pd_len = 0
                if pd_len > 255:
                    init_lines += f"/* WARNING: private_data_len={pd_len} exceeds uint8_t; clamped to 255 */\n"
                    pd_len = 255
                len_expr = f"{pd_len}"

        elif isinstance(self.private_data, (bytes, bytearray)):
            # Embed as a static uint8_t array
            b = bytes(self.private_data)
            pd_len = min(len(b), 255)
            if len(b) > 255:
                init_lines += f"/* WARNING: private_data size {len(b)} truncated to 255 bytes for uint8_t length */\n"
            array_init = ", ".join(str(x) for x in b[:pd_len])
            var_name = f"ece_priv{suffix}"
            init_lines += f"static const uint8_t {var_name}[] = {{ {array_init} }};\n"
            ptr_expr = var_name
            len_expr = f"{pd_len}"

        elif isinstance(self.private_data, str):
            # Embed as a static C string; send bytes as the literal content
            # Compute length in bytes (C will store it as char[])
            # We'll treat each char's ord value; ensure length fits uint8_t
            s = self.private_data
            # Escape backslashes and quotes for C
            escaped = (
                s.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t")
            )
            var_name = f"ece_str{suffix}"
            # Compute byte length as len of the original Python string (assuming ASCII-compatible usage).
            # For fuzzing purposes this is acceptable; users needing binary should pass bytes instead.
            pd_len = len(s)
            if pd_len > 255:
                init_lines += f"/* WARNING: private_data string length {pd_len} truncated to 255 for uint8_t */\n"
                pd_len = 255
            init_lines += f'static const char {var_name}[] = "{escaped}";\n'
            ptr_expr = var_name
            # Don't use sizeof(var_name)-1 to keep explicit clamp behavior consistent across backends.
            len_expr = f"{pd_len}"

        else:
            init_lines += "/* WARNING: Unsupported private_data type; sending no private data */\n"
            ptr_expr = "NULL"
            len_expr = "0"

        # Generate the C call. Wrap within IF_OK_PTR(id, {...}) as used by the framework.
        return f"""
    /* rdma_reject_ece */
    IF_OK_PTR({id_name}, {{
        {init_lines}
        int ret = rdma_reject_ece({id_name}, (const void *){ptr_expr}, (uint8_t)({len_expr}));
        if (ret) {{
            fprintf(stderr, "rdma_reject_ece failed on cm_id %s (ret=%d, errno=%d): %s\\n",
                    "{id_name}", ret, errno, strerror(errno));
        }} else {{
            fprintf(stderr, "rdma_reject_ece succeeded on cm_id %s\\n", "{id_name}");
        }}
    }});
"""
