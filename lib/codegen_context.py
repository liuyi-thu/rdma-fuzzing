from typing import Dict
from .objtracker import ObjectTracker

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

        # self.global_variables = {}

    # ---- alloc helpers ----
    def alloc_variable(self, name, value, init_value=None):
        print('alloc_variable', name, value, init_value)
        if name in self.variables and value != self.variables[name][0]:
            raise ValueError(f"Variable '{name}' already allocated, but with a different type {self.variables[name]}.")
        else:
            if name in self.variables:
                return False
            else:
                self.variables[name] = [value, init_value]
                return True
            
    def use_variable(self, name):
        if name not in self.variables:
            raise ValueError(f"Variable '{name}' used before allocation")
        return self.variables[name]
    
    def generate_variable_definition(self, name):
        if name not in self.variables:
            raise ValueError(f"Variable '{name}' not allocated")
        if self.variables[name][1] is not None:
            return f"{self.variables[name][0]} {name} = {self.variables[name][1]};"
        return f"{self.variables[name][0]} {name};"
        # if '*' in self.variables[name][0]:
        #     return f"{self.variables[name][0]} {name} = NULL;"
        # # elif 'struct' in self.variables[name]:
        # #     return f"{self.variables[name]} {name} = {{{{0}}}};"
        # else:
        #     return f"{self.variables[name][0]} {name};"
        
    def generate_variable_definitions_all(self):
        definitions = []
        for name, value in self.variables.items():
            definitions.append(self.generate_variable_definition(name))
        return "\n    ".join(definitions)
    
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
        # for name, value in predefined_variables.items():
        #     if not self.tracker.alloc_variable(name, value):
        #         print(f"[Warning] Variable '{name}' already allocated with a different type.")
        # return self.tracker
#         
# class CodeGenContext:
#     """Holds object-name mappings used during code generation."""

#     def __init__(self):
#         self.qp_map: Dict[str, str] = {}   # addr(str) -> name (e.g., qp_table[0])
#         self.mr_map: Dict[str, str] = {}
#         self.qp_cnt = 0
#         self.mr_cnt = 0
#         self.dev_list = "dev_list"  # Device list name
#         self.ib_ctx = "ctx"  # IB context name
#         self.dev_attr = "dev_attr"  # Device attributes name
#         self.port_attr = "port_attr"  # Port attributes name
        
#         self.pd_map: Dict[str, str] = {}  # pd_name -> pd_table name
#         self.pd_cnt = 0
        
#         self.cq_map: Dict[str, str] = {}  # cq_name -> cq_table name
#         self.cq_cnt = 0

#         self.srq_map: Dict[str, str] = {}  # srq_name -> srq_table name
#         self.srq_cnt = 0

#         self.td_map: Dict[str, str] = {}  # td_name -> td_table name
#         self.td_cnt = 0

#         self.xrcd_map: Dict[str, str] = {}  # xrcd_name -> xrcd_table name
#         self.xrcd_cnt = 0

#         self.comp_channel_map: Dict[str, str] = {}  # comp_channel_name -> comp_channel_table name
#         self.comp_channel_cnt = 0

#         self.cq_ex_map: Dict[str, str] = {}  # comp_channel_name -> comp_channel_table name
#         self.cq_ex_cnt = 0

#         self.flow_map: Dict[str, str] = {}  # flow_name -> flow_table name
#         self.flow_cnt = 0

#         self.mw_map: Dict[str, str] = {}  # memory window name -> memory window table name
#         self.mw_cnt = 0

#         self.wq_map: Dict[str, str] = {}  # work queue name -> work queue table name
#         self.wq_cnt = 0

#         self.dm_map: Dict[str, str] = {}  # dm_name -> dm_table name
#         self.dm_cnt = 0

#         self.qp_ex_map: Dict[str, str] = {}  # qp_ex_name -> qp_ex_table name
#         self.qp_ex_cnt = 0

#         self.gid_idx = 1
        
#         self.max_QPs = 100

#         self.variables = {}

#     # ---- alloc helpers ----
#     def alloc_variable(self, name, value, init_value=None):
#         print('alloc_variable', name, value, init_value)
#         if name in self.variables and value != self.variables[name][0]:
#             raise ValueError(f"Variable '{name}' already allocated, but with a different type {self.variables[name]}.")
#         else:
#             if name in self.variables:
#                 return False
#             else:
#                 self.variables[name] = [value, init_value]
#                 return True
            
