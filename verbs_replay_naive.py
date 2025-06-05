
"""verbs_replay.py  —  Generate RDMA replay C code from JSON trace.

Initial verb coverage:
  * ibv_create_qp
  * ibv_reg_mr
  * ibv_post_send
  * ibv_post_recv
"""

import json
import re
from typing import List, Dict, Any
import os


class Config:
    def __init__(self):
        self.dev_name: str = None       # IB device name
        self.server_name: str = None    # server host name
        self.tcp_port: int = 0          # server TCP port
        self.ib_port: int = 1           # local IB port to work with
        self.gid_idx: int = -1          # gid index to use
        self.udp_sport: int = 0         # udp source port
        
        
# ---------- Internal helpers -------------------------------------------------
def _parse_kv(info: str) -> Dict[str, str]:
    """Parse "k=v k2=v2" style string into dict."""
    out = {}
    for tok in info.replace(',', ' ').split():
        if '=' in tok:
            k, v = tok.split('=', 1)
            out[k.strip()] = v.strip()
    return out


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
        


# ---------- Verb call base ----------------------------------------------------
class VerbCall:
    def generate_c(self, ctx: CodeGenContext) -> str:  # pylint: disable=unused-argument
        raise NotImplementedError

class UtilityCall: # 生成verbs之外的函数
    def generate_c(self, ctx: CodeGenContext) -> str:  # pylint: disable=unused-argument
        raise NotImplementedError

# Utility functions for the generated code
class AllocBuf(UtilityCall):
    def __init__(self, buf_size: int = 4096):
        self.buf_size = buf_size

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* Allocate buffer */
    char buf[{self.buf_size}];
    if (!buf) {{
        fprintf(stderr, "Failed to allocate buffer\\n");
        return -1;
    }}
"""

class SockConnect(UtilityCall):
    def __init__(self, server_name: str, port: int):
        self.server_name = server_name
        self.port = port

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* Connect to server */
    sock = sock_connect("{self.server_name}", {self.port});
    if (sock < 0) {{
        fprintf(stderr, "Failed to connect to {self.server_name}:{self.port}\\n");
        return -1;
    }}
"""

# class SockSyncData(UtilityCall):
#     def __init__(self, xfer_size: int = 4096):
#         self.xfer_size = xfer_size

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         return f"""
#     /* Synchronize data over socket */
#     int rc = sock_sync_data(sock, {self.xfer_size}, buf, remote_con_data);
#     if (rc < 0) {{
#         fprintf(stderr, "Failed to sync data over socket\\n");
#         return -1;
#     }}
# """

class SockSyncData(UtilityCall):
    def __init__(self):
        pass

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_addr = ctx.get_qp("qp_table[0]")
        mr = ctx.get_mr("mr_table[0]")

        return f"""
    local_con_data.addr = htonll((uintptr_t)buf);
    local_con_data.rkey = htonl({mr}->rkey);
    local_con_data.qp_num = htonl({qp_addr}->qp_num);
    local_con_data.lid = htons(port_attr.lid);
    memcpy(local_con_data.gid, &my_gid, 16);
    if(sock_sync_data(sock, sizeof(struct cm_con_data_t), (char *) &local_con_data, (char *) &tmp_con_data) < 0)
    {{
        fprintf(stderr, "failed to exchange connection data between sides\\n");
        return 1;
    }}

    remote_con_data.addr = ntohll(tmp_con_data.addr);
    remote_con_data.rkey = ntohl(tmp_con_data.rkey);
    remote_con_data.qp_num = ntohl(tmp_con_data.qp_num);
    remote_con_data.lid = ntohs(tmp_con_data.lid);
    memcpy(remote_con_data.gid, tmp_con_data.gid, 16);
"""
    
class SockSyncDummy(UtilityCall):
    def __init__(self, char = "Q"):
        self.char = char  # This is a dummy synchronization character, not used in the actual data transfer.
        pass
    """Dummy synchronization, used when no actual data transfer is needed."""
    def generate_c(self, ctx: CodeGenContext) -> str:
        return """
    /* Dummy sync, no actual data transfer */
    sock_sync_data(sock, 1, "{char}", &temp_char);
"""
# ---------- Specific verb implementations ------------------------------------


