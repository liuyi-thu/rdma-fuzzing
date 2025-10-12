# -*- coding: utf-8 -*-
# rdma_create_srq_ex: Create an SRQ (Shared Receive Queue) associated with a given rdma_cm_id.
# This CM API uses the device/context bound to the rdma_cm_id and creates an SRQ using extended
# attributes (ibv_srq_init_attr_ex). On success, the created SRQ is stored in id->srq and the
# function returns 0; on failure it returns a non-zero error code. Typical usage is to prepare
# ibv_srq_init_attr_ex (including a valid PD) and then call rdma_create_srq_ex to enable SRQ-based
# receive queuing across multiple QPs.

"""
Plugin modeling of RDMA CM API rdma_create_srq_ex for a Python+C RDMA verbs fuzzing framework.

This plugin provides a VerbCall-derived class that:
- Encapsulates rdma_create_srq_ex into a high-level operation for sequence generation.
- Captures resource contracts (requires/provides) for the CM ID and SRQ.
- Emits C code to invoke rdma_create_srq_ex and bind the resulting SRQ pointer.

Function signature:
    int rdma_create_srq_ex(struct rdma_cm_id *id, struct ibv_srq_init_attr_ex *attr);

Semantics:
- Creates a Shared Receive Queue on the RDMA device/context associated with 'id'.
- Uses extended SRQ attributes provided via ibv_srq_init_attr_ex, which should typically contain
  a valid ibv_pd pointer and any desired SRQ attributes (e.g., max_wr, max_sge).
- On success: returns 0 and sets id->srq to the created SRQ.
- On failure: returns non-zero, errno is set.

Notes:
- The framework's contract system may require that the PD inside the attr_ex object is allocated.
- The generated C code assigns the created SRQ to the user-provided SRQ variable from id->srq.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, RequireSpec, State
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class CreateSRQEx(VerbCall):
    """
    Model for rdma_create_srq_ex.

    Parameters:
    - id: str
        The rdma_cm_id resource name. Must reference an allocated CM ID bound to a device/context.
    - srq: str
        The local SRQ resource name to bind the created SRQ pointer into.
    - init_attr_ex_obj: IbvSRQInitAttrEx
        A high-level object that can generate C code for struct ibv_srq_init_attr_ex initialization.
        It is expected to include a valid PD (attr.pd) when creating a functional SRQ.

    Contract:
    - requires:
        * cm_id in ALLOCATED state
        * pd referenced by init_attr_ex_obj.pd in ALLOCATED state
    - produces:
        * srq in ALLOCATED state
    """

    MUTABLE_FIELDS = ["id", "srq", "init_attr_ex_obj"]

    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
            # The PD must come from the same context/device as 'id'. We require the PD referenced in the extended attr.
            RequireSpec(rtype="pd", state=State.ALLOCATED, name_attr="init_attr_ex_obj.pd"),
        ],
        produces=[
            ProduceSpec(rtype="srq", state=State.ALLOCATED, name_attr="srq", metadata_fields=["cm_id", "pd"]),
        ],
        transitions=[],
    )

    def __init__(self, id: str = None, srq: str = None, init_attr_ex_obj: "IbvSRQInitAttrEx" = None):
        # rdma_cm_id resource (must be allocated/bound to a device to be usable)
        self.id = ResourceValue(resource_type="cm_id", value=id) if id else "NULL"

        if not srq:
            raise ValueError("srq must be provided for CreateSRQEx")
        # SRQ resource handle name (will be assigned from id->srq after successful creation)
        self.srq = ResourceValue(resource_type="srq", value=srq, mutable=False)

        # Extended SRQ init attribute object (should provide .to_cxx(name, ctx) to generate C code)
        self.init_attr_ex_obj = init_attr_ex_obj

    def apply(self, ctx: CodeGenContext):
        # Allocate SRQ variable to hold pointer after creation
        ctx.alloc_variable(str(self.srq), "struct ibv_srq *", "NULL")

        # Apply contract (preconditions and postconditions)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext):
        srq_name = str(self.srq)
        id_name = self.id
        attr_suffix = "_" + srq_name.replace("srq[", "").replace("]", "")
        attr_name = f"srq_attr_ex{attr_suffix}"

        code = ""
        if self.init_attr_ex_obj is not None:
            code += self.init_attr_ex_obj.to_cxx(attr_name, ctx)

        return f"""
    /* rdma_create_srq_ex */
    IF_OK_PTR({id_name}, {{
        {code}
        int rc = rdma_create_srq_ex({id_name}, &{attr_name});
        if (rc) {{
            fprintf(stderr, "rdma_create_srq_ex failed for SRQ {srq_name}, rc=%d, errno=%d (%s)\\n", rc, errno, strerror(errno));
        }} else {{
            {srq_name} = {id_name}->srq;
            if (!{srq_name}) {{
                fprintf(stderr, "rdma_create_srq_ex returned success but id->srq is NULL for {srq_name}\\n");
            }}
        }}
    }});
"""
