# -*- coding: utf-8 -*-
# rdma_get_send_comp: Block until a send completion is available on the QP associated with the given rdma_cm_id,
# retrieve a single ibv_wc describing the completed send work request, and return the number of completions found.
# Typically returns 1 on success, or -1 with errno set on error. This helper wraps completion channel/cq polling
# for the send side in librdmacm-based flows.

"""
Plugin: RdmaGetSendComp
This module models the RDMA CM API rdma_get_send_comp as a VerbCall for the fuzzing framework.
It generates C code to wait for and retrieve a send work completion on the QP associated with a cm_id.
"""

from typing import Optional

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaGetSendComp(VerbCall):
    """
    Model for rdma_get_send_comp(struct rdma_cm_id *id, struct ibv_wc *wc).

    Semantics:
    - Waits for a send completion event tied to the rdma_cm_id's QP send CQ (and its completion channel).
    - Retrieves a single ibv_wc describing the completed send work request.
    - Returns the number of completions found (typically 1), or -1 on error with errno set.

    Usage notes:
    - The cm_id should have an associated QP, send CQ, and completion channel properly set up (e.g., after route resolution and QP creation).
    - The returned work completion status must be checked by the caller; non-success status indicates a failed send operation.
    """

    MUTABLE_FIELDS = ["id", "wc_var"]

    CONTRACT = Contract(
        requires=[
            # cm_id must exist; many flows require it to be connected or have a QP bound. We keep it minimal here.
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
        ],
        produces=[
            # This call does not allocate or change ownership of resources; it only returns a completion.
        ],
        transitions=[
            # No explicit resource state transitions modeled for cm_id here.
        ],
    )

    def __init__(self, id: str, wc_var: Optional[str] = None):
        if not id:
            raise ValueError("id (cm_id variable name) must be provided for RdmaGetSendComp")

        # CM ID resource
        self.id = ResourceValue(resource_type="cm_id", value=id)

        # Optional user-specified WC variable name (struct ibv_wc). If not provided, a local temporary will be used.
        self.wc_var = wc_var

        # Optionally expose last return value if needed by the harness (not strictly required)
        self._ret_local_name = None

    def apply(self, ctx: CodeGenContext):
        # Optionally allocate a persistent wc variable in the context if user provided a wc_var.
        # If wc_var is None, we'll use a temporary local in generate_c.
        if hasattr(ctx, "alloc_variable") and self.wc_var:
            try:
                ctx.alloc_variable(self.wc_var, "struct ibv_wc")
            except Exception:
                # If allocation already exists or ctx does not support, ignore gracefully
                pass

        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def _sanitize_symbol(self, s: str) -> str:
        return (
            s.replace("[", "_")
            .replace("]", "")
            .replace(".", "_")
            .replace("-", "_")
            .replace("->", "_")
            .replace("*", "p")
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)

        # Decide on wc variable name
        if self.wc_var:
            wc_name = self.wc_var
            declare_wc = ""  # Assume allocated/declared elsewhere or by apply()
            wc_addr = f"&{wc_name}"
        else:
            wc_name = f"wc_send_{self._sanitize_symbol(id_name)}"
            declare_wc = f"struct ibv_wc {wc_name};"
            wc_addr = f"&{wc_name}"

        ret_name = f"ret_get_send_comp_{self._sanitize_symbol(id_name)}"
        self._ret_local_name = ret_name

        # Generate code:
        # - Optional local declaration of wc
        # - Call rdma_get_send_comp
        # - Log on error or non-success WC status
        code = f"""
    /* rdma_get_send_comp */
    IF_OK_PTR({id_name}, {{
        {declare_wc}
        int {ret_name} = rdma_get_send_comp({id_name}, {wc_addr});
        if ({ret_name} <= 0) {{
            fprintf(stderr, "rdma_get_send_comp({id_name}) failed: ret=%d errno=%d (%s)\\n", {ret_name}, errno, strerror(errno));
        }} else {{
            /* Successfully retrieved a send completion */
            if ({wc_name}.status != IBV_WC_SUCCESS) {{
                fprintf(stderr, "Send WC status %d (%s) for cm_id=%s, wr_id=%" "PRIu64" "\\n",
                        {wc_name}.status,
                        ibv_wc_status_str({wc_name}.status),
                        "{id_name}",
                        (uint64_t){wc_name}.wr_id);
            }} else {{
                /* Optional: Log success details */
                // fprintf(stderr, "Send WC success: wr_id=%" "PRIu64" ", opcode=%d, byte_len=%u, qp_num=%u\\n",
                //         (uint64_t){wc_name}.wr_id, {wc_name}.opcode, {wc_name}.byte_len, {wc_name}.qp_num);
            }}
        }}
    }});
"""
        return code.strip("\n")
