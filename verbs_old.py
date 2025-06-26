from codegen_context import CodeGenContext
from typing import Dict, Optional

def _parse_kv(info: str) -> Dict[str, str]:
    """Parse "k=v k2=v2" style string into dict."""
    out = {}
    for tok in info.replace(',', ' ').split():
        if '=' in tok:
            k, v = tok.split('=', 1)
            out[k.strip()] = v.strip()
    return out

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
    """Generate code to establish a TCP connection.

    When `server_name` is `None` the generated code waits for an incoming
    connection, acting as a server. Otherwise it connects to `server_name`
    as a client."""

    def __init__(self, server_name: str | None, port: int):
        self.server_name = server_name
        self.port = port

    def generate_c(self, ctx: CodeGenContext) -> str:
        if self.server_name:
            server_arg = f"\"{self.server_name}\""
            fail_msg = f"Failed to connect to {self.server_name}:{self.port}"
        else:
            server_arg = "NULL"
            fail_msg = f"Failed to accept connection on port {self.port}"

        return f"""
    /* Establish TCP connection */
    sock = sock_connect({server_arg}, {self.port});
    if (sock < 0) {{
        fprintf(stderr, "{fail_msg}\\n");
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
class ExportQPInfo(UtilityCall):
    def __init__(self, qp_addr: str = "QP", mr_addr: str = "MR"):
        self.qp_addr = qp_addr  # QP address, used to get the QP number
        self.mr_addr = mr_addr

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        qp = kv.get("qp", "QP")
        mr = kv.get("mr", "MR")
        return cls(qp_addr=qp, mr_addr=mr)
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        qp = ctx.get_qp(self.qp_addr)
        mr = ctx.get_mr(self.mr_addr)
        qpn = qp.replace("qp[", "").replace("]", "")  # e.g., "0" for qp[0]

        return f"""
    /* Export connection data */
    local_con_data.addr = htonll((uintptr_t)bufs[{qpn}]);
    local_con_data.rkey = htonl({mr}->rkey);
    local_con_data.qp_num = htonl({qp}->qp_num);
    local_con_data.lid = htons(port_attr.lid);
    memcpy(local_con_data.gid, &my_gid, 16);
"""

class ImportQPInfo(UtilityCall):
    def __init__(self, qpn: int = 0):
        self.qpn = qpn  # QP address, used to get the QP number
        pass

    @classmethod
    def from_trace(cls, info: str):
        return cls()
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_num = self.qpn
        return f"""
    /* Import connection data */
    remote_con_datas[{qp_num}].addr = ntohll(tmp_con_data.addr);
    remote_con_datas[{qp_num}].rkey = ntohl(tmp_con_data.rkey);
    remote_con_datas[{qp_num}].qp_num = ntohl(tmp_con_data.qp_num);
    remote_con_datas[{qp_num}].lid = ntohs(tmp_con_data.lid);
    memcpy(remote_con_datas[{qp_num}].gid, tmp_con_data.gid, 16);
"""

#         return f"""
#     /* Import connection data */
#     remote_con_data.addr = ntohll(tmp_con_data.addr);
#     remote_con_data.rkey = ntohl(tmp_con_data.rkey);
#     remote_con_data.qp_num = ntohl(tmp_con_data.qp_num);
#     remote_con_data.lid = ntohs(tmp_con_data.lid);
#     memcpy(remote_con_data.gid, tmp_con_data.gid, 16);
# """

class SockSyncData(UtilityCall):
    def __init__(self):
        pass

    @classmethod
    def from_trace(cls, info: str):
        return cls()
    
    def generate_c(self, ctx: CodeGenContext) -> str:

        return f"""
    if(sock_sync_data(sock, sizeof(struct cm_con_data_t), (char *) &local_con_data, (char *) &tmp_con_data) < 0)
    {{
        fprintf(stderr, "failed to exchange connection data between sides\\n");
        return 1;
    }}

"""
    
class SockSyncDummy(UtilityCall):
    def __init__(self, char = "Q"):
        self.char = char  # This is a dummy synchronization character, not used in the actual data transfer.
        pass
    """Dummy synchronization, used when no actual data transfer is needed."""
    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* Dummy sync, no actual data transfer */
    sock_sync_data(sock, 1, "{self.char}", &temp_char);
