from collections import defaultdict
from typing import Dict

try:
    from .objtracker import ObjectTracker
except ImportError:
    from objtracker import ObjectTracker


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

        self.claim_qps = []  # 仅用于可选的全局统计；实际 CLAIМ 用事件化方式
        self.claim_mrs = []
        self.claim_pairs = []  # [{id, cli_id, srv_id}]
        self.bindings = {}  # {"qp0": "srv0"}
        self.gid_var = "gid"

        # 事件：在第 i 个 verb 之前/之后插入代码片段
        self.events_before = defaultdict(list)  # i -> [str...]
        self.events_after = defaultdict(list)  # i -> [str...]

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

    def get_peer_qp_num(self, local_qp: str) -> str:
        if local_qp not in self.bindings:
            raise ValueError(f"No binding found for local QP '{local_qp}'")
        return self.bindings[local_qp]

    # 绑定本地 QP → 远端 ID（例如 "qp0" → "srv0"）
    def make_qp_binding(self, local_qp: str, remote_id: str):
        self.bindings[local_qp] = remote_id

    def get_peer_id(self, local_qp: str) -> str:
        return self.bindings.get(local_qp, "srv0")

    # ========= 便捷：在 verb 后就地 CLAIM =========
    def schedule_claim_qp_after(self, idx: int, qp_id: str, qp_var: str, port: int = 1, lid: int = 0):
        code = f"""
    // CLAIM QP {qp_id}
    qps[qps_size++] = (PR_QP){{ .id="{qp_id}", .qpn={qp_var}->qp_num, .psn=0, .port={port}, .lid={lid}, .gid="" }};
    pr_gid_to_str({self.gid_var}.raw, qps[qps_size-1].gid, PR_GID_STRLEN);
    pr_write_client_update_claimed(CLIENT_UPDATE_PATH, qps, qps_size, mrs, mrs_size, prs, prs_size);
"""
        self.events_after[idx].append(code)

    def schedule_claim_mr_after(self, idx: int, mr_id: str, mr_var: str, length_expr: str):
        code = f"""
    // CLAIM MR {mr_id}
    mrs[mrs_size++] = (PR_MR){{ .id="{mr_id}", .addr=(uint64_t)({mr_var}->addr), .length={length_expr}, .lkey={mr_var}->lkey }};
    pr_write_client_update_claimed(CLIENT_UPDATE_PATH, qps, qps_size, mrs, mrs_size, prs, prs_size);
"""
        self.events_after[idx].append(code)

    # ========= 便捷：在 verb 前就地 WAIT & 解析远端字段 =========
    def schedule_wait_and_resolve_before(self, idx: int, pair_id: str, qp_name: str, srv_id: str):
        rqpn = f"rqpn_{qp_name}"
        rlid = f"rlid_{qp_name}"
        rport = f"rport_{qp_name}"
        rgid = f"rgid_{qp_name}"
        self.alloc_variable(rqpn, "uint32_t")
        self.alloc_variable(rlid, "uint32_t")
        self.alloc_variable(rport, "uint32_t")
        self.alloc_variable(rgid, "const char*")
        code = f"""
    // WAIT & RESOLVE for {pair_id}
    if (!pr_wait_pair_state(BUNDLE_ENV, "{pair_id}", "BOTH_RTS", 15000)) {{
        fprintf(stderr, "wait gate failed\\n"); return -1;
    }}
    {rqpn}  = rr_u32_by_id("remote.QP", "{srv_id}", "qpn");
    {rlid}  = rr_u32_by_id("remote.QP", "{srv_id}", "lid");
    {rport} = rr_u32_by_id("remote.QP", "{srv_id}", "port");
    {rgid}  = rr_str_by_id("remote.QP", "{srv_id}", "gid");
    pr_write_client_update_ready(CLIENT_UPDATE_PATH, qps, qps_size, mrs, mrs_size, prs, prs_size);
"""
        self.events_before[idx].append(code)

    def remote_syms_for_qp(self, qp_name: str):
        return {
            "rqpn": f"rqpn_{qp_name}",
            "rlid": f"rlid_{qp_name}",
            "rport": f"rport_{qp_name}",
            "rgid": f"rgid_{qp_name}",  # char*
        }
