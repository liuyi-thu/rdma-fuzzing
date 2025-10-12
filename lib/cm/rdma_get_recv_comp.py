# RDMA CM API modeling: rdma_get_recv_comp
# This CM helper blocks/waits for a receive completion on the QP associated with a given rdma_cm_id,
# and fills the provided ibv_wc with the completion. It returns <0 on error, 0 if no completion,
# and >0 (typically 1) when a completion is retrieved. Commonly used after rdma_post_recv to
# harvest RX completions in the CM-managed QP lifecycle.

"""
Plugin that models the RDMA CM API rdma_get_recv_comp as a VerbCall.

- Encapsulates a call to rdma_get_recv_comp(id, wc) and emits C code.
- Validates (optionally) the returned WC status/opcode for fuzzing assertions.
- Integrates with the framework's contract system to ensure the CM ID is in a proper state
  (usually connected/ready) before attempting to read RX completions.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State
from lib.value import (
    ConstantValue,
    ListValue,
    LocalResourceValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RDMAGetRecvComp(VerbCall):
    """
    Model rdma_get_recv_comp(struct rdma_cm_id *id, struct ibv_wc *wc).

    Parameters:
      - id: name of the rdma_cm_id resource (must be known to the framework)
      - wc: name for the struct ibv_wc local variable to receive the completion. If not provided,
            a unique name will be generated based on the cm_id.
      - expect_status: optional expected WC status (default: IBV_WC_SUCCESS). If provided,
            generated C code will assert/print on mismatch.
      - expect_opcodes: optional list of acceptable WC opcodes (e.g., ["IBV_WC_RECV", "IBV_WC_RECV_RDMA_WITH_IMM"]).
            If provided, generated C code will assert/print on mismatch.

    Contract:
      - requires: the cm_id must be CONNECTED (or equivalent "ready" state) to ensure a QP exists and RX
                  completions can be harvested.
      - produces: none (wc is a local output buffer, not a tracked resource).
      - transitions: none (this operation is observational over RX CQ; does not change tracked resource states).
    """

    MUTABLE_FIELDS = ["id", "wc", "expect_status", "expect_opcodes"]

    CONTRACT = Contract(
        requires=[
            # The rdma_cm_id should be in a connected state to have an active QP/CQ for recv completions.
            RequireSpec(rtype="cm_id", state=State.CONNECTED, name_attr="id"),
        ],
        produces=[
            # No new tracked resources are produced; wc is a local variable.
        ],
        transitions=[
            # No state transition for cm_id; RX completion is observational.
        ],
    )

    def __init__(
        self,
        id: str,
        wc: str = None,
        expect_status: str = "IBV_WC_SUCCESS",
        expect_opcodes: list[str] | None = None,
    ):
        if not id:
            raise ValueError("id (cm_id variable name) must be provided for RDMAGetRecvComp")
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

        # Local WC buffer variable name; auto-generate if not provided.
        if wc is None:
            # Create a stable, unique wc name from id
            wc_suffix = str(id).replace("[", "_").replace("]", "").replace(".", "_")
            wc = f"wc_{wc_suffix}"
        self.wc = LocalResourceValue(resource_type="wc", value=wc)

        # Expectations for fuzzing-time checks
        self.expect_status = ConstantValue(expect_status) if expect_status else None
        self.expect_opcodes = ListValue(expect_opcodes) if expect_opcodes else None

    def apply(self, ctx: CodeGenContext):
        # Register local variable(s) used by generated C
        ctx.alloc_variable(self.wc.value, "struct ibv_wc")

        # Apply contracts if the framework carries them
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)
        wc_name = self.wc.value

        opcode_check_code = ""
        if self.expect_opcodes and isinstance(self.expect_opcodes.value, list) and len(self.expect_opcodes.value) > 0:
            # Build a disjunction for acceptable opcodes
            acceptable = " || ".join([f"{wc_name}.opcode == {op}" for op in self.expect_opcodes.value])
            opcode_check_code = f"""
        if (!({acceptable})) {{
            fprintf(stderr,
                    "rdma_get_recv_comp: unexpected opcode %d (allowed: {", ".join(self.expect_opcodes.value)})\\n",
                    {wc_name}.opcode);
        }}
"""

        status_check_code = ""
        if self.expect_status and self.expect_status.value:
            status_check_code = f"""
        if ({wc_name}.status != {self.expect_status.value}) {{
            fprintf(stderr,
                    "rdma_get_recv_comp: unexpected status %d (expected {self.expect_status.value})\\n",
                    {wc_name}.status);
        }}
"""

        # Additional informative prints to aid fuzzing/debugging
        info_dump_code = f"""
        fprintf(stdout, "recv wc: wr_id=%" PRIu64 ", byte_len=%u, qp_num=%u, status=%d, opcode=%d\\n",
                (uint64_t){wc_name}.wr_id,
                {wc_name}.byte_len,
                {wc_name}.qp ? {wc_name}.qp->qp_num : 0,
                {wc_name}.status,
                {wc_name}.opcode);
"""

        return f"""
    /* rdma_get_recv_comp */
    IF_OK_PTR({id_name}, {{
        int __rc = rdma_get_recv_comp({id_name}, &{wc_name});
        if (__rc < 0) {{
            fprintf(stderr, "rdma_get_recv_comp(id={id_name}) failed: rc=%d\\n", __rc);
        }} else if (__rc == 0) {{
            fprintf(stderr, "rdma_get_recv_comp(id={id_name}) returned 0 (no recv completions)\\n");
        }} else {{
            /* One completion retrieved into {wc_name} */
            {status_check_code}
            {opcode_check_code}
            {info_dump_code}
        }}
    }});
"""