class GetDeviceList(VerbCall):
    def __init__(self, ctx: CodeGenContext):
        self.ctx = ctx

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        return cls(mr_addr=kv.get("addr", "unknown"))
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        dev_list = ctx.dev_list
        return f"""
    /* ibv_get_device_list */
    {dev_list} = ibv_get_device_list(NULL);
    if (!{dev_list}) {{
        fprintf(stderr, "Failed to get device list\\n");
        return -1;
    }}
"""

class OpenDevice(VerbCall):
    def __init__(self, ctx: CodeGenContext):
        self.ctx = ctx

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        return cls()
    def generate_c(self, ctx: CodeGenContext) -> str:
        dev_list = ctx.dev_list
        ib_ctx = ctx.ib_ctx # 默认打开第0个设备
        return f"""
    /* ibv_open_device */
    {ib_ctx} = ibv_open_device({dev_list}[0]);
    if (!{ib_ctx}) {{
        fprintf(stderr, "Failed to open device\\n");
        return -1;
    }}
"""

class FreeDeviceList(VerbCall):
    def __init__(self, ctx: CodeGenContext):
        self.ctx = ctx
    def generate_c(self, ctx: CodeGenContext) -> str:
        dev_list = ctx.dev_list
        return f"""
    /* ibv_free_device_list */
    ibv_free_device_list({dev_list});
"""

class QueryDeviceAttr(VerbCall):
    def __init__(self, ctx: CodeGenContext):
        self.ctx = ctx
    def generate_c(self, ctx: CodeGenContext) -> str:
        dev_attr = ctx.dev_attr
        ib_ctx = ctx.ib_ctx
        return f"""
    /* ibv_query_device */
    if (ibv_query_device({ib_ctx}, &{dev_attr})) {{
        fprintf(stderr, "Failed to query device attributes\\n");
        return -1;
    }}
"""

class QueryPortAttr(VerbCall):
    def __init__(self, ctx: CodeGenContext):
        self.ctx = ctx
    def generate_c(self, ctx: CodeGenContext) -> str:
        dev_attr = ctx.dev_attr
        ib_ctx = ctx.ib_ctx
        port_attr = ctx.port_attr # 1 待改
        return f"""
    /* ibv_query_port */
    if (ibv_query_port({ib_ctx}, 1, &{port_attr})) {{
        fprintf(stderr, "Failed to query port attributes\\n");
        return -1;
    }}
"""

class QueryGID(VerbCall):
    def __init__(self, ctx: CodeGenContext):
        self.ctx = ctx

    def generate_c(self, ctx: CodeGenContext) -> str:
        port_attr = ctx.port_attr
        gid_idx = ctx.gid_idx
        return f"""
    /* ibv_query_gid */
    if (ibv_query_gid({ctx.ib_ctx}, 1, {gid_idx}, &my_gid)) {{
        fprintf(stderr, "Failed to query GID\\n");
        return -1;
    }}
"""
class AllocPD(VerbCall):
    def __init__(self, ctx: CodeGenContext):
        self.ctx = ctx

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.alloc_pd("pd_table[0]")
        return f"""
    /* ibv_alloc_pd */
    {pd_name} = ibv_alloc_pd({ctx.ib_ctx});
    if (!{pd_name}) {{
        fprintf(stderr, "Failed to allocate protection domain\\n");
        return -1;
    }}
"""

class CreateCQ(VerbCall):
    def __init__(self, ctx: CodeGenContext):
        self.ctx = ctx
        
    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = ctx.alloc_cq("cq_table[0]")
        return f"""
    /* ibv_create_cq */
    {cq_name} = ibv_create_cq({ctx.ib_ctx}, 32, NULL, NULL, 0);
    if (!{cq_name}) {{
        fprintf(stderr, "Failed to create completion queue\\n");
        return -1;
    }}
"""