"""
# ---------- Specific verb implementations ------------------------------------


class GetDeviceList(VerbCall): # 暂时只需要一个，所以不考虑alloc
    def __init__(self):
        pass

    @classmethod
    def from_trace(cls, info: str, ctx : CodeGenContext = None):
        kv = _parse_kv(info)
        return cls()
    
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

class OpenDevice(VerbCall): # 暂时只需要一个，所以不考虑alloc
    def __init__(self):
        pass

    @classmethod
    def from_trace(cls, info: str, ctx : CodeGenContext = None):
        kv = _parse_kv(info)
        return cls()
    
    """Open the first device in the device list."""
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

class FreeDeviceList(VerbCall): # 暂时只需要一个，所以不考虑alloc
    def __init__(self):
        pass
    
    @classmethod # dummy function
    def from_trace(cls, info: str, ctx : CodeGenContext = None):
        kv = _parse_kv(info)
        return cls()
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        dev_list = ctx.dev_list
        return f"""
    /* ibv_free_device_list */
    ibv_free_device_list({dev_list});
"""

class QueryDeviceAttr(VerbCall): # 暂时只需要一个，所以不考虑alloc
    def __init__(self):
        pass
    
    @classmethod # dummy function
    def from_trace(cls, info: str, ctx : CodeGenContext = None):
        kv = _parse_kv(info)
        return cls()
    
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
    def __init__(self):
        pass
    
    @classmethod # dummy function
    def from_trace(cls, info: str, ctx : CodeGenContext = None):
        kv = _parse_kv(info)
        return cls()
    
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
    def __init__(self):
        pass
    
    @classmethod # dummy function
    def from_trace(cls, info: str, ctx : CodeGenContext = None):
        kv = _parse_kv(info)
        return cls()
    
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
    def __init__(self, pd_addr, ctx: CodeGenContext):
        self.pd_addr = pd_addr
        self.ctx = ctx  # Store context for code generation
        ctx.alloc_pd(pd_addr)  # Register the PD address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        return cls(pd_addr=pd, ctx=ctx)
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.get_pd(self.pd_addr)
        return f"""
    /* ibv_alloc_pd */
    {pd_name} = ibv_alloc_pd({ctx.ib_ctx});
    if (!{pd_name}) {{
        fprintf(stderr, "Failed to allocate protection domain\\n");
        return -1;
    }}
"""

class CreateCQ(VerbCall):
    def __init__(self, cq_addr: str, ctx: CodeGenContext):
        self.cq_addr = cq_addr  # Address of the completion queue, used for code generation.
        ctx.alloc_cq(cq_addr)
        pass
    
    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq = kv.get("cq", "unknown")
        return cls(cq_addr=cq, ctx=ctx)
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = ctx.get_cq(self.cq_addr)
        return f"""
    /* ibv_create_cq */
    {cq_name} = ibv_create_cq({ctx.ib_ctx}, 32, NULL, NULL, 0);
    if (!{cq_name}) {{
        fprintf(stderr, "Failed to create completion queue\\n");
        return -1;
    }}
"""

class ModifyQP(VerbCall):
    def __init__(self, qp_addr: str, attr: Dict, attr_mask: str, ctx: CodeGenContext = None):
        self.qp_addr = qp_addr
        self.attr = attr
        self.attr_mask = attr_mask  # e.g., "IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS"

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        ctx.use_qp(qp)
        attr_keys = {"qp_state", "pkey_index", "port_num", "qp_access_flags", 
                     "path_mtu", "dest_qp_num", "rq_psn", "max_dest_rd_atomic", 
                     "min_rnr_timer", "ah_attr.is_global", "ah_attr.dlid", 
                     "ah_attr.sl", "ah_attr.src_path_bits", "ah_attr.port_num",
                    #  "ah_attr.grh.dgid", 
                     "ah_attr.grh.flow_label", 
                     "ah_attr.grh.hop_limit", "ah_attr.grh.sgid_index",
                     "ah_attr.grh.traffic_class", "timeout", "retry_cnt", "rnr_retry", "sq_psn", "max_rd_atomic"}
        attr_params = {k: kv[k] for k in attr_keys if k in kv}
        attr_mask = kv.get("attr_mask", "IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS")
        return cls(qp_addr=qp, attr=attr_params, attr_mask = attr_mask)


    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")  # e.g., "_0" for qp[0]
        # attr_name = f"attr_modify_rtr{attr_suffix}"
        attr_name = "qp_attr"
        # ah_attr.grh.dgid 特殊，必须用memcpy
        # 现在认为ah_attr.grh.dgid是一个变量名
        attr_lines = "\n    ".join(
            f"{attr_name}.{k} = {v};" for k, v in self.attr.items()
        )
        memcpy_line = f"""
            memcpy(&{attr_name}.ah_attr.grh.dgid, {self.attr['ah_attr.grh.dgid']}, 16);
        """
        return f"""
        memset(&{attr_name}, 0, sizeof({attr_name}));
        {attr_lines}
        ibv_modify_qp({qp_name}, &{attr_name}, {self.attr_mask})
        """
    
# class ModifyQP(VerbCall):
#     def __init__(self, qp_addr: str, state: str):
#         self.qp_addr = qp_addr
#         self.state = state

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         qp = kv.get("qp", "unknown")
#         state = kv.get("state", "IBV_QPS_INIT")
#         ctx.use_qp(qp)  # Ensure the QP is used before generating code
#         return cls(qp_addr = qp, state = state)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         qp_name = ctx.get_qp(self.qp_addr)
#         attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")  # e.g., "_0" for qp[0]
#         attr_name = f"attr_modify_init{attr_suffix}"
#         return f"""
#     /* ibv_modify_qp */
#     struct ibv_qp_attr {attr_name} = {{0}};
#     {attr_name}.qp_state = {self.state};
#     {attr_name}.pkey_index = 0;
#     {attr_name}.port_num = 1;
#     {attr_name}.qp_access_flags = IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE;
#     ibv_modify_qp({qp_name}, &{attr_name}, IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS);
#     """

