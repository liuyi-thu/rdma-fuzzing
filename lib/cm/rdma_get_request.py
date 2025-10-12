#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modeling rdma_get_request CM API.

rdma_get_request is a server-side CM operation that dequeues a pending connection
request from a listening rdma_cm_id. On success, it returns 0 and sets *id to a new
rdma_cm_id representing the incoming connection request. This new cm_id can later be
used to accept or reject the connection (e.g., via rdma_accept/rdma_reject).
Typical usage flow: rdma_create_id -> rdma_bind_addr -> rdma_listen -> rdma_get_request.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, RequireSpec, State
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaGetRequest(VerbCall):
    """
    Python-side model for rdma_get_request(listen, &id).

    Parameters:
    - listen: variable name of an existing listening struct rdma_cm_id *
    - id: variable name to hold the resulting struct rdma_cm_id * for the request

    Contract:
    - Requires: listen cm_id is in a listening/allocated state.
    - Produces: a new cm_id in allocated state, associated with the given listen cm_id.
    """

    MUTABLE_FIELDS = ["listen", "id"]

    CONTRACT = Contract(
        requires=[
            # The listening CM ID must exist/allocated (and, semantically, in listening state).
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="listen"),
        ],
        produces=[
            # Produce a new cm_id representing the request; store metadata linking to parent listen id.
            ProduceSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id", metadata_fields=["listen"]),
        ],
        transitions=[
            # rdma_get_request does not change the listen cm_id state.
        ],
    )

    def __init__(self, listen: str = None, id: str = None):
        if not listen:
            raise ValueError("listen (listening rdma_cm_id variable name) must be provided for RdmaGetRequest")
        if not id:
            raise ValueError("id (output rdma_cm_id variable name) must be provided for RdmaGetRequest")

        self.listen = ResourceValue(resource_type="cm_id", value=listen)
        # The output cm_id holder; name is fixed, will be assigned in generated C.
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

    def apply(self, ctx: CodeGenContext):
        self.context = ctx

        # Ensure the output variable exists in the generated C environment.
        ctx.alloc_variable(str(self.id), "struct rdma_cm_id *", "NULL")

        # Apply contract tracking if the framework supports it.
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        listen_name = str(self.listen)
        id_name = str(self.id)

        return f"""
    /* rdma_get_request */
    IF_OK_PTR({listen_name}, {{
        int rc = rdma_get_request({listen_name}, &{id_name});
        if (rc) {{
            fprintf(stderr, "rdma_get_request on %s failed: %d (%s)\\n", "{listen_name}", rc, strerror(-rc));
        }} else if (!{id_name}) {{
            fprintf(stderr, "rdma_get_request succeeded but returned NULL id\\n");
        }}
    }});
"""
