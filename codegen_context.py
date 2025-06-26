from typing import Dict

predefined_variables = { # 全局变量，写在template里面的
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
    "rc": "int"

}

class CodeGenContext:
    """Holds object-name mappings used during code generation."""

    def __init__(self):
        self.qp_map: Dict[str, str] = {}   # addr(str) -> name (e.g., qp_table[0])
        self.mr_map: Dict[str, str] = {}
        self.qp_cnt = 0
        self.mr_cnt = 0
        self.dev_list = "dev_list"  # Device list name
        self.ib_ctx = "ctx"  # IB context name
        self.dev_attr = "dev_attr"  # Device attributes name
        self.port_attr = "port_attr"  # Port attributes name
        
        self.pd_map: Dict[str, str] = {}  # pd_name -> pd_table name
        self.pd_cnt = 0
        
        self.cq_map: Dict[str, str] = {}  # cq_name -> cq_table name
        self.cq_cnt = 0

        self.gid_idx = 1
        
        self.max_QPs = 100

        self.variables = {}

    # ---- alloc helpers ----
    def alloc_varaible(self, name, value):
        if name in self.variables and value != self.variables[name]:
            raise ValueError(f"Variable '{name}' already allocated, but with a different type.")
        else:
            if name in self.variables:
                return False
            else:
                self.variables[name] = value
                return True
            
    def use_variable(self, name):
        if name not in self.variables:
            raise ValueError(f"Variable '{name}' used before allocation")
        return self.variables[name]
    
    def generate_variable_definition(self, name):
        if name not in self.variables:
            raise ValueError(f"Variable '{name}' not allocated")
        if '*' in self.variables[name]:
            return f"{self.variables[name]} {name} = NULL;"
        # elif 'struct' in self.variables[name]:
        #     return f"{self.variables[name]} {name} = {{{{0}}}};"
        else:
            return f"{self.variables[name]} {name};"
        
    def generate_variable_definitions_all(self):
        definitions = []
        for name, value in self.variables.items():
            definitions.append(self.generate_variable_definition(name))
        return "\n    ".join(definitions)

    def alloc_qp(self, addr):
        name = f"qp[{self.qp_cnt}]"
        self.qp_map[addr] = name
        self.qp_cnt += 1
        return name

    def get_qp(self, addr):
        if addr not in self.qp_map:
            raise ValueError(f"QP address {addr} used before allocation")
        return self.qp_map[addr]

    def use_qp(self, addr):
        if addr not in self.qp_map:
            print(f"[Warning] QP {addr} used before allocation. Auto-allocating.")
            return self.alloc_qp(addr)
        return self.qp_map[addr]
    
    def alloc_pd(self, addr):
        name = f"pd[{self.pd_cnt}]"
        self.pd_map[addr] = name
        self.pd_cnt += 1
        return name

    def get_pd(self, addr):
        if addr not in self.pd_map:
            raise ValueError(f"PD address {addr} used before allocation")
        return self.pd_map[addr]

    def use_pd(self, addr):
        if addr not in self.pd_map:
            print(f"[Warning] PD {addr} used before allocation. Auto-allocating.")
            return self.alloc_pd(addr)
        return self.pd_map[addr]
    
   
    def alloc_mr(self, addr):
        name = f"mr[{self.mr_cnt}]"
        self.mr_map[addr] = name
        self.mr_cnt += 1
        return name

    def get_mr(self, addr):
        if addr not in self.mr_map:
            raise ValueError(f"MR address {addr} used before allocation")
        return self.mr_map[addr]

    def use_mr(self, addr):
        if addr not in self.mr_map:
            print(f"[Warning] MR {addr} used before allocation. Auto-allocating.")
            return self.alloc_mr(addr)
        return self.mr_map[addr]
    
    def alloc_cq(self, addr):
        name = f"cq[{self.cq_cnt}]"
        self.cq_map[addr] = name
        self.cq_cnt += 1
        return name

    def get_cq(self, addr):
        if addr not in self.cq_map:
            raise ValueError(f"CQ address {addr} used before allocation")
        return self.cq_map[addr]

    def use_cq(self, addr):
        if addr not in self.cq_map:
            print(f"[Warning] CQ {addr} used before allocation. Auto-allocating.")
            return self.alloc_cq(addr)
        return self.cq_map[addr]
    
    def destroy_qp(self, addr):
        if addr in self.qp_map:
            del self.qp_map[addr]
        else:
            print(f"[Warning] destroy_qp: QP {addr} was not allocated.")

    def destroy_cq(self, addr):
        if addr in self.cq_map:
            del self.cq_map[addr]
        else:
            print(f"[Warning] destroy_cq: CQ {addr} was not allocated.")

    def destroy_pd(self, addr):
        if addr in self.pd_map:
            del self.pd_map[addr]
        else:
            print(f"[Warning] destroy_pd: PD {addr} was not allocated.")

    def destroy_mr(self, addr):
        if addr in self.mr_map:
            del self.mr_map[addr]
        else:
            print(f"[Warning] destroy_mr: MR {addr} was not allocated.")

    def dump_summary(self):
        return {
            "QP": list(self.qp_map.values()),
            "CQ": list(self.cq_map.values()),
            "PD": list(self.pd_map.values()),
            "MR": list(self.mr_map.values()),
        }
