# RDMA CM API modeling plugin for rdma_create_qp
# This plugin models rdma_create_qp, which allocates an ibv_qp associated with a given rdma_cm_id.
# Semantics:
# - The rdma_cm_id must be bound to a local RDMA device beforehand (e.g., via rdma_bind_addr / rdma_resolve_addr).
# - A protection domain (PD) may be provided; if NULL, a default PD for the device is used by librdmacm.
# - The QP is made ready for posting receives automatically; if the QP is unconnected, it will be ready to post sends.
# Use:
# - Provides a QP resource in RESET state (logical modeling) and binds it to the cm_id.
# - Generates C code that calls rdma_create_qp(id, pd, &attr), then reflects the created QP pointer from id->qp.

from typing import Optional

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, RequireSpec, State
from lib.IbvQPInitAttr import IbvQPInitAttr
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaCreateQP(VerbCall):
    """
    Model of rdma_create_qp:
      int rdma_create_qp(struct rdma_cm_id *id, struct ibv_pd *pd, struct ibv_qp_init_attr *qp_init_attr);

    Arguments:
      - id: rdma_cm_id that has been bound to a local RDMA device.
      - pd: optional ibv_pd; if None/NULL, librdmacm uses a default PD associated with the device.
      - qp_init_attr: IbvQPInitAttr-like object that can render a 'struct ibv_qp_init_attr' in C.

    Produces:
      - An ibv_qp resource (RESET state in the logical model), associated with the given cm_id.

    Notes:
      - The generated C code calls rdma_create_qp, checks return value, and then assigns the created QP pointer
        from id->qp into the named QP variable.
      - CQ requirements are modeled; SRQ is optional but included if present in qp_init_attr.
    """

    MUTABLE_FIELDS = ["id", "pd", "qp", "init_attr_obj"]

    CONTRACT = Contract(
        requires=[
            # rdma_cm_id must be bound to a device before creation
            RequireSpec(rtype="cm_id", state=State.BOUND, name_attr="id"),
            # pd is optional; if provided, it must be allocated and belong to the same device as id
            RequireSpec(rtype="pd", state=State.ALLOCATED, name_attr="pd"),
            # qp_init_attr must reference valid CQs (required by verbs)
            RequireSpec(rtype="cq", state=State.ALLOCATED, name_attr="init_attr_obj.send_cq"),
            RequireSpec(rtype="cq", state=State.ALLOCATED, name_attr="init_attr_obj.recv_cq"),
            # SRQ is optional; if present within qp_init_attr, it must be allocated
            RequireSpec(rtype="srq", state=State.ALLOCATED, name_attr="init_attr_obj.srq"),
        ],
        produces=[
            ProduceSpec(rtype="qp", state=State.RESET, name_attr="qp", metadata_fields=["pd", "id"]),
        ],
        transitions=[],
    )

    def __init__(
        self,
        id: str,
        pd: Optional[str] = None,
        init_attr_obj: IbvQPInitAttr = None,  # IbvQPInitAttr-like object with to_cxx(attr_name, ctx)
    ):
        if not id:
            raise ValueError("id (cm_id) must be provided for RdmaCreateQP")

        # rdma_cm_id to bind QP to
        self.id = ResourceValue(
            resource_type="cm_id", value=id, mutable=False
        )  # 这个地方我想的是不要 mutable，减少困难
        # PD may be NULL (default PD will be used by librdmacm)
        self.pd = ResourceValue(resource_type="pd", value=pd) if pd else "NULL"
        # # Target QP variable to hold id->qp after successful rdma_create_qp
        # self.qp = ResourceValue(resource_type="qp", value=qp, mutable=False)
        self.qp = ResourceValue(resource_type="qp", value=f"{id}->qp", mutable=False)
        # QP init attr object (responsible for generating the ibv_qp_init_attr C struct)
        self.init_attr_obj = init_attr_obj

    def _contract(self) -> Contract:
        # override the CONTRACT if needed

        CONTRACT = Contract(
            requires=[
                # rdma_cm_id must be bound to a device before creation
                RequireSpec(rtype="cm_id", state=State.BOUND, name_attr="id"),
                # qp_init_attr must reference valid CQs (required by verbs)
                # SRQ is optional; if present within qp_init_attr, it must be allocated
                # RequireSpec(rtype="srq", state=State.ALLOCATED, name_attr="init_attr_obj.srq"),
            ],
            produces=[
                ProduceSpec(rtype="qp", state=State.RESET, name_attr="qp", metadata_fields=["pd", "id"]),
            ],
            transitions=[],
        )
        if self.pd != "NULL":
            # If a specific PD is provided, ensure it is allocated
            CONTRACT.requires.append(RequireSpec(rtype="pd", state=State.ALLOCATED, name_attr="pd"))
        # if self.init_attr_obj.send_cq != "NULL":
        #     CONTRACT.requires.append(RequireSpec(rtype="cq", state=State.ALLOCATED, name_attr="init_attr_obj.send_cq"))
        # if self.init_attr_obj.recv_cq != "NULL":
        #     CONTRACT.requires.append(RequireSpec(rtype="cq", state=State.ALLOCATED, name_attr="init_attr_obj.recv_cq"))

        return self.CONTRACT

    def apply(self, ctx: CodeGenContext):
        # Allocate the QP variable name in the codegen context (pointer, initialized to NULL)
        # ctx.alloc_variable(str(self.qp), "struct ibv_qp *", "NULL")

        # Best-effort binding hints for visualization/tracking
        # If available in context, register that this QP is associated with this cm_id.
        # if hasattr(ctx, "make_cm_qp_binding"):
        #     try:
        #         ctx.make_cm_qp_binding(str(self.id), str(self.qp))
        #     except Exception:
        #         pass
        # 暂时不知道是否必要

        # Contract application (state/resource tracking)
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = str(self.qp)
        id_name = str(self.id)
        pd_name = self.pd

        # Create a unique attribute variable name per QP
        attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
        attr_name = f"attr_init{attr_suffix}"

        attr_code = ""
        if self.init_attr_obj is not None:
            # Generate the C struct 'struct ibv_qp_init_attr attr_name = {...};'
            attr_code = self.init_attr_obj.to_cxx(attr_name, ctx)

        return f"""
    /* rdma_create_qp: allocate QP for cm_id and auto-transition via librdmacm */
    IF_OK_PTR({id_name}, {{
        {attr_code}
        int rc = rdma_create_qp({id_name}, {pd_name}, &{attr_name});
        if (rc) {{
            fprintf(stderr, "rdma_create_qp failed for id {id_name} (rc=%d)\\n", rc);
        }} else {{

        }}
    }});"""

        # /* On success, the created QP pointer is in id->qp */
        # {qp_name} = {id_name}->qp;
        # assert({qp_name} != NULL);
        # /* QP is now in RESET state and ready for posting receives (if unconnected) */