class ModifyQP(VerbCall):
    def __init__(self, qp_addr: str, state: str):
        self.qp_addr = qp_addr
        self.state = state

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        return cls(kv.get("qp", "unknown"), kv.get("state", "IBV_QPS_INIT"))

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        attr_suffix = "_" + qp_name.replace("qp_table[", "").replace("]", "")  # e.g., "_0" for qp_table[0]
        attr_name = f"attr_modify_init{attr_suffix}"
        return f"""
    /* ibv_modify_qp */
    struct ibv_qp_attr {attr_name} = {{0}};
    {attr_name}.qp_state = {self.state};
    {attr_name}.pkey_index = 0;
    {attr_name}.port_num = 1;
    {attr_name}.qp_access_flags = IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE;
    ibv_modify_qp({qp_name}, &{attr_name}, IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS);
    """

class ModifyQPToRTR(VerbCall):
    def __init__(self, qp_addr: str, remote_qpn: int = 0, dlid: int = 0, dgid: str = "0"):
        self.qp_addr = qp_addr
        # self.remote_qpn = remote_qpn
        # self.dlid = dlid
        # self.dgid = dgid  # Global ID, not used in this example
        self.remote_qpn = "remote_con_data.qp_num"
        self.dlid = "remote_con_data.lid"
        self.dgid = "remote_con_data.gid"  # Use the gid from the remote connection data

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        return cls(kv.get("qp", "unknown"))

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        attr_suffix = "_" + qp_name.replace("qp_table[", "").replace("]", "")  # e.g., "_0" for qp_table[0]
        attr_name = f"attr_modify_rtr{attr_suffix}"
        return f"""
    /* ibv_modify_qp to RTR */
    struct ibv_qp_attr {attr_name} = {{0}};
    {attr_name}.qp_state = IBV_QPS_RTR;
    {attr_name}.path_mtu = IBV_MTU_256; /* this field specifies the MTU from source code*/
    {attr_name}.dest_qp_num = {self.remote_qpn};
    {attr_name}.rq_psn = 0;
    {attr_name}.max_dest_rd_atomic = 1;
    {attr_name}.min_rnr_timer = 0x12;
    {attr_name}.ah_attr.is_global = 0;
    {attr_name}.ah_attr.dlid = {self.dlid};
    {attr_name}.ah_attr.sl = 0;
    {attr_name}.ah_attr.src_path_bits = 0;
    {attr_name}.ah_attr.port_num = 1;
    if(1 >= 0)
    {{
        {attr_name}.ah_attr.is_global = 1;
        {attr_name}.ah_attr.port_num = 1;
        memcpy(&{attr_name}.ah_attr.grh.dgid, {self.dgid}, 16);
        /* this field specify the UDP source port. if the target UDP source port is expected to be X, the value of flow_label = X ^ 0xC000 */
        {attr_name}.ah_attr.grh.flow_label = 0;
        {attr_name}.ah_attr.grh.hop_limit = 1;
        {attr_name}.ah_attr.grh.sgid_index = 1;
        {attr_name}.ah_attr.grh.traffic_class = 0;
    }}
    ibv_modify_qp({qp_name}, &{attr_name}, IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER);
"""

class ModifyQPToRTS(VerbCall):
    def __init__(self, qp_addr: str):
        self.qp_addr = qp_addr

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        return cls(kv.get("qp", "unknown"))

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        attr_suffix = "_" + qp_name.replace("qp_table[", "").replace("]", "")  # e.g., "_0" for qp_table[0]
        attr_name = f"attr_modify_rts{attr_suffix}"
        return f"""
    /* ibv_modify_qp to RTS */
    struct ibv_qp_attr {attr_name} = {{0}};
    {attr_name}.qp_state = IBV_QPS_RTS;
    {attr_name}.timeout = 0x12;
    {attr_name}.retry_cnt = 6;
    {attr_name}.rnr_retry = 0;
    {attr_name}.sq_psn = 0;
    {attr_name}.max_rd_atomic = 1;
    ibv_modify_qp({qp_name}, &{attr_name}, IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC);
"""
    
