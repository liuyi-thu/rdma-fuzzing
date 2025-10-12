# Model for RDMA CM API rdma_post_sendv: posts a SEND work request using an SGE vector via a rdma_cm_id.
# This is a thin wrapper around ibv_post_send with opcode IBV_WR_SEND and a scatter-gather list.
# Typical usage requires an rdma_cm_id that has an associated QP in a send-capable state (e.g., RTS) and a connection established.
# The 'context' is a user pointer returned in the corresponding completion, 'sgl' describes the data buffers, 'nsge' is the SGE count, and 'flags' are verbs send flags.

"""
Python plugin that models the RDMA CM API rdma_post_sendv as a VerbCall.

This class encapsulates posting a SEND work request through the RDMA CM id using a vector of SGEs.
It is designed for a Python+C mixed fuzzing framework where Python constructs operation sequences
and generates corresponding C code snippets for compilation and execution.

Function prototype being modeled:
    static inline int rdma_post_sendv(struct rdma_cm_id *id, void *context, struct ibv_sge *sgl, int nsge, int flags);

Key semantics:
- Posts a SEND operation to the QP associated with the given rdma_cm_id.
- 'context' is carried to the completion entry for identification.
- 'sgl' and 'nsge' define the payload buffers; flags are passed through as verbs send flags (e.g., IBV_SEND_SIGNALED).
- Requires the CM ID to be connected and its QP to be in a send-capable state.

Notes:
- This model emphasizes generation of C code that constructs an SGE array and calls rdma_post_sendv.
- For fuzzing, the SGE list can be synthetically generated or provided explicitly. If not provided, a zeroed SGE may be posted.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    ConstantValue,
    FlagValue,
    IntValue,
    LocalResourceValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaPostSendV(VerbCall):
    """
    Model for rdma_post_sendv(id, context, sgl, nsge, flags)

    Parameters:
    - id: name of the rdma_cm_id resource in the context
    - context: optional local context pointer/identifier to tag the send WR (returned in completion)
    - sgl: list of dict entries describing SGEs: [{"addr": <expr or var>, "length": <int>, "lkey": <int>}, ...]
            - addr can be a numeric expression or a variable name (casted to uintptr_t in generated C)
            - length and lkey are integers (or IntValue/ConstantValue)
    - nsge: number of SGE entries; if not given, inferred from len(sgl) when sgl provided, else defaults to 0
    - flags: verbs send flags (e.g., IBV_SEND_SIGNALED | IBV_SEND_INLINE). Accepts int or FlagValue.
    """

    MUTABLE_FIELDS = ["id", "context", "sgl", "nsge", "flags"]

    CONTRACT = Contract(
        requires=[
            # Require the CM ID to be in a connected (ready to send) state.
            # In typical flows, this implies the underlying QP is created, transitioned to RTS,
            # and the connection established via rdma_connect/rdma_accept.
            RequireSpec(rtype="cm_id", state=State.CONNECTED, name_attr="id"),
        ],
        produces=[
            # rdma_post_sendv does not create resources; it just posts a WR.
        ],
        transitions=[
            # No state transition for cm_id; posting a WR keeps the CM ID connected/used.
            TransitionSpec(rtype="cm_id", from_state=State.CONNECTED, to_state=State.USED, name_attr="id"),
        ],
    )

    def __init__(self, id: str = None, context: str = None, sgl: list = None, nsge: int = None, flags: int = 0):
        if not id:
            raise ValueError("id (rdma_cm_id resource name) must be provided for RdmaPostSendV")

        # RDMA CM identifier (resource)
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

        # user context pointer; we store as a local value if provided else "NULL"
        self.user_context = LocalResourceValue(resource_type="context", value=context) if context else "NULL"

        # SGE list (list of dicts with keys addr, length, lkey). Leave as raw Python structure for codegen.
        self.sgl = sgl if isinstance(sgl, list) else None

        # nsge: if provided, IntValue or int; else inferred during codegen
        self.nsge = IntValue(nsge) if isinstance(nsge, int) else (nsge if nsge is not None else None)

        # flags: allow raw int or FlagValue; default 0
        self.flags = (
            FlagValue(flags) if isinstance(flags, FlagValue) else (IntValue(flags) if isinstance(flags, int) else flags)
        )

    def apply(self, ctx: CodeGenContext):
        # Keep a handle to the context if needed for later bindings
        self.context = ctx

        # Apply contract semantics if the framework supports it
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def _flags_expr(self):
        # Convert flags to a C expression string
        if isinstance(self.flags, FlagValue):
            return str(self.flags)
        if isinstance(self.flags, (IntValue, ConstantValue)):
            return str(self.flags)
        # Fallback to raw 0 when unspecified/unknown
        return "0"

    def _nsge_value(self):
        # Determine nsge value
        if isinstance(self.nsge, IntValue):
            return int(self.nsge.value)
        if isinstance(self.nsge, ConstantValue):
            try:
                return int(self.nsge.value)
            except Exception:
                return 0
        if self.sgl is not None:
            return len(self.sgl)
        return 0

    def _gen_sgl_init(self, sgl_var_name: str, nsge: int):
        # Generate C code to declare and initialize the SGE array
        lines = []
        if nsge <= 0:
            # Declare one zeroed SGE to exercise error paths or minimal posting
            lines.append(f"struct ibv_sge {sgl_var_name}[1];")
            lines.append(f"memset({sgl_var_name}, 0, sizeof({sgl_var_name}));")
            return "\n        ".join(lines), 1

        lines.append(f"struct ibv_sge {sgl_var_name}[{nsge}];")
        # Initialize either with provided list or zeroed
        if self.sgl:
            for idx in range(nsge):
                entry = self.sgl[idx] if idx < len(self.sgl) else {}
                addr = entry.get("addr", "0")
                length = entry.get("length", 0)
                lkey = entry.get("lkey", 0)

                # Normalize fields to strings
                addr_expr = str(addr)
                length_expr = str(length) if not isinstance(length, IntValue) else str(length)
                lkey_expr = str(lkey) if not isinstance(lkey, IntValue) else str(lkey)

                lines.append(f"{sgl_var_name}[{idx}].addr = (uintptr_t)({addr_expr});")
                lines.append(f"{sgl_var_name}[{idx}].length = {length_expr};")
                lines.append(f"{sgl_var_name}[{idx}].lkey = {lkey_expr};")
        else:
            lines.append(f"memset({sgl_var_name}, 0, sizeof({sgl_var_name}));")

        return "\n        ".join(lines), nsge

    def generate_c(self, ctx: CodeGenContext):
        id_name = str(self.id)
        user_ctx_expr = (
            str(self.user_context) if isinstance(self.user_context, (LocalResourceValue, ResourceValue)) else "NULL"
        )
        flags_expr = self._flags_expr()
        nsge = self._nsge_value()

        # Build unique SGL variable name based on cm_id name
        suffix = "_" + id_name.replace("cm_id[", "").replace("]", "")
        sgl_var_name = f"sgl{suffix}"

        sgl_init_code, nsge_final = self._gen_sgl_init(sgl_var_name, nsge)

        return f"""
    /* rdma_post_sendv */
    IF_OK_PTR({id_name}, {{
        {sgl_init_code}
        int _ret_sendv = rdma_post_sendv({id_name}, {user_ctx_expr}, {sgl_var_name}, {nsge_final}, {flags_expr});
        if (_ret_sendv) {{
            fprintf(stderr, "rdma_post_sendv failed on {id_name}: %d\\n", _ret_sendv);
        }} else {{
            VERBOSE_LOG("rdma_post_sendv posted on {id_name}, nsge={{{{int}}}}", {nsge_final});
        }}
    }});
"""
