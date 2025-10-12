# RDMA CM API modeling plugin for rdma_create_ep
# This plugin models rdma_create_ep, which allocates an rdma_cm_id and optionally
# creates and associates an ibv_qp with the cm_id based on provided pd and qp_init_attr.
# The cm_id is set to synchronous operation mode by default. If qp_init_attr is given,
# QP is created on the provided PD (or a default PD if PD is NULL).

"""
RdmaCreateEP VerbCall plugin

Semantics:
- Wraps rdma_create_ep to allocate a communication identifier (rdma_cm_id) and
  optionally a queue pair (ibv_qp) associated with the cm_id.
- Input:
  - id: The name of the cm_id resource variable (output).
  - res: The rdma_addrinfo resource (from rdma_getaddrinfo), specifying source/destination and routing info.
  - pd: Optional protection domain; used only if qp_init_attr is provided.
  - qp_init_attr: Optional QP init attributes; if provided, QP is created on the cm_id.
  - qp: Optional name of the QP variable to capture id->qp, auto-generated if not provided but qp_init_attr is present.
- Effects:
  - Produces a cm_id in ALLOCATED state.
  - If qp_init_attr is provided, produces a qp in RESET state, bound to given send/recv CQs (and SRQ if provided).
  - Sets cm_id to synchronous mode (per kernel semantics; migration to async requires rdma_migrate_id).
"""

from typing import Optional

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, RequireSpec, State
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


# Type hint only; actual implementation is provided by framework.
# Must provide .to_cxx(attr_name: str, ctx: CodeGenContext) -> str and fields send_cq/recv_cq/srq
class IbvQPInitAttr:  # noqa: N801
    pass