class CreateQP(VerbCall):
    def __init__(self, pd="pd_table[0]", qp_addr="unknown", qp_type="IBV_QPT_RC"):
        self.pd = pd
        self.qp_addr = qp_addr
        self.qp_type = qp_type

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        return cls(qp_addr=kv.get("qp", "unknown"), qp_type="IBV_QPT_RC")

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.alloc_qp(self.qp_addr)
        attr_suffix = "_" + qp_name.replace("qp_table[", "").replace("]", "")  # e.g., "_0" for qp_table[0]
        attr_name = f"attr_init{attr_suffix}"
        return f"""
    /* ibv_create_qp */
    struct ibv_qp_init_attr {attr_name} = {{0}};
    {attr_name}.qp_type = {self.qp_type};
    {attr_name}.send_cq = cq_table[0];
    {attr_name}.recv_cq = cq_table[0];
    {attr_name}.cap.max_send_wr = 1;
    {attr_name}.cap.max_recv_wr = 1;
    {attr_name}.cap.max_send_sge = 1;
    {attr_name}.cap.max_recv_sge = 1;
    {qp_name} = ibv_create_qp({self.pd}, &{attr_name});
"""


class RegMR(VerbCall):
    def __init__(self, pd="pd_table[0]", buf="buf", length=4096, mr_addr="unknown", flags="IBV_ACCESS_LOCAL_WRITE"):
        self.pd = pd
        self.buf = buf
        self.length = length
        self.mr_addr = mr_addr
        self.flags = flags

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        return cls(mr_addr=kv.get("addr", "unknown"))

    def generate_c(self, ctx: CodeGenContext) -> str:
        mr_name = ctx.alloc_mr(self.mr_addr)
        return f"""
    /* ibv_reg_mr */
    {mr_name} = ibv_reg_mr({self.pd}, {self.buf}, {self.length}, {self.flags});
"""


class PostSend(VerbCall):
    def __init__(self, qp_addr: str, wr_id: str, opcode: str):
        self.qp_addr = qp_addr
        self.wr_id = wr_id
        self.opcode = opcode

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        return cls(kv.get("qp", "unknown"), kv.get("wr_id", "0"), kv.get("opcode", "0"))

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        suffix = "_" + qp_name.replace("qp_table[", "").replace("]", "")  # e.g., "_0" for qp_table[0]
        sr = f"sr{suffix}"
        mr = ctx.get_mr("mr_table[0]")  # Assume mr_table[0] is the MR we registered
        buf = "buf"  # Assume buf is the buffer we registered
        sge = f"sge_send{suffix}"
        bad_wr = f"bad_wr_send{suffix}"
        return f"""
    /* ibv_post_send */
    struct ibv_send_wr {sr};
    struct ibv_sge {sge};
    struct ibv_send_wr *{bad_wr} = NULL;

    memset(&{sge}, 0, sizeof({sge})); // nested variables
    {sge}.addr = (uintptr_t)buf; // HARD-WIRED
    {sge}.length = MSG_SIZE;
    {sge}.lkey = {mr}->lkey; // HARD-WIRED

    /* prepare the send work request */
    memset(&{sr}, 0, sizeof({sr})); // nested variables
    {sr}.next = NULL;
    {sr}.wr_id = {self.wr_id};  // HARD-WIRED
    {sr}.sg_list = &{sge};
    {sr}.num_sge = 1;
    {sr}.opcode = {self.opcode};
    {sr}.send_flags = IBV_SEND_SIGNALED;

    /*
    if({self.opcode} != IBV_WR_SEND) // 暂不考虑READ和WRITE？
    {{
        {sr}.wr.rdma.remote_addr = res->remote_props.addr; // HARD-WIRED
        {sr}.wr.rdma.rkey = res->remote_props.rkey; // HARD-WIRED
    }}
    */

    /* there is a Receive Request in the responder side, so we won't get any into RNR flow */
    ibv_post_send({qp_name}, &{sr}, &{bad_wr});
"""


