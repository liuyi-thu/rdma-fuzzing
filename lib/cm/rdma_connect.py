# RDMA CM API modeling: rdma_connect
# This plugin models the rdma_connect call, which initiates an active connection
# request for a rdma_cm_id. It requires that rdma_resolve_route has been called
# beforehand. An optional rdma_conn_param may be provided to override defaults
# and exchange private data. On success, the cm_id transitions to a CONNECTING
# state and an ESTABLISHED event is expected via the CM event channel later.


from lib.cm.rdma_conn_param import RdmaConnParam
from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaConnect(VerbCall):
    """
    Model for RDMA CM API: rdma_connect(struct rdma_cm_id *id, struct rdma_conn_param *conn_param)

    Semantics:
    - Initiates an active connection request for a connected rdma_cm_id (RC/UC) or triggers
      a remote QP lookup for datagram service (UD).
    - Prerequisite: rdma_resolve_route must have completed successfully on 'id'.
    - Optionally accepts connection parameters (rdma_conn_param), enabling application
      to override defaults and exchange private data during the handshake.
    - This call initiates connection; the ESTABLISHED state is reached upon receiving
      a RDMA_CM_EVENT_ESTABLISHED event via rdma_get_cm_event.

    Contract modeling:
    - Requires 'cm_id' in ROUTE_RESOLVED state (i.e., after rdma_resolve_route).
    - Transitions 'cm_id' from ROUTE_RESOLVED to CONNECTING upon successful call.
    - No resources are produced directly by this call; QP state transitions are
      driven by CM/verbs internally and typically signaled via CM events.
    """

    MUTABLE_FIELDS = ["id", "conn_param_obj"]

    CONTRACT = Contract(
        requires=[
            # Must have resolved route before calling rdma_connect
            RequireSpec(rtype="cm_id", state=State.ROUTE_RESOLVED, name_attr="id"),
        ],
        produces=[
            # rdma_connect does not produce new resources synchronously
        ],
        transitions=[
            # The cm_id begins the connection process
            TransitionSpec(rtype="cm_id", from_state=State.ROUTE_RESOLVED, to_state=State.CONNECTED, name_attr="id"),
        ],
    )

    def __init__(self, id: str, conn_param_obj: RdmaConnParam = None):
        """
        Args:
            id: Name of the rdma_cm_id resource to connect.
            conn_param_obj: Optional structured object representing rdma_conn_param.
                            If provided, it must implement `to_cxx(var_name, ctx) -> str`
                            which returns C code that declares and initializes a variable
                            named `var_name` of type `struct rdma_conn_param`.
                            If None, rdma_connect will be invoked with NULL for default params.
        """
        if not id:
            raise ValueError("id (rdma_cm_id) must be provided for RdmaConnect")

        # CM-ID resource reference
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

        # Optional connection parameter object
        # This is treated as an opaque codegen helper with a to_cxx method.
        self.conn_param_obj = conn_param_obj

    def apply(self, ctx: CodeGenContext):
        # Hook for binding or bookkeeping in the codegen context if needed.
        # For now, we only apply the contract.
        self.context = ctx
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)

        # Derive a readable suffix from the cm_id name for variable naming.
        suffix = "_" + id_name.replace("id[", "").replace("]", "")
        conn_var = f"conn_param{suffix}"

        # If a conn_param_obj is provided, emit its C code; otherwise pass NULL.
        param_code = ""
        if self.conn_param_obj is not None:
            # Expect conn_param_obj.to_cxx to declare and initialize `conn_var`
            # as a `struct rdma_conn_param`.
            param_code = self.conn_param_obj.to_cxx(conn_var, ctx)
            conn_arg = f"&{conn_var}"
        else:
            conn_arg = "NULL"

        return f"""
    /* rdma_connect: initiate active connection request */
    IF_OK_PTR({id_name}, {{
        {param_code}
        int rc = rdma_connect({id_name}, {conn_arg});
        if (rc) {{
            fprintf(stderr, "rdma_connect({id_name}) failed: rc=%d (%s)\\n", rc, strerror(errno));
        }} else {{
            // Runtime model hint: cm_id is now connecting; actual ESTABLISHED is async via CM events.
            mark_cm_id_state("{id_name}", "CONNECTING");
        }}
    }});
"""