#     def use_variable(self, name):
#         if name not in self.variables:
#             raise ValueError(f"Variable '{name}' used before allocation")
#         return self.variables[name]
    
#     def generate_variable_definition(self, name):
#         if name not in self.variables:
#             raise ValueError(f"Variable '{name}' not allocated")
#         if self.variables[name][1] is not None:
#             return f"{self.variables[name][0]} {name} = {self.variables[name][1]};"
#         return f"{self.variables[name][0]} {name};"
#         # if '*' in self.variables[name][0]:
#         #     return f"{self.variables[name][0]} {name} = NULL;"
#         # # elif 'struct' in self.variables[name]:
#         # #     return f"{self.variables[name]} {name} = {{{{0}}}};"
#         # else:
#         #     return f"{self.variables[name][0]} {name};"
        
#     def generate_variable_definitions_all(self):
#         definitions = []
#         for name, value in self.variables.items():
#             definitions.append(self.generate_variable_definition(name))
#         return "\n    ".join(definitions)

#     def alloc_qp(self, addr):
#         name = f"qp[{self.qp_cnt}]"
#         self.qp_map[addr] = name
#         self.qp_cnt += 1
#         return name

#     def get_qp(self, addr):
#         if addr not in self.qp_map:
#             raise ValueError(f"QP address {addr} used before allocation")
#         return self.qp_map[addr]

#     def use_qp(self, addr):
#         if addr not in self.qp_map:
#             print(f"[Warning] QP {addr} used before allocation. Auto-allocating.")
#             return self.alloc_qp(addr)
#         return self.qp_map[addr]
    
#     def alloc_pd(self, addr):
#         name = f"pd[{self.pd_cnt}]"
#         self.pd_map[addr] = name
#         self.pd_cnt += 1
#         return name

#     def get_pd(self, addr):
#         if addr not in self.pd_map:
#             raise ValueError(f"PD address {addr} used before allocation")
#         return self.pd_map[addr]

#     def use_pd(self, addr):
#         if addr not in self.pd_map:
#             print(f"[Warning] PD {addr} used before allocation. Auto-allocating.")
#             return self.alloc_pd(addr)
#         return self.pd_map[addr]
    
   
#     def alloc_mr(self, addr):
#         name = f"mr[{self.mr_cnt}]"
#         self.mr_map[addr] = name
#         self.mr_cnt += 1
#         return name

#     def get_mr(self, addr):
#         if addr not in self.mr_map:
#             raise ValueError(f"MR address {addr} used before allocation")
#         return self.mr_map[addr]

#     def use_mr(self, addr):
#         if addr not in self.mr_map:
#             print(f"[Warning] MR {addr} used before allocation. Auto-allocating.")
#             return self.alloc_mr(addr)
#         return self.mr_map[addr]
    
#     def alloc_cq(self, addr):
#         name = f"cq[{self.cq_cnt}]"
#         self.cq_map[addr] = name
#         self.cq_cnt += 1
#         return name

#     def get_cq(self, addr):
#         if addr not in self.cq_map:
#             raise ValueError(f"CQ address {addr} used before allocation")
#         return self.cq_map[addr]

#     def use_cq(self, addr):
#         if addr not in self.cq_map:
#             print(f"[Warning] CQ {addr} used before allocation. Auto-allocating.")
#             return self.alloc_cq(addr)
#         return self.cq_map[addr]
    
#     def alloc_srq(self, addr):
#         name = f"srq[{self.srq_cnt}]"
#         self.srq_map[addr] = name
#         self.srq_cnt += 1
#         return name
    
#     def get_srq(self, addr):
#         if addr not in self.srq_map:
#             raise ValueError(f"SRQ address {addr} used before allocation")
#         return self.srq_map[addr]

#     def use_srq(self, addr):
#         if addr not in self.srq_map:
#             print(f"[Warning] SRQ {addr} used before allocation. Auto-allocating.")
#             return self.alloc_srq(addr)
#         return self.srq_map[addr]
    
#     def destroy_qp(self, addr):
#         if addr in self.qp_map:
#             del self.qp_map[addr]
#         else:
#             print(f"[Warning] destroy_qp: QP {addr} was not allocated.")