class PostRecv(VerbCall):
    def __init__(self, qp_addr: str, wr_id: str):
        self.qp_addr = qp_addr
        self.wr_id = wr_id

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        return cls(kv.get("qp", "unknown"), kv.get("wr_id", "0"))

    # def generate_c(self, ctx: CodeGenContext) -> str:
    #     qp_name = ctx.get_qp(self.qp_addr)
    #     return f"""
    # /* ibv_post_recv */
    # struct ibv_recv_wr rwr = {{0}}; struct ibv_recv_wr *bad_rwr;
    # rwr.wr_id = {self.wr_id};
    # ibv_post_recv({qp_name}, &rwr, &bad_rwr);
    # """
    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        suffix = "_" + qp_name.replace("qp_table[", "").replace("]", "")  # e.g., "_0" for qp_table[0]
        rr = f"rr{suffix}"
        mr = ctx.get_mr("mr_table[0]")  # Assume mr_table[0] is the MR we registered
        buf = "buf"  # Assume buf is the buffer we registered
        sge = f"sge_recv{suffix}"
        bad_wr = f"bad_wr_recv{suffix}"
        # Use the buf and mr directly, assuming they are hard-wired as per the original code
        return f"""
    /* ibv_post_recv */
    struct ibv_recv_wr {rr};
    struct ibv_sge {sge};
    struct ibv_recv_wr *{bad_wr};
    memset(&{sge}, 0, sizeof({sge}));
    {sge}.addr = (uintptr_t)buf; // HARD-WIRED
    {sge}.length = MSG_SIZE;
    {sge}.lkey = {mr}->lkey; // HARD-WIRED

    /* prepare the receive work request */
    memset(&{rr}, 0, sizeof({rr}));
    {rr}.next = NULL;
    {rr}.wr_id = {self.wr_id};  // HARD-WIRED
    {rr}.sg_list = &{sge};
    {rr}.num_sge = 1;
    ibv_post_recv({qp_name}, &{rr}, &{bad_wr});
    """

class PollCompletion(VerbCall):
    """Poll completion queue for a specific QP."""
    def __init__(self, qp_addr: str):
        self.qp_addr = qp_addr

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        return cls(kv.get("qp", "unknown"))

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        cq_name = ctx.get_cq("cq_table[0]")  # Assume cq_table[0] is the CQ we created
        return f"""
    /* Poll completion queue */
    struct ibv_wc wc;
    unsigned long start_time_msec;
    unsigned long cur_time_msec;
    struct timeval cur_time;
    int poll_result;
    int rc = 0;
    /* poll the completion for a while before giving up of doing it .. */
    gettimeofday(&cur_time, NULL);
    start_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    do
    {{
        poll_result = ibv_poll_cq({cq_name}, 1, &wc);
        gettimeofday(&cur_time, NULL);
        cur_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
    }}
    while((poll_result == 0) && ((cur_time_msec - start_time_msec) < MAX_POLL_CQ_TIMEOUT));

    if(poll_result < 0)
    {{
        /* poll CQ failed */
        fprintf(stderr, "poll CQ failed\\n");
        rc = 1;
    }}
    else if(poll_result == 0)
    {{
        /* the CQ is empty */
        fprintf(stderr, "completion wasn't found in the CQ after timeout\\n");
        rc = 1;
    }}
    else
    {{
        /* CQE found */
        fprintf(stdout, "completion was found in CQ with status 0x%x\\n", wc.status);
        /* check the completion status (here we don't care about the completion opcode */
        if(wc.status != IBV_WC_SUCCESS)
        {{
            fprintf(stderr, "got bad completion with status: 0x%x, vendor syndrome: 0x%x\\n", 
                    wc.status, wc.vendor_err);
            rc = 1;
        }}
    }}
"""
    
class DestroyQP(VerbCall):
    """Destroy a QP."""
    def __init__(self, qp_addr: str):
        self.qp_addr = qp_addr

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        return cls(kv.get("qp", "unknown"))

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        return f"""
    /* ibv_destroy_qp */
    if (ibv_destroy_qp({qp_name})) {{
        fprintf(stderr, "Failed to destroy QP\\n");
        return -1;
    }}
"""
    
