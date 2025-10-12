# -*- coding: utf-8 -*-
"""
Model for RDMA CM API: rdma_getaddrinfo

Semantics:
- rdma_getaddrinfo resolves RDMA addresses and routes similar to POSIX getaddrinfo.
- Inputs: node (hostname/IP), service (service name/port), optional hints (struct rdma_addrinfo).
- Output: res (struct rdma_addrinfo *) which must be freed via rdma_freeaddrinfo.
- This plugin wraps the API as a VerbCall for use in a fuzzing/trace framework, producing an
  rdma_addrinfo resource on success.
"""

from typing import Optional

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, State
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaAddrinfoHints:
    """
    Lightweight Python-side model of struct rdma_addrinfo used as 'hints'.
    Only a subset of fields are supported for fuzzing convenience.
    """

    def __init__(
        self,
        ai_flags: Optional[int] = None,
        ai_port_space: Optional[int] = None,  # e.g., RDMA_PS_TCP, RDMA_PS_UDP
        ai_qp_type: Optional[int] = None,  # e.g., IBV_QPT_RC, IBV_QPT_UD
        ai_family: Optional[int] = None,  # e.g., AF_INET, AF_INET6
    ):
        self.ai_flags = ai_flags
        self.ai_port_space = ai_port_space
        self.ai_qp_type = ai_qp_type
        self.ai_family = ai_family

    def to_cxx(self, var_name: str, ctx: CodeGenContext) -> str:
        """
        Emit C code that declares and initializes a struct rdma_addrinfo <var_name> as hints.
        """
        lines = []
        lines.append(f"struct rdma_addrinfo {var_name};")
        lines.append(f"memset(&{var_name}, 0, sizeof({var_name}));")
        if self.ai_flags is not None:
            lines.append(f"{var_name}.ai_flags = {int(self.ai_flags)};")
        if self.ai_port_space is not None:
            lines.append(f"{var_name}.ai_port_space = {int(self.ai_port_space)};")
        if self.ai_qp_type is not None:
            lines.append(f"{var_name}.ai_qp_type = {int(self.ai_qp_type)};")
        if self.ai_family is not None:
            lines.append(f"{var_name}.ai_family = {int(self.ai_family)};")
        return "\n        ".join(lines)


class RdmaGetAddrInfo(VerbCall):
    """
    Wrap rdma_getaddrinfo(node, service, hints, &res).

    Parameters:
    - node: Optional[str] hostname/IP. If None, pass NULL.
    - service: Optional[str] service name or port string. If None, pass NULL.
    - hints_obj: Optional[RdmaAddrinfoHints] to initialize 'struct rdma_addrinfo' hints; if None, pass NULL.
    - res: str name for the produced rdma_addrinfo resource pointer (required).

    Produces:
    - rdma_addrinfo resource (state=ALLOCATED).
    """

    MUTABLE_FIELDS = ["node", "service", "hints_obj", "res"]

    CONTRACT = Contract(
        requires=[],
        produces=[
            ProduceSpec(rtype="rdma_addrinfo", state=State.ALLOCATED, name_attr="res"),
        ],
        transitions=[],
    )

    def __init__(
        self,
        node: Optional[str] = None,
        service: Optional[str] = None,
        hints_obj: Optional[RdmaAddrinfoHints] = None,
        res: Optional[str] = None,
    ):
        if not res:
            raise ValueError("res must be provided for RdmaGetAddrInfo")

        # Raw Python strings for node/service; turned into C-string literals in generate_c
        self.node = node
        self.service = service

        # Optional hints object
        self.hints_obj = hints_obj

        # Produced resource pointer; framework manages lifecycle via rdma_freeaddrinfo later
        self.res = ResourceValue(resource_type="rdma_addrinfo", value=res, mutable=False)

    @staticmethod
    def _c_escape(s: str) -> str:
        """
        Convert a Python string into a properly escaped C string literal.
        """
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        # Also escape newlines/tabs if present
        escaped = escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f'"{escaped}"'

    def apply(self, ctx: CodeGenContext):
        # Allocate the result pointer variable in the C context
        ctx.alloc_variable(str(self.res), "struct rdma_addrinfo *", "NULL")

        # Allow contract-based resource/state bookkeeping
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        res_name = str(self.res)
        suffix = "_" + res_name.replace("[", "_").replace("]", "_")

        node_var = f"rai_node{suffix}"
        service_var = f"rai_service{suffix}"
        hints_name = f"rai_hints{suffix}"

        # Build code for optional hints
        hints_code = ""
        hints_ptr = "NULL"
        if self.hints_obj is not None:
            hints_code = self.hints_obj.to_cxx(hints_name, ctx)
            hints_ptr = f"&{hints_name}"

        # Node/Service C-string setup
        node_init = f"const char *{node_var} = NULL;"
        service_init = f"const char *{service_var} = NULL;"

        if self.node is not None:
            node_init = f"const char *{node_var} = {self._c_escape(self.node)};"
        if self.service is not None:
            service_init = f"const char *{service_var} = {self._c_escape(self.service)};"

        return f"""
    /* rdma_getaddrinfo */
    {node_init}
    {service_init}
    {hints_code}
    do {{
        int gai_ret = rdma_getaddrinfo({node_var}, {service_var}, {hints_ptr}, &{res_name});
        if (gai_ret) {{
            fprintf(stderr, "rdma_getaddrinfo failed (ret=%d, node=%s, service=%s)\\n",
                    gai_ret,
                    {node_var} ? {node_var} : "NULL",
                    {service_var} ? {service_var} : "NULL");
        }}
    }} while (0);
"""
