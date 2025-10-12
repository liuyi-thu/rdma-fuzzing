# -*- coding: utf-8 -*-
# rdma_dereg_mr CM API modeling plugin
# Semantics: rdma_dereg_mr releases/deregisters an existing memory region (MR) that was
# previously registered via RDMA CM/verbs (e.g., rdma_reg_msgs, ibv_reg_mr). It invalidates
# the MR and frees associated resources. This operation is destructive: the MR must be valid
# and registered before calling; after success, the MR pointer becomes unusable.

"""
Plugin to model the RDMA CM API: rdma_dereg_mr(struct ibv_mr *mr)

This class encapsulates rdma_dereg_mr as a VerbCall for the fuzzing framework:
- Tracks resource contracts: requires an MR in REGISTERED state.
- Transitions the MR to DEREGISTERED state on success.
- Emits C code snippet to perform the actual rdma_dereg_mr call and nulls the pointer.

Usage in generated sequences:
    RDMADeregMR(mr="mr0")
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import ResourceValue
from lib.verbs import VerbCall


class RDMADeregMR(VerbCall):
    MUTABLE_FIELDS = ["mr"]

    # Contract:
    # - Requires 'mr' to be in REGISTERED state.
    # - After calling rdma_dereg_mr, the MR is considered DEREGISTERED.
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="mr", state=State.REGISTERED, name_attr="mr"),
        ],
        produces=[],
        transitions=[
            TransitionSpec(rtype="mr", from_state=State.REGISTERED, to_state=State.DEREGISTERED, name_attr="mr"),
        ],
    )

    def __init__(self, mr: str = None):
        if not mr:
            raise ValueError("mr must be provided for RDMADeregMR")
        # MR pointer we will deregister; keep mutable to allow setting to NULL post-call
        self.mr = ResourceValue(resource_type="mr", value=mr, mutable=True)

    def apply(self, ctx: CodeGenContext):
        # Apply resource/contract tracking to the framework
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        mr_name = str(self.mr)

        return f"""
    /* rdma_dereg_mr */
    IF_OK_PTR({mr_name}, {{
        int __ret_dereg_mr = rdma_dereg_mr({mr_name});
        if (__ret_dereg_mr) {{
            fprintf(stderr, "rdma_dereg_mr failed on {mr_name}: ret=%d\\n", __ret_dereg_mr);
        }} else {{
            {mr_name} = NULL; /* Pointer invalidated after successful deregistration */
        }}
    }});
"""