class DestroyMR(VerbCall):
    """Destroy a Memory Region."""
    def __init__(self, mr_addr: str):
        self.mr_addr = mr_addr

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        return cls(kv.get("addr", "unknown"))

    def generate_c(self, ctx: CodeGenContext) -> str:
        mr_name = ctx.get_mr(self.mr_addr)
        return f"""
    /* ibv_dereg_mr */
    if (ibv_dereg_mr({mr_name})) {{
        fprintf(stderr, "Failed to deregister MR\\n");
        return -1;
    }}
"""
    
class DestroyCQ(VerbCall):
    """Destroy a Completion Queue."""
    def __init__(self, cq_addr: str):
        self.cq_addr = cq_addr

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        return cls(kv.get("cq", "unknown"))

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = ctx.get_cq(self.cq_addr)
        return f"""
    /* ibv_destroy_cq */
    if (ibv_destroy_cq({cq_name})) {{
        fprintf(stderr, "Failed to destroy CQ\\n");
        return -1;
    }}
"""
    
class DestroyPD(VerbCall):
    """Destroy a Protection Domain."""
    def __init__(self, pd_addr: str):
        self.pd_addr = pd_addr

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        return cls(kv.get("pd", "unknown"))

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.get_pd(self.pd_addr)
        return f"""
    /* ibv_dealloc_pd */
    if (ibv_dealloc_pd({pd_name})) {{
        fprintf(stderr, "Failed to deallocate PD\\n");
        return -1;
    }}
"""

class CloseDevice(VerbCall):
    """Close the IB device context."""
    def __init__(self, ctx: CodeGenContext):
        self.ctx = ctx

    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = ctx.ib_ctx
        return f"""
    /* ibv_close_device */
    if (ibv_close_device({ib_ctx})) {{
        fprintf(stderr, "Failed to close device\\n");
        return -1;
    }}
"""

class SocketClose(UtilityCall):
    """Close the socket connection."""
    def __init__(self, sock: str):
        self.sock = sock

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* Close socket */
    if (close({self.sock}) < 0) {{
        fprintf(stderr, "Failed to close socket\\n");
        return -1;
    }}
"""
# Mapping verb -> constructor
VERB_FACTORY = {
    "ibv_create_qp": CreateQP.from_trace,
    "ibv_reg_mr": RegMR.from_trace,
    "ibv_post_send": PostSend.from_trace,
    "ibv_post_recv": PostRecv.from_trace,
    "ibv_get_device_list": GetDeviceList.from_trace,
    "ibv_open_device": OpenDevice.from_trace
}


# ---------- Public helpers ----------------------------------------------------
def parse_trace(json_path: str) -> List[VerbCall]:
    """Read trace_output.json and convert to VerbCall list."""
    calls: List[VerbCall] = []
    with open(json_path, "r") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            verb = rec["verb"]
            info = rec["info"]
            ctor = VERB_FACTORY.get(verb)
            if ctor:
                calls.append(ctor(info))
    return calls


def generate_replay_code(trace_json: str, buf_size: int = 4096) -> str:
    """Generate full C source file string from trace JSON."""
    calls = parse_trace(trace_json)
    ctx = CodeGenContext()

    header = f"""#include <stdio.h>\n#include <infiniband/verbs.h>\n\nstruct ibv_context *ctx;\nstruct ibv_pd *pd_table[10];\nstruct ibv_cq *cq_table[10];\nstruct ibv_qp *qp_table[10];\nstruct ibv_mr *mr_table[10];\n\nchar buf[{buf_size}];\n\nint main() {{\n    struct ibv_device **dev_list = ibv_get_device_list(NULL);\n    ctx = ibv_open_device(dev_list[0]);\n    pd_table[0] = ibv_alloc_pd(ctx);\n    cq_table[0] = ibv_create_cq(ctx, 32, NULL, NULL, 0);\n"""

    body = "".join(call.generate_c(ctx) for call in calls)

    footer = """\n    ibv_free_device_list(dev_list);\n    return 0;\n}\n"""

    return header + body + footer