#     def destroy_cq(self, addr):
#         if addr in self.cq_map:
#             del self.cq_map[addr]
#         else:
#             print(f"[Warning] destroy_cq: CQ {addr} was not allocated.")

#     def destroy_pd(self, addr):
#         if addr in self.pd_map:
#             del self.pd_map[addr]
#         else:
#             print(f"[Warning] destroy_pd: PD {addr} was not allocated.")

#     def destroy_mr(self, addr):
#         if addr in self.mr_map:
#             del self.mr_map[addr]
#         else:
#             print(f"[Warning] destroy_mr: MR {addr} was not allocated.")

#     def destroy_srq(self, addr):
#         if addr in self.srq_map:
#             del self.srq_map[addr]
#         else:
#             print(f"[Warning] destroy_srq: SRQ {addr} was not allocated.")

#     def alloc_td(self, addr):
#         name = f"td[{self.td_cnt}]"
#         self.td_map[addr] = name
#         self.td_cnt += 1
#         return name
    
#     def get_td(self, addr):
#         if addr not in self.td_map:
#             raise ValueError(f"td address {addr} used before allocation")
#         return self.td_map[addr]

#     def use_td(self, addr):
#         if addr not in self.td_map:
#             print(f"[Warning] td {addr} used before allocation. Auto-allocating.")
#             return self.alloc_td(addr)
#         return self.td_map[addr]
        
#     def destroy_td(self, addr):
#         if addr in self.td_map:
#             del self.td_map[addr]
#         else:
#             print(f"[Warning] destroy_td: TD {addr} was not allocated.")

#     def alloc_xrcd(self, addr):
#         name = f"xrcd[{self.xrcd_cnt}]"
#         self.xrcd_map[addr] = name
#         self.xrcd_cnt += 1
#         return name
    
#     def get_xrcd(self, addr):
#         if addr not in self.xrcd_map:
#             raise ValueError(f"xrcd address {addr} used before allocation")
#         return self.xrcd_map[addr]

#     def use_xrcd(self, addr):
#         if addr not in self.xrcd_map:
#             print(f"[Warning] xrcd {addr} used before allocation. Auto-allocating.")
#             return self.alloc_xrcd(addr)
#         return self.xrcd_map[addr]
        
#     def destroy_xrcd(self, addr):
#         if addr in self.xrcd_map:
#             del self.xrcd_map[addr]
#         else:
#             print(f"[Warning] destroy_xrcd: XRCD {addr} was not allocated.")

#     def alloc_comp_channel(self, addr):
#         name = f"comp_channel[{self.comp_channel_cnt}]"
#         self.comp_channel_map[addr] = name
#         self.comp_channel_cnt += 1
#         return name
    
#     def get_comp_channel(self, addr):
#         if addr not in self.comp_channel_map:
#             raise ValueError(f"comp_channel address {addr} used before allocation")
#         return self.comp_channel_map[addr]

#     def use_comp_channel(self, addr):
#         if addr not in self.comp_channel_map:
#             print(f"[Warning] comp_channel {addr} used before allocation. Auto-allocating.")
#             return self.alloc_comp_channel(addr)
#         return self.comp_channel_map[addr]
        
#     def destroy_comp_channel(self, addr):
#         if addr in self.comp_channel_map:
#             del self.comp_channel_map[addr]
#         else:
#             print(f"[Warning] destroy_comp_channel: comp_channel {addr} was not allocated.")

#     def alloc_cq_ex(self, addr):
#         name = f"cq_ex[{self.cq_ex_cnt}]"
#         self.cq_ex_map[addr] = name
#         self.cq_ex_cnt += 1
#         return name
    
#     def get_cq_ex(self, addr):
#         if addr not in self.cq_ex_map:
#             raise ValueError(f"cq_ex address {addr} used before allocation")
#         return self.cq_ex_map[addr]

#     def use_cq_ex(self, addr):
#         if addr not in self.cq_ex_map:
#             print(f"[Warning] cq_ex {addr} used before allocation. Auto-allocating.")
#             return self.alloc_cq_ex(addr)
#         return self.cq_ex_map[addr]
        
#     def destroy_cq_ex(self, addr):
#         if addr in self.cq_ex_map:
#             del self.cq_ex_map[addr]
#         else:
#             print(f"[Warning] destroy_cq_ex: cq_ex {addr} was not allocated.")

