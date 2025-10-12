# RDMA CM Plugin: rdma_listen
# This plugin models the rdma_listen API, which initiates listening for incoming RDMA connection requests
# (or datagram service lookup) on a previously bound rdma_cm_id. The listen is restricted to the locally
# bound source address and associated device/port. Users must have called rdma_bind_addr on the cm_id before
# invoking rdma_listen. On success, the cm_id transitions into a passive/listening state ready to produce
# RDMA_CM_EVENT_CONNECT_REQUEST events via rdma_get_cm_event.

"""
RdmaListen plugin class that wraps rdma_listen(struct rdma_cm_id *id, int backlog).

Semantics:
- Requires a valid rdma_cm_id bound to a local address (rdma_bind_addr already performed).
- Initiates a passive listen for incoming connection requests with a specified backlog.
- Transitions the cm_id from BOUND to LISTENING state in the framework's resource contract system.

Notes:
- The listen is restricted to the bound local address and associated RDMA device/port.
- If bound to a specific IP, listening is restricted to that address/device.
- If bound only to an RDMA port number, listening occurs across all RDMA devices.

See also:
- rdma_bind_addr, rdma_connect, rdma_accept, rdma_reject, rdma_get_cm_event
"""

from typing import Optional

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State, TransitionSpec
from lib.value import (
    IntValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaListen(VerbCall):
    """
    Python-side model for rdma_listen.

    Parameters:
    - id: Name of the rdma_cm_id resource (struct rdma_cm_id *) to listen on.
    - backlog: Integer backlog for incoming connection requests.

    Example usage in a scenario:
        RdmaListen(id="cm_id0", backlog=16)
    """

    MUTABLE_FIELDS = ["id", "backlog"]

    CONTRACT = Contract(
        requires=[
            # rdma_listen requires the CM ID to be bound to a local address first.
            RequireSpec(rtype="cm_id", state=State.BOUND, name_attr="id"),
        ],
        produces=[
            # No new resource is produced; the cm_id transitions to LISTENING.
        ],
        transitions=[
            TransitionSpec(rtype="cm_id", from_state=State.BOUND, to_state=State.LISTENING, name_attr="id"),
        ],
    )

    def __init__(self, id: str, backlog: int = 16):
        if not id:
            raise ValueError("id (rdma_cm_id resource name) must be provided for RdmaListen")

        # Resource handle to the rdma_cm_id
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

        # Backlog for incoming connection requests (use IntValue so fuzzing can mutate/override)
        self.backlog = IntValue(value=backlog)

        # Codegen context populated in apply()
        self.context: Optional[CodeGenContext] = None

    def apply(self, ctx: CodeGenContext):
        """
        Apply contracts and potentially register any context-level bindings.
        """
        self.context = ctx
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        """
        Emit C code that calls rdma_listen(id, backlog) with basic error handling.
        """
        id_name = str(self.id)
        backlog_expr = str(self.backlog)

        return f"""
    /* rdma_listen */
    IF_OK_PTR({id_name}, {{
        int ret = rdma_listen({id_name}, {backlog_expr});
        if (ret) {{
            perror("rdma_listen");
            fprintf(stderr, "rdma_listen failed on {id_name} (backlog=%d), ret=%d\\n", {backlog_expr}, ret);
        }} else {{
            fprintf(stdout, "rdma_listen succeeded on {id_name} (backlog=%d)\\n", {backlog_expr});
        }}
    }});
"""
