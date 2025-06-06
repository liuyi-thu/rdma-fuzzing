from typing import Dict
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

    # ---- alloc helpers ----
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