#     def alloc_flow(self, addr):
#         name = f"flow[{self.flow_cnt}]"
#         self.flow_map[addr] = name
#         self.flow_cnt += 1
#         return name
    
#     def get_flow(self, addr):
#         if addr not in self.flow_map:
#             raise ValueError(f"flow address {addr} used before allocation")
#         return self.flow_map[addr]

#     def use_flow(self, addr):
#         if addr not in self.flow_map:
#             print(f"[Warning] flow {addr} used before allocation. Auto-allocating.")
#             return self.alloc_flow(addr)
#         return self.flow_map[addr]
        
#     def destroy_flow(self, addr):
#         if addr in self.flow_map:
#             del self.flow_map[addr]
#         else:
#             print(f"[Warning] destroy_flow: flow {addr} was not allocated.")

#     def alloc_mw(self, addr):
#         name = f"mw[{self.mw_cnt}]"
#         self.mw_map[addr] = name
#         self.mw_cnt += 1
#         return name
    
#     def get_mw(self, addr):
#         if addr not in self.mw_map:
#             raise ValueError(f"mw address {addr} used before allocation")
#         return self.mw_map[addr]

#     def use_mw(self, addr):
#         if addr not in self.mw_map:
#             print(f"[Warning] mw {addr} used before allocation. Auto-allocating.")
#             return self.alloc_mw(addr)
#         return self.mw_map[addr]
        
#     def destroy_mw(self, addr):
#         if addr in self.mw_map:
#             del self.mw_map[addr]
#         else:
#             print(f"[Warning] destroy_mw: mw {addr} was not allocated.")

#     def alloc_wq(self, addr):
#         name = f"wq[{self.wq_cnt}]"
#         self.wq_map[addr] = name
#         self.wq_cnt += 1
#         return name
    
#     def get_wq(self, addr):
#         if addr not in self.wq_map:
#             raise ValueError(f"wq address {addr} used before allocation")
#         return self.wq_map[addr]

#     def use_wq(self, addr):
#         if addr not in self.wq_map:
#             print(f"[Warning] wq {addr} used before allocation. Auto-allocating.")
#             return self.alloc_wq(addr)
#         return self.wq_map[addr]
        
#     def destroy_wq(self, addr):
#         if addr in self.wq_map:
#             del self.wq_map[addr]
#         else:
#             print(f"[Warning] destroy_wq: wq {addr} was not allocated.")

#     def alloc_dm(self, addr):
#         name = f"dm[{self.dm_cnt}]"
#         self.dm_map[addr] = name
#         self.dm_cnt += 1
#         return name
    
#     def get_dm(self, addr):
#         if addr not in self.dm_map:
#             raise ValueError(f"dm address {addr} used before allocation")
#         return self.dm_map[addr]

#     def use_dm(self, addr):
#         if addr not in self.dm_map:
#             print(f"[Warning] dm {addr} used before allocation. Auto-allocating.")
#             return self.alloc_dm(addr)
#         return self.dm_map[addr]
        
#     def destroy_dm(self, addr):
#         if addr in self.dm_map:
#             del self.dm_map[addr]
#         else:
#             print(f"[Warning] destroy_dm: dm {addr} was not allocated.")

#     def alloc_qp_ex(self, addr):
#         name = f"qp_ex[{self.qp_ex_cnt}]"
#         self.qp_ex_map[addr] = name
#         self.qp_ex_cnt += 1
#         return name
    
#     def get_qp_ex(self, addr):
#         if addr not in self.qp_ex_map:
#             raise ValueError(f"qp_ex address {addr} used before allocation")
#         return self.qp_ex_map[addr]

#     def use_qp_ex(self, addr):
#         if addr not in self.qp_ex_map:
#             print(f"[Warning] qp_ex {addr} used before allocation. Auto-allocating.")
#             return self.alloc_qp_ex(addr)
#         return self.qp_ex_map[addr]
        
#     def destroy_qp_ex(self, addr):
#         if addr in self.qp_ex_map:
#             del self.qp_ex_map[addr]
#         else:
#             print(f"[Warning] destroy_qp_ex: qp_ex {addr} was not allocated.")



#     def dump_summary(self):
#         return {
#             "QP": list(self.qp_map.values()),
#             "CQ": list(self.cq_map.values()),
#             "PD": list(self.pd_map.values()),
#             "MR": list(self.mr_map.values()),
#             "SRQ": list(self.srq_map.values()),
#         }
