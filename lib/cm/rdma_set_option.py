# -*- coding: utf-8 -*-
# rdma_set_option model: Set options on an rdma_cm_id (or underlying provider/adapter/socket) before or during
# connection management flows. This call allows tuning behavior such as TOS, REUSEADDR, IB path parameters, etc.
# It does not create or destroy resources; it mutates option state on an existing rdma_cm_id.

"""
Plugin: RdmaSetOption
This plugin models the rdma_cm API call:
    int rdma_set_option(struct rdma_cm_id *id, int level, int optname, void *optval, size_t optlen);

Semantics:
- Applies one option to a given rdma_cm_id at the specified protocol level.
- Does not produce or transition any new RDMA resources; it only requires a valid cm_id.
- The model supports either:
    - Passing an integer optval with sizeof(int) length (typical for many options),
    - Passing a raw byte buffer (allocated on the fly and filled with a deterministic pattern),
    - Passing a NULL optval with optlen 0.
- The call is emitted in C and returns an error code that is logged to stderr upon failure.

Notes for fuzzing:
- If optval_int is provided, the model passes &optval_int with optlen set to sizeof(optval_int) unless optlen is explicitly specified.
- If raw buffer is desired, set optval_int=None and provide optlen>0. The model will allocate an unsigned char buffer and fill it using a deterministic pattern.
- If both optval_int is None and optlen is 0 (or None), the call will pass optval=NULL, optlen=0.

Typical usage examples:
    RdmaSetOption(id="cm0", level="RDMA_OPTION_ID", optname="RDMA_OPTION_ID_REUSEADDR", optval_int=1)
    RdmaSetOption(id="cm0", level=0, optname=2, optlen=32)    # raw 32-byte buffer
    RdmaSetOption(id="cm0", level=0, optname=0)               # NULL optval with 0 length
"""

