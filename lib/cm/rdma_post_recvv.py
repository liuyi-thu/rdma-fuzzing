# RDMA CM modeling plugin for rdma_post_recvv
# This models the rdma_post_recvv API, which posts a receive work request (WR) on
# the QP associated with a given rdma_cm_id. It allows specifying an SGE vector (sgl)
# so the incoming message can be scattered over multiple buffers. The WR context
# is stored in wr_id and returned upon completion on the CQ.

"""
Python plugin that models the RDMA CM API rdma_post_recvv and emits C code to call it.

API prototype:
    static inline int rdma_post_recvv(struct rdma_cm_id *id, void *context, struct ibv_sge *sgl, int nsge);

Semantics:
- Posts a receive WR on the QP bound to the provided rdma_cm_id.
- 'context' is stored in wr_id and returned through completion events.
- 'sgl' is the array of struct ibv_sge describing receive buffers; 'nsge' is its length.
- Returns 0 on success, or an errno-compatible negative value on failure.

Usage in the fuzzing framework:
- This class provides a high-level semantic wrapper for rdma_post_recvv, including
  optional SGE construction and basic contract requirements on the cm_id and QP state.
- It can be instantiated with either a predefined SGE list or none (NULL SGL), allowing
  fuzzing of error paths as well.
"""