class ModifyQPToRTR(VerbCall):
    def __init__(self, qp_addr: str, qpn: int = 0):
        self.qp_addr = qp_addr
        # self.remote_qpn = remote_qpn
        # self.dlid = dlid
        # self.dgid = dgid  # Global ID, not used in this example
        self.qpn = qpn
        self.remote_qpn = f"remote_con_datas[{self.qpn}].qp_num"
        self.dlid = f"remote_con_datas[{self.qpn}].lid"
        self.dgid = f"remote_con_datas[{self.qpn}].gid"  # Use the gid from the remote connection data

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        ctx.use_qp(qp)  # Ensure the QP is used before generating code
        return cls(qp_addr = qp)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")  # e.g., "_0" for qp[0]
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
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        ctx.use_qp(qp)  # Ensure the QP is used before generating code
        return cls(qp_addr = qp)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")  # e.g., "_0" for qp[0]
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
    def __init__(self, pd_addr="pd[0]", qp_addr="unknown", cq_addr = "cq[0]", qp_type="IBV_QPT_RC", cap_params=None, ctx = None):
        self.pd_addr = pd_addr
        self.qp_addr = qp_addr
        self.cq_addr = cq_addr  # Completion queue address, used for code generation
        self.qp_type = qp_type
        self.cap_params = cap_params or {}
        ctx.alloc_qp(self.qp_addr)

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cap_keys = {"max_send_wr", "max_recv_wr", "max_send_sge", "max_recv_sge"}
        cap_params = {k: kv[k] for k in cap_keys if k in kv}
        pd = kv.get("pd", "pd[0]")
        qp = kv.get("qp", "unknown")
        cq = kv.get("cq", "cq[0]")  # Default CQ address
        
        return cls(pd_addr=pd, qp_addr=qp, cq_addr=cq, qp_type="IBV_QPT_RC", cap_params=cap_params, ctx = ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        pd_name = ctx.get_pd(self.pd_addr)
        cq_name = ctx.get_cq(self.cq_addr)
        attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
        attr_name = f"attr_init{attr_suffix}"
        cap = self.cap_params
        cap_lines = "\n    ".join(
            f"{attr_name}.cap.{k} = {v};" for k, v in cap.items()
        )
        return f"""
    /* ibv_create_qp */
    struct ibv_qp_init_attr {attr_name} = {{0}};
    {attr_name}.qp_type = {self.qp_type};
    {attr_name}.send_cq = {cq_name};
    {attr_name}.recv_cq = {cq_name};
    {cap_lines}
    {qp_name} = ibv_create_qp({pd_name}, &{attr_name});
"""


class RegMR(VerbCall):
    def __init__(self, pd_addr, mr_addr, buf="buf", length=4096, flags="IBV_ACCESS_LOCAL_WRITE", ctx = None):
        self.pd_addr = pd_addr
        self.mr_addr = mr_addr
        self.buf = buf
        self.length = length
        self.flags = flags
        ctx.alloc_mr(mr_addr)  # Register the MR address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "pd[0]")
        mr = kv.get("mr", "unknown")
        return cls(pd_addr=pd, mr_addr=mr, flags=kv.get("flags", "IBV_ACCESS_LOCAL_WRITE"), ctx = ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        mr_name = ctx.get_mr(self.mr_addr)
        pd_name = ctx.get_pd(self.pd_addr)
        return f"""
    /* ibv_reg_mr */
    {mr_name} = ibv_reg_mr({pd_name}, {self.buf}, {self.length}, {self.flags});
"""


class PostSend(VerbCall):
    def __init__(self, qp_addr: str, mr_addr: str, wr_id: str = "0", opcode: str = "IBV_WR_SEND", 
                 remote_addr: str = None, rkey: str = None, send_flags: str = "IBV_SEND_SIGNALED"):
        self.qp_addr = qp_addr
        self.mr_addr = mr_addr  # Memory Region address, used for lkey
        self.wr_id = wr_id
        self.opcode = opcode
        self.remote_addr = remote_addr
        self.rkey = rkey
        self.send_flags = send_flags

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        mr = kv.get("mr", "MR")  # Default MR name
        ctx.use_qp(qp)
        ctx.use_mr(mr)  # Ensure the MR is used before generating code
        return cls(
            qp_addr=qp,
            mr_addr=mr,
            wr_id=kv.get("wr_id", "0"),
            opcode=kv.get("opcode", "IBV_WR_SEND"),
            remote_addr=kv.get("remote_addr"),
            rkey=kv.get("rkey"),
            send_flags=kv.get("send_flags", "IBV_SEND_SIGNALED")
        )
        
    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        qpn = qp_name.replace("qp[", "").replace("]", "")  # e.g., "0" for qp[0]
        suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
        sr = f"sr{suffix}"
        mr = ctx.get_mr(self.mr_addr)
        buf = "bufs[" + qpn + "]"  # Use bufs array for multiple QPs
        sge = f"sge_send{suffix}"
        bad_wr = f"bad_wr_send{suffix}"

        rdma_lines = ""
        # if self.remote_addr and self.rkey:
        #     rdma_lines = f"""
        # {sr}.wr.rdma.remote_addr = {self.remote_addr};
        # {sr}.wr.rdma.rkey = {self.rkey};"""

        return f"""
    /* ibv_post_send */
    struct ibv_send_wr {sr};
    struct ibv_sge {sge};
    struct ibv_send_wr *{bad_wr} = NULL;

    memset(&{sge}, 0, sizeof({sge}));
    {sge}.addr = (uintptr_t){buf};
    {sge}.length = MSG_SIZE;
    {sge}.lkey = {mr}->lkey;

    memset(&{sr}, 0, sizeof({sr}));
    {sr}.next = NULL;
    {sr}.wr_id = {self.wr_id};
    {sr}.sg_list = &{sge};
    {sr}.num_sge = 1;
    {sr}.opcode = {self.opcode};
    {sr}.send_flags = {self.send_flags};{rdma_lines}

    ibv_post_send({qp_name}, &{sr}, &{bad_wr});
"""


class PostRecv(VerbCall):
    def __init__(self, qp_addr: str, mr_addr:str, wr_id: str = "0", length: str = "MSG_SIZE"):
        self.qp_addr = qp_addr
        self.mr_addr = mr_addr  # Memory Region address, used for lkey
        self.wr_id = wr_id
        self.length = length  # default: MSG_SIZE

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        mr = kv.get("mr", "MR")  # Default MR name
        ctx.use_qp(qp)
        ctx.use_mr(mr)  # Ensure the MR is used before generating code
        return cls(
            qp_addr=qp,
            mr_addr=mr,
            wr_id=kv.get("wr_id", "0"),
            length=kv.get("length", "MSG_SIZE")
        )
    
    # """
    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        qpn = qp_name.replace("qp[", "").replace("]", "")
        suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
        rr = f"rr{suffix}"
        mr = ctx.get_mr(self.mr_addr)
        buf = "bufs[" + qpn + "]"  # Use bufs array for multiple QPs
        sge = f"sge_recv{suffix}"
        bad_wr = f"bad_wr_recv{suffix}"

        return f"""
    /* ibv_post_recv */
    struct ibv_recv_wr {rr};
    struct ibv_sge {sge};
    struct ibv_recv_wr *{bad_wr};
    memset(&{sge}, 0, sizeof({sge}));
    {sge}.addr = (uintptr_t){buf};
    {sge}.length = {self.length};
    {sge}.lkey = {mr}->lkey;

    memset(&{rr}, 0, sizeof({rr}));
    {rr}.next = NULL;
    {rr}.wr_id = {self.wr_id};
    {rr}.sg_list = &{sge};
    {rr}.num_sge = 1;

    ibv_post_recv({qp_name}, &{rr}, &{bad_wr});
    """
    
class PollCQ(VerbCall):
    def __init__(self, cq_addr: str):
        self.cq_addr = cq_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq = kv.get("cq", "unknown")
        ctx.use_cq(cq)
        return cls(cq_addr = cq)

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = ctx.get_cq(self.cq_addr)
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

# class PollCompletion(VerbCall): # deprecated, use PollCQ
#     """Poll completion queue for a specific QP."""
#     def __init__(self, qp_addr: str):
#         self.qp_addr = qp_addr

#     @classmethod
#     def from_trace(cls, info: str):
#         kv = _parse_kv(info)
#         return cls(kv.get("qp", "unknown"))

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         qp_name = ctx.get_qp(self.qp_addr)
#         cq_name = ctx.get_cq("CQ")  # Assume cq[0] is the CQ we created
#         return f"""
#     /* Poll completion queue */
#     struct ibv_wc wc;
#     unsigned long start_time_msec;
#     unsigned long cur_time_msec;
#     struct timeval cur_time;
#     int poll_result;
#     int rc = 0;
#     /* poll the completion for a while before giving up of doing it .. */
#     gettimeofday(&cur_time, NULL);
#     start_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
#     do
#     {{
#         poll_result = ibv_poll_cq({cq_name}, 1, &wc);
#         gettimeofday(&cur_time, NULL);
#         cur_time_msec = (cur_time.tv_sec * 1000) + (cur_time.tv_usec / 1000);
#     }}
#     while((poll_result == 0) && ((cur_time_msec - start_time_msec) < MAX_POLL_CQ_TIMEOUT));

#     if(poll_result < 0)
#     {{
#         /* poll CQ failed */
#         fprintf(stderr, "poll CQ failed\\n");
#         rc = 1;
#     }}
#     else if(poll_result == 0)
#     {{
#         /* the CQ is empty */
#         fprintf(stderr, "completion wasn't found in the CQ after timeout\\n");
#         rc = 1;
#     }}
#     else
#     {{
#         /* CQE found */
#         fprintf(stdout, "completion was found in CQ with status 0x%x\\n", wc.status);
#         /* check the completion status (here we don't care about the completion opcode */
#         if(wc.status != IBV_WC_SUCCESS)
#         {{
#             fprintf(stderr, "got bad completion with status: 0x%x, vendor syndrome: 0x%x\\n", 
#                     wc.status, wc.vendor_err);
#             rc = 1;
#         }}
#     }}
# """
    
class DestroyQP(VerbCall):
    """Destroy a QP."""
    def __init__(self, qp_addr: str):
        self.qp_addr = qp_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        ctx.use_qp(qp)  # Ensure the QP is used before generating code
        return cls(qp_addr = qp)

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
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        mr = kv.get("mr", "unknown")
        ctx.use_mr(mr)  # Ensure the MR is used before generating code
        return cls(mr_addr = mr)

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
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq = kv.get("cq", "unknown")
        ctx.use_cq(cq)  # Ensure the CQ is used before generating code
        return cls(cq_addr = cq)

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
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        ctx.use_pd(pd)  # Ensure the PD is used before generating code
        return cls(pd_addr = pd)

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
    def __init__(self):
        pass

    @classmethod
    def from_trace(cls, info: str, ctx : CodeGenContext = None):
        return cls()
    
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
    "ibv_open_device": OpenDevice.from_trace,
    "ibv_free_device_list": FreeDeviceList.from_trace,
    "ibv_query_device": QueryDeviceAttr.from_trace,
    "ibv_query_port": QueryPortAttr.from_trace,
    "ibv_query_gid": QueryGID.from_trace,
    "ibv_alloc_pd": AllocPD.from_trace,
    "ibv_create_cq": CreateCQ.from_trace,
    "ibv_modify_qp": ModifyQP.from_trace,
    "ibv_modify_qp_rtr": ModifyQPToRTR.from_trace,
    "ibv_modify_qp_rts": ModifyQPToRTS.from_trace,
    "ibv_poll_cq": PollCQ.from_trace,
    "ibv_destroy_qp": DestroyQP.from_trace,
    "ibv_dereg_mr": DestroyMR.from_trace,
    "ibv_destroy_cq": DestroyCQ.from_trace,
    "ibv_dealloc_pd": DestroyPD.from_trace,
    "ibv_close_device": CloseDevice.from_trace
}