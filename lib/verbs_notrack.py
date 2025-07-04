from .codegen_context import CodeGenContext
from .IbvQPAttr import *
from .IbvCQInitAttrEx import *
from .IbvFlowAttr import *
from .IbvQPInitAttrEx import *
from .IbvSrqInitAttrEx import *
from .IbvWQInitAttr import *
from .IbvQPRateLimitAttr import IbvQPRateLimitAttr
from .IbvWQAttr import *
from .IbvECE import IbvECE
from .IbvSge import IbvSge

from .objtracker import ObjectTracker

from typing import Dict, Optional, List, Union
from jinja2 import Template

IB_UVERBS_ADVISE_MR_ADVICE_ENUM = {
    0: "IB_UVERBS_ADVISE_MR_ADVICE_PREFETCH",
    1: "IB_UVERBS_ADVISE_MR_ADVICE_PREFETCH_WRITE",
    2: "IB_UVERBS_ADVISE_MR_ADVICE_PREFETCH_NO_FAULT",
}

IBV_QP_ATTR_MASK_ENUM = {
    "IBV_QP_STATE":              1 << 0,
    "IBV_QP_CUR_STATE":          1 << 1,
    "IBV_QP_EN_SQD_ASYNC_NOTIFY":1 << 2,
    "IBV_QP_ACCESS_FLAGS":       1 << 3,
    "IBV_QP_PKEY_INDEX":         1 << 4,
    "IBV_QP_PORT":               1 << 5,
    "IBV_QP_QKEY":               1 << 6,
    "IBV_QP_AV":                 1 << 7,
    "IBV_QP_PATH_MTU":           1 << 8,
    "IBV_QP_TIMEOUT":            1 << 9,
    "IBV_QP_RETRY_CNT":          1 << 10,
    "IBV_QP_RNR_RETRY":          1 << 11,
    "IBV_QP_RQ_PSN":             1 << 12,
    "IBV_QP_MAX_QP_RD_ATOMIC":   1 << 13,
    "IBV_QP_ALT_PATH":           1 << 14,
    "IBV_QP_MIN_RNR_TIMER":      1 << 15,
    "IBV_QP_SQ_PSN":             1 << 16,
    "IBV_QP_MAX_DEST_RD_ATOMIC": 1 << 17,
    "IBV_QP_PATH_MIG_STATE":     1 << 18,
    "IBV_QP_CAP":                1 << 19,
    "IBV_QP_DEST_QPN":           1 << 20,
    "IBV_QP_RATE_LIMIT":         1 << 25,
}


def mask_fields_to_c(mask):
    """
    mask: 可以是字符串（如"IBV_QP_STATE | IBV_QP_PKEY_INDEX"）
          或list/set（如["IBV_QP_STATE", "IBV_QP_PKEY_INDEX"]）
          或int
    返回可插入C代码的字符串
    """
    if isinstance(mask, int):
        return str(mask)
    elif isinstance(mask, (list, set, tuple)):
        # 转成类似 IBV_QP_STATE | IBV_QP_PKEY_INDEX
        return " | ".join(mask)
    elif isinstance(mask, str):
        # 若全为数字直接返回
        if mask.isdigit():
            return mask
        # 若是宏名组合字符串，直接原样输出
        return mask.strip()
    else:
        raise ValueError(f"Unknown mask type: {mask}")
    
    
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

# deprecated
# class ExportQPInfo(UtilityCall):
#     def __init__(self, qp_addr: str = "QP", mr_addr: str = "MR"):
#         self.qp_addr = qp_addr  # QP address, used to get the QP number
#         self.mr_addr = mr_addr

#     @classmethod
#     def from_trace(cls, info: str):
#         kv = _parse_kv(info)
#         qp = kv.get("qp", "QP")
#         mr = kv.get("mr", "MR")
#         return cls(qp_addr=qp, mr_addr=mr)
    
#     def generate_c(self, ctx: CodeGenContext) -> str:
#         qp = ctx.get_qp(self.qp_addr)
#         mr = ctx.get_mr(self.mr_addr)
#         qpn = qp.replace("qp[", "").replace("]", "")  # e.g., "0" for qp[0]

#         return f"""
#     /* Export connection data */
#     local_con_data.addr = htonll((uintptr_t)bufs[{qpn}]);
#     local_con_data.rkey = htonl({mr}->rkey);
#     local_con_data.qp_num = htonl({qp}->qp_num);
#     local_con_data.lid = htons(port_attr.lid);
#     memcpy(local_con_data.gid, &my_gid, 16);
# """

class ExchangeQPInfo(UtilityCall):
    def __init__(self, qp_addr: str = "QP", remote_qp_index: int = 0):
        self.qp_addr = qp_addr  # QP address, used to get the QP number
        self.remote_qp_index = remote_qp_index  # Index of the remote QP, used for pairing

    @classmethod
    def from_trace(cls, info: str):
        kv = _parse_kv(info)
        qp = kv.get("qp", "QP")
        return cls(qp_addr=qp)
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        qp = ctx.get_qp(self.qp_addr)
        qpn = qp.replace("qp[", "").replace("]", "")  # e.g., "0" for qp[0]

        return f"""
    /* Export connection data */
    req.local_qpn = {qp}->qp_num;
    req.remote_qp_index = {self.remote_qp_index};
    send_pair_request_to_controller(req, sockfd);
    receive_metadata_from_controller(sockfd); // is that correct? 接收配对信息
"""
    
class ReceiveMR(UtilityCall):
    def __init__(self):
        pass

    @classmethod
    def from_trace(cls, info: str):
        return cls()
    
    def generate_c(self, ctx):
        return f"""
    receive_metadata_from_controller(sockfd); // get remote MRs, and remote GID
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
    
# ---------- Specific verb implementations ------------------------------------

class AckAsyncEvent(VerbCall):
    def __init__(self, event_addr: str):
        self.event_addr = event_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        event = kv.get("event", "unknown")
        return cls(event_addr=event)

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_ack_async_event */
    ibv_ack_async_event(&{self.event_addr});
"""

class AckCQEvents(VerbCall):
    """Acknowledge completion queue events for a given CQ."""

    def __init__(self, cq_addr: str, nevents: int = 1):
        self.cq_addr = cq_addr
        self.nevents = nevents

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq = kv.get("cq", "unknown")
        nevents = int(kv.get("nevents", 1))
        ctx.use_cq(cq)  # Ensure the CQ is used before generating code
        return cls(cq_addr=cq, nevents=nevents)

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = ctx.get_cq(self.cq_addr)
        return f"""
    /* ibv_ack_cq_events */
    ibv_ack_cq_events({cq_name}, {self.nevents});
"""

class AdviseMR(VerbCall):
    """
    表示 ibv_advise_mr() 调用。支持多SGE/flags/advice参数自动生成。
    参数：
        pd_addr   -- PD 资源变量名
        advice    -- 枚举 advice 值（int 或 str）
        flags     -- flags 参数（int）
        sg_list   -- IbvSge对象列表
        num_sge   -- SGE个数（int）
    """
    def __init__(self, pd_addr: str, advice: int, flags: int, sg_list: list, num_sge: int = None, sg_var: str = "sg_list"):
        self.pd_addr = pd_addr
        self.advice = advice
        self.flags = flags
        self.sg_list = sg_list or []
        self.num_sge = num_sge if num_sge is not None else len(self.sg_list)
        self.sg_var = sg_var

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd_addr = kv.get("pd", "pd")
        advice = kv.get("advice", 0)
        flags = int(kv.get("flags", 0))
        num_sge = int(kv.get("num_sge", 1))
        # 假定 trace 传递的是已建好的 sg_list 对象列表
        sg_list = kv.get("sg_list", [IbvSge.random_mutation() for _ in range(num_sge)])
        return cls(pd_addr, int(advice), flags, sg_list, num_sge)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.get_pd(self.pd_addr) if hasattr(ctx, "get_pd") else self.pd_addr
        # SGE数组生成
        sg_var = self.sg_var
        s = ""
        if ctx:
            ctx.alloc_variable(sg_var + f"[{self.num_sge}]", "struct ibv_sge")
        for idx, sge in enumerate(self.sg_list):
            s += sge.to_cxx(f"{sg_var}[{idx}]", ctx)
        # Advice宏
        advice_macro = IB_UVERBS_ADVISE_MR_ADVICE_ENUM.get(self.advice, str(self.advice))
        s += f"""
    if (ibv_advise_mr({pd_name}, {advice_macro}, {self.flags}, {sg_var}, {self.num_sge}) != 0) {{
        fprintf(stderr, "ibv_advise_mr failed\\n");
        return -1;
    }}
"""
        return s

class AllocDM(VerbCall):
    def __init__(self, dm_addr: str, attr_obj = None, ctx: CodeGenContext = None):
        self.dm_addr = dm_addr
        self.attr_obj = attr_obj
        ctx.alloc_dm(dm_addr)  # Register the DM address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        dm = kv.get("dm", "unknown")
        length = int(kv.get("length", 0))
        log_align_req = int(kv.get("log_align_req", 0))
        return cls(dm_addr=dm, length=length, log_align_req=log_align_req, ctx=ctx)
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        dm_name = ctx.get_dm(self.dm_addr)
        ib_ctx = ctx.ib_ctx
        code = ""
        # 生成 alloc_dm_attr 结构体内容（如果有）
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        code += f"""
    {dm_name} = ibv_alloc_dm({ib_ctx}, &{self.attr_var});
    if (!{dm_name}) {{
        fprintf(stderr, "Failed to allocate device memory (DM)\\n");
        return -1;
    }}
"""
        return code

