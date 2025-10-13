# rdma_conn_param model for RDMA CM API
# This plugin models the rdma_conn_param structure used in RDMA Connection Manager (CM) for
# connection requests and replies. It encapsulates parameters like private_data payload,
# resource depths, flow control, retry counts, and optional SRQ/QP number hints.
# Note:
# - retry_count is ignored when accepting a connection on the passive side.
# - srq and qp_num are ignored if a QP is created on the rdma_cm_id by the CM.
# - private_data is an optional opaque payload propagated by CM; private_data_len must match.

"""
Python model for struct rdma_conn_param.

This class wraps CM connection parameters for rdma_connect/rdma_accept and friends,
and emits corresponding C code that initializes a struct rdma_conn_param instance.

Fields:
- private_data: opaque application-defined bytes (None or bytes/bytearray/list[int])
- private_data_len: length of private_data (uint8_t). If private_data is provided and
  private_data_len is omitted, the plugin uses the full buffer size. If private_data
  is omitted but private_data_len is provided, a zero-initialized buffer of that size
  is emitted.
- responder_resources: device resources responder will provide (uint8_t)
- initiator_depth: maximum outstanding RDMA read/atomic for initiator (uint8_t)
- flow_control: enable CM-managed flow control (uint8_t, boolean-like)
- retry_count: path retries for CM (uint8_t). Ignored during accept.
- rnr_retry_count: RNR retry count (uint8_t)
- srq: indicates SRQ usage (uint8_t, boolean-like). Ignored if CM creates the QP.
- qp_num: explicit QP number if not using CM-created QP (uint32_t)

Behavior:
- Emits a memset to zero the struct.
- Emits a static/private buffer for private_data if provided, with length handling.
- Enforces reasonable defaults for fields if not specified.
"""

from typing import Optional, Sequence, Union

# These imports assume the framework layout; provide fallbacks for standalone usage.
try:
    from .base import Attr
    from .codegen import emit_assign
    from .values import IntValue, OptionalValue
except ImportError:
    # Fallbacks for environments where relative imports are not available.
    from base import Attr
    from codegen import emit_assign
    from values import IntValue, OptionalValue


class RdmaConnParam(Attr):
    FIELD_LIST = [
        "private_data",
        "private_data_len",
        "responder_resources",
        "initiator_depth",
        "flow_control",
        "retry_count",
        "rnr_retry_count",
        "srq",
        "qp_num",
    ]
    MUTABLE_FIELD_LIST = [
        "private_data",
        "private_data_len",
        "responder_resources",
        "initiator_depth",
        "flow_control",
        "retry_count",
        "rnr_retry_count",
        "srq",
        "qp_num",
    ]

    def __init__(
        self,
        private_data: Optional[Union[bytes, bytearray, Sequence[int]]] = None,
        private_data_len: Optional[int] = None,
        responder_resources: Optional[int] = None,
        initiator_depth: Optional[int] = None,
        flow_control: Optional[int] = None,
        retry_count: Optional[int] = None,
        rnr_retry_count: Optional[int] = None,
        srq: Optional[int] = None,
        qp_num: Optional[int] = None,
    ):
        # Opaque private payload; handled specially in to_cxx.
        self.private_data = OptionalValue(private_data if private_data is not None else None, factory=lambda: None)
        # Length is uint8_t; leave 0 by default. If private_data present but len is None, we use the buffer size.
        self.private_data_len = OptionalValue(
            IntValue(private_data_len) if private_data_len is not None else None,
            factory=lambda: IntValue(0),
        )
        # Reasonable defaults based on common CM usage.
        self.responder_resources = OptionalValue(
            IntValue(responder_resources) if responder_resources is not None else None,
            factory=lambda: IntValue(1),
        )
        self.initiator_depth = OptionalValue(
            IntValue(initiator_depth) if initiator_depth is not None else None,
            factory=lambda: IntValue(1),
        )
        self.flow_control = OptionalValue(
            IntValue(flow_control) if flow_control is not None else None,
            factory=lambda: IntValue(0),
        )
        self.retry_count = OptionalValue(
            IntValue(retry_count) if retry_count is not None else None,
            factory=lambda: IntValue(7),
        )
        self.rnr_retry_count = OptionalValue(
            IntValue(rnr_retry_count) if rnr_retry_count is not None else None,
            factory=lambda: IntValue(7),
        )
        self.srq = OptionalValue(
            IntValue(srq) if srq is not None else None,
            factory=lambda: IntValue(0),
        )
        self.qp_num = OptionalValue(
            IntValue(qp_num) if qp_num is not None else None,
            factory=lambda: IntValue(0),
        )

    def _normalize_private_bytes(self, data: Union[bytes, bytearray, Sequence[int]]) -> bytes:
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        # Accept list/sequence of ints; clamp to 0..255
        return bytes(int(x) & 0xFF for x in data)

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct rdma_conn_param")
        s = ""
        s += f"    memset(&{varname}, 0, sizeof({varname}));\n"

        # Handle private_data and private_data_len together.
        pd = getattr(self, "private_data")
        pd_len_opt = getattr(self, "private_data_len")
        pd_len_val = None
        if pd_len_opt:
            # IntValue likely wraps a numeric; emit_assign will handle actual assignment later if needed.
            try:
                pd_len_val = int(pd_len_opt.value)
            except Exception:
                pd_len_val = None

        if pd and pd.value is not None:
            buf = self._normalize_private_bytes(pd.value)
            buf_var = f"{varname}_private_buf"
            # Emit a compile-time array with the provided contents.
            hex_list = ", ".join(f"0x{b:02x}" for b in buf)
            s += f"    unsigned char {buf_var}[{len(buf)}] = {{ {hex_list} }};\n"
            s += f"    {varname}.private_data = {buf_var};\n"
            if pd_len_val is not None and 0 <= pd_len_val < 256:
                # Use provided length (clamped to buffer size if larger).
                if pd_len_val <= len(buf):
                    s += f"    {varname}.private_data_len = (uint8_t){pd_len_val};\n"
                else:
                    s += f"    {varname}.private_data_len = (uint8_t)sizeof({buf_var});\n"
            else:
                s += f"    {varname}.private_data_len = (uint8_t)sizeof({buf_var});\n"
        elif pd_len_val is not None and pd_len_val > 0:
            # No data provided, but a length is specified: emit zero-initialized buffer.
            buf_var = f"{varname}_private_buf"
            s += f"    unsigned char {buf_var}[{pd_len_val}];\n"
            s += f"    memset({buf_var}, 0, sizeof({buf_var}));\n"
            s += f"    {varname}.private_data = {buf_var};\n"
            s += f"    {varname}.private_data_len = (uint8_t)sizeof({buf_var});\n"
        else:
            # No private data.
            s += f"    {varname}.private_data = NULL;\n"
            s += f"    {varname}.private_data_len = (uint8_t)0;\n"

        # Emit the remaining fields.
        for field in self.FIELD_LIST:
            if field in ("private_data", "private_data_len"):
                continue
            val = getattr(self, field)
            if not val:
                continue
            s += emit_assign(varname, field, val)
        return s