class RdmaCreateEP(VerbCall):
    """
    VerbCall wrapper for rdma_create_ep.

    Parameters:
    - id: str. Name of rdma_cm_id resource to be produced.
    - res: str. Name of rdma_addrinfo resource (from rdma_getaddrinfo).
    - pd: Optional[str]. Name of PD resource (used if qp_init_attr is provided).
    - qp_init_attr: Optional[IbvQPInitAttr]. QP init attributes; if provided, QP will be created.
    - qp: Optional[str]. Name of QP resource variable to store id->qp. If omitted but qp_init_attr
          is provided, a name will be auto-generated based on 'id'.
    """

    MUTABLE_FIELDS = ["id", "res", "pd", "qp_init_attr", "qp"]

    def __init__(
        self,
        id: str,
        res: str,
        pd: Optional[str] = None,
        qp_init_attr: Optional[IbvQPInitAttr] = None,
        qp: Optional[str] = None,
    ):
        if not id:
            raise ValueError("id must be provided for RdmaCreateEP")
        if not res:
            raise ValueError("res (rdma_addrinfo) must be provided for RdmaCreateEP")

        # Resources
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)
        self.res = ResourceValue(resource_type="rdma_addrinfo", value=res)

        # Optional PD. Ignored by rdma_create_ep if qp_init_attr is NULL.
        self.pd = ResourceValue(resource_type="pd", value=pd) if pd else "NULL"

        # QP init attributes object handled externally; framework generates its C representation.
        self.qp_init_attr = qp_init_attr

        # Optional QP resource name to reflect the created id->qp
        self.qp = ResourceValue(resource_type="qp", value=qp, mutable=False) if qp else None

        # Context will be set in apply()
        self.context: Optional[CodeGenContext] = None

    def _contract(self) -> Contract:
        requires = [
            RequireSpec(rtype="rdma_addrinfo", state=State.ALLOCATED, name_attr="res"),
        ]
        produces = [
            ProduceSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
        ]
        transitions = []

        # If QP attributes are provided, ensure dependent resources are available and produce QP.
        if self.qp_init_attr is not None:
            # PD requirement only applies if provided (non-NULL)
            if self.pd != "NULL":
                requires.append(RequireSpec(rtype="pd", state=State.ALLOCATED, name_attr="pd"))
            # CQs/SRQ optional but if specified in qp_init_attr, they must exist
            requires.append(RequireSpec(rtype="cq", state=State.ALLOCATED, name_attr="qp_init_attr.send_cq"))
            requires.append(RequireSpec(rtype="cq", state=State.ALLOCATED, name_attr="qp_init_attr.recv_cq"))
            requires.append(RequireSpec(rtype="srq", state=State.ALLOCATED, name_attr="qp_init_attr.srq"))

            # Produce QP in RESET state (consistent with ibv_create_qp behavior)
            # metadata includes PD for downstream reasoning
            produces.append(ProduceSpec(rtype="qp", state=State.RESET, name_attr="qp", metadata_fields=["pd"]))

        return Contract(requires=requires, produces=produces, transitions=transitions)

    def apply(self, ctx: CodeGenContext):
        self.context = ctx

        # Allocate variable for cm_id
        ctx.alloc_variable(str(self.id), "struct rdma_cm_id *", "NULL")

        # If creating QP, prepare a variable name and bind CQs
        if self.qp_init_attr is not None:
            if self.qp is None:
                # Auto-generate a qp name based on id
                suffix = str(self.id).replace("cm_id[", "").replace("]", "").replace("*", "")
                auto_qp_name = f"qp_ep_{suffix}"
                self.qp = ResourceValue(resource_type="qp", value=auto_qp_name, mutable=False)
            # Ensure QP var exists
            ctx.alloc_variable(str(self.qp), "struct ibv_qp *", "NULL")

            # Bind send/recv CQs if available (no-op if attr fields are None/NULL)
            ctx.make_qp_recv_cq_binding(str(self.qp), self.qp_init_attr.recv_cq if self.qp_init_attr else "NULL")
            ctx.make_qp_send_cq_binding(str(self.qp), self.qp_init_attr.send_cq if self.qp_init_attr else "NULL")

        # Apply dynamic contract
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)
        res_name = str(self.res)
        pd_name = self.pd
        attr_code = ""
        attr_name = None

        # Prepare qp_init_attr C struct if provided
        if self.qp_init_attr is not None:
            # Derive a unique attribute variable name from id
            attr_suffix = "_" + id_name.replace("cm_id[", "").replace("]", "")
            attr_name = f"attr_ep{attr_suffix}"
            attr_code = self.qp_init_attr.to_cxx(attr_name, ctx)

        qp_assign_block = ""
        qp_registration_block = ""

        if self.qp_init_attr is not None and self.qp is not None:
            qp_name = str(self.qp)
            # After successful rdma_create_ep, extract id->qp into qp_name
            qp_assign_block = f"""
        /* Capture created QP from cm_id */
        {qp_name} = {id_name} ? {id_name}->qp : NULL;
        if (!{qp_name}) {{
            fprintf(stderr, "rdma_create_ep did not produce a QP (qp_init_attr provided)\\n");
        }}
"""
            # Register in tracking structures if available
            gid_fmt_block = ""
            if hasattr(self.context, "gid_var"):
                gid_var = self.context.gid_var
                gid_fmt_block = f"""
            snprintf(qps[qps_size-1].gid, sizeof(qps[qps_size-1].gid),
                        "%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x",
                        {gid_var}.raw[0], {gid_var}.raw[1], {gid_var}.raw[2], {gid_var}.raw[3], {gid_var}.raw[4], {gid_var}.raw[5], {gid_var}.raw[6], {gid_var}.raw[7],
                        {gid_var}.raw[8], {gid_var}.raw[9], {gid_var}.raw[10], {gid_var}.raw[11], {gid_var}.raw[12], {gid_var}.raw[13], {gid_var}.raw[14], {gid_var}.raw[15]);
"""
            qp_registration_block = f"""
        IF_OK_PTR({qp_name}, {{
            qps[qps_size++] = (PR_QP){{
                .id = "{qp_name}",
                .qpn = {qp_name}->qp_num,
                .psn = 0,
                .port = 1,
                .lid = 0,
                .gid = "" // will set below
            }};
            {gid_fmt_block}
            pr_write_client_update_claimed(CLIENT_UPDATE_PATH, qps, qps_size, mrs, mrs_size, prs, prs_size);
        }});"""

        create_ep_call = f"""
    /* rdma_create_ep: allocate cm_id and optional QP */
    IF_OK_PTR({res_name}, {{
        {attr_code}
        int ret = rdma_create_ep(&{id_name}, {res_name}, {pd_name}, {"&" + attr_name if attr_name else "NULL"});
        if (ret) {{
            fprintf(stderr, "rdma_create_ep failed ret=%d\\n");
        }}
    }});"""

        post_block = f"""
    /* Post-creation handling */
    IF_OK_PTR({id_name}, {{
        {qp_assign_block}
        {qp_registration_block}
    }});"""

        return f"""{create_ep_call}
{post_block}
"""