from typing import Dict, List, Optional, Tuple, Union

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State
from lib.value import (
    IntValue,
    ListValue,
    OptionalValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RDMAPostRecvv(VerbCall):
    """
    Model for rdma_post_recvv. This class emits code to prepare an SGE array (if provided) and
    call rdma_post_recvv(id, context, sgl, nsge).

    Parameters:
    - cm_id: str
        Name of the rdma_cm_id resource to post the receive on.
    - sgl: Optional[List[Union[Tuple[Union[int, str], int, int], Dict[str, Union[int, str]]]]]
        SGE entries. Each entry can be:
          * a tuple (addr, length, lkey), where addr can be an int or a C symbol name (str),
          * a dict with keys {'addr': ..., 'length': ..., 'lkey': ...}.
        If omitted or empty, sgl will be passed as NULL with nsge=0.
    - nsge: Optional[int]
        Number of SGE entries. If not provided, deduced from len(sgl) if sgl is given.
        If sgl is None, defaults to 0.
    - context: Optional[Union[int, str]]
        The wr_id/context pointer for the posted WR. Can be an integer that will be cast to (void*),
        or a C symbol name string. If omitted, set to NULL.

    Notes:
    - This class does not create or register memory regions; it assumes that lkey and buffer
      addresses provided in SGE entries are valid for the target device/QP when fuzzing for success.
    - For fuzzing invalid paths, you can provide bogus addresses or lkeys.
    """

    MUTABLE_FIELDS = ["cm_id", "context", "sgl", "nsge"]

    # Contracts here are conservative; you may tune states to your framework's actual CM/QP lifecycle.
    # We assume a cm_id is allocated and a QP is attached/usable before posting receives.
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="cm_id"),
            # Require the bound QP exists; many stacks allow posting recv before connection is fully established.
            RequireSpec(rtype="qp", state=State.USED, name_attr="cm_id.qp"),
        ],
        produces=[],
        transitions=[
            # Posting a receive does not change cm_id or qp resource states in this abstraction.
        ],
    )

    def __init__(
        self,
        cm_id: str,
        sgl: Optional[List[Union[Tuple[Union[int, str], int, int], Dict[str, Union[int, str]]]]] = None,
        nsge: Optional[int] = None,
        context: Optional[Union[int, str]] = None,
    ):
        if not cm_id:
            raise ValueError("cm_id must be provided for RDMAPostRecvv")

        # Resource representing the cm_id
        self.cm_id = ResourceValue(resource_type="cm_id", value=cm_id, mutable=False)

        # Store raw SGE items for code generation (Python-level)
        self._sgl_items: List[Dict[str, Union[int, str]]] = []
        if sgl:
            for idx, item in enumerate(sgl):
                if isinstance(item, dict):
                    # Expect keys: addr, length, lkey
                    addr = item.get("addr", 0)
                    length = item.get("length", 0)
                    lkey = item.get("lkey", 0)
                elif isinstance(item, tuple) and len(item) == 3:
                    addr, length, lkey = item
                else:
                    raise ValueError(f"Unsupported SGE entry at index {idx}: {item!r}")
                self._sgl_items.append({"addr": addr, "length": length, "lkey": lkey})

            self.sgl = ListValue(self._sgl_items)
        else:
            # Represent 'no SGL' as NULL for the generator
            self.sgl = "NULL"

        # nsge derived from provided sgl if not explicitly set
        derived_nsge = len(self._sgl_items) if self._sgl_items else 0
        self.nsge = IntValue(nsge if nsge is not None else derived_nsge)

        # The WR context (wr_id); wrap as OptionalValue for flexibility
        if context is None:
            self.context = OptionalValue(None)
        else:
            # Accept either integer or C symbol string
            self.context = OptionalValue(context)

    def apply(self, ctx: CodeGenContext):
        # Apply contracts to update resource states / checks before generation
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def _format_addr(self, addr: Union[int, str]) -> str:
        """
        Helper to format addr for C code:
        - If int, cast to uintptr_t.
        - If str, assume it's a valid C symbol already representing a pointer or address.
        """
        if isinstance(addr, int):
            return f"(uintptr_t){addr}"
        elif isinstance(addr, str):
            # Allow symbol names like buf_ptr, mr_base, etc.
            return f"(uintptr_t){addr}"
        else:
            # Fallback to zero if wrong type
            return "(uintptr_t)0"

    def _format_length(self, length: Union[int, str]) -> str:
        if isinstance(length, int):
            return f"{length}"
        elif isinstance(length, str):
            return f"{length}"
        else:
            return "0"

    def _format_lkey(self, lkey: Union[int, str]) -> str:
        if isinstance(lkey, int):
            return f"{lkey}"
        elif isinstance(lkey, str):
            return f"{lkey}"
        else:
            return "0"

    def generate_c(self, ctx: CodeGenContext):
        cm_name = str(self.cm_id)

        # Deduce names for local variables
        suffix = "_" + cm_name.replace("cm_id[", "").replace("]", "").replace("*", "").replace("&", "").replace(
            ".", "_"
        ).replace("->", "_")
        sgl_name = f"sgl{suffix}"

        # Prepare SGE array initialization code
        nsge_val = 0
        try:
            nsge_val = int(self.nsge.value if hasattr(self.nsge, "value") else int(str(self.nsge)))
        except Exception:
            # If parsing fails, we will still emit nsge using str(self.nsge) for C side
            pass

        sgl_init_code = ""
        if self._sgl_items and nsge_val > 0:
            sgl_init_code += f"    struct ibv_sge {sgl_name}[{nsge_val}];\n"
            for i, sge in enumerate(self._sgl_items):
                addr_c = self._format_addr(sge["addr"])
                len_c = self._format_length(sge["length"])
                lkey_c = self._format_lkey(sge["lkey"])
                sgl_init_code += (
                    f"    {sgl_name}[{i}] = (struct ibv_sge){{\n"
                    f"        .addr = {addr_c},\n"
                    f"        .length = {len_c},\n"
                    f"        .lkey = {lkey_c}\n"
                    f"    }};\n"
                )
        else:
            # No SGL provided; we'll pass NULL and nsge 0
            sgl_init_code += f"    /* No SGL provided: will pass NULL with nsge=0 */\n"

        # Context (wr_id) formatting
        if isinstance(self.context, OptionalValue) and self.context.value is None:
            ctx_expr = "NULL"
        else:
            ctx_val = self.context.value if isinstance(self.context, OptionalValue) else self.context
            if isinstance(ctx_val, int):
                ctx_expr = f"(void*){ctx_val}"
            elif isinstance(ctx_val, str):
                ctx_expr = f"(void*){ctx_val}"
            else:
                ctx_expr = "NULL"

        nsge_expr = f"{nsge_val}"
        # If nsge was not a concrete int, fallback to string representation
        if nsge_val == 0 and self._sgl_items:
            # In case conversion failed but items exist, use len(self._sgl_items)
            nsge_expr = f"{len(self._sgl_items)}"
        elif hasattr(self.nsge, "value"):
            nsge_expr = str(self.nsge.value)

        # Choose sgl pointer for call
        sgl_ptr_expr = sgl_name if (self._sgl_items and nsge_expr != "0") else "NULL"

        return f"""
    /* rdma_post_recvv */
    IF_OK_PTR({cm_name}, {{
{sgl_init_code}
        int rc = rdma_post_recvv({cm_name}, {ctx_expr}, {sgl_ptr_expr}, {nsge_expr});
        if (rc) {{
            fprintf(stderr, "rdma_post_recvv failed on cm_id %s: rc=%d (errno=%d)\\n", "{cm_name}", rc, errno);
        }} else {{
            fprintf(stdout, "rdma_post_recvv posted on cm_id %s (nsge={nsge_expr})\\n", "{cm_name}");
        }}
    }});
"""
