from typing import Dict

try:
    from .objtracker import ObjectTracker
except ImportError:
    from objtracker import ObjectTracker

try:
    from .contracts import ContractTable
except ImportError:
    from contracts import ContractTable

predefined_variables = {  # 全局变量，写在template里面的
    "ibv_qp": "struct ibv_qp",
    "ibv_cq": "struct ibv_cq",
    "ibv_pd": "struct ibv_pd",
    "ibv_mr": "struct ibv_mr",
    "ibv_context": "struct ibv_context",
    "ibv_device_attr": "struct ibv_device_attr",
    "ibv_port_attr": "struct ibv_port_attr",
    "ibv_gid": "struct ibv_gid",
    "MRPool": "struct metadata_pool",
    "mr_pool_size": "int",
    "remote_info": "struct metadata_global",
    "local_remote_qp_map": "map<int, int>",
    "qpn_to_index_map": "map<int, int>",
    "qp_pool": "QPWithBufferPool",
    "bufs": "char",
    "req": "struct pair_request",
    "qp_attr": "struct ibv_qp_attr",
    "wc": "struct ibv_wc",
    "start_time_msec": "unsigned long",
    "end_time_msec": "unsigned long",
    "cur_time": "struct timeval",
    "poll_result": "int",
    "rc": "int",
}


class CodeGenContext:
    """Holds object-name mappings used during code generation."""

    RES_TO_TYPE = {
        "pd": "struct ibv_pd*",
        "cq": "struct ibv_cq*",
        "qp": "struct ibv_qp*",
        "mr": "struct ibv_mr*",
        "srq": "struct ibv_srq*",
        "td": "struct ibv_td*",
        "xrcd": "struct ibv_xrcd*",
        "ah": "struct ibv_ah*",
        "dm": "struct ibv_dm*",
        "mw": "struct ibv_mw*",
        "wq": "struct ibv_wq*",
        "context": "struct ibv_context*",
    }

    def __init__(self):
        self.dev_list = "dev_list"  # Device list name
        self.ib_ctx = "ctx"  # IB context name
        self.dev_attr = "dev_attr"  # Device attributes name
        self.port_attr = "port_attr"  # Port attributes name
        self.tracker = ObjectTracker()  # Object tracker for managing resources

        self.variables = {}
        self.max_QPs = 100
        self.gid_idx = 1
        self.msg_buf_name = "bufs"

        self.alloc_variable(self.msg_buf_name, "char", None, "[1024][1024]")
        self.bindings = {}  # local qp -> remote qp

        self.qp_recv_cq_binding = {}  # local qp -> cq
        self.qp_send_cq_binding = {}  # local qp -> cq

        self.contracts = ContractTable()

    # ---- alloc helpers ----
    def alloc_variable(self, name, type, init_value=None, array_size=None):
        if name in self.variables and type != self.variables[name][0]:
            raise ValueError(f"Variable '{name}' already allocated, but with a different type {self.variables[name]}.")
        else:
            if name in self.variables:
                # raise ValueError(f"Variable '{name}' already allocated.")
                # support reuse
                return False
            else:
                self.variables[name] = [type, init_value, array_size]
                return True

    def use_variable(self, name):
        if name not in self.variables:
            raise ValueError(f"Variable '{name}' used before allocation")
        return self.variables[name]

    def generate_variable_definition(self, name):
        if name not in self.variables:
            raise ValueError(f"Variable '{name}' not allocated")
        type = self.variables[name][0]
        init_value = self.variables[name][1]
        array_size = self.variables[name][2]
        if array_size is not None:
            if init_value is not None:
                raise ValueError("Array variable cannot have an initial value")
            # return f"{type} {name}[{array_size}];"
            return f"{type} {name}{array_size};"
        if init_value is not None:
            return f"{type} {name} = {init_value};"
        return f"{type} {name};"
        # if self.variables[name][1] is not None:
        #     return f"{self.variables[name][0]} {name} = {self.variables[name][1]};"
        # return f"{self.variables[name][0]} {name};"

    def generate_variable_definitions_all(self):
        definitions = []
        for name, type in self.variables.items():
            definitions.append(self.generate_variable_definition(name))
        return "\n".join(definitions)

    def alloc_variables_objtracker(self):
        """Allocates all predefined variables in the object tracker."""
        for type in ObjectTracker.SUPPORTED_TYPES:
            variables = self.tracker.find_by_type(type)
            # if not variables:
            #     print(f"[Warning] No variables of type '{type}' found in the tracker.")
            #     return
            for varname in variables:
                self.alloc_variable(varname, self.RES_TO_TYPE[type])

        pass

    def gen_var_name(self, prefix="var", sep="_"):
        idx = 0
        while True:
            name = f"{prefix}{sep}{idx}"
            if name not in self.variables:
                return name
            idx += 1

    def make_qp_binding(self, local_qp: str, remote_qp: str):
        self.bindings[local_qp] = remote_qp

    def make_qp_recv_cq_binding(self, local_qp: str, cq: str):
        self.qp_recv_cq_binding[local_qp] = cq

    def make_qp_send_cq_binding(self, local_qp: str, cq: str):
        self.qp_send_cq_binding[local_qp] = cq

    def get_peer_qp_num(self, local_qp: str) -> str:
        if local_qp not in self.bindings:
            raise ValueError(f"No binding found for local QP '{local_qp}'")
        return self.bindings[local_qp]