class AllocMW(VerbCall):
    def __init__(self, pd_addr, mw_addr, mw_type='IBV_MW_TYPE_1', ctx: CodeGenContext = None):
        self.pd_addr = pd_addr
        self.mw_addr = mw_addr
        self.mw_type = mw_type
        ctx.alloc_mw(mw_addr)  # Register the MW address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get('pd', 'unknown')
        mw = kv.get('mw', 'unknown')
        mw_type = kv.get('type', 'IBV_MW_TYPE_1')
        return cls(pd_addr=pd, mw_addr=mw, mw_type=mw_type, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.get_pd(self.pd_addr)
        mw_name = ctx.get_mw(self.mw_addr)
        
        return f"""
    /* ibv_alloc_mw */
    {mw_name} = ibv_alloc_mw({pd_name}, {self.mw_type});
    if (!{mw_name}) {{
        fprintf(stderr, "Failed to allocate memory window\\n");
        return -1;
    }}
"""

class AllocNullMR(VerbCall):
    """Allocate a null memory region (MR) associated with a protection domain."""

    def __init__(self, pd_addr, mr_addr, ctx: CodeGenContext):
        self.pd_addr = pd_addr
        self.mr_addr = mr_addr
        ctx.alloc_mr(mr_addr)  # Register the MR address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        mr = kv.get("mr", "unknown")
        return cls(pd_addr=pd, mr_addr=mr, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.get_pd(self.pd_addr)
        mr_name = ctx.get_mr(self.mr_addr)
        return f"""
    /* ibv_alloc_null_mr */
    {mr_name} = ibv_alloc_null_mr({pd_name});
    if (!{mr_name}) {{
        fprintf(stderr, "Failed to allocate null MR\\n");
        return -1;
    }}
"""

class AllocParentDomain(VerbCall):
    """
    Allocate a new parent domain using an existing protection domain.

    Attributes:
        context (str): Associated IBV context.
        pd_addr (str): Address of the existing protection domain.
        parent_pd_addr (str): Address for the new parent domain.
        attr_obj (IbvParentDomainInitAttr): Optional, struct fields.
    """
    def __init__(self, context, pd_addr: str = None, parent_pd_addr: str = None, attr_var: str = None, attr_obj=None):
        self.context = context  # 变量名或ctx.ib_ctx
        self.pd_addr = pd_addr  # 旧PD变量名
        self.parent_pd_addr = parent_pd_addr  # 新PD变量名
        self.attr_var = attr_var or f"pd_attr_{parent_pd_addr}"
        self.attr_obj = attr_obj             # 可为 None，trace replay 下只传变量名

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        pd_new = kv.get("parent_pd", "unknown")
        attr_var = kv.get("attr_var", f"pd_attr_{pd_new}")
        attr_obj = kv.get("attr_obj")  # 可选，trace/fuzz模式灵活
        return cls(context=ctx.ib_ctx, pd_addr=pd, parent_pd_addr=pd_new, attr_var=attr_var, attr_obj=attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        if self.pd_addr is None and self.attr_obj is None:
            raise ValueError("Either pd_addr or attr_obj must be provided for AllocParentDomain")
        if self.pd_addr is not None:
            pd_name = ctx.get_pd(self.pd_addr)
        parent_pd_name = ctx.get_pd(self.parent_pd_addr)
        code = ""
        # 生成 struct ibv_parent_domain_init_attr 内容
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            # fallback: 最简明手写（兼容旧trace）
            code += f"\n    struct ibv_parent_domain_init_attr {self.attr_var} = {{0}};\n"
            code += f"    {self.attr_var}.pd = {pd_name};\n"
            code += f"    {self.attr_var}.td = NULL;\n"
            code += f"    {self.attr_var}.comp_mask = 0;\n"
            code += f"    {self.attr_var}.pd_context = NULL;\n"
        code += f"""
    {parent_pd_name} = ibv_alloc_parent_domain({self.context}, &{self.attr_var});
    if (!{parent_pd_name}) {{
        fprintf(stderr, "Failed to allocate parent domain\\n");
        return -1;
    }}
"""
        return code

class AllocPD(VerbCall):
    """Allocate a protection domain (PD) for the RDMA device context."""
    
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

class AllocTD(VerbCall):
    """
    Represents ibv_alloc_td() verb call to allocate a thread domain object.
    """

    def __init__(self, td_addr: str, attr_var: str = None, attr_obj=None, ctx: CodeGenContext = None):
        self.td_addr = td_addr            # 目标变量名
        self.attr_var = attr_var or f"td_init_attr_{td_addr}"         # 结构体变量名
        self.attr_obj = attr_obj          # IbvTdInitAttr对象，若有则生成内容
        # 一般建议在CodeGenContext中注册td_addr资源（可选）
        if ctx:
            ctx.alloc_td(td_addr)

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        td = kv.get("td", "td")
        attr_var = kv.get("attr_var", "td_attr")
        attr_obj = kv.get("attr_obj")  # 若trace记录了具体结构体内容
        return cls(td_addr=td, attr_var=attr_var, attr_obj=attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        td_name = ctx.get_td(self.td_addr)
        code = ""
        # 若结构体对象不为None，自动生成初始化内容
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            code += f"\n    struct ibv_td_init_attr {self.attr_var} = {{0}};\n"
        code += f"""
    {td_name} = ibv_alloc_td({ctx.ib_ctx}, &{self.attr_var});
    if (!{td_name}) {{
        fprintf(stderr, "Failed to allocate thread domain\\n");
        return -1;
    }}
"""
        return code

class AttachMcast(VerbCall):
    def __init__(self, qp_addr: str, gid: str, lid: int): # 注意gid需要是变量，不然无法传参
        self.qp_addr = qp_addr
        self.gid = gid
        self.lid = lid

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        gid = kv.get("gid", "unknown")
        lid = int(kv.get("lid", "0"))
        ctx.use_qp(qp)  # Ensure the QP is used before generating code
        return cls(qp_addr=qp, gid=gid, lid=lid)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        gid_value = f"{self.gid}"
        return f"""
    /* ibv_attach_mcast */
    if (ibv_attach_mcast({qp_name}, &{gid_value}, {self.lid})) {{
        fprintf(stderr, "Failed to attach multicast group\\n");
        return -1;
    }}
"""

class BindMW(VerbCall):
    def __init__(self, qp_addr: str, mw_addr: str, mw_bind_var: str = None, mw_bind_obj=None):
        """
        qp_addr: QP变量名
        mw_addr: MW变量名
        mw_bind_var: mw_bind结构体变量名
        mw_bind_obj: IbvMwBind对象（可选，若有则自动生成结构体内容）
        """
        self.qp_addr = qp_addr
        self.mw_addr = mw_addr
        self.mw_bind_var = mw_bind_var or f"mw_bind_{mw_addr}"  # 默认生成 mw_bind_<mw_addr>
        self.mw_bind_obj = mw_bind_obj

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        mw = kv.get("mw", "unknown")
        mw_bind_var = kv.get("mw_bind_var", f"mw_bind_{mw}")
        mw_bind_obj = kv.get("mw_bind_obj")  # 可选，支持结构体对象
        ctx.use_qp(qp)
        ctx.use_mw(mw)
        return cls(qp_addr=qp, mw_addr=mw, mw_bind_var=mw_bind_var, mw_bind_obj=mw_bind_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        mw_name = ctx.get_mw(self.mw_addr)
        mw_bind_var = self.mw_bind_var
        code = ""
        # 支持自动生成结构体内容
        if self.mw_bind_obj is not None:
            code += self.mw_bind_obj.to_cxx(mw_bind_var, ctx)
        else:
            # 兼容 trace replay，手动逐字段赋值
            code += f"""
    struct ibv_mw_bind {mw_bind_var} = {{0}};
    // TODO: Assign fields as needed for trace replay.
    // e.g. {mw_bind_var}.wr_id = ...;
    //      {mw_bind_var}.send_flags = ...;
    //      {mw_bind_var}.bind_info.mr = ...;
    //      ...
"""
        code += f"""
    if (ibv_bind_mw({qp_name}, {mw_name}, &{mw_bind_var}) != 0) {{
        fprintf(stderr, "Failed to bind MW\\n");
        return -1;
    }}
"""
        return code
    

class CloseDevice(VerbCall):
    """Close the RDMA device context. This does not release all resources allocated using the context.
    Make sure to release all associated resources before closing."""
    
    def __init__(self):
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        return cls()

    def generate_c(self, ctx: CodeGenContext) -> str:
        context_name = ctx.ib_ctx
        return f"""
    /* ibv_close_device */
    if (ibv_close_device({context_name})) {{
        fprintf(stderr, "Failed to close device\\n");
        return -1;
    }}
"""

class CloseXRCD(VerbCall):
    """Close an XRC domain."""

    def __init__(self, xrcd_addr: str):
        self.xrcd_addr = xrcd_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        xrcd = kv.get("xrcd", "unknown")
        ctx.use_xrcd(xrcd)  # Ensure the XRCD is used before generating code
        return cls(xrcd_addr=xrcd)

    def generate_c(self, ctx: CodeGenContext) -> str:
        xrcd_name = ctx.get_xrcd(self.xrcd_addr)
        return f"""
    /* ibv_close_xrcd */
    if (ibv_close_xrcd({xrcd_name})) {{
        fprintf(stderr, "Failed to close XRCD\\n");
        return -1;
    }}
"""

class CreateAH(VerbCall):
    """
    ibv_create_ah() - 创建 address handle。
    参数：
        pd_addr    -- PD变量名（如"pd1"）
        attr_var   -- 结构体变量名（如"ah_attr1"）
        attr_obj   -- IbvAHAttr对象（可选，自动生成结构体内容）
        ret_var    -- 返回的 ibv_ah* 变量名（如"ah1"）
    """
    def __init__(self, pd_addr: str, attr_var: str = None, ret_var: str = "ah", attr_obj: 'IbvAHAttr' = None):
        self.pd_addr = pd_addr
        self.attr_var = attr_var or f"ah_attr_{pd_addr}"  # 默认生成 ah_attr_<pd_addr>
        self.ret_var = ret_var
        self.attr_obj = attr_obj  # 若为 None 则仅引用变量名

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd_addr = kv.get("pd", "pd")
        attr_var = kv.get("attr", "ah_attr")
        ret_var = kv.get("ret_var", "ah")
        attr_obj = kv.get("attr_obj")  # trace 里若含结构体内容
        return cls(pd_addr, attr_var, ret_var, attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.get_pd(self.pd_addr)
        ah_var = self.ret_var
        if ctx:
            ctx.alloc_variable(ah_var, "struct ibv_ah *")  # Register the AH variable in the context
        code = ""
        # 自动生成结构体内容
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            code += f"\n    struct ibv_ah_attr {self.attr_var} = {{0}};\n"
        code += f"""
    {ah_var} = ibv_create_ah({pd_name}, &{self.attr_var});
    if (!{ah_var}) {{
        fprintf(stderr, "ibv_create_ah failed\\n");
        return -1;
    }}
"""
        return code


# class CreateAH(VerbCall):
#     def __init__(self, pd_addr: str, ah_addr: str, ah_attr_params: Dict[str, str]):
#         self.pd_addr = pd_addr
#         self.ah_addr = ah_addr
#         self.ah_attr_params = ah_attr_params

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         pd = kv.get("pd", "unknown")
#         ah = kv.get("ah", "unknown")
#         attr_keys = {"dlid", "sl", "src_path_bits", "static_rate", "is_global", "port_num",
#                      "dgid", "flow_label", "sgid_index", "hop_limit", "traffic_class"}
#         ah_attr_params = {k: kv[k] for k in attr_keys if k in kv}
#         ctx.use_pd(pd)
#         return cls(pd_addr=pd, ah_addr=ah, ah_attr_params=ah_attr_params)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         pd_name = ctx.get_pd(self.pd_addr)
#         ah_name = f"{self.ah_addr}"
#         attr_name = f"ah_attr_{ah_name}"

#         grh_params = ""
#         if self.ah_attr_params.get("is_global") == "1":
#             grh_params = f"""
#         .grh = {{
#             .dgid = {{.raw = {{0}}}},
#             .flow_label = {self.ah_attr_params.get("flow_label", "0")},
#             .sgid_index = {self.ah_attr_params.get("sgid_index", "0")},
#             .hop_limit = {self.ah_attr_params.get("hop_limit", "0")},
#             .traffic_class = {self.ah_attr_params.get("traffic_class", "0")},
#         }},"""

#         return f"""
#     /* ibv_create_ah */
#     struct ibv_ah_attr {attr_name} = {{
#         {grh_params}
#         .dlid = {self.ah_attr_params.get("dlid", "0")},
#         .sl = {self.ah_attr_params.get("sl", "0")},
#         .src_path_bits = {self.ah_attr_params.get("src_path_bits", "0")},
#         .static_rate = {self.ah_attr_params.get("static_rate", "0")},
#         .is_global = {self.ah_attr_params.get("is_global", "0")},
#         .port_num = {self.ah_attr_params.get("port_num", "0")},
#     }};
#     struct ibv_ah *{ah_name} = ibv_create_ah({pd_name}, &{attr_name});
#     if (!{ah_name}) {{
#         fprintf(stderr, "Failed to create AH\\n");
#         return -1;
#     }}
# """

class CreateAHFromWC(VerbCall):
    def __init__(self, pd_addr: str, wc_addr: str, grh_addr: str, port_num: int, ret_var: str = "ah"):
        self.pd_addr = pd_addr
        self.wc_addr = wc_addr
        self.grh_addr = grh_addr
        self.port_num = port_num
        self.ret_var = ret_var  # Variable name for the created AH 变量名手动维护，暂时不提供ctx

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        wc = kv.get("wc", "unknown")
        grh = kv.get("grh", "unknown")
        port_num = int(kv.get("port_num", 1))
        ctx.use_pd(pd)  # Ensure the PD is used before generating code
        return cls(pd_addr=pd, wc_addr=wc, grh_addr=grh, port_num=port_num)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.get_pd(self.pd_addr)
        wc_name = self.wc_addr
        grh_name = self.grh_addr
        port_num = self.port_num

        return f"""
    /* ibv_create_ah_from_wc */
    if (!ibv_create_ah_from_wc({pd_name}, &{wc_name}, &{grh_name}, {port_num})) {{
        fprintf(stderr, "Failed to create AH from work completion\\n");
        return -1;
    }}
"""

class CreateCompChannel(VerbCall):
    def __init__(self, channel_addr: str, ctx: CodeGenContext = None):
        self.channel_addr = channel_addr
        if ctx:
            ctx.alloc_comp_channel(channel_addr)  # Register the channel address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        channel = kv.get("channel", "unknown")
        ctx.alloc_comp_channel(channel)
        return cls(channel_addr=channel)

    def generate_c(self, ctx: CodeGenContext) -> str:
        channel_name = ctx.get_comp_channel(self.channel_addr)
        ib_ctx = ctx.ib_ctx
        return f"""
    /* ibv_create_comp_channel */
    {channel_name} = ibv_create_comp_channel({ib_ctx});
    if (!{channel_name}) {{
        fprintf(stderr, "Failed to create completion channel\\n");
        return -1;
    }}
"""

class CreateCQ(VerbCall):
    def __init__(self, ctx: str, cqe: int = 32, cq_context: str = "NULL",
                 channel: str = "NULL", comp_vector: int = 0, cq_addr: str = "unknown"):
        self.context = ctx
        self.cqe = cqe
        self.cq_context = cq_context
        self.channel = channel
        self.comp_vector = comp_vector
        self.cq_addr = cq_addr
        ctx.alloc_cq(cq_addr)  # Register the CQ address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        context = kv.get("context", ctx.ib_ctx)
        cqe = int(kv.get("cqe", 32))
        cq_context = kv.get("cq_context", "NULL")
        channel = kv.get("channel", "NULL")
        comp_vector = int(kv.get("comp_vector", 0))
        cq_addr = kv.get("cq", "unknown")
        # ctx.alloc_cq(cq_addr)
        return cls(context=context, cqe=cqe, cq_context=cq_context,
                   channel=channel, comp_vector=comp_vector, cq_addr=cq_addr)

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = ctx.get_cq(self.cq_addr)
        return f"""
    /* ibv_create_cq */
    {cq_name} = ibv_create_cq({self.context.ib_ctx}, {self.cqe}, 
                              {self.cq_context}, {self.channel}, 
                              {self.comp_vector});
    if (!{cq_name}) {{
        fprintf(stderr, "Failed to create completion queue\\n");
        return -1;
    }}
"""

class CreateCQEx(VerbCall):
    """
    表示 ibv_create_cq_ex() 调用，自动生成/重放 cq_ex 的初始化与调用。
    参数：
        ctx_name      -- IBV context 变量名（如"ctx"）
        cq_var        -- 返回 CQ_EX 变量名（如"cq_ex1"）
        cq_attr_var   -- cq_attr 结构体变量名（如"cq_attr1"）
        cq_attr_obj   -- IbvCQInitAttrEx对象（可选，自动生成结构体内容）
    """
    def __init__(self, ctx_name: str, cq_ex_addr: str, cq_attr_var: str = None, cq_attr_obj: 'IbvCQInitAttrEx' = None, ctx: CodeGenContext = None):
        self.ctx_name = ctx_name
        self.cq_ex_addr = cq_ex_addr  # CQ_EX变量名
        self.cq_attr_var = cq_attr_var or f"cq_ex_attr_{cq_ex_addr}"  # 默认生成 cq_attr_<cq_var>
        self.cq_attr_obj = cq_attr_obj  # 若为None仅生成结构体声明
        if ctx:
            ctx.alloc_cq_ex(cq_ex_addr)

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ctx_name = kv.get("ctx", "ctx")
        cq_var = kv.get("cq_var", "cq_ex")
        cq_attr_var = kv.get("cq_attr_var", "cq_attr")
        cq_attr_obj = kv.get("cq_attr_obj")  # 若trace含结构体内容
        return cls(ctx_name, cq_var, cq_attr_var, cq_attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        self.cq_var = ctx.get_cq_ex(self.cq_ex_addr)  # 获取CQ_EX变量名
        code = ""
        # 自动生成结构体内容
        if self.cq_attr_obj is not None:
            code += self.cq_attr_obj.to_cxx(self.cq_attr_var, ctx)
        else:
            code += f"\n    struct ibv_cq_init_attr_ex {self.cq_attr_var} = {{0}};\n"
        code += f"""
    {self.cq_var} = ibv_create_cq_ex({self.ctx_name}, &{self.cq_attr_var});
    if (!{self.cq_var}) {{
        fprintf(stderr, "ibv_create_cq_ex failed\\n");
        return -1;
    }}
"""
        return code   

class CreateFlow(VerbCall):
    """
    表示 ibv_create_flow() 调用，自动生成/重放 flow_attr 的初始化与调用。
    参数：
        qp_addr      -- QP变量名（如"qp1"）
        flow_var     -- 返回 flow 变量名（如"flow1"）
        flow_attr_var-- flow_attr 结构体变量名（如"flow_attr1"）
        flow_attr_obj-- IbvFlowAttr对象（可选，自动生成结构体内容）
    """
    def __init__(self, qp_addr: str, flow_addr: str = None, flow_attr_var: str = None, flow_attr_obj: 'IbvFlowAttr' = None, ctx: CodeGenContext = None):
        self.qp_addr = qp_addr
        self.flow_addr = flow_addr
        self.flow_attr_var = flow_attr_var or f"flow_attr_{qp_addr}"  # 默认生成 flow_attr_<qp_addr>
        self.flow_attr_obj = flow_attr_obj  # None时仅生成结构体声明
        ctx.alloc_flow(flow_addr)  # Register the flow address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp_addr = kv.get("qp", "qp")
        flow_var = kv.get("flow_var", "flow")
        flow_attr_var = kv.get("flow_attr_var", "flow_attr")
        flow_attr_obj = kv.get("flow_attr_obj")  # 若trace含结构体内容
        return cls(qp_addr, flow_var, flow_attr_var, flow_attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        flow_var = ctx.get_flow(self.flow_addr)
        # ctx.alloc_variable(flow_var, "struct ibv_flow *")  # Register the flow variable in the context
        flow_attr_var = self.flow_attr_var
        code = ""
        if self.flow_attr_obj is not None:
            code += self.flow_attr_obj.to_cxx(flow_attr_var, ctx)
        else:
            code += f"\n    struct ibv_flow_attr {flow_attr_var} = {{0}};\n"
        code += f"""
    {flow_var} = ibv_create_flow({qp_name}, &{flow_attr_var});
    if (!{flow_var}) {{
        fprintf(stderr, "ibv_create_flow failed\\n");
        return -1;
    }}
"""
        return code

class CreateQP(VerbCall):
    def __init__(self, pd_addr, qp_addr, init_attr_obj=None, ctx: CodeGenContext = None):
        self.pd_addr = pd_addr                    # PD变量名
        self.qp_addr = qp_addr                    # QP变量名
        self.init_attr_obj = init_attr_obj      # IbvQpInitAttr实例（如自动生成/trace重放）
        if ctx:
            ctx.alloc_qp(self.qp_addr)

    @classmethod
    def from_trace(cls, info, ctx):
        kv = _parse_kv(info)
        return cls(
            pd_var=kv.get("pd"),
            init_attr_var=kv.get("init_attr"),
            qp_var=kv.get("qp"),
            init_attr_obj=kv.get("init_attr_obj")  # 若trace包含IbvQpInitAttr对象
        )

    def generate_c(self, ctx):
        qp_name = ctx.get_qp(self.qp_addr)
        pd_name = ctx.get_pd(self.pd_addr)
        attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
        attr_name = f"attr_init{attr_suffix}"
        # ctx.alloc_variable(attr_name, "struct ibv_qp_init_attr")  # Register the attribute name in the context
        code = ""
        # 1. 生成/声明init_attr结构体
        if self.init_attr_obj is not None:
            code += self.init_attr_obj.to_cxx(attr_name, ctx)
        # 2. 声明QP变量
        return f"""
    /* ibv_create_qp */
    {code}
    {qp_name} = ibv_create_qp({pd_name}, &{attr_name});
    if (!{qp_name}) {{
        fprintf(stderr, "Failed to create QP\\n");
        return -1;
    }}
"""
        # code += f"\n    struct ibv_qp* {self.qp_var} = ibv_create_qp({self.pd_var}, &{self.init_attr_var});\n"
        # code += (
        #     f"    if (!{self.qp_var}) {{ printf(\"ibv_create_qp failed\\n\"); }}\n"
        # )
        # return code
    
# class CreateQP(VerbCall):
#     """Create a Queue Pair (QP) using the given attributes."""
#     def __init__(self, pd_addr="pd[0]", qp_addr="unknown", cq_addr="cq[0]", qp_type="IBV_QPT_RC", cap_params=None, ctx=None):
#         self.pd_addr = pd_addr
#         self.qp_addr = qp_addr
#         self.cq_addr = cq_addr  # Completion queue address, used for code generation
#         self.qp_type = qp_type
#         self.cap_params = cap_params or {}
#         ctx.alloc_qp(self.qp_addr)

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         cap_keys = {"max_send_wr", "max_recv_wr", "max_send_sge", "max_recv_sge", "max_inline_data"}
#         cap_params = {k: kv[k] for k in cap_keys if k in kv}
#         pd = kv.get("pd", "pd[0]")
#         qp = kv.get("qp", "unknown")
#         cq = kv.get("cq", "cq[0]")  # Default CQ address
        
#         return cls(pd_addr=pd, qp_addr=qp, cq_addr=cq, qp_type="IBV_QPT_RC", cap_params=cap_params, ctx=ctx)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         qp_name = ctx.get_qp(self.qp_addr)
#         pd_name = ctx.get_pd(self.pd_addr)
#         cq_name = ctx.get_cq(self.cq_addr)
#         attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
#         attr_name = f"attr_init{attr_suffix}"
#         ctx.alloc_variable(attr_name, "struct ibv_qp_init_attr")  # Register the attribute name in the context
#         cap = self.cap_params
#         cap_lines = "\n    ".join(
#             f"{attr_name}.cap.{k} = {v};" for k, v in cap.items()
#         )
#         return f"""
#     /* ibv_create_qp */
#     memset(&{attr_name}, 0, sizeof({attr_name}));
#     {attr_name}.qp_type = {self.qp_type};
#     {attr_name}.send_cq = {cq_name};
#     {attr_name}.recv_cq = {cq_name};
#     {cap_lines}
#     {qp_name} = ibv_create_qp({pd_name}, &{attr_name});
#     if (!{qp_name}) {{
#         fprintf(stderr, "Failed to create QP\\n");
#         return -1;
#     }}
# """


class CreateQPEx(VerbCall):
    """
    表示 ibv_create_qp_ex() 调用，自动生成/重放 qp_init_attr_ex 的初始化与调用。
    参数：
        ctx_name        -- IBV context 变量名（如"ctx"）
        qp_var          -- 返回 QP 变量名（如"qp1"）
        qp_attr_var     -- qp_init_attr_ex 结构体变量名（如"qp_init_attr_ex1"）
        qp_attr_obj     -- IbvQPInitAttrEx对象（可选，自动生成结构体内容）
    """
    def __init__(self, ctx_name: str, qp_addr: str, qp_attr_var: str = None, qp_attr_obj: 'IbvQPInitAttrEx' = None):
        self.ctx_name = ctx_name
        self.qp_addr = qp_addr
        self.qp_attr_var = qp_attr_var or f"qp_init_attr_ex_{qp_addr}"  # 默认生成 qp_init_attr_ex_<qp_var>
        self.qp_attr_obj = qp_attr_obj  # 若为None仅生成结构体声明

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ctx_name = kv.get("ctx", "ctx")
        qp_var = kv.get("qp_var", "qp")
        qp_attr_var = kv.get("qp_attr_var", "qp_init_attr_ex")
        qp_attr_obj = kv.get("qp_attr_obj")  # 若trace含结构体内容
        return cls(ctx_name, qp_var, qp_attr_var, qp_attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        self.qp_var = ctx.get_qp(self.qp_addr)
        code = ""
        # 自动生成结构体内容
        if self.qp_attr_obj is not None:
            code += self.qp_attr_obj.to_cxx(self.qp_attr_var, ctx)
        else:
            code += f"\n    struct ibv_qp_init_attr_ex {self.qp_attr_var} = {{0}};\n"
        code += f"""
    {self.qp_var} = ibv_create_qp_ex({self.ctx_name}, &{self.qp_attr_var});
    if (!{self.qp_var}) {{
        fprintf(stderr, "ibv_create_qp_ex failed\\n");
        return -1;
    }}
"""
        return code


# class CreateQPEx(VerbCall):
#     def __init__(self, ctx: CodeGenContext, qp_addr: str, pd_addr: str, send_cq_addr: str,
#                  recv_cq_addr: str, srq_addr: Optional[str], qp_type: str = "IBV_QPT_RC", 
#                  cap_params: Optional[Dict[str, int]] = None, comp_mask: int = 0,
#                  create_flags: int = 0):
#         self.qp_addr = qp_addr
#         self.pd_addr = pd_addr
#         self.send_cq_addr = send_cq_addr
#         self.recv_cq_addr = recv_cq_addr
#         self.srq_addr = srq_addr
#         self.qp_type = qp_type
#         self.cap_params = cap_params or {}
#         self.comp_mask = comp_mask
#         self.create_flags = create_flags
#         ctx.alloc_qp(qp_addr)  # Register the QP in the context

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         qp = kv.get("qp", "unknown")
#         pd = kv.get("pd", "pd[0]")
#         send_cq = kv.get("send_cq", "cq[0]")
#         recv_cq = kv.get("recv_cq", "cq[0]")
#         srq = kv.get("srq", None)
#         cap_keys = {"max_send_wr", "max_recv_wr", "max_send_sge", "max_recv_sge", "max_inline_data"}
#         cap_params = {k: int(kv[k]) for k in cap_keys if k in kv}
#         qp_type = kv.get("qp_type", "IBV_QPT_RC")
#         comp_mask = int(kv.get("comp_mask", "0"))
#         create_flags = int(kv.get("create_flags", "0"))
#         return cls(ctx, qp, pd, send_cq, recv_cq, srq, qp_type, cap_params, comp_mask, create_flags)
    
#     def generate_c(self, ctx: CodeGenContext) -> str:
#         qp_name = ctx.get_qp(self.qp_addr)
#         pd_name = ctx.get_pd(self.pd_addr)
#         send_cq_name = ctx.get_cq(self.send_cq_addr)
#         recv_cq_name = ctx.get_cq(self.recv_cq_addr)
#         srq_name = ctx.get_srq(self.srq_addr) if self.srq_addr else "NULL"
#         attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
#         attr_name = f"attr_ex{attr_suffix}"
#         cap = self.cap_params
#         cap_lines = "\n    ".join(
#             f"{attr_name}.cap.{k} = {v};" for k, v in cap.items()
#         )
#         return f"""
#     /* ibv_create_qp_ex */
#     struct ibv_qp_init_attr_ex {attr_name} = {{}};
#     {attr_name}.qp_context = NULL;
#     {attr_name}.send_cq = {send_cq_name};
#     {attr_name}.recv_cq = {recv_cq_name};
#     {attr_name}.srq = {srq_name};
#     {attr_name}.qp_type = {self.qp_type};
#     {attr_name}.comp_mask = {self.comp_mask};
#     {attr_name}.create_flags = {self.create_flags};
#     {attr_name}.pd = {pd_name};
#     {cap_lines}
#     {qp_name} = ibv_create_qp_ex({ctx.ib_ctx}, &{attr_name});
#     if (!{qp_name}) {{
#         fprintf(stderr, "Failed to create QP\\n");
#         return -1;
#     }}
# """

# class CreateRWQIndTable(VerbCall):
#     def __init__(self, context_addr: str, log_ind_tbl_size: int = 0, ind_tbl_addrs: list = []):
#         self.context_addr = context_addr
#         self.log_ind_tbl_size = log_ind_tbl_size
#         self.ind_tbl_addrs = ind_tbl_addrs or []

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         context = kv.get("context", "unknown")
#         ctx.use_context(context)
#         log_size = int(kv.get("log_ind_tbl_size", 0))
#         ind_tbl_addrs = kv.get("ind_tbl", "").split()
#         return cls(context_addr=context, log_ind_tbl_size=log_size, ind_tbl_addrs=ind_tbl_addrs)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         context_name = ctx.get_context(self.context_addr)
#         ind_tbl_name = f"ind_tbl[{len(self.ind_tbl_addrs)}]"
#         init_attr_name = f"init_attr_{self.context_addr}"

#         ind_tbl_entries = ", ".join(f"wq[{i}]" for i in range(len(self.ind_tbl_addrs)))
#         init_attr_struct = f"""
#     struct ibv_rwq_ind_table_init_attr {init_attr_name};
#     {init_attr_name}.log_ind_tbl_size = {self.log_ind_tbl_size};
#     {init_attr_name}.ind_tbl = {ind_tbl_name};
#     {init_attr_name}.comp_mask = 0; // Comp mask can be modified based on requirements
# """

#         return f"""
#     /* ibv_create_rwq_ind_table */
#     struct ibv_rwq_ind_table *rwq_ind_table;
#     struct ibv_wq *{ind_tbl_name}[] = {{{ind_tbl_entries}}};
#     {init_attr_struct}
#     rwq_ind_table = ibv_create_rwq_ind_table({context_name}, &{init_attr_name});
#     if (!rwq_ind_table) {{
#         fprintf(stderr, "Failed to create RWQ indirection table\\n");
#         return -1;
#     }}
# """

class CreateSRQ(VerbCall):
    """Create a shared receive queue (SRQ)"""

    def __init__(self, pd_addr: str, srq_addr: str, srq_init_obj=None, ctx: CodeGenContext = None):
        self.pd_addr = pd_addr
        self.srq_addr = srq_addr
        self.srq_init_obj = srq_init_obj
        if ctx:
            ctx.alloc_srq(srq_addr)  # Register SRQ address in context if provided

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        srq = kv.get("srq", "unknown")
        srq_attr_keys = {"max_wr", "max_sge", "srq_limit"}
        srq_attr_params = {k: kv[k] for k in srq_attr_keys if k in kv}
        return cls(pd_addr=pd, srq_addr=srq, srq_attr_params=srq_attr_params, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.get_pd(self.pd_addr)
        srq_name = ctx.get_srq(self.srq_addr)
        
        code = ""
        attr_name = f"srq_init_attr_{srq_name.replace('srq', '').replace('[', '').replace(']', '')}"
        if self.srq_init_obj is not None:
            code += self.srq_init_obj.to_cxx(attr_name, ctx)

        return f"""
    /* ibv_create_srq */
    {code}
    {srq_name} = ibv_create_srq({pd_name}, &{attr_name});
    if (!{srq_name}) {{
        fprintf(stderr, "Failed to create SRQ\\n");
        return -1;
    }}
"""


class CreateSRQEx(VerbCall):
    """
    表示 ibv_create_srq_ex() 调用，自动生成/重放 srq_init_attr_ex 的初始化与调用。
    参数：
        ctx_name      -- IBV context 变量名（如"ctx"）
        srq_var       -- 返回 SRQ 变量名（如"srq1"）
        srq_attr_var  -- srq_init_attr_ex 结构体变量名（如"srq_attr_ex1"）
        srq_attr_obj  -- IbvSrqInitAttrEx对象（可选，自动生成结构体内容）
    """
    def __init__(self, ctx_name: str, srq_addr: str, srq_attr_var: str = None, srq_attr_obj: 'IbvSrqInitAttrEx' = None, ctx: CodeGenContext = None):
        self.ctx_name = ctx_name
        self.srq_addr = srq_addr
        self.srq_attr_var = srq_attr_var or f"srq_attr_ex_{srq_addr}"  # 默认生成 srq_attr_ex_<srq_var>
        self.srq_attr_obj = srq_attr_obj  # 若为None仅生成结构体声明
        if ctx:
            ctx.alloc_srq(srq_addr)

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ctx_name = kv.get("ctx", "ctx")
        srq_var = kv.get("srq_var", "srq")
        srq_attr_var = kv.get("srq_attr_var", "srq_attr_ex")
        srq_attr_obj = kv.get("srq_attr_obj")  # 若trace含结构体内容
        return cls(ctx_name, srq_var, srq_attr_var, srq_attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        if self.ctx_name is None:
            self.ctx_name = ctx.ib_ctx  # Default to ib_ctx if ctx_name is not provided
        self.srq_var = ctx.get_srq(self.srq_addr)
        code = ""
        # 自动生成结构体内容
        if self.srq_attr_obj is not None:
            code += self.srq_attr_obj.to_cxx(self.srq_attr_var, ctx)
        else:
            code += f"\n    struct ibv_srq_init_attr_ex {self.srq_attr_var} = {{0}};\n"
        code += f"""
    {self.srq_var} = ibv_create_srq_ex({self.ctx_name}, &{self.srq_attr_var});
    if (!{self.srq_var}) {{
        fprintf(stderr, "ibv_create_srq_ex failed\\n");
        return -1;
    }}
"""
        return code
    

class CreateWQ(VerbCall):
    """
    表示 ibv_create_wq() 调用，自动生成/重放 wq_init_attr 的初始化与调用。
    参数：
        ctx_name     -- IBV context 变量名（如"ctx"）
        wq_var       -- 返回 WQ 变量名（如"wq1"）
        wq_attr_var  -- wq_init_attr 结构体变量名（如"wq_attr1"）
        wq_attr_obj  -- IbvWQInitAttr对象（可选，自动生成结构体内容）
    """
    def __init__(self, ctx_name: str = None, wq_addr: str = None, wq_attr_var: str = None, wq_attr_obj: 'IbvWQInitAttr' = None, ctx: CodeGenContext = None):
        self.ctx_name = ctx_name
        self.wq_addr = wq_addr
        self.wq_attr_var = wq_attr_var or f"wq_attr_{wq_addr}"  # 默认生成 wq_attr_<wq_var>
        self.wq_attr_obj = wq_attr_obj  # 若为None仅生成结构体声明
        if ctx:
            ctx.alloc_wq(wq_addr)

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ctx_name = kv.get("ctx", "ctx")
        wq_var = kv.get("wq_var", "wq")
        wq_attr_var = kv.get("wq_attr_var", "wq_attr")
        wq_attr_obj = kv.get("wq_attr_obj")  # 若trace含结构体内容
        return cls(ctx_name, wq_var, wq_attr_var, wq_attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        self.wq_var = ctx.get_wq(self.wq_addr)  # 获取WQ变量名
        if self.ctx_name is None:
            self.ctx_name = ctx.ib_ctx
        code = ""
        # 自动生成结构体内容
        if self.wq_attr_obj is not None:
            code += self.wq_attr_obj.to_cxx(self.wq_attr_var, ctx)
        else:
            code += f"\n    struct ibv_wq_init_attr {self.wq_attr_var} = {{0}};\n"
        code += f"""
    {self.wq_var} = ibv_create_wq({self.ctx_name}, &{self.wq_attr_var});
    if (!{self.wq_var}) {{
        fprintf(stderr, "ibv_create_wq failed\\n");
        return -1;
    }}
"""
        return code


class DeallocMW(VerbCall):
    """Deallocate a Memory Window (MW)."""
    def __init__(self, mw_addr: str):
        self.mw_addr = mw_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        mw = kv.get("mw", "unknown")
        ctx.use_mw(mw)  # Ensure the MW is used before generating code
        return cls(mw_addr=mw)

    def generate_c(self, ctx: CodeGenContext) -> str:
        mw_name = ctx.get_mw(self.mw_addr)
        return f"""
    /* ibv_dealloc_mw */
    if (ibv_dealloc_mw({mw_name})) {{
        fprintf(stderr, "Failed to deallocate MW\\n");
        return -1;
    }}
"""

class DeallocPD(VerbCall):
    """Deallocate a protection domain (PD)."""
    def __init__(self, pd_addr: str):
        self.pd_addr = pd_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        ctx.use_pd(pd)  # Ensure the PD is used before generating code
        return cls(pd_addr=pd)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.get_pd(self.pd_addr)
        return f"""
    /* ibv_dealloc_pd */
    if (ibv_dealloc_pd({pd_name})) {{
        fprintf(stderr, "Failed to deallocate PD \\n");
        return -1;
    }}
"""

class DeallocTD(VerbCall):
    """Deallocate an RDMA thread domain (TD) object."""
    def __init__(self, td_addr: str):
        self.td_addr = td_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        td = kv.get("td", "unknown")
        ctx.use_td(td)  # Ensure the TD is used before generating code
        return cls(td_addr=td)

    def generate_c(self, ctx: CodeGenContext) -> str:
        td_name = ctx.get_td(self.td_addr)
        return f"""
    /* ibv_dealloc_td */
    if (ibv_dealloc_td({td_name})) {{
        fprintf(stderr, "Failed to deallocate TD\\n");
        return -1;
    }}
"""

class DeregMR(VerbCall):
    """Deregister a Memory Region."""

    def __init__(self, mr_addr: str):
        self.mr_addr = mr_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        mr = kv.get("mr", "unknown")
        ctx.use_mr(mr)  # Ensure the MR is used before generating code
        return cls(mr_addr=mr)

    def generate_c(self, ctx: CodeGenContext) -> str:
        mr_name = ctx.get_mr(self.mr_addr)
        return f"""
    /* ibv_dereg_mr */
    if (ibv_dereg_mr({mr_name})) {{
        fprintf(stderr, "Failed to deregister MR\\n");
        return -1;
    }}
"""

class DestroyAH(VerbCall):
    """Destroy an Address Handle (AH)."""
    def __init__(self, ah_addr: str):
        self.ah_addr = ah_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ah = kv.get("ah", "unknown")
        ctx.use_ah(ah)  # Ensure the AH is used before generating code
        return cls(ah_addr=ah)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ah_name = ctx.get_ah(self.ah_addr)
        return f"""
    /* ibv_destroy_ah */
    if (ibv_destroy_ah({ah_name})) {{
        fprintf(stderr, "Failed to destroy AH\\n");
        return -1;
    }}
"""

class DestroyCompChannel(VerbCall):
    """Destroy a completion event channel."""
    def __init__(self, comp_channel_addr: str):
        self.comp_channel_addr = comp_channel_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        comp_channel = kv.get("comp_channel", "unknown")
        ctx.use_comp_channel(comp_channel)  # Ensure the completion channel is used before generating code
        return cls(comp_channel_addr=comp_channel)

    def generate_c(self, ctx: CodeGenContext) -> str:
        comp_channel_name = ctx.get_comp_channel(self.comp_channel_addr)
        return f"""
    /* ibv_destroy_comp_channel */
    if (ibv_destroy_comp_channel({comp_channel_name})) {{
        fprintf(stderr, "Failed to destroy completion channel\\n");
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
        return cls(cq_addr=cq)

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = ctx.get_cq(self.cq_addr)
        return f"""
    /* ibv_destroy_cq */
    if (ibv_destroy_cq({cq_name})) {{
        fprintf(stderr, "Failed to destroy CQ\\n");
        return -1;
    }}
"""

class DestroyFlow(VerbCall):
    """Destroy a flow steering rule."""

    def __init__(self, flow_id: str):
        self.flow_id = flow_id

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        flow_id = kv.get("flow_id", "unknown")
        ctx.use_flow(flow_id)  # Ensure the flow is used before generating code
        return cls(flow_id=flow_id)

    def generate_c(self, ctx: CodeGenContext) -> str:
        flow_name = ctx.get_flow(self.flow_id)
        return f"""
    /* ibv_destroy_flow */
    if (ibv_destroy_flow({flow_name})) {{
        fprintf(stderr, "Failed to destroy flow\\n");
        return -1;
    }}
"""

class DestroyQP(VerbCall):
    """Destroy a Queue Pair (QP)."""
    def __init__(self, qp_addr: str):
        self.qp_addr = qp_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        ctx.use_qp(qp)  # Ensure the QP is used before generating code
        return cls(qp_addr=qp)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        return f"""
    /* ibv_destroy_qp */
    if (ibv_destroy_qp({qp_name})) {{
        fprintf(stderr, "Failed to destroy QP\\n");
        return -1;
    }}
"""

class DestroyRWQIndTable(VerbCall):
    """Destroy a Receive Work Queue Indirection Table (RWQ IND TBL)."""
    
    def __init__(self, rwq_ind_table_addr: str):
        self.rwq_ind_table_addr = rwq_ind_table_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        rwq_ind_table = kv.get("rwq_ind_table", "unknown")
        ctx.use_rwq_ind_table(rwq_ind_table)  # Ensure the RWQ IND TBL is used before generating code
        return cls(rwq_ind_table_addr=rwq_ind_table)

    def generate_c(self, ctx: CodeGenContext) -> str:
        rwq_ind_table_name = ctx.get_rwq_ind_table(self.rwq_ind_table_addr)
        return f"""
    /* ibv_destroy_rwq_ind_table */
    if (ibv_destroy_rwq_ind_table({rwq_ind_table_name})) {{
        fprintf(stderr, "Failed to destroy RWQ IND TBL\\n");
        return -1;
    }}
"""

class DestroySRQ(VerbCall):
    """Destroy a Shared Receive Queue (SRQ)."""
    
    def __init__(self, srq_addr: str):
        self.srq_addr = srq_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        srq = kv.get("srq", "unknown")
        ctx.use_srq(srq)  # Ensure the SRQ is used before generating code
        return cls(srq_addr=srq)

    def generate_c(self, ctx: CodeGenContext) -> str:
        srq_name = ctx.get_srq(self.srq_addr)
        return f"""
    /* ibv_destroy_srq */
    if (ibv_destroy_srq({srq_name}) != 0) {{
        fprintf(stderr, "Failed to destroy SRQ\\n");
        return -1;
    }}
"""

class DestroyWQ(VerbCall):
    """Destroy a Work Queue (WQ)."""
    
    def __init__(self, wq_addr: str):
        self.wq_addr = wq_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        wq = kv.get("wq", "unknown")
        ctx.use_wq(wq)  # Ensure the WQ is used before generating code
        return cls(wq_addr=wq)

    def generate_c(self, ctx: CodeGenContext) -> str:
        wq_name = ctx.get_wq(self.wq_addr)
        return f"""
    /* ibv_destroy_wq */
    if (ibv_destroy_wq({wq_name})) {{
        fprintf(stderr, "Failed to destroy WQ\\n");
        return -1;
    }}
"""

class DetachMcast(VerbCall):
    """Detach a QP from a multicast group."""
    def __init__(self, qp_addr: str, gid: str, lid: int):
        self.qp_addr = qp_addr
        self.gid = gid
        self.lid = lid

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        gid = kv.get("gid", "unknown")
        lid = int(kv.get("lid", "0"))
        ctx.use_qp(qp)  # Ensure the QP is used before generating code
        return cls(qp_addr=qp, gid=gid, lid=lid)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        return f"""
    /* ibv_detach_mcast */
    if (ibv_detach_mcast({qp_name}, &{self.gid}, {self.lid})) {{
        fprintf(stderr, "Failed to detach multicast group\\n");
        return -1;
    }}
"""

class EventTypeStr(VerbCall):
    """Generate code for ibv_event_type_str.

    Returns a string describing the enum value for the given event type."""

    def __init__(self, event: str):
        self.event = event

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        event = kv.get("event", "IBV_EVENT_COMM_EST")
        return cls(event=event)

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_event_type_str */
    const char *event_desc = ibv_event_type_str({self.event});
    fprintf(stdout, "Event description: %s\\n", event_desc);
"""

# class FlowActionESP(VerbCall):
#     def __init__(self, ctx: str = "ctx", esp_params: Dict[str, any] = {}):
#         self.ctx = ctx
#         self.esp_params = esp_params
    
#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext = None):
#         kv = _parse_kv(info)
#         esp_params = {
#             "esp_attr": kv.get("esp_attr"),
#             "keymat_proto": kv.get("keymat_proto"),
#             "keymat_len": kv.get("keymat_len"),
#             "keymat_ptr": kv.get("keymat_ptr"),
#             "replay_proto": kv.get("replay_proto"),
#             "replay_len": kv.get("replay_len"),
#             "replay_ptr": kv.get("replay_ptr"),
#             "esp_encap": kv.get("esp_encap"),
#             "comp_mask": kv.get("comp_mask"),
#             "esn": kv.get("esn")
#         }
#         return cls(ctx=ctx.ib_ctx, esp_params=esp_params)
    
#     def generate_c(self, ctx: CodeGenContext) -> str:
#         esp_var = "esp_params"
#         esp_lines = "\n    ".join(
#             f"{esp_var}.{key} = {value};" for key, value in self.esp_params.items()
#         )
        
#         return f"""
#     struct ibv_flow_action_esp {esp_var};
#     memset(&{esp_var}, 0, sizeof({esp_var}));
#     {esp_lines}
#     struct ibv_flow_action *esp_action = `ibv_create_flow_action_esp({self.ctx}, &{esp_var})`;
#     if (!esp_action) {{
#         fprintf(stderr, "Failed to create ESP flow action\\n");
#         return -1;
#     }}
# """

class ForkInit(VerbCall):
    def __init__(self):
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        return cls()

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_fork_init */
    if (ibv_fork_init()) {{
        fprintf(stderr, "Failed to initialize fork support\\n");
        return -1;
    }}
"""

class FreeDeviceList(VerbCall):
    """Release the array of RDMA devices obtained from ibv_get_device_list."""

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

class FreeDM(VerbCall):
    """Release a device memory buffer (DM)."""

    def __init__(self, dm_addr: str):
        self.dm_addr = dm_addr
        
    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        dm = kv.get("dm", "unknown")
        ctx.use_dm(dm)  # Ensure the DM is used before generating code
        return cls(dm_addr=dm)
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        dm_name = ctx.get_dm(self.dm_addr)
        return f"""
    /* ibv_free_dm */
    if (ibv_free_dm({dm_name})) {{
        fprintf(stderr, "Failed to free device memory (DM)\\n");
        return -1;
    }}
"""

class GetAsyncEvent(VerbCall):
    def __init__(self):
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        return cls()
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_get_async_event */
    struct ibv_async_event async_event;
    if (ibv_get_async_event({ctx.ib_ctx}, &async_event)) {{
        fprintf(stderr, "Failed to get async_event\\n");
        return -1;
    }}

    /* Process the async event */
    switch (async_event.event_type) {{
        case IBV_EVENT_CQ_ERR:
            fprintf(stderr, "CQ error\\n");
            break;
        case IBV_EVENT_QP_FATAL:
            fprintf(stderr, "QP fatal error\\n");
            break;
        case IBV_EVENT_QP_REQ_ERR:
            fprintf(stderr, "QP request error\\n");
            break;
        case IBV_EVENT_QP_ACCESS_ERR:
            fprintf(stderr, "QP access error\\n");
            break;
        case IBV_EVENT_COMM_EST:
            fprintf(stderr, "Communication established\\n");
            break;
        case IBV_EVENT_SQ_DRAINED:
            fprintf(stderr, "Send Queue drained\\n");
            break;
        case IBV_EVENT_PATH_MIG:
            fprintf(stderr, "Path migrated\\n");
            break;
        case IBV_EVENT_PATH_MIG_ERR:
            fprintf(stderr, "Path migration error\\n");
            break;
        case IBV_EVENT_DEVICE_FATAL:
            fprintf(stderr, "Device fatal error\\n");
            break;
        case IBV_EVENT_PORT_ACTIVE:
            fprintf(stderr, "Port active\\n");
            break;
        case IBV_EVENT_PORT_ERR:
            fprintf(stderr, "Port error\\n");
            break;
        case IBV_EVENT_LID_CHANGE:
            fprintf(stderr, "LID changed\\n");
            break;
        case IBV_EVENT_PKEY_CHANGE:
            fprintf(stderr, "P_Key table changed\\n");
            break;
        case IBV_EVENT_SM_CHANGE:
            fprintf(stderr, "SM changed\\n");
            break;
        case IBV_EVENT_SRQ_ERR:
            fprintf(stderr, "SRQ error\\n");
            break;
        case IBV_EVENT_SRQ_LIMIT_REACHED:
            fprintf(stderr, "SRQ limit reached\\n");
            break;
        case IBV_EVENT_QP_LAST_WQE_REACHED:
            fprintf(stderr, "Last WQE reached\\n");
            break;
        case IBV_EVENT_CLIENT_REREGISTER:
            fprintf(stderr, "Client re-register request\\n");
            break;
        case IBV_EVENT_GID_CHANGE:
            fprintf(stderr, "GID table changed\\n");
            break;
        case IBV_EVENT_WQ_FATAL:
            fprintf(stderr, "WQ fatal error\\n");
            break;
        default:
            fprintf(stderr, "Unknown event type\\n");
            break;
    }}

    /* Acknowledge the async event */
    ibv_ack_async_event(&async_event);
"""

class GetCQEvent(VerbCall):
    def __init__(self, channel_addr: str, cq_addr: str, cq_context: str):
        self.channel_addr = channel_addr
        self.cq_addr = cq_addr
        self.cq_context = cq_context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        channel = kv.get("channel", "unknown")
        cq = kv.get("cq", "unknown")
        cq_context = kv.get("cq_context", "unknown")
        ctx.use_cq(cq)  # Ensure the CQ is used before generating code
        return cls(channel_addr=channel, cq_addr=cq, cq_context=cq_context)

    def generate_c(self, ctx: CodeGenContext) -> str:
        channel_name = ctx.get_obj(self.channel_addr)  # Assume context resolves object names
        cq_name = ctx.get_cq(self.cq_addr)
        return f"""
    /* ibv_get_cq_event */
    if (ibv_get_cq_event({channel_name}, &{cq_name}, &{self.cq_context})) {{
        fprintf(stderr, "Failed to get CQ event\\n");
        return -1;
    }}
    /* Acknowledge the event */
    ibv_ack_cq_events({cq_name}, 1);
"""

class GetDeviceGUID(VerbCall):
    """Get the Global Unique Identifier (GUID) of the RDMA device."""

    def __init__(self, device="dev_list[0]", output: str= None, ctx: CodeGenContext = None):
        self.device = device
        self.output = output or "guid"  # Default output variable name
        if ctx:
            # ctx.alloc_variable("guid", "uint64_t")  # Register the GUID variable in context
            ctx.alloc_variable(self.output, "__be64")

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        device = kv.get("device", "dev_list[0]")
        return cls(device=device)

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_get_device_guid */
    {self.output} = ibv_get_device_guid({self.device});
    printf("Device GUID: %llx\\n", (unsigned long long)be64toh({self.output}));
"""

class GetDeviceIndex(VerbCall):
    """Retrieve the device index for the specified IB device."""
    
    def __init__(self, device_name: str, output: str= None, ctx: CodeGenContext = None):
        self.device_name = device_name
        self.output = output or f"device_index_{device_name}"  # Default output variable name
        if ctx:
            ctx.alloc_variable(self.output, "int")  # Register the index variable in context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        device_name = kv.get("device", "unknown")
        ctx.use_device(device_name)  # Register the device in the context
        return cls(device_name=device_name)

    def generate_c(self, ctx: CodeGenContext) -> str:
        # device = ctx.get_device(self.device_name)
        # index_var = f"device_index_{self.device_name}"
        device = self.device_name
        index_var = self.output
        return f"""
    /* Retrieve IB device index */
    {index_var} = ibv_get_device_index({device});
    if ({index_var} < 0) {{
        fprintf(stderr, "Failed to get device index for {device}\\n");
        return -1;
    }}
"""

class GetDeviceList(VerbCall):
    """Fetch the list of available RDMA devices.

    This verb generates the C code to retrieve a list of RDMA devices currently
    available on the system using ibv_get_device_list(). If successful, a 
    NULL-terminated array of available devices is returned. This is typically
    the first step in setting up RDMA resources.

    Errors:
    - EPERM: Permission denied.
    - ENOSYS: Function not implemented.
    """

    def __init__(self):
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        """Create an instance based on a parsed JSON trace line."""
        kv = _parse_kv(info)
        return cls()

    def generate_c(self, ctx: CodeGenContext) -> str:
        dev_list = ctx.dev_list
        num_devices = "num_devices"
        return f"""
    /* ibv_get_device_list */
    {dev_list} = ibv_get_device_list(NULL);
    if (!{dev_list}) {{
        fprintf(stderr, "Failed to get device list: %s\\n", strerror(errno));
        return -1;
    }}
"""

# class GetDeviceName(VerbCall):
#     def __init__(self, device: str = "dev_list[0]"):
#         self.device = device

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext = None):
#         kv = _parse_kv(info)
#         device = kv.get("device", "dev_list[0]")
#         return cls(device=device)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         dev_name = f"device_name"
#         return f"""
#     /* ibv_get_device_name */
#     const char *{dev_name} = ibv_get_device_name({self.device});
#     if (!{dev_name}) {{
#         fprintf(stderr, "Failed to get device name\\n");
#         return -1;
#     }} else {{
#         printf("Device name: %s\\n", {dev_name});
#     }}
# """

class GetPKeyIndex(VerbCall):
    def __init__(self, port_num: int, pkey: int, output: str = "pkey_index"):
        self.port_num = port_num
        self.pkey = pkey
        self.output = output  # Variable name to store the P_Key index

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        port_num = int(kv.get("port_num", 1))
        pkey = int(kv.get("pkey", 0))
        return cls(port_num=port_num, pkey=pkey)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = ctx.ib_ctx
        ctx.alloc_variable(self.output, "int")  # Register the P_Key index variable in context
        pkey_index = self.output  # Use the output variable name for the P_Key index
        return f"""
    /* ibv_get_pkey_index */
    if (({pkey_index} = ibv_get_pkey_index({ib_ctx}, {self.port_num}, {self.pkey})) < 0) {{
        fprintf(stderr, "Failed to get P_Key index\\n");
        return -1;
    }}
"""

class GetSRQNum(VerbCall):
    def __init__(self, srq_addr: str, srq_num_var: str):
        self.srq_addr = srq_addr  # Shared Receive Queue address
        self.srq_num_var = srq_num_var  # Variable name to store the SRQ number

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        srq = kv.get("srq", "unknown")
        srq_num_var = kv.get("srq_num", "srq_num")
        ctx.use_srq(srq)  # Ensure the SRQ is used before generating code
        return cls(srq_addr=srq, srq_num_var=srq_num_var)
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        srq_name = ctx.get_srq(self.srq_addr)
        ctx.alloc_variable(self.srq_num_var, "uint32_t")  # Register the SRQ number variable in context
        return f"""
    /* ibv_get_srq_num */
    if (ibv_get_srq_num({srq_name}, &{self.srq_num_var})) {{
        fprintf(stderr, "Failed to get SRQ number\\n");
        return -1;
    }}
"""

class ImportDevice(VerbCall):
    def __init__(self, cmd_fd: int, ctx_var: str = "ctx"):
        self.ctx_var = ctx_var  # Variable name for the context
        self.cmd_fd = cmd_fd

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cmd_fd = int(kv.get("cmd_fd", "-1"))  # Default to -1 if not found
        return cls(cmd_fd=cmd_fd)

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_import_device */
    {self.ctx_var} = ibv_import_device({self.cmd_fd});
    if (!{self.ctx_var}) {{
        fprintf(stderr, "Failed to import device\\n");
        return -1;
    }}
"""

class ImportDM(VerbCall):
    # def __init__(self, dm_handle: int, dm_var: str = "dm"):
    #     self.dm_handle = dm_handle
    #     self.dm_var = dm_var  # Variable name for the imported device memory
    def __init__(self, dm_handle: int, dm_addr: str = "dm", ctx: CodeGenContext = None):
        self.dm_handle = dm_handle
        self.dm_addr = dm_addr  # Variable name for the imported device memory

        if ctx:
            ctx.alloc_dm(dm_addr)  # Register the DM address in the context


    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        dm_handle = int(kv.get("dm_handle", "0"))
        return cls(dm_handle=dm_handle)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = ctx.ib_ctx
        self.dm_var = ctx.get_dm(self.dm_addr)  # Get the DM variable name from context
        # ctx.alloc_variable(self.dm_var, "struct ibv_dm *")  # Register the DM variable in context
        return f"""
    /* ibv_import_dm */
    {self.dm_var} = ibv_import_dm({ib_ctx}, {self.dm_handle});
    if (!{self.dm_var}) {{
        fprintf(stderr, "Failed to import device memory\\n");
        return -1;
    }}
"""

class ImportMR(VerbCall):
    def __init__(self, pd_addr: str, mr_handle: int, mr_addr: str, ctx: CodeGenContext):
        self.pd_addr = pd_addr
        self.mr_handle = mr_handle
        self.mr_addr = mr_addr
        ctx.alloc_mr(mr_addr)  # Register the MR address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        mr_handle = int(kv.get("mr_handle", 0))
        mr = kv.get("mr", "unknown")
        return cls(pd_addr=pd, mr_handle=mr_handle, mr_addr=mr, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.get_pd(self.pd_addr)
        mr_name = ctx.get_mr(self.mr_addr)
        return f"""
    /* ibv_import_mr */
    {mr_name} = ibv_import_mr({pd_name}, {self.mr_handle});
    if (!{mr_name}) {{
        fprintf(stderr, "Failed to import MR\\n");
        return -1;
    }}
"""

class ImportPD(VerbCall):
    def __init__(self, pd_addr: str, pd_handle: int, ctx: CodeGenContext):
        self.pd_addr = pd_addr
        self.pd_handle = pd_handle
        ctx.alloc_pd(pd_addr)
        
    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        pd_handle = int(kv.get("pd_handle", 0))
        return cls(pd_addr=pd, pd_handle=pd_handle, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.get_pd(self.pd_addr)
        return f"""
    /* ibv_import_pd */
    {pd_name} = ibv_import_pd({ctx.ib_ctx}, {self.pd_handle});
    if (!{pd_name}) {{
        fprintf(stderr, "Failed to import PD\\n");
        return -1;
    }}
"""

class IncRKey(VerbCall):
    """Verb to increment the rkey value."""

    def __init__(self, rkey: str, new_rkey: str = "new_rkey"):
        self.rkey = rkey
        self.new_rkey = new_rkey  # Variable name for the new rkey

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        rkey = kv.get("rkey", "unknown")
        return cls(rkey=rkey)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ctx.alloc_variable(self.rkey, "uint32_t")  # Register the rkey variable in context
        return f"""
    /* ibv_inc_rkey */
    {self.new_rkey} = ibv_inc_rkey({self.rkey});
    fprintf(stdout, "Old RKey: %u, New RKey: %u\\n", {self.rkey}, {self.new_rkey});
"""

class InitAHFromWC(VerbCall):
    def __init__(self, context: str, port_num: int, wc: str, grh: str, ah_attr: str):
        self.context = context
        self.port_num = port_num
        self.wc = wc
        self.grh = grh
        self.ah_attr = ah_attr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        context = kv.get("context", "ctx")
        port_num = int(kv.get("port_num", 1))
        wc = kv.get("wc", "wc")
        grh = kv.get("grh", "grh")
        ah_attr = kv.get("ah_attr", "ah_attr")
        return cls(context=context, port_num=port_num, wc=wc, grh=grh, ah_attr=ah_attr)

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_init_ah_from_wc */
    if (ibv_init_ah_from_wc({self.context}, {self.port_num}, &{self.wc}, &{self.grh}, &{self.ah_attr})) {{
        fprintf(stderr, "Failed to initialize AH from WC\\n");
        return -1;
    }}
"""

class IsForkInitialized(VerbCall):
    """Check if fork support is enabled using ibv_is_fork_initialized."""

    def __init__(self, output: str = None):
        self.output = output or 'fork_status'
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        return cls()

    def generate_c(self, ctx: CodeGenContext) -> str:
        ctx.alloc_variable(self.output, "enum ibv_fork_status")  # Register the fork status variable in context
        return f"""
    /* Check if fork support is initialized */
    {self.output} = ibv_is_fork_initialized();
    switch ({self.output}) {{
        case IBV_FORK_DISABLED:
            fprintf(stdout, "Fork support is disabled\\n");
            break;
        case IBV_FORK_ENABLED:
            fprintf(stdout, "Fork support is enabled\\n");
            break;
        case IBV_FORK_UNNEEDED:
            fprintf(stdout, "Fork support is unneeded\\n");
            break;
        default:
            fprintf(stdout, "Unknown fork status\\n");
            break;
    }}
"""

class MemcpyFromDM(VerbCall):
    def __init__(self, host_addr: str, dm_addr: str, dm_offset: int = 0, length: int = 0):
        self.host_addr = host_addr
        self.dm_addr = dm_addr
        self.dm_offset = dm_offset
        self.length = length

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        host_addr = kv.get("host_addr", "unknown")
        dm_addr = kv.get("dm", "unknown")
        dm_offset = int(kv.get("dm_offset", 0))
        length = int(kv.get("length", 0))
        ctx.use_dm(dm_addr)
        return cls(host_addr=host_addr, dm_addr=dm_addr, dm_offset=dm_offset, length=length)

    def generate_c(self, ctx: CodeGenContext) -> str:
        dm_name = ctx.get_dm(self.dm_addr)
        return f"""
    /* ibv_memcpy_from_dm */
    if (ibv_memcpy_from_dm({self.host_addr}, {dm_name}, {self.dm_offset}, {self.length}) != 0) {{
        fprintf(stderr, "Failed to copy from device memory\\n");
        return -1;
    }}
"""

class MemcpyToDM(VerbCall):
    def __init__(self, dm_addr: str, dm_offset: int, host_addr: str, length: int):
        self.dm_addr = dm_addr  # Device memory address
        self.dm_offset = dm_offset  # Offset in the device memory
        self.host_addr = host_addr  # Host memory address
        self.length = length  # Length of data to copy

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        dm = kv.get("dm", "unknown")
        ctx.use_dm(dm)  # Ensure the DM is used before generating code
        return cls(
            dm_addr=dm,
            dm_offset=int(kv.get("dm_offset", 0)),
            host_addr=kv.get("host_addr", "host_buf"),
            length=int(kv.get("length", 0))
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        dm_name = ctx.get_dm(self.dm_addr)
        return f"""
    /* ibv_memcpy_to_dm */
    if (ibv_memcpy_to_dm({dm_name}, {self.dm_offset}, {self.host_addr}, {self.length}) != 0) {{
        fprintf(stderr, "Failed to copy to device memory\\n");
        return -1;
    }}
"""


class ModifyCQ(VerbCall):
    """Modify a Completion Queue (CQ) attributes.
    
    This verb modifies a CQ with new moderation attributes 
    like number of completions per event and period in microseconds.
    The `attr_mask` field in `ibv_modify_cq_attr` specifies which 
    attributes to modify.
    """

    def __init__(self, cq_addr: str, attr_object = None, attr_var: str = None):
        self.cq_addr = cq_addr
        self.attr_object = attr_object  # This can be a dict or an object with attributes
        self.attr_var = attr_var or f"attr_modify_cq_{cq_addr}"  # Default variable name for the CQ attributes

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq_var = kv.get("cq", "cq")
        attr_var = kv.get("attr_var", "modify_cq_attr")
        attr_obj = kv.get("attr_obj")  # trace中如含结构体内容
        return cls(cq_var, attr_var, attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        self.cq_var = ctx.get_cq(self.cq_addr)  # Get the CQ variable name from context
        code = ""
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            code += f"\n    struct ibv_modify_cq_attr {self.attr_var} = {{0}};\n"
        code += f"""
    if (ibv_modify_cq({self.cq_var}, &{self.attr_var}) != 0) {{
        fprintf(stderr, "ibv_modify_cq failed\\n");
        return -1;
    }}
"""
        return code

class ModifyQP(VerbCall):
    def __init__(self, qp_addr: str, attr: IbvQPAttr, attr_mask: str, ctx: CodeGenContext = None): # ctx for backward compatibility
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
        attr_name = f"qp_attr{attr_suffix}"
        attr_lines = self.attr.to_cxx(attr_name, ctx)  # Convert the attr dict to C++ code
        mask_code = mask_fields_to_c(self.attr_mask)
        return f"""
    memset(&{attr_name}, 0, sizeof({attr_name}));
    {attr_lines}
    ibv_modify_qp({qp_name}, &{attr_name}, {mask_code});
        """
        
# class ModifyQP(VerbCall):
#     def __init__(self, qp_addr: str, attr: Dict, attr_mask: str, ctx: CodeGenContext = None): # ctx for backward compatibility
#         self.qp_addr = qp_addr
#         self.attr = attr
#         self.attr_mask = attr_mask  # e.g., "IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS"

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         qp = kv.get("qp", "unknown")
#         ctx.use_qp(qp)
#         attr_keys = {"qp_state", "pkey_index", "port_num", "qp_access_flags", 
#                      "path_mtu", "dest_qp_num", "rq_psn", "max_dest_rd_atomic", 
#                      "min_rnr_timer", "ah_attr.is_global", "ah_attr.dlid", 
#                      "ah_attr.sl", "ah_attr.src_path_bits", "ah_attr.port_num",
#                     #  "ah_attr.grh.dgid", 
#                      "ah_attr.grh.flow_label", 
#                      "ah_attr.grh.hop_limit", "ah_attr.grh.sgid_index",
#                      "ah_attr.grh.traffic_class", "timeout", "retry_cnt", "rnr_retry", "sq_psn", "max_rd_atomic"}
#         attr_params = {k: kv[k] for k in attr_keys if k in kv}
#         attr_mask = kv.get("attr_mask", "IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS")
#         return cls(qp_addr=qp, attr=attr_params, attr_mask = attr_mask)


#     def generate_c(self, ctx: CodeGenContext) -> str:
#         qp_name = ctx.get_qp(self.qp_addr)
#         attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")  # e.g., "_0" for qp[0]
#         # attr_name = f"attr_modify_rtr{attr_suffix}"
#         attr_name = f"qp_attr{attr_suffix}"
#         ctx.alloc_variable(attr_name, "struct ibv_qp_attr")  # Register the attribute variable in the context
        
#         # Initialize the attribute structure
#         # Note: The attr dict contains keys like "qp_state", "pkey_index", etc.
#         # We will generate code to set these attributes in the attr_name variable.
#         # ah_attr.grh.dgid 特殊，必须用memcpy
#         # 现在认为ah_attr.grh.dgid是一个变量名
        
#         if 'ah_attr.grh.dgid' in self.attr:
#             # If the dgid is present, we need to handle it separately

#             memcpy_line = f"""
#     memcpy(&{attr_name}.ah_attr.grh.dgid, {self.attr['ah_attr.grh.dgid']}, 16);
#             """
#             del self.attr['ah_attr.grh.dgid']  # Remove it from the attr dict
#         else:
#             memcpy_line = ""
#         attr_lines = "\n    ".join(
#             f"{attr_name}.{k} = {v};" for k, v in self.attr.items()
#         )
#         return f"""
#     memset(&{attr_name}, 0, sizeof({attr_name}));
#     {attr_lines}
#     {memcpy_line}
#     ibv_modify_qp({qp_name}, &{attr_name}, {self.attr_mask});
#         """
    
# class ModifyQP(VerbCall):
#     def __init__(self, qp_addr: str, attr_mask: int, attr_values: Dict[str, str]):
#         self.qp_addr = qp_addr
#         self.attr_mask = attr_mask
#         self.attr_values = attr_values  # Dictionary containing ibv_qp_attr values.

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         qp = kv.get("qp", "unknown")
#         attr_mask = int(kv.get("attr_mask", "0"))
#         attr_values = {k: kv[k] for k in kv if k not in {"qp", "attr_mask"}}
#         ctx.use_qp(qp)  # Ensure the QP is used before generating code
#         return cls(qp_addr=qp, attr_mask=attr_mask, attr_values=attr_values)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         qp_name = ctx.get_qp(self.qp_addr)
#         attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
#         attr_name = f"attr_modify{attr_suffix}"
#         attr_lines = "\n    ".join(f"{attr_name}.{k} = {v};" for k, v in self.attr_values.items())
        
#         return f"""
#     /* ibv_modify_qp */
#     struct ibv_qp_attr {attr_name} = {{0}};
#     {attr_lines}
#     if (ibv_modify_qp({qp_name}, &{attr_name}, {self.attr_mask}) != 0) {{
#         fprintf(stderr, "Failed to modify QP\\n");
#         return -1;
#     }}
# """


class ModifyQPRateLimit(VerbCall):
    """
    表示 ibv_modify_qp_rate_limit() 调用，自动生成/重放 ibv_qp_rate_limit_attr 的初始化与调用。
    参数：
        qp_var      -- QP 变量名（如"qp1"）
        attr_var    -- qp_rate_limit_attr 结构体变量名（如"rate_limit_attr1"）
        attr_obj    -- IbvQPRateLimitAttr对象（可选，自动生成结构体内容）
    """
    def __init__(self, qp_addr: str, attr_var: str, attr_obj: 'IbvQPRateLimitAttr' = None):
        self.qp_addr = qp_addr
        self.attr_var = attr_var or f"rate_limit_attr_{qp_addr}"  # Default variable name for the rate limit attributes
        self.attr_obj = attr_obj

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp_var = kv.get("qp", "qp")
        attr_var = kv.get("attr_var", "rate_limit_attr")
        attr_obj = kv.get("attr_obj")  # 若trace含结构体内容
        return cls(qp_var, attr_var, attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        self.qp_var = ctx.get_qp(self.qp_addr)  # Get the QP variable name from context
        code = ""
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            code += f"\n    struct ibv_qp_rate_limit_attr {self.attr_var} = {{0}};\n"
        code += f"""
    if (ibv_modify_qp_rate_limit({self.qp_var}, &{self.attr_var}) != 0) {{
        fprintf(stderr, "ibv_modify_qp_rate_limit failed\\n");
        return -1;
    }}
"""
        return code


class ModifySRQ(VerbCall):
    """
    表示 ibv_modify_srq() 调用，自动生成/重放 srq_attr 的初始化与调用。
    参数：
        srq_var      -- SRQ 变量名（如"srq1"）
        attr_var     -- srq_attr 结构体变量名（如"srq_attr1"）
        attr_obj     -- IbvSrqAttr对象（可选，自动生成结构体内容）
        attr_mask    -- int，传递给 C API 的 srq_attr_mask
    """
    def __init__(self, srq_addr: str, attr_var: str = None, attr_obj: 'IbvSrqAttr' = None, attr_mask: int = 0):
        self.srq_addr = srq_addr
        self.attr_var = attr_var or f"srq_attr_{srq_addr}"  # Default variable name for the SRQ attributes
        self.attr_obj = attr_obj
        self.attr_mask = attr_mask

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        srq_var = kv.get("srq", "srq")
        attr_var = kv.get("attr_var", "srq_attr")
        attr_obj = kv.get("attr_obj")  # 若trace含结构体内容
        attr_mask = int(kv.get("attr_mask", 0))
        return cls(srq_var, attr_var, attr_obj, attr_mask)

    def generate_c(self, ctx: CodeGenContext) -> str:
        self.srq_var = ctx.get_srq(self.srq_addr)
        code = ""
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            code += f"\n    struct ibv_srq_attr {self.attr_var} = {{0}};\n"
        code += f"""
    if (ibv_modify_srq({self.srq_var}, &{self.attr_var}, {self.attr_mask}) != 0) {{
        fprintf(stderr, "ibv_modify_srq failed\\n");
        return -1;
    }}
"""
        return code
    
class ModifyWQ(VerbCall):
    """
    表示 ibv_modify_wq() 调用，自动生成/重放 wq_attr 的初始化与调用。
    参数：
        wq_var      -- WQ 变量名（如"wq1"）
        attr_var    -- wq_attr 结构体变量名（如"wq_attr1"）
        attr_obj    -- IbvWQAttr对象（可选，自动生成结构体内容）
    """
    def __init__(self, wq_addr: str, attr_var: str = None, attr_obj: 'IbvWQAttr' = None):
        self.wq_addr = wq_addr
        self.attr_var = attr_var or f"wq_attr_{wq_addr}"  # Default variable name for the WQ attributes
        self.attr_obj = attr_obj

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        wq_var = kv.get("wq", "wq")
        attr_var = kv.get("attr_var", "wq_attr")
        attr_obj = kv.get("attr_obj")  # trace中如含结构体内容
        return cls(wq_var, attr_var, attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        self.wq_var = ctx.get_wq(self.wq_addr)  # Get the WQ variable name from context
        code = ""
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            code += f"\n    struct ibv_wq_attr {self.attr_var} = {{0}};\n"
        code += f"""
    if (ibv_modify_wq({self.wq_var}, &{self.attr_var}) != 0) {{
        fprintf(stderr, "ibv_modify_wq failed\\n");
        return -1;
    }}
"""
        return code


class OpenDevice(VerbCall):
    """Open an RDMA device and create a context for use."""
    
    def __init__(self, device: str = "dev_list[0]"):
        self.device = device  # Device name or variable, e.g., "dev_list[
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        return cls()  # No special initialization needed from trace
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = ctx.ib_ctx
        dev_list = ctx.dev_list  # Assuming correct allocation of device list
        return f"""
    /* ibv_open_device */
    {ib_ctx} = ibv_open_device({dev_list}[0]);
    if (!{ib_ctx}) {{
        fprintf(stderr, "Failed to open device\\n");
        return -1;
    }}
"""

class OpenQP(VerbCall):
    """
    表示 ibv_open_qp() 调用。
    参数：
        ctx_var      -- ibv_context 变量名（如"ctx"）
        qp_var       -- QP 变量名（如"qp1"）
        attr_var     -- qp_open_attr 结构体变量名（如"qp_open_attr1"）
        attr_obj     -- IbvQPOpenAttr对象（可选，自动生成结构体内容）
    """
    def __init__(self, ctx_var, qp_addr: str, attr_var: str, attr_obj = None, ctx: CodeGenContext = None):
        self.ctx_var = ctx_var or "ctx"
        self.qp_addr = qp_addr
        self.attr_var = attr_var or f"qp_open_attr_{qp_addr}"  # Default variable name for the QP open attributes
        self.attr_obj = attr_obj
        ctx.alloc_qp(self.qp_addr)  # Register the QP address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ctx_var = kv.get("ctx", "ctx")
        qp_var = kv.get("qp", "qp")
        attr_var = kv.get("attr_var", "qp_open_attr")
        attr_obj = kv.get("attr_obj")  # 若trace中含结构体内容
        return cls(ctx_var, qp_var, attr_var, attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        self.qp_var = ctx.get_qp(self.qp_addr)  # Get the
        code = ""
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            code += f"\n    struct ibv_qp_open_attr {self.attr_var} = {{0}};\n"
        code += f"""
    {self.qp_var} = ibv_open_qp({self.ctx_var}, &{self.attr_var});
    if (!{self.qp_var}) {{
        fprintf(stderr, "ibv_open_qp failed\\n");
        return -1;
    }}
"""
        return code

class OpenXRCD(VerbCall):
    """
    表示 ibv_open_xrcd() 调用，自动生成 struct ibv_xrcd_init_attr 初始化与调用。
    参数：
        ctx_var     -- ibv_context 变量名（如"ctx"）
        xrcd_var    -- XRC Domain 变量名（如"xrcd1"）
        attr_var    -- xrcd_init_attr 结构体变量名（如"xrcd_init_attr1"）
        attr_obj    -- IbvXRCDInitAttr对象（可选，自动生成结构体内容）
    """
    def __init__(self, ctx_var: str, xrcd_addr: str, attr_var: str, attr_obj = None):
        self.ctx_var = ctx_var
        self.xrcd_addr = xrcd_addr
        self.attr_var = attr_var or f"xrcd_init_attr_{xrcd_addr}"  # Default variable name for the XRC Domain attributes
        self.attr_obj = attr_obj

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ctx_var = kv.get("ctx", "ctx")
        xrcd_var = kv.get("xrcd", "xrcd")
        attr_var = kv.get("attr_var", "xrcd_init_attr")
        attr_obj = kv.get("attr_obj")  # 若trace含结构体内容
        return cls(ctx_var, xrcd_var, attr_var, attr_obj)

    def generate_c(self, ctx: CodeGenContext) -> str:
        self.xrcd_addr = ctx.get_xrcd(self.xrcd_addr)  # Get the XRC Domain variable name from context
        code = ""
        if self.attr_obj is not None:
            code += self.attr_obj.to_cxx(self.attr_var, ctx)
        else:
            code += f"\n    struct ibv_xrcd_init_attr {self.attr_var} = {{0}};\n"
        code += f"""
    {self.xrcd_var} = ibv_open_xrcd({self.ctx_var}, &{self.attr_var});
    if (!{self.xrcd_var}) {{
        fprintf(stderr, "ibv_open_xrcd failed\\n");
        return -1;
    }}
"""
        return code


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
    
# class PollCQ(VerbCall):
#     def __init__(self, cq_addr: str, num_entries: int = 1):
#         self.cq_addr = cq_addr
#         self.num_entries = num_entries

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         cq = kv.get("cq", "unknown")
#         num_entries = kv.get("num_entries", 1)
#         ctx.use_cq(cq)
#         return cls(cq_addr=cq, num_entries=int(num_entries))

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         cq_name = ctx.get_cq(self.cq_addr)
#         return f"""
#     /* Poll completion queue */
#     struct ibv_wc wc[{self.num_entries}];
#     int num_completions = ibv_poll_cq({cq_name}, {self.num_entries}, wc);

#     if (num_completions < 0) {{
#         fprintf(stderr, "Error polling CQ\\n");
#         return -1;
#     }} else {{
#         fprintf(stdout, "Found %d completions\\n", num_completions);
#     }}

#     for (int i = 0; i < num_completions; ++i) {{
#         if (wc[i].status != IBV_WC_SUCCESS) {{
#             fprintf(stderr, "Completion with error: %d, vendor error: %d\\n", wc[i].status, wc[i].vendor_err);
#         }} else {{
#             fprintf(stdout, "Completion successful, opcode: %d, byte_len: %d\\n", wc[i].opcode, wc[i].byte_len);
#         }}
#     }}
# """

class PostRecv(VerbCall):
    """
    表示 ibv_post_recv() 调用，自动生成 recv_wr 链与调用代码。
    参数：
        qp_addr   -- QP 资源变量名/trace名
        wr_obj    -- IbvRecvWR对象（支持链表）
        wr_var    -- recv_wr 结构体变量名
        bad_wr_var-- bad_wr 结构体指针变量名
    """
    def __init__(self, qp_addr: str, wr_obj = None, wr_var: str = "recv_wr", bad_wr_var: str = "bad_recv_wr"):
        self.qp_addr = qp_addr
        self.wr_obj = wr_obj
        self.wr_var = wr_var or f"recv_wr_{qp_addr}"  # Default variable name for the receive work request
        self.bad_wr_var = bad_wr_var

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp_addr = kv.get("qp", "qp")
        # 假设 trace 提供 wr 对象（或需自己构造/解析）
        wr_obj = kv.get("wr_obj")
        wr_var = kv.get("wr_var", "recv_wr")
        bad_wr_var = kv.get("bad_wr_var", "bad_recv_wr")
        return cls(qp_addr, wr_obj, wr_var, bad_wr_var)

    def generate_c(self, ctx: CodeGenContext) -> str:
        s = ""
        # 构造 WR 结构体（链表/单个）
        if self.wr_obj is not None:
            s += self.wr_obj.to_cxx(self.wr_var, ctx)
        else:
            s += f"\n    struct ibv_recv_wr {self.wr_var} = {{0}};\n"
        # bad_wr 定义
        if ctx:
            ctx.alloc_variable(self.bad_wr_var, "struct ibv_recv_wr *", "NULL")  # Register the bad work request pointer in the context
        else:
            s += f"\n    struct ibv_recv_wr *{self.bad_wr_var} = NULL;\n"
        # 调用
        qp_name = ctx.get_qp(self.qp_addr) if hasattr(ctx, 'get_qp') else self.qp_addr
        s += f"""
    if (ibv_post_recv({qp_name}, &{self.wr_var}, &{self.bad_wr_var}) != 0) {{
        fprintf(stderr, "ibv_post_recv failed\\n");
        return -1;
    }}
"""
        return s

class PostSend(VerbCall):
    def __init__(self, qp_addr, wr_obj = None, ctx: CodeGenContext = None):
        self.qp_addr = qp_addr        # qp对象变量名或trace地址
        self.wr_obj = wr_obj          # IbvSendWR实例（用于自动生成WR内容）

    @classmethod
    def from_trace(cls, info, ctx):
        # info: 字符串或者dict，含qp/wr/bad_wr等参数
        kv = _parse_kv(info)  # 假设有类似 {'qp':'qp1', 'wr':'wr1', ...}
        wr_obj = None
        if 'wr_obj' in kv:
            wr_obj = kv['wr_obj']
        return cls(
            qp_addr=kv.get("qp"),
            wr_addr=kv.get("wr"),
            bad_wr_addr=kv.get("bad_wr"),
            wr_obj=wr_obj
        )

    def generate_c(self, ctx):
        # ctx: CodeGenContext，负责变量声明/资源管理
        qp_name = ctx.get_qp(self.qp_addr)
        attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")  # e.g., "_0" for qp[0]
        wr_name = f"wr{attr_suffix}"  # e.g., "wr_0"
        bad_wr_name = f"bad_wr{attr_suffix}"  # e.g., "bad_wr_0"
        code = ""
        # 1. 声明send_wr结构体内容
        if self.wr_obj is not None:
            code += self.wr_obj.to_cxx(wr_name, ctx)
        # 2. 声明bad_wr变量
        if bad_wr_name:
            ctx.alloc_variable(bad_wr_name, "struct ibv_send_wr *", "NULL")  # Register the bad work request pointer in the context
        # 3. 生成ibv_post_send调用
        bad_wr_arg = f"&{bad_wr_name}" if bad_wr_name else "NULL"
        # code += (
        #     f"\n    int rc = ibv_post_send({self.qp_addr}, "
        #     f"&{self.wr_addr}, {bad_wr_arg});\n"
        #     f"    if (ibv_post_send({self.qp_addr}, "
        #     f"&{self.wr_addr}, {bad_wr_arg})) {{ printf(\"ibv_post_send failed: %d\\n\", rc); }}\n"
        # )
        return f"""
    /* ibv_post_send */
    {code}
    
    if (ibv_post_send({qp_name}, &{wr_name}, {bad_wr_arg}) != 0) {{
        fprintf(stderr, "Failed to post send work request\\n");
        return -1;
    }}
    """
        # return code
    
# class PostSend(VerbCall):
#     """Post Send Work Request to a Queue Pair's Send Queue.

#     This class generates the code for the `ibv_post_send` verb, which posts a linked list of
#     work requests (WRs) to the send queue of a specified Queue Pair (QP). 

#     The `ibv_post_send` function interface:
#     ```c
#     int ibv_post_send(struct ibv_qp *qp, struct ibv_send_wr *wr,
#                       struct ibv_send_wr **bad_wr);
#     ```

#     Parameters:
#     - qp_addr (str): The address of the Queue Pair (QP) to which the work request is to be posted.
#     - mr_addr (str): The Memory Region (MR) address used for the local keys in scatter/gather entries.
#     - wr_id (str): User-defined ID of the work request. Default is "0".
#     - opcode (str): Specifies the operation type. Default is "IBV_WR_SEND".
#     - remote_addr (str): Remote memory buffer's start address (for RDMA operations).
#     - rkey (str): Remote key of the memory region (for RDMA operations).
#     - send_flags (str): Flags defining properties of the WR, for example, `IBV_SEND_SIGNALED`.
#     """

#     def __init__(self, qp_addr: str, mr_addr: str, wr_id: str = "0", opcode: str = "IBV_WR_SEND", 
#                  remote_addr: str = None, rkey: str = None, send_flags: str = "IBV_SEND_SIGNALED"):
#         self.qp_addr = qp_addr
#         self.mr_addr = mr_addr
#         self.wr_id = wr_id
#         self.opcode = opcode
#         self.remote_addr = remote_addr
#         self.rkey = rkey
#         self.send_flags = send_flags

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         qp = kv.get("qp", "unknown")
#         mr = kv.get("mr", "MR")
#         ctx.use_qp(qp)
#         ctx.use_mr(mr)
#         return cls(
#             qp_addr=qp,
#             mr_addr=mr,
#             wr_id=kv.get("wr_id", "0"),
#             opcode=kv.get("opcode", "IBV_WR_SEND"),
#             remote_addr=kv.get("remote_addr"),
#             rkey=kv.get("rkey"),
#             send_flags=kv.get("send_flags", "IBV_SEND_SIGNALED")
#         )

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         qp_name = ctx.get_qp(self.qp_addr)
#         qpn = qp_name.replace("qp[", "").replace("]", "")
#         suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
#         sr = f"sr{suffix}"
#         mr = ctx.get_mr(self.mr_addr)
#         buf = "bufs[" + qpn + "]"
#         sge = f"sge_send{suffix}"
#         bad_wr = f"bad_wr_send{suffix}"
        
#         ctx.alloc_variable(sr, "struct ibv_send_wr")  # Register the send request variable in the context
#         ctx.alloc_variable(sge, "struct ibv_sge")  # Register the scatter/gather entry variable in the context
#         ctx.alloc_variable(bad_wr, "struct ibv_send_wr *")  # Register the bad work request pointer in the context

#         # Prepare the RDMA lines if remote address and rkey are provided

#         rdma_lines = ""
#         if self.remote_addr and self.rkey:
#             rdma_lines = f"""
#     {sr}.wr.rdma.remote_addr = {self.remote_addr};
#     {sr}.wr.rdma.rkey = {self.rkey};"""

#         return f"""
#     /* ibv_post_send */

#     memset(&{sge}, 0, sizeof({sge}));
#     {sge}.addr = (uintptr_t){buf};
#     {sge}.length = MSG_SIZE;
#     {sge}.lkey = {mr}->lkey;

#     memset(&{sr}, 0, sizeof({sr}));
#     {sr}.next = NULL;
#     {sr}.wr_id = {self.wr_id};
#     {sr}.sg_list = &{sge};
#     {sr}.num_sge = 1;
#     {sr}.opcode = {self.opcode};
#     {sr}.send_flags = {self.send_flags};{rdma_lines}

#     ibv_post_send({qp_name}, &{sr}, &{bad_wr});
# """

# class PostSRQOps(VerbCall):
#     """Perform operations on a special shared receive queue (SRQ)."""

#     def __init__(self, srq_addr: str, wr_id: str, opcode: str, flags: str, tm_params: Dict):
#         self.srq_addr = srq_addr
#         self.wr_id = wr_id
#         self.opcode = opcode
#         self.flags = flags
#         self.tm_params = tm_params

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         srq = kv.get("srq", "unknown")
#         ctx.use_srq(srq)  # Ensure the SRQ is used before generating code
#         return cls(
#             srq_addr=srq,
#             wr_id=kv.get("wr_id", "0"),
#             opcode=kv.get("opcode", "IBV_WR_TAG_ADD"),
#             flags=kv.get("flags", "0"),
#             tm_params={
#                 "unexpected_cnt": kv.get("unexpected_cnt", "0"),
#                 "handle": kv.get("handle", "0"),
#                 "recv_wr_id": kv.get("recv_wr_id", "0"),
#                 "sg_list": kv.get("sg_list", "NULL"),
#                 "num_sge": kv.get("num_sge", "0"),
#                 "tag": kv.get("tag", "0"),
#                 "mask": kv.get("mask", "0")
#             }
#         )

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         srq_name = ctx.get_srq(self.srq_addr)
#         op_wr_suffix = "_" + self.srq_addr.replace("srq[", "").replace("]", "")
#         op_wr_name = f"op_wr{op_wr_suffix}"
#         bad_op_name = f"bad_op{op_wr_suffix}"
#         tm_params = self.tm_params

#         return f"""
#     /* ibv_post_srq_ops */
#     struct ibv_ops_wr {op_wr_name};
#     struct ibv_ops_wr *{bad_op_name};

#     memset(&{op_wr_name}, 0, sizeof({op_wr_name}));
#     {op_wr_name}.wr_id = {self.wr_id};
#     {op_wr_name}.opcode = {self.opcode};
#     {op_wr_name}.flags = {self.flags};
#     {op_wr_name}.tm.unexpected_cnt = {tm_params.get("unexpected_cnt")};
#     {op_wr_name}.tm.handle = {tm_params.get("handle")};
#     {op_wr_name}.tm.add.recv_wr_id = {tm_params.get("recv_wr_id")};
#     {op_wr_name}.tm.add.sg_list = {tm_params.get("sg_list")};
#     {op_wr_name}.tm.add.num_sge = {tm_params.get("num_sge")};
#     {op_wr_name}.tm.add.tag = {tm_params.get("tag")};
#     {op_wr_name}.tm.add.mask = {tm_params.get("mask")};

#     if (ibv_post_srq_ops({srq_name}, &{op_wr_name}, &{bad_op_name})) {{
#         fprintf(stderr, "Failed to post srq ops\\n");
#         return -1;
#     }}
# """

class PostSRQRecv(VerbCall):
    """
    表示 ibv_post_srq_recv() 调用，自动生成 recv_wr 链和调用代码。
    参数：
        srq_addr   -- SRQ 资源变量名（或 trace 名）
        wr_obj     -- IbvRecvWR 对象（支持链表）
        wr_var     -- recv_wr 结构体变量名
        bad_wr_var -- bad_recv_wr 结构体指针变量名
    """
    def __init__(self, srq_addr: str, wr_obj = None, wr_var : str = None, bad_wr_var: str = "bad_recv_wr"):
        self.srq_addr = srq_addr
        self.wr_obj = wr_obj
        self.wr_var = wr_var or f"recv_wr_{srq_addr}"  # Default variable name for the receive work request
        self.bad_wr_var = bad_wr_var

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        srq_addr = kv.get("srq", "srq")
        wr_obj = kv.get("wr_obj")
        wr_var = kv.get("wr_var", "recv_wr")
        bad_wr_var = kv.get("bad_wr_var", "bad_recv_wr")
        return cls(srq_addr, wr_obj, wr_var, bad_wr_var)

    def generate_c(self, ctx: CodeGenContext) -> str:
        s = ""
        # WR结构体生成
        if self.wr_obj is not None:
            s += self.wr_obj.to_cxx(self.wr_var, ctx)
        else:
            s += f"\n    struct ibv_recv_wr {self.wr_var} = {{0}};\n"
        # bad_wr 定义
        if ctx:
            ctx.alloc_variable(self.bad_wr_var, "struct ibv_recv_wr *", "NULL")  # Register the bad work request pointer in the context
        else:
            s += f"\n    struct ibv_recv_wr *{self.bad_wr_var} = NULL;\n"
        # 调用
        srq_name = ctx.get_srq(self.srq_addr) if hasattr(ctx, "get_srq") else self.srq_addr
        s += f"""
    if (ibv_post_srq_recv({srq_name}, &{self.wr_var}, &{self.bad_wr_var}) != 0) {{
        fprintf(stderr, "ibv_post_srq_recv failed\\n");
        return -1;
    }}
"""
        return s


# class PostSRQRecv(VerbCall):
#     def __init__(self, srq_addr: str, wr_id: str = "0", num_sge: int = 1, addr: str = "0", length: str = "0", lkey: str = "0"):
#         self.srq_addr = srq_addr
#         self.wr_id = wr_id
#         self.num_sge = num_sge
#         self.addr = addr
#         self.length = length
#         self.lkey = lkey

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         srq = kv.get("srq", "unknown")
#         ctx.use_srq(srq)
#         return cls(
#             srq_addr=srq,
#             wr_id=kv.get("wr_id", "0"),
#             num_sge=int(kv.get("num_sge", "1")),
#             addr=kv.get("addr", "0"),
#             length=kv.get("length", "0"),
#             lkey=kv.get("lkey", "0")
#         )

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         srq_name = ctx.get_srq(self.srq_addr)
#         wr_suffix = "_" + srq_name.replace("srq[", "").replace("]", "")
#         recv_wr_name = f"recv_wr{wr_suffix}"
#         sge_name = f"sge_recv{wr_suffix}"
#         bad_recv_wr_name = f"bad_recv_wr{wr_suffix}"

#         return f"""
#     /* ibv_post_srq_recv */
#     struct ibv_recv_wr {recv_wr_name};
#     struct ibv_sge {sge_name};
#     struct ibv_recv_wr *{bad_recv_wr_name};

#     memset(&{sge_name}, 0, sizeof({sge_name}));
#     {sge_name}.addr = (uintptr_t){self.addr};
#     {sge_name}.length = {self.length};
#     {sge_name}.lkey = {self.lkey};

#     memset(&{recv_wr_name}, 0, sizeof({recv_wr_name}));
#     {recv_wr_name}.wr_id = {self.wr_id};
#     {recv_wr_name}.num_sge = {self.num_sge};
#     {recv_wr_name}.sg_list = &{sge_name};
#     {recv_wr_name}.next = NULL;

#     ibv_post_srq_recv({srq_name}, &{recv_wr_name}, &{bad_recv_wr_name});
# """

class QueryDeviceAttr(VerbCall):
    """Query the attributes of an RDMA device using its context."""

    def __init__(self, output):
        self.output = output
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        return cls()

    def generate_c(self, ctx: CodeGenContext) -> str:
        dev_attr = ctx.dev_attr
        if self.output is None:
            self.output = dev_attr  # Use the context's device attribute variable
        ib_ctx = ctx.ib_ctx
        return f"""
    /* ibv_query_device */
    if (ibv_query_device({ib_ctx}, &{self.output})) {{
        fprintf(stderr, "Failed to query device attributes\\n");
        return -1;
    }}
"""

class QueryDeviceEx(VerbCall):
    """
    表示 ibv_query_device_ex() 调用。
    参数:
        ctx_var  -- ibv_context 变量名
        attr_var -- ibv_device_attr_ex 变量名
        comp_mask -- input.comp_mask 的值
        input_var -- (可选) input 结构体变量名
    """
    def __init__(self, ctx_var: str, attr_var: str = "dev_attr_ex", comp_mask: int = 0, input_var: str = "query_input"):
        self.ctx_var = ctx_var
        self.attr_var = attr_var # this is output
        self.comp_mask = comp_mask
        self.input_var = input_var # this is input

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        ctx_var = kv.get("ctx", "ctx")
        attr_var = kv.get("attr_var", "dev_attr_ex")
        comp_mask = int(kv.get("comp_mask", 0))
        input_var = kv.get("input_var", "query_input")
        return cls(ctx_var, attr_var, comp_mask, input_var)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ctx.alloc_variable(self.input_var, "struct ibv_query_device_ex_input")  # Register the input variable in the context
        ctx.alloc_variable(self.attr_var, "struct ibv_device_attr_ex")  # Register
        s = f"""
    memset(&{self.input_var}, 0, sizeof({self.input_var}));
    {self.input_var}.comp_mask = {self.comp_mask};
    if (ibv_query_device_ex({self.ctx_var}, &{self.input_var}, &{self.attr_var}) != 0) {{
        fprintf(stderr, "ibv_query_device_ex failed\\n");
        return -1;
    }}
"""
        return s


class QueryECE(VerbCall):
    def __init__(self, qp_addr: str, output: str = "ece"):
        self.qp_addr = qp_addr
        self.output = output  # Variable name for the ECE options output

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        ctx.use_qp(qp)  # Ensure the QP is used before generating code
        return cls(qp_addr=qp)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        ctx.alloc_variable(self.output, "struct ibv_ece")  # Register the ECE options variable in the context
        return f"""
    /* ibv_query_ece */
    if (ibv_query_ece({qp_name}, &{self.output})) {{
        fprintf(stderr, "Failed to query ECE options, error code: %d\\n", query_result);
        return -1;
    }}
    fprintf(stdout, "ECE options for QP: vendor_id=0x%x, options=0x%x, comp_mask=0x%x\\n",
            {self.output}.vendor_id, {self.output}.options, {self.output}.comp_mask);
"""

class QueryGID(VerbCall):
    def __init__(self, port_num: int = 1, index: int = 1):
        self.port_num = port_num
        self.index = index

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        port_num = int(kv.get("port_num", "1"))
        index = int(kv.get("index", "0"))
        return cls(port_num=port_num, index=index)
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        gid_var = "my_gid"
        return f"""
    /* ibv_query_gid */
    union ibv_gid {gid_var};
    if (ibv_query_gid({ctx.ib_ctx}, {self.port_num}, {self.index}, &{gid_var})) {{
        fprintf(stderr, "Failed to query GID\\n");
        return -1;
    }}
    struct metadata_global meta_global = {{
        .lid = port_attr.lid,
        .gid = {{my_gid.raw[0], my_gid.raw[1], my_gid.raw[2], my_gid.raw[3],
                my_gid.raw[4], my_gid.raw[5], my_gid.raw[6], my_gid.raw[7],
                my_gid.raw[8], my_gid.raw[9], my_gid.raw[10], my_gid.raw[11],
                my_gid.raw[12], my_gid.raw[13], my_gid.raw[14], my_gid.raw[15]}}}};

    char *json_str = serialize_metadata_global(&meta_global);
    printf("[Controller] Global Metadata: %s\\n", json_str);
    char buf[256];
    snprintf(buf, sizeof(buf), "%s\\n", json_str);
    send(sockfd, buf, strlen(buf), 0);
    free(json_str);
    send(sockfd, "END\\n", 4, 0); // 发送结束标志
"""

class QueryGIDEx(VerbCall):
    def __init__(self, port_num: int = 1, gid_index: int = 0, flags: int = 0, output: str = "gid_entry"):
        self.port_num = port_num
        self.gid_index = gid_index
        self.flags = flags
        self.output = output  # Variable name for the GID entry output

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        port_num = int(kv.get("port_num", 1))
        gid_index = int(kv.get("gid_index", 0))
        flags = int(kv.get("flags", 0))
        return cls(port_num=port_num, gid_index=gid_index, flags=flags)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = ctx.ib_ctx
        ctx.alloc_variable(self.output, "struct ibv_gid_entry")
        return f"""
    /* ibv_query_gid_ex */
    if (ibv_query_gid_ex({ib_ctx}, {self.port_num}, {self.gid_index}, &{self.output}, {self.flags})) {{
        fprintf(stderr, "Failed to query GID\\n");
        return -1;
    }}
"""

class QueryGIDTable(VerbCall):
    """Query GID table of a given RDMA device context."""
    def __init__(self, max_entries: int = 10, output: str = "gid_entries"):
        self.max_entries = max_entries
        self.output = output  # Variable name for the GID entries output

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        return cls(max_entries=int(kv.get("max_entries", 10)))

    def generate_c(self, ctx: CodeGenContext) -> str:
        ctx.alloc_variable(self.output, "struct ibv_gid_entry", f"entries[{self.max_entries}]")
        ib_ctx = ctx.ib_ctx
        return f"""
    /* ibv_query_gid_table */
    if (ibv_query_gid_table({ctx.ib_ctx}, {self.output}, {self.max_entries}, 0) < 0) {{
        fprintf(stderr, "Failed to query GID table\\n");
        return -1;
    }}
"""

class QueryPKey(VerbCall):
    """Query an InfiniBand port's P_Key table entry."""

    def __init__(self, port_num: int = 1, index: int = 0, pkey: str = "pkey"):
        self.port_num = port_num
        self.index = index
        self.pkey = pkey

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        port_num = int(kv.get("port_num", "1"))
        index = int(kv.get("index", "0"))
        pkey = kv.get("pkey", "pkey")
        ctx.alloc_pkey(pkey)
        return cls(port_num=port_num, index=index, pkey=pkey)
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        pkey_name = ctx.get_pkey(self.pkey)
        return f"""
    /* ibv_query_pkey */
    if (ibv_query_pkey({ctx.ib_ctx}, {self.port_num}, {self.index}, &{pkey_name})) {{
        fprintf(stderr, "Failed to query P_Key\\n");
        return -1;
    }}
"""

class QueryPortAttr(VerbCall):
    """Query the attributes of a specified RDMA port on a given device context."""
    
    def __init__(self, port_num: int = 1):
        self.port_num = port_num

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        return cls(port_num=int(kv.get("port_num", "1")))

    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = ctx.ib_ctx
        port_attr = ctx.port_attr
        return f"""
    /* ibv_query_port */
    if (ibv_query_port({ib_ctx}, {self.port_num}, &{port_attr})) {{
        fprintf(stderr, "Failed to query port attributes\\n");
        return -1;
    }}
"""

class QueryQP(VerbCall):
    def __init__(self, qp_addr: str, attr_mask: int):
        self.qp_addr = qp_addr
        self.attr_mask = attr_mask

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        mask = kv.get("attr_mask", "0")
        ctx.use_qp(qp)  # Ensure the QP is used before generating code
        return cls(qp_addr=qp, attr_mask=int(mask))

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")  # e.g., "_0" for qp[0]
        attr_name = f"attr_query{attr_suffix}"
        init_attr_name = f"init_attr{attr_suffix}"  
        ctx.alloc_variable(attr_name, "struct ibv_qp_attr")  # Register the QP attribute variable in the context
        ctx.alloc_variable(init_attr_name, "struct ibv_qp_init_attr")  #
        return f"""
    /* ibv_query_qp */
    if (ibv_query_qp({qp_name}, &{attr_name}, {self.attr_mask}, &{init_attr_name})) {{
        fprintf(stderr, "Failed to query QP\\n");
        return -1;
    }}
"""

# class QueryQPDataInOrder(VerbCall):
#     def __init__(self, qp_addr: str, opcode: str, flags: int):
#         self.qp_addr = qp_addr
#         self.opcode = opcode
#         self.flags = flags

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         qp = kv.get("qp", "unknown")
#         opcode = kv.get("opcode", "IBV_WR_SEND")
#         flags = int(kv.get("flags", "0"), 0)
#         ctx.use_qp(qp)  # Ensure the QP is used before generating code
#         return cls(qp_addr=qp, opcode=opcode, flags=flags)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         qp_name = ctx.get_qp(self.qp_addr)
#         return f"""
#     /* ibv_query_qp_data_in_order */
#     int in_order = ibv_query_qp_data_in_order({qp_name}, {self.opcode}, {self.flags});
#     if (in_order < 0) {{
#         fprintf(stderr, "Failed to query QP data in order\\n");
#         return -1;
#     }}
#     printf("QP data in order query result: %d\\n", in_order);
# """

# class QueryRTValuesEx(VerbCall):
#     def __init__(self):
#         pass

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         return cls()
    
#     def generate_c(self, ctx: CodeGenContext) -> str:
#         ib_ctx = ctx.ib_ctx
#         return f"""
#     /* ibv_query_rt_values_ex */
#     struct ibv_values_ex values;
#     values.comp_mask = IBV_VALUES_MASK_RAW_CLOCK; /* Request to query the raw clock */
#     if (ibv_query_rt_values_ex({ib_ctx}, &values)) {{
#         fprintf(stderr, "Failed to query real time values\\n");
#         return -1;
#     }}
#     fprintf(stdout, "HW raw clock queried successfully\\n");
# """

class QuerySRQ(VerbCall):
    """Query a Shared Receive Queue (SRQ) for its attributes."""
    def __init__(self, srq_addr):
        self.srq_addr = srq_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        srq = kv.get("srq", "unknown")
        ctx.use_srq(srq)  # Ensure the SRQ is used before generating code
        return cls(srq_addr=srq)

    def generate_c(self, ctx: CodeGenContext) -> str:
        srq_name = ctx.get_srq(self.srq_addr)
        attr_name = f"srq_attr_{srq_name.replace('[', '_').replace(']', '')}"
        ctx.alloc_variable(attr_name, "struct ibv_srq_attr")
        return f"""
    /* ibv_query_srq */
    if (ibv_query_srq({srq_name}, &{attr_name})) {{
        fprintf(stderr, "Failed to query SRQ\\n");
        return -1;
    }}
    fprintf(stdout, "SRQ max_wr: %u, max_sge: %u, srq_limit: %u\\n", 
            {attr_name}.max_wr, {attr_name}.max_sge, {attr_name}.srq_limit);
"""

class RateToMbps(VerbCall):
    """Convert IB rate enumeration to Mbps."""
    def __init__(self, rate: str, output: str = "mbps"):
        self.rate = rate  # IB rate enumeration
        self.output = output

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        rate = kv.get("rate", "IBV_RATE_MAX")
        return cls(rate=rate)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ctx.alloc_variable(self.output, "int")  # Register the output variable in the context
        return f"""
    /* ibv_rate_to_mbps */
    {self.output} = ibv_rate_to_mbps({self.rate});
    printf("Rate: %s, Mbps: %d\\n", "{self.rate}", mbps);
"""


class RateToMult(VerbCall):
    """Convert IB rate enumeration to multiplier of 2.5 Gbit/sec (IBV_RATE_TO_MULT)"""
    
    def __init__(self, rate: str, output: str = "mbps"):
        self.rate = rate  # IB rate enumeration
        self.output = output

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        rate = kv.get("rate", "IBV_RATE_MAX")
        return cls(rate=rate)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ctx.alloc_variable(self.output, "int")  # Register the output variable in the context
        return f"""
    /* ibv_rate_to_mult */
    {self.output}  ibv_rate_to_mult({self.rate});
    printf("Rate multiplier for {self.rate}: %d\\n", multiplier);
"""

class RegDmaBufMR(VerbCall):
    def __init__(self, pd_addr: str, mr_addr: str, offset: int, length: int, iova: int, fd: int, access: int, ctx: CodeGenContext):
        self.pd_addr = pd_addr
        self.mr_addr = mr_addr
        self.offset = offset
        self.length = length
        self.iova = iova
        self.fd = fd
        self.access = access
        ctx.alloc_mr(mr_addr)  # Register the MR address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "pd[0]")
        mr = kv.get("mr", "unknown")
        offset = int(kv.get("offset", "0"))
        length = int(kv.get("length", "0"))
        iova = int(kv.get("iova", "0"))
        fd = int(kv.get("fd", "0"))
        access = int(kv.get("access", "0"))
        return cls(pd_addr=pd, mr_addr=mr, offset=offset, length=length, iova=iova, fd=fd, access=access, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        mr_name = ctx.get_mr(self.mr_addr)
        pd_name = ctx.get_pd(self.pd_addr)
        return f"""
    /* ibv_reg_dmabuf_mr */
    {mr_name} = ibv_reg_dmabuf_mr({pd_name}, {self.offset}, {self.length}, {self.iova}, {self.fd}, {self.access});
    if (!{mr_name}) {{
        fprintf(stderr, "Failed to register dmabuf MR\\n");
        return -1;
    }}
"""

class RegMR(VerbCall):
    def __init__(self, pd_addr, mr_addr, buf="buf", length=4096, flags="IBV_ACCESS_LOCAL_WRITE", ctx=None):
        self.pd_addr = pd_addr
        self.mr_addr = mr_addr
        self.buf = buf
        self.length = length
        self.flags = flags
        if ctx:
            ctx.alloc_mr(mr_addr)  # Register the MR address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "pd[0]")
        mr = kv.get("mr", "unknown")
        flags = kv.get("flags", "IBV_ACCESS_LOCAL_WRITE")
        return cls(pd_addr=pd, mr_addr=mr, flags=flags, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        mr_name = ctx.get_mr(self.mr_addr)
        pd_name = ctx.get_pd(self.pd_addr)
        return f"""
    /* ibv_reg_mr */
    {mr_name} = ibv_reg_mr({pd_name}, {self.buf}, {self.length}, {self.flags});
    if (!{mr_name}) {{
        fprintf(stderr, "Failed to register memory region\\n");
        return -1;
    }}
"""

class RegMRIova(VerbCall):
    def __init__(self, pd_addr, mr_addr, buf="buf", length=4096, iova=0, access="IBV_ACCESS_LOCAL_WRITE", ctx=None):
        self.pd_addr = pd_addr
        self.mr_addr = mr_addr
        self.buf = buf
        self.length = length
        self.iova = iova
        self.access = access
        if ctx:
            ctx.alloc_mr(mr_addr)  # Register the MR address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "pd[0]")
        mr = kv.get("mr", "unknown")
        return cls(
            pd_addr=pd, 
            mr_addr=mr, 
            buf=kv.get("buf", "buf"), 
            length=int(kv.get("length", 4096)),
            iova=int(kv.get("iova", 0)), 
            access=kv.get("access", "IBV_ACCESS_LOCAL_WRITE"),
            ctx=ctx
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.get_pd(self.pd_addr)
        mr_name = ctx.get_mr(self.mr_addr)
        return f"""
    /* ibv_reg_mr_iova */
    {mr_name} = ibv_reg_mr_iova({pd_name}, {self.buf}, {self.length}, {self.iova}, {self.access});
    if (!{mr_name}) {{
        fprintf(stderr, "Failed to register MR with IOVA\\n");
        return -1;
    }}
"""

class ReqNotifyCQ(VerbCall):
    """Request completion notification on a completion queue (CQ)."""
    def __init__(self, cq_addr: str, solicited_only: int = 0):
        self.cq_addr = cq_addr
        self.solicited_only = solicited_only

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq = kv.get("cq", "unknown")
        solicited_only = int(kv.get("solicited_only", 0))
        ctx.use_cq(cq)  # Ensure the CQ is used before generating code
        return cls(cq_addr = cq, solicited_only = solicited_only)

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = ctx.get_cq(self.cq_addr)
        return f"""
    /* ibv_req_notify_cq */
    if (ibv_req_notify_cq({cq_name}, {self.solicited_only})) {{
        fprintf(stderr, "Failed to request CQ notification\\n");
        return -1;
    }}
"""


class ReRegMR(VerbCall):
    def __init__(self, mr_addr: str, flags: int, pd_addr: Optional[str] = None, addr: Optional[str] = None, length: int = 0, access: int = 0):
        self.mr_addr = mr_addr
        self.flags = flags
        self.pd_addr = pd_addr
        self.addr = addr
        self.length = length
        self.access = access

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        mr = kv.get("mr", "unknown")
        flags = int(kv.get("flags", 0))
        pd = kv.get("pd")
        addr = kv.get("addr")
        length = int(kv.get("length", 0))
        access = int(kv.get("access", 0))
        ctx.use_mr(mr)  # Ensure the MR is used before generating code
        if pd:
            ctx.use_pd(pd)  # Ensure the PD is used before generating code if specified
        return cls(
            mr_addr=mr,
            flags=flags,
            pd_addr=pd,
            addr=addr,
            length=length,
            access=access
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        mr_name = ctx.get_mr(self.mr_addr)
        pd_name = ctx.get_pd(self.pd_addr) if self.pd_addr else "NULL"
        addr = self.addr if self.addr else "NULL"
        return f"""
    /* ibv_rereg_mr */
    if (ibv_rereg_mr({mr_name}, {self.flags}, {pd_name}, {addr}, {self.length}, {self.access}) != 0) {{
        fprintf(stderr, "Failed to re-register MR\\n");
        return -1;
    }}
"""

class ResizeCQ(VerbCall):
    def __init__(self, cq_addr: str, cqe: int):
        self.cq_addr = cq_addr
        self.cqe = cqe

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq = kv.get("cq", "unknown")
        cqe = int(kv.get("cqe", 0))
        ctx.use_cq(cq)  # Ensure the CQ is used before generating code
        return cls(cq_addr=cq, cqe=cqe)

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = ctx.get_cq(self.cq_addr)
        return f"""
    /* ibv_resize_cq */
    if (ibv_resize_cq({cq_name}, {self.cqe})) {{
        fprintf(stderr, "Failed to resize CQ\\n");
        return -1;
    }}
"""

class SetECE(VerbCall):
    """
    表示 ibv_set_ece() 调用。
    参数：
        qp_addr    -- QP 资源变量名
        ece_obj    -- IbvECE 对象
        ece_var    -- ece 结构体变量名
    """
    def __init__(self, qp_addr: str, ece_obj: 'IbvECE', ece_var: str = "ece"):
        self.qp_addr = qp_addr
        self.ece_obj = ece_obj
        self.ece_var = ece_var

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp_addr = kv.get("qp", "qp")
        # 支持 trace 中直接提供 ece_obj 或手动构造
        ece_obj = kv.get("ece_obj", IbvECE.random_mutation())
        ece_var = kv.get("ece_var", "ece")
        return cls(qp_addr, ece_obj, ece_var)

    def generate_c(self, ctx: CodeGenContext) -> str:
        s = ""
        if self.ece_obj is not None:
            s += self.ece_obj.to_cxx(self.ece_var, ctx)
        else:
            s += f"\n    struct ibv_ece {self.ece_var} = {{0}};\n"
        qp_name = ctx.get_qp(self.qp_addr) if hasattr(ctx, "get_qp") else self.qp_addr
        s += f"""
    if (ibv_set_ece({qp_name}, &{self.ece_var}) != 0) {{
        fprintf(stderr, "ibv_set_ece failed\\n");
        return -1;
    }}
"""
        return s

# class AbortWR(VerbCall):
#     """Abort all prepared work requests since wr_start."""
#     def __init__(self, qp_addr: str):
#         self.qp_addr = qp_addr

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         qp = kv.get("qp", "unknown")
#         ctx.use_qp(qp)  # Ensure the QP is used before generating code
#         return cls(qp_addr=qp)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         qp_name = ctx.get_qp(self.qp_addr)
#         qp_ex_name = f"{qp_name}_ex"
#         return f"""
#     /* Abort all work requests */
#     struct ibv_qp_ex *{qp_ex_name} = ibv_qp_to_qp_ex({qp_name});
#     ibv_wr_abort({qp_ex_name});
# """

class AbortWR(VerbCall):
    """Abort all prepared work requests since wr_start."""
    def __init__(self, qp_ex_addr: str):
        self.qp_ex_addr = qp_ex_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        ctx.use_qp(qp)  # Ensure the QP is used before generating code
        return cls(qp_addr=qp)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_ex_name = ctx.get_qp_ex(self.qp_ex_addr)
        return f"""
    /* Abort all work requests */
    struct ibv_qp_ex *{qp_ex_name} = ibv_qp_to_qp_ex({qp_ex_name});
    ibv_wr_abort({qp_ex_name});
"""

class WRComplete(VerbCall):
    def __init__(self, qp_ex_addr: str):
        self.qp_ex_addr = qp_ex_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp_ex = kv.get("qp_ex", "unknown")
        return cls(qp_ex_addr=qp_ex)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_ex_name = ctx.get_qp_ex(self.qp_ex_addr)
        return f"""
    /* ibv_wr_complete */
    if (ibv_wr_complete({qp_ex_name}) != 0) {{
        fprintf(stderr, "Failed to complete work request\\n");
        return -1;
    }}
"""

class WrStart(VerbCall):
    def __init__(self, qp_ex_addr: str):
        self.qp_ex_addr = qp_ex_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp_ex = kv.get("qp_ex", "unknown")
        ctx.use_qp(qp_ex)  # Ensure the QP extension is used before generating code
        return cls(qp_ex_addr=qp_ex)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_ex_name = ctx.get_qp_ex(self.qp_ex_addr)
        return f"""
    /* ibv_wr_start */
    ibv_wr_start({qp_ex_name});
"""

# Old verbs PROTECTED!

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

# class ModifyQPToRTR(VerbCall):
#     # def __init__(self, qp_addr: str, remote_qpn: int = 0, dlid: int = 0, dgid: str = "0"):
#     #     self.qp_addr = qp_addr
#     #     # self.remote_qpn = remote_qpn
#     #     # self.dlid = dlid
#     #     # self.dgid = dgid  # Global ID, not used in this example
#     #     self.remote_qpn = "remote_con_data.qp_num"
#     #     self.dlid = "remote_con_data.lid"
#     #     self.dgid = "remote_con_data.gid"  # Use the gid from the remote connection data
#     def __init__(self, qp_addr: str, qpn: int = 0):
#         self.qp_addr = qp_addr
#         # self.remote_qpn = remote_qpn
#         # self.dlid = dlid
#         # self.dgid = dgid  # Global ID, not used in this example
#         self.qpn = qpn
#         self.remote_qpn = f"remote_con_datas[{self.qpn}].qp_num"
#         self.dlid = f"remote_con_datas[{self.qpn}].lid"
#         self.dgid = f"remote_con_datas[{self.qpn}].gid"  # Use the gid from the remote connection data

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         qp = kv.get("qp", "unknown")
#         ctx.use_qp(qp)  # Ensure the QP is used before generating code
#         return cls(qp_addr = qp)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         qp_name = ctx.get_qp(self.qp_addr)
#         attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")  # e.g., "_0" for qp[0]
#         attr_name = f"attr_modify_rtr{attr_suffix}"
#         return f"""
#     /* ibv_modify_qp to RTR */
#     struct ibv_qp_attr {attr_name} = {{0}};
#     {attr_name}.qp_state = IBV_QPS_RTR;
#     {attr_name}.path_mtu = IBV_MTU_256; /* this field specifies the MTU from source code*/
#     {attr_name}.dest_qp_num = {self.remote_qpn};
#     {attr_name}.rq_psn = 0;
#     {attr_name}.max_dest_rd_atomic = 1;
#     {attr_name}.min_rnr_timer = 0x12;
#     {attr_name}.ah_attr.is_global = 0;
#     {attr_name}.ah_attr.dlid = {self.dlid};
#     {attr_name}.ah_attr.sl = 0;
#     {attr_name}.ah_attr.src_path_bits = 0;
#     {attr_name}.ah_attr.port_num = 1;
#     if(1 >= 0)
#     {{
#         {attr_name}.ah_attr.is_global = 1;
#         {attr_name}.ah_attr.port_num = 1;
#         memcpy(&{attr_name}.ah_attr.grh.dgid, {self.dgid}, 16);
#         /* this field specify the UDP source port. if the target UDP source port is expected to be X, the value of flow_label = X ^ 0xC000 */
#         {attr_name}.ah_attr.grh.flow_label = 0;
#         {attr_name}.ah_attr.grh.hop_limit = 1;
#         {attr_name}.ah_attr.grh.sgid_index = 1;
#         {attr_name}.ah_attr.grh.traffic_class = 0;
#     }}
#     ibv_modify_qp({qp_name}, &{attr_name}, IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER);
# """

# class ModifyQPToRTS(VerbCall):
#     def __init__(self, qp_addr: str):
#         self.qp_addr = qp_addr

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         qp = kv.get("qp", "unknown")
#         ctx.use_qp(qp)  # Ensure the QP is used before generating code
#         return cls(qp_addr = qp)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         qp_name = ctx.get_qp(self.qp_addr)
#         attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")  # e.g., "_0" for qp[0]
#         attr_name = f"attr_modify_rts{attr_suffix}"
#         return f"""
#     /* ibv_modify_qp to RTS */
#     struct ibv_qp_attr {attr_name} = {{0}};
#     {attr_name}.qp_state = IBV_QPS_RTS;
#     {attr_name}.timeout = 0x12;
#     {attr_name}.retry_cnt = 6;
#     {attr_name}.rnr_retry = 0;
#     {attr_name}.sq_psn = 0;
#     {attr_name}.max_rd_atomic = 1;
#     ibv_modify_qp({qp_name}, &{attr_name}, IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC);
# """
    


# class PollCQ(VerbCall):
#     def __init__(self, cq_addr: str):
#         self.cq_addr = cq_addr

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         cq = kv.get("cq", "unknown")
#         ctx.use_cq(cq)
#         return cls(cq_addr = cq)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         cq_name = ctx.get_cq(self.cq_addr)
#         return f"""
#     /* Poll completion queue */
    
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
#            d fprintf(stderr, "got bad completion with status: 0x%x, vendor syndrome: 0x%x\\n", 
#                     wc.status, wc.vendor_err);
#             rc = 1;
#         }}
#     }}
# """
    

# class DestroyMR(VerbCall):
#     """Destroy a Memory Region."""
#     def __init__(self, mr_addr: str):
#         self.mr_addr = mr_addr

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         mr = kv.get("mr", "unknown")
#         ctx.use_mr(mr)  # Ensure the MR is used before generating code
#         return cls(mr_addr = mr)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         mr_name = ctx.get_mr(self.mr_addr)
#         return f"""
#     /* ibv_dereg_mr */
#     if (ibv_dereg_mr({mr_name})) {{
#         fprintf(stderr, "Failed to deregister MR\\n");
#         return -1;
#     }}
# """
    
# class DestroyCQ(VerbCall):
#     """Destroy a Completion Queue."""
#     def __init__(self, cq_addr: str):
#         self.cq_addr = cq_addr

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         cq = kv.get("cq", "unknown")
#         ctx.use_cq(cq)  # Ensure the CQ is used before generating code
#         return cls(cq_addr = cq)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         cq_name = ctx.get_cq(self.cq_addr)
#         return f"""
#     /* ibv_destroy_cq */
#     if (ibv_destroy_cq({cq_name})) {{
#         fprintf(stderr, "Failed to destroy CQ\\n");
#         return -1;
#     }}
# """
    
# class DestroyPD(VerbCall):
#     """Destroy a Protection Domain."""
#     def __init__(self, pd_addr: str):
#         self.pd_addr = pd_addr

#     @classmethod
#     def from_trace(cls, info: str, ctx: CodeGenContext):
#         kv = _parse_kv(info)
#         pd = kv.get("pd", "unknown")
#         ctx.use_pd(pd)  # Ensure the PD is used before generating code
#         return cls(pd_addr = pd)

#     def generate_c(self, ctx: CodeGenContext) -> str:
#         pd_name = ctx.get_pd(self.pd_addr)
#         return f"""
#     /* ibv_dealloc_pd */
#     if (ibv_dealloc_pd({pd_name})) {{
#         fprintf(stderr, "Failed to deallocate PD\\n");
#         return -1;
#     }}
# """

# class CloseDevice(VerbCall):
#     """Close the IB device context."""
#     def __init__(self):
#         pass

#     @classmethod
#     def from_trace(cls, info: str, ctx : CodeGenContext = None):
#         return cls()
    
#     def generate_c(self, ctx: CodeGenContext) -> str:
#         ib_ctx = ctx.ib_ctx
#         return f"""
#     /* ibv_close_device */
#     if (ibv_close_device({ib_ctx})) {{
#         fprintf(stderr, "Failed to close device\\n");
#         return -1;
#     }}
# """


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
    # "ibv_modify_qp_rtr": ModifyQPToRTR.from_trace,
    # "ibv_modify_qp_rts": ModifyQPToRTS.from_trace,
    "ibv_poll_cq": PollCQ.from_trace,
    "ibv_destroy_qp": DestroyQP.from_trace,
    "ibv_dereg_mr": DeregMR.from_trace,
    "ibv_destroy_cq": DestroyCQ.from_trace,
    "ibv_dealloc_pd": DeallocPD.from_trace,
    "ibv_close_device": CloseDevice.from_trace
}