def generate_replay_code_fixed(buf_size):
    ctx = CodeGenContext()
    calls = [
        SockConnect(server_name="192.168.56.11", port=19875),  # Connect to server, hard-coded for example

        # resources_create start
        GetDeviceList(ctx),
        OpenDevice(ctx),
        FreeDeviceList(ctx),
        QueryDeviceAttr(ctx),
        QueryPortAttr(ctx),
        AllocPD(ctx),
        CreateCQ(ctx),
        RegMR(pd=ctx.get_pd("pd_table[0]"), buf="buf", length=buf_size, mr_addr="mr_table[0]", flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE"),
        CreateQP(pd=ctx.get_pd("pd_table[0]"), qp_addr="qp_table[0]", qp_type="IBV_QPT_RC"),
        # resources_create end

        # connect_qp start
        QueryGID(ctx),  # Query GID for the local port
        SockSyncData(),  # Synchronize connection data over socket


        # modify QP to INIT state
        ModifyQP(qp_addr="qp_table[0]", state="IBV_QPS_INIT"),

        PostRecv(qp_addr="qp_table[0]", wr_id="0"),  # Post a receive request

        # modify QP to RTR state
        ModifyQPToRTR(qp_addr="qp_table[0]", remote_qpn=1, dlid=0, dgid="0"), # 这是一个问题，remote_qpn和dlid应该从远端获取，暂时写死为1和0

        # modify QP to RTS state
        ModifyQPToRTS(qp_addr="qp_table[0]"),
        SockSyncDummy(),  # Dummy sync, no actual data transfer


        # connect_qp end

        # post_send start
        PostSend(qp_addr="qp_table[0]", wr_id="1", opcode="IBV_WR_SEND"),
        PollCompletion(qp_addr="qp_table[0]"),  # Poll for completion

        # post_send end

        SockSyncDummy(char="R"),  # Dummy sync, no actual data transfer

        DestroyQP(qp_addr="qp_table[0]"),  # Destroy the QP

        DestroyMR(mr_addr="mr_table[0]"),  # Destroy the MR
        DestroyCQ(cq_addr="cq_table[0]"),  # Destroy the CQ
        DestroyPD(pd_addr="pd_table[0]"),  # Destroy the PD
        CloseDevice(ctx),  # Close the device context
        SocketClose(sock="sock")  # Close the socket connection 







    ]

    header = f"""#include <stdio.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdint.h>
#include <inttypes.h>
#include <endian.h>
#include <byteswap.h>
#include <getopt.h>
#include <sys/time.h>
#include <arpa/inet.h>
#include <infiniband/verbs.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netdb.h>\n

#define MAX_POLL_CQ_TIMEOUT 2000
#define MSG_S "SEND operation from server"
#define MSG_C "SEND operation from client"
#define RDMAMSGR "RDMA read operation "
#define RDMAMSGW "RDMA write operation"
#define MSG_SIZE 64
#if __BYTE_ORDER == __LITTLE_ENDIAN
static inline uint64_t htonll(uint64_t x)
{{
    return bswap_64(x);
}}
static inline uint64_t ntohll(uint64_t x)
{{
    return bswap_64(x);
}}
#elif __BYTE_ORDER == __BIG_ENDIAN
static inline uint64_t htonll(uint64_t x)
{{
    return x;
}}
static inline uint64_t ntohll(uint64_t x)
{{
    return x;
}}
#else
#error __BYTE_ORDER is neither __LITTLE_ENDIAN nor __BIG_ENDIAN
#endif

struct ibv_context *ctx;
struct ibv_pd *pd_table[10];
struct ibv_cq *cq_table[10];
struct ibv_qp *qp_table[10];
struct ibv_mr *mr_table[10];
struct ibv_device **dev_list;
struct ibv_device_attr {ctx.dev_attr};
struct ibv_port_attr {ctx.port_attr};
struct cm_con_data_t local_con_data;
struct cm_con_data_t remote_con_data;
struct cm_con_data_t tmp_con_data;
struct cm_con_data_t remote_props;
union ibv_gid my_gid;

int sock;
char temp_char;
char buf[{buf_size}];\n

struct cm_con_data_t
{{
    uint64_t addr;        /* Buffer address */
    uint32_t rkey;        /* Remote key */
    uint32_t qp_num;      /* QP number */
    uint16_t lid;         /* LID of the IB port */
    uint8_t gid[16];      /* gid */
}} __attribute__((packed));

static int sock_connect(const char *servername, int port)
{{
    struct addrinfo *resolved_addr = NULL;
    struct addrinfo *iterator;
    char service[6];
    int sockfd = -1;
    int listenfd = 0;
    int tmp;
    struct addrinfo hints =
    {{
        .ai_flags    = AI_PASSIVE,
        .ai_family   = AF_INET,
        .ai_socktype = SOCK_STREAM
    }};

    if(sprintf(service, "%d", port) < 0)
    {{
        goto sock_connect_exit;
    }}

    /* Resolve DNS address, use sockfd as temp storage */
    sockfd = getaddrinfo(servername, service, &hints, &resolved_addr);
    if(sockfd < 0)
    {{
        fprintf(stderr, "%s for %s:%d\\n", gai_strerror(sockfd), servername, port);
        goto sock_connect_exit;
    }}

    /* Search through results and find the one we want */
    for(iterator = resolved_addr; iterator ; iterator = iterator->ai_next)
    {{
        sockfd = socket(iterator->ai_family, iterator->ai_socktype, iterator->ai_protocol);
        if(sockfd >= 0)
        {{
            if(servername)
            {{
                /* Client mode. Initiate connection to remote */
                if((tmp=connect(sockfd, iterator->ai_addr, iterator->ai_addrlen)))
                {{
                    fprintf(stdout, "failed connect \\n");
                    close(sockfd);
                    sockfd = -1;
                }}
            }}
            else
            {{
                /* Server mode. Set up listening socket an accept a connection */
                listenfd = sockfd;
                sockfd = -1;
                if(bind(listenfd, iterator->ai_addr, iterator->ai_addrlen))
                {{
                    goto sock_connect_exit;
                }}
                listen(listenfd, 1);
                sockfd = accept(listenfd, NULL, 0);
            }}
        }}
    }}

sock_connect_exit:
    if(listenfd)
    {{
        close(listenfd);
    }}

    if(resolved_addr)
    {{
        freeaddrinfo(resolved_addr);
    }}

    if(sockfd < 0)
    {{
        if(servername)
        {{
            fprintf(stderr, "Couldn't connect to %s:%d\\n", servername, port);
        }}
        else
        {{
            perror("server accept");
            fprintf(stderr, "accept() failed\\n");
        }}
    }}

    return sockfd;
}}
int sock_sync_data(int sock, int xfer_size, char *local_data, char *remote_data)
{{
    int rc;
    int read_bytes = 0;
    int total_read_bytes = 0;
    rc = write(sock, local_data, xfer_size);

    if(rc < xfer_size)
    {{
        fprintf(stderr, "Failed writing data during sock_sync_data\\n");
    }}
    else
    {{
        rc = 0;
    }}

    while(!rc && total_read_bytes < xfer_size)
    {{
        read_bytes = read(sock, remote_data, xfer_size);
        if(read_bytes > 0)
        {{
            total_read_bytes += read_bytes;
        }}
        else
        {{
            rc = read_bytes;
        }}
    }}
    return rc;
}}

int main() {{
"""
    body = "".join(call.generate_c(ctx) for call in calls)
    footer = """\n return 0;\n}\n"""
    code = header + body + footer
    return code

# # for testing purposes, you can run this script directly
# if __name__  == "__main__":
#     import sys
#     if len(sys.argv) != 2:
#         print("Usage: python verbs_replay.py <trace_output.json>")
#         sys.exit(1)
    
#     trace_file = sys.argv[1]
#     code = generate_replay_code(trace_file)
#     print(code)

if __name__ == "__main__":
    # Example usage
    code = generate_replay_code_fixed(buf_size=4096)
    print(code)
    with open("verbs_replay_fixed.c", "w") as f:
        f.write(code)
    os.system('gcc -o verbs_replay_fixed verbs_replay_fixed.c  -libverbs -g')