from typing import Optional, Union

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State
from lib.value import (
    ConstantValue,
    EnumValue,
    FlagValue,
    IntValue,
    OptionalValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaSetOption(VerbCall):
    """
    Model for rdma_set_option.
    """

    MUTABLE_FIELDS = ["id", "level", "optname", "optval_int", "optlen"]

    # Requires a valid cm_id. No production or state transitions.
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
        ],
        produces=[],
        transitions=[],
    )

    def __init__(
        self,
        id: str,
        level: Union[int, str, EnumValue, FlagValue, IntValue, ConstantValue],
        optname: Union[int, str, EnumValue, FlagValue, IntValue, ConstantValue],
        optval_int: Optional[Union[int, IntValue]] = None,
        optlen: Optional[int] = None,
    ):
        """
        Parameters:
        - id: name of the rdma_cm_id resource variable (must already exist).
        - level: protocol level (e.g., RDMA_OPTION_ID, RDMA_OPTION_IB, ...). Accepts int or C enum token.
        - optname: option name within level. Accepts int or C enum token.
        - optval_int: if provided, pass an integer value via &optval_int (sizeof(int) unless optlen specified).
        - optlen: optional explicit length. If using a raw buffer (no optval_int), a non-zero optlen will allocate a buffer.
        """
        if not id:
            raise ValueError("id (cm_id resource variable name) must be provided")

        # Resource handle
        self.id = ResourceValue(resource_type="cm_id", value=id)

        # Normalize level/optname into values suitable for C emission
        self.level = self._normalize_scalar(level, default="0")
        self.optname = self._normalize_scalar(optname, default="0")

        # Either integer optval or raw buffer or NULL
        self.optval_int = self._normalize_optval_int(optval_int)
        self.optlen = self._normalize_optlen(optlen)

    def _normalize_scalar(self, v, default="0"):
        if isinstance(v, (EnumValue, FlagValue, IntValue, ConstantValue)):
            return v
        if isinstance(v, int):
            return IntValue(v)
        if isinstance(v, str) and v.strip():
            return ConstantValue(v.strip())
        # fallback
        return ConstantValue(default)

    def _normalize_optval_int(self, v):
        if v is None:
            return None
        if isinstance(v, IntValue):
            return v
        if isinstance(v, int):
            return IntValue(v)
        raise TypeError("optval_int must be an int or IntValue when provided")

    def _normalize_optlen(self, v):
        if v is None:
            return OptionalValue(None)
        if isinstance(v, IntValue):
            return v
        if isinstance(v, int):
            if v < 0:
                v = 0
            return IntValue(v)
        raise TypeError("optlen must be an int or IntValue when provided")

    def _c_expr(self, val):
        # Convert our value wrappers to a C expression string
        if isinstance(val, (EnumValue, FlagValue, IntValue, ConstantValue)):
            return str(val)
        if val is None:
            return "0"
        return str(val)

    def apply(self, ctx: CodeGenContext):
        # No extra bookkeeping besides contract enforcement
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext):
        id_name = str(self.id)
        level_expr = self._c_expr(self.level)
        optname_expr = self._c_expr(self.optname)

        # Create a deterministic suffix from the id variable name
        suffix = "_" + id_name.replace("[", "_").replace("]", "").replace("*", "p").replace(".", "_")

        prelude_lines = []

        # Prepare optval pointer and length expression
        optptr_expr = "NULL"
        optlen_expr = "0"

        if self.optval_int is not None:
            int_sym = f"optval_int{suffix}"
            prelude_lines.append(f"int {int_sym} = {self._c_expr(self.optval_int)};")
            optptr_expr = f"&{int_sym}"
            if isinstance(self.optlen, OptionalValue) and self.optlen.value is None:
                optlen_expr = f"sizeof({int_sym})"
            else:
                optlen_expr = f"(size_t)({self._c_expr(self.optlen)})"
        else:
            # No integer optval. If optlen > 0, build a byte buffer filled with a deterministic pattern.
            if not (isinstance(self.optlen, OptionalValue) and self.optlen.value is None):
                optlen_expr = f"(size_t)({self._c_expr(self.optlen)})"
                prelude_lines.append(f"size_t optlen{suffix} = {optlen_expr};")
                prelude_lines.append(f"unsigned char optbuf{suffix}[{max(1, 1)}]; /* VLA-like guarded below */")
                # In C89, variable length arrays aren't allowed: use malloc for arbitrary optlen.
                # But to stay header-only and simple in snippets, we choose a conditional approach:
                # allocate on heap when len is not known at compile time.
                prelude_lines.append(f"unsigned char *optbuf_dyn{suffix} = NULL;")
                prelude_lines.append(f"if (optlen{suffix} > 0) {{")
                prelude_lines.append(f"    optbuf_dyn{suffix} = (unsigned char*)malloc(optlen{suffix});")
                prelude_lines.append(f"    if (optbuf_dyn{suffix}) {{")
                # Deterministic pattern seeded by level and optname
                prelude_lines.append(
                    f"        memset(optbuf_dyn{suffix}, (unsigned char)((({level_expr}) ^ ({optname_expr})) & 0xFF), optlen{suffix});"
                )
                prelude_lines.append(f"    }}")
                prelude_lines.append(f"}}")
                optptr_expr = f"optbuf_dyn{suffix}"
                optlen_expr = f"optlen{suffix}"

        prelude = "\n        ".join(prelude_lines) if prelude_lines else ""

        cleanup = ""
        if self.optval_int is None:
            # Only free when we malloc'd a dynamic buffer
            if not (isinstance(self.optlen, OptionalValue) and self.optlen.value is None):
                cleanup = f"""
        if (optbuf_dyn{suffix}) {{
            free(optbuf_dyn{suffix});
        }}"""

        return f"""
    /* rdma_set_option */
    IF_OK_PTR({id_name}, {{
        {prelude}
        int rc_setopt{suffix} = rdma_set_option({id_name}, {level_expr}, {optname_expr}, {optptr_expr}, {optlen_expr});
        if (rc_setopt{suffix}) {{
            fprintf(stderr, "rdma_set_option(id=%p, level=%d, optname=%d, optlen=%zu) failed: errno=%d (%s)\\n",
                    (void*){id_name}, (int)({level_expr}), (int)({optname_expr}), (size_t)({optlen_expr}), errno, strerror(errno));
        }} else {{
            fprintf(stderr, "rdma_set_option(id=%p, level=%d, optname=%d, optlen=%zu) succeeded\\n",
                    (void*){id_name}, (int)({level_expr}), (int)({optname_expr}), (size_t)({optlen_expr}));
        }}{cleanup}
    }});
"""
