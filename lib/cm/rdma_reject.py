# rdma_reject CM API modeling
# This plugin models the RDMA CM API rdma_reject(), which is called on the listening/passive side
# to reject an incoming connection request (RDMA_CM_EVENT_CONNECT_REQUEST) or datagram service
# lookup. Optionally, a small private data payload (0-255 bytes) can be sent to the remote peer
# along with the reject message.

from typing import List, Optional, Union

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, InstantiatedContract, RequireSpec, State, TransitionSpec
from lib.value import (
    IntValue,
    LocalResourceValue,
    OptionalValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaReject(VerbCall):
    """
    Model for rdma_reject(struct rdma_cm_id *id, const void *private_data, uint8_t private_data_len)

    Semantics:
      - Send a rejection for an incoming connection or datagram lookup request.
      - May include optional private data (transport dependent, up to 255 bytes).
      - Typically used after receiving RDMA_CM_EVENT_CONNECT_REQUEST on the server side.

    Notes:
      - The rdma_cm_id used here generally represents the newly created connection request id
        (not the listening id). After rejecting, users normally ACK the CM event and destroy
        the request id, but those steps are modeled by other calls in this framework.
    """

    MUTABLE_FIELDS = ["id", "private_data", "private_data_len"]

    # Contract assumptions for fuzzing framework:
    # - We require a valid cm_id allocated (the id associated with the incoming request).
    # - After calling rdma_reject, we mark the cm_id as USED (reflecting it has been acted upon).
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
        ],
        produces=[],
        transitions=[
            TransitionSpec(rtype="cm_id", from_state=State.ALLOCATED, to_state=State.USED, name_attr="id"),
        ],
    )

    def __init__(
        self,
        id: str,
        private_data: Optional[Union[bytes, bytearray, List[int]]] = None,
        private_data_len: Optional[int] = None,
    ):
        if not id:
            raise ValueError("id must be provided for RdmaReject")

        # rdma_cm_id resource
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

        # Prepare optional private data
        # We will materialize it as a local buffer in generated C if provided.
        self._priv_bytes: Optional[List[int]] = None
        self._priv_buf_name: Optional[str] = None

        if private_data is None:
            # No private data
            self.private_data = OptionalValue(value="NULL")
            self.private_data_len = IntValue(value=int(private_data_len or 0))
        else:
            # Normalize to list of uint8 values
            if isinstance(private_data, (bytes, bytearray)):
                b_list = list(private_data)
            else:
                b_list = list(private_data)

            # Infer/adjust length
            inferred_len = len(b_list)
            if private_data_len is None:
                pd_len = inferred_len
            else:
                pd_len = int(private_data_len)

            # rdma_reject uses uint8_t for length; clamp to [0, 255]
            if pd_len < 0:
                pd_len = 0
            if pd_len > 255:
                pd_len = 255

            # Fit the data to pd_len: truncate or pad with zeros
            if inferred_len >= pd_len:
                b_list = b_list[:pd_len]
            else:
                b_list = b_list + [0] * (pd_len - inferred_len)

            # Save for codegen
            self._priv_bytes = [int(x) & 0xFF for x in b_list]

            # Create a deterministic local buffer name based on id
            sanitized = str(self.id).replace("[", "_").replace("]", "").replace(".", "_")
            self._priv_buf_name = f"reject_priv_{sanitized}"

            # Set values used for codegen
            self.private_data = LocalResourceValue(resource_type="buffer", value=self._priv_buf_name)
            self.private_data_len = IntValue(value=pd_len)

    def apply(self, ctx: CodeGenContext):
        # Register local variable names etc. if needed
        self.context = ctx

        # If we plan to reference a local buffer, let the context know about the symbol.
        if isinstance(self.private_data, LocalResourceValue):
            # We do not assign an initial value here; the actual array definition will be emitted in generate_c.
            ctx.alloc_variable(str(self.private_data), "const void *", "NULL")

        # Apply contract semantics (resource state transitions)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)
        pdata_expr = "NULL"
        plen_expr = f"(uint8_t){int(self.private_data_len)}"

        # Emit a static buffer for private data if provided
        priv_def_code = ""
        if isinstance(self.private_data, LocalResourceValue) and self._priv_bytes is not None:
            buf_name = str(self.private_data)
            byte_list = ", ".join(f"0x{b:02x}" for b in self._priv_bytes)
            priv_def_code = f"static uint8_t {buf_name}[{int(self.private_data_len)}] = {{ {byte_list} }};\n"
            pdata_expr = buf_name
        else:
            pdata_expr = "NULL"
            plen_expr = "(uint8_t)0"

        # Compose C code for rdma_reject
        code = f"""
    /* rdma_reject: reject a connection/datagram request, optionally with private data */
    IF_OK_PTR({id_name}, {{
        {priv_def_code}int rc = rdma_reject({id_name}, {pdata_expr}, {plen_expr});
        if (rc) {{
            fprintf(stderr, "rdma_reject failed on %s (rc=%d)\\n", "{id_name}", rc);
        }} else {{
            fprintf(stderr, "rdma_reject succeeded on %s\\n", "{id_name}");
        }}
    }});
"""

        return code

    def instantiate_contract(self) -> InstantiatedContract:
        # Bridge to framework if needed; in many cases, the static CONTRACT is enough.
        return InstantiatedContract.from_contract(self.CONTRACT)
