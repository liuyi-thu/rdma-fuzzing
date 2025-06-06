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
    def alloc_qp(self, addr: str) -> str:
        if addr not in self.qp_map:
            self.qp_map[addr] = f"qp_table[{self.qp_cnt}]"
            self.qp_cnt += 1
        return self.qp_map[addr]

    def get_qp(self, addr: str) -> str:
        return self.qp_map.get(addr, "qp_table[0]")

    def alloc_mr(self, addr: str) -> str:
        if addr not in self.mr_map:
            self.mr_map[addr] = f"mr_table[{self.mr_cnt}]"
            self.mr_cnt += 1
        return self.mr_map[addr]

    def get_mr(self, addr: str) -> str:
        return self.mr_map.get(addr, "mr_table[0]")
    
    def alloc_pd(self, pd_name: str) -> str:
        if pd_name not in self.pd_map:
            self.pd_map[pd_name] = f"pd_table[{self.pd_cnt}]"
            self.pd_cnt += 1
        return self.pd_map[pd_name]
    
    def get_pd(self, pd_name: str) -> str:
        return self.pd_map.get(pd_name, "pd_table[0]")
    
    def alloc_cq(self, cq_name: str) -> str:
        if cq_name not in self.cq_map:
            self.cq_map[cq_name] = f"cq_table[{self.cq_cnt}]"
            self.cq_cnt += 1
        return self.cq_map[cq_name]
    def get_cq(self, cq_name: str) -> str:
        return self.cq_map.get(cq_name, "cq_table[0]")