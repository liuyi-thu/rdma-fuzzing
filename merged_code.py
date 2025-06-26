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
    def __init__(self, pd_addr: str, advice: str, flags: int, sg_list: List[Dict[str, str]], num_sge: int):
        self.pd_addr = pd_addr
        self.advice = advice
        self.flags = flags
        self.sg_list = sg_list
        self.num_sge = num_sge

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        advice = kv.get("advice", "IBV_ADVISE_MR_ADVICE_PREFETCH")
        flags = int(kv.get("flags", 0))
        num_sge = int(kv.get("num_sge", 0))
        
        # Parse scatter-gather list
        sg_list_raw = kv.get("sg_list", "")
        sg_list = []
        for sg in sg_list_raw.split(";"):
            sg_kv = _parse_kv(sg)
            sg_list.append(sg_kv)

        ctx.use_pd(pd)  # Ensure the PD is used before generating code
        return cls(pd_addr=pd, advice=advice, flags=flags, sg_list=sg_list, num_sge=num_sge)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.get_pd(self.pd_addr)
        sg_list_str = ", ".join(
            f"{{ .addr = {sg['addr']}, .length = {sg['length']}, .lkey = {sg['lkey']} }}" for sg in self.sg_list
        )
        return f"""
    /* ibv_advise_mr */
    struct ibv_sge sg_list[{self.num_sge}] = {{ {sg_list_str} }};
    if (ibv_advise_mr({pd_name}, {self.advice}, {self.flags}, sg_list, {self.num_sge}) != 0) {{
        fprintf(stderr, "Failed to advise memory region\\n");
        return -1;
    }}
"""

# Add to VERB_FACTORY
VERB_FACTORY["ibv_advise_mr"] = AdviseMR.from_trace

class AllocDM(VerbCall):
    def __init__(self, dm_addr: str, length: int, log_align_req: int, ctx: CodeGenContext):
        self.dm_addr = dm_addr
        self.length = length
        self.log_align_req = log_align_req
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
        alloc_dm_attr = f"alloc_dm_attr_{dm_name.replace('dm[', '').replace(']', '')}"

        return f"""
    /* ibv_alloc_dm */
    struct ibv_alloc_dm_attr {alloc_dm_attr} = {{
        .length = {self.length},
        .log_align_req = {self.log_align_req},
        .comp_mask = 0
    }};
    {dm_name} = ibv_alloc_dm({ib_ctx}, &{alloc_dm_attr});
    if (!{dm_name}) {{
        fprintf(stderr, "Failed to allocate device memory (DM)\\n");
        return -1;
    }}
"""

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

VERB_FACTORY["ibv_alloc_mw"] = AllocMW.from_trace

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
        pd_addr (str): Address of the existing protection domain.
        parent_pd_addr (str): Address for the new parent domain.
    """
    def __init__(self, context, pd_addr: str, parent_pd_addr: str, ctx: CodeGenContext):
        self.context = context  # Associated IBV context
        self.pd_addr = pd_addr  # Address of the existing protection domain
        self.parent_pd_addr = parent_pd_addr
        ctx.alloc_pd(parent_pd_addr)  # Register the Parent Domain address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        pd_new = kv.get("parent_pd", "unknown")
        return cls(context=ctx.ib_ctx, pd_addr=pd, parent_pd_addr=pd_new, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.get_pd(self.pd_addr)
        parent_pd_name = ctx.get_pd(self.parent_pd_addr)
        pd_context = "NULL"  # Default value used for pd_context
        return f"""
    /* ibv_alloc_parent_domain */
    struct ibv_parent_domain_init_attr pd_attr_{self.parent_pd_addr} = {{0}};
    pd_attr_{self.parent_pd_addr}.pd = {ctx.get_pd(self.pd_addr)};
    pd_attr_{self.parent_pd_addr}.td = NULL; /* NULL indicates no thread domain */
    pd_attr_{self.parent_pd_addr}.comp_mask = IBV_PARENT_DOMAIN_INIT_ATTR_PD_CONTEXT;
    pd_attr_{self.parent_pd_addr}.pd_context = {pd_context};

    {parent_pd_name} = ibv_alloc_parent_domain({ctx.ib_ctx}, &pd_attr_{self.parent_pd_addr});
    if (!{parent_pd_name}) {{
        fprintf(stderr, "Failed to allocate parent domain\\n");
        return -1;
    }}
"""

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
    """Represents ibv_alloc_td() verb call to allocate a thread domain object."""

    def __init__(self, td_addr: str, ctx: CodeGenContext):
        self.td_addr = td_addr
        ctx.alloc_td(td_addr)

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        td = kv.get("td", "unknown")
        return cls(td_addr=td, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        td_name = ctx.get_td(self.td_addr)
        return f"""
    /* ibv_alloc_td */
    struct ibv_td_init_attr td_attr = {{0}};
    {td_name} = ibv_alloc_td({ctx.ib_ctx}, &td_attr);
    if (!{td_name}) {{
        fprintf(stderr, "Failed to allocate thread domain\\n");
        return -1;
    }}
"""

class AttachMcast(VerbCall):
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
        gid_value = f"{self.gid}"
        return f"""
    /* ibv_attach_mcast */
    if (ibv_attach_mcast({qp_name}, &{gid_value}, {self.lid})) {{
        fprintf(stderr, "Failed to attach multicast group\\n");
        return -1;
    }}
"""

# Add to VERB_FACTORY dictionary
VERB_FACTORY["ibv_attach_mcast"] = AttachMcast.from_trace

class BindMW(VerbCall):
    def __init__(self, qp_addr: str, mw_addr: str, mw_bind_info: Dict[str, str]):
        self.qp_addr = qp_addr
        self.mw_addr = mw_addr
        self.mw_bind_info = mw_bind_info

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        mw = kv.get("mw", "unknown")
        bind_info_keys = {"wr_id", "send_flags", "mr", "addr", "length", "mw_access_flags"}
        mw_bind_info = {k: kv[k] for k in bind_info_keys if k in kv}
        
        ctx.use_qp(qp)  # Ensure the QP is used before generating code
        ctx.use_mw(mw)  # Ensure the MW is used before generating code
        
        return cls(qp_addr=qp, mw_addr=mw, mw_bind_info=mw_bind_info)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        mw_name = ctx.get_mw(self.mw_addr)
        mw_bind_name = f"mw_bind_{mw_name.replace('mw[', '').replace(']', '')}"
        
        return f"""
    /* ibv_bind_mw */
    struct ibv_mw_bind {mw_bind_name} = {{0}};
    {mw_bind_name}.wr_id = {self.mw_bind_info.get("wr_id", "0")};
    {mw_bind_name}.send_flags = {self.mw_bind_info.get("send_flags", "IBV_SEND_SIGNALED")};
    {mw_bind_name}.bind_info.mr = {ctx.get_mr(self.mw_bind_info["mr"])};
    {mw_bind_name}.bind_info.addr = {self.mw_bind_info.get("addr", "0")};
    {mw_bind_name}.bind_info.length = {self.mw_bind_info.get("length", "0")};
    {mw_bind_name}.bind_info.mw_access_flags = {self.mw_bind_info.get("mw_access_flags", "IBV_ACCESS_REMOTE_WRITE")};
    
    if (ibv_bind_mw({qp_name}, {mw_name}, &{mw_bind_name}) != 0) {{
        fprintf(stderr, "Failed to bind MW\\n");
        return -1;
    }}
"""

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
    def __init__(self, pd_addr: str, ah_addr: str, ah_attr_params: Dict[str, str]):
        self.pd_addr = pd_addr
        self.ah_addr = ah_addr
        self.ah_attr_params = ah_attr_params

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        pd = kv.get("pd", "unknown")
        ah = kv.get("ah", "unknown")
        attr_keys = {"dlid", "sl", "src_path_bits", "static_rate", "is_global", "port_num",
                     "dgid", "flow_label", "sgid_index", "hop_limit", "traffic_class"}
        ah_attr_params = {k: kv[k] for k in attr_keys if k in kv}
        ctx.use_pd(pd)
        return cls(pd_addr=pd, ah_addr=ah, ah_attr_params=ah_attr_params)

    def generate_c(self, ctx: CodeGenContext) -> str:
        pd_name = ctx.get_pd(self.pd_addr)
        ah_name = f"{self.ah_addr}"
        attr_name = f"ah_attr_{ah_name}"

        grh_params = ""
        if self.ah_attr_params.get("is_global") == "1":
            grh_params = f"""
        .grh = {{
            .dgid = {{.raw = {{0}}}},
            .flow_label = {self.ah_attr_params.get("flow_label", "0")},
            .sgid_index = {self.ah_attr_params.get("sgid_index", "0")},
            .hop_limit = {self.ah_attr_params.get("hop_limit", "0")},
            .traffic_class = {self.ah_attr_params.get("traffic_class", "0")},
        }},"""

        return f"""
    /* ibv_create_ah */
    struct ibv_ah_attr {attr_name} = {{
        {grh_params}
        .dlid = {self.ah_attr_params.get("dlid", "0")},
        .sl = {self.ah_attr_params.get("sl", "0")},
        .src_path_bits = {self.ah_attr_params.get("src_path_bits", "0")},
        .static_rate = {self.ah_attr_params.get("static_rate", "0")},
        .is_global = {self.ah_attr_params.get("is_global", "0")},
        .port_num = {self.ah_attr_params.get("port_num", "0")},
    }};
    struct ibv_ah *{ah_name} = ibv_create_ah({pd_name}, &{attr_name});
    if (!{ah_name}) {{
        fprintf(stderr, "Failed to create AH\\n");
        return -1;
    }}
"""

class CreateAHFromWC(VerbCall):
    def __init__(self, pd_addr: str, wc_addr: str, grh_addr: str, port_num: int):
        self.pd_addr = pd_addr
        self.wc_addr = wc_addr
        self.grh_addr = grh_addr
        self.port_num = port_num

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
    struct ibv_ah *ah;
    ah = ibv_create_ah_from_wc({pd_name}, &{wc_name}, &{grh_name}, {port_num});
    if (!ah) {{
        fprintf(stderr, "Failed to create AH from work completion\\n");
        return -1;
    }}
"""

class CreateCompChannel(VerbCall):
    def __init__(self, channel_addr: str):
        self.channel_addr = channel_addr

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

class IbvCreateCQ(VerbCall):
    def __init__(self, context: str, cqe: int, cq_context: str = "NULL",
                 channel: str = "NULL", comp_vector: int = 0, cq_addr: str = "unknown"):
        self.context = context
        self.cqe = cqe
        self.cq_context = cq_context
        self.channel = channel
        self.comp_vector = comp_vector
        self.cq_addr = cq_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        context = kv.get("context", ctx.ib_ctx)
        cqe = int(kv.get("cqe", 32))
        cq_context = kv.get("cq_context", "NULL")
        channel = kv.get("channel", "NULL")
        comp_vector = int(kv.get("comp_vector", 0))
        cq_addr = kv.get("cq", "unknown")
        ctx.alloc_cq(cq_addr)
        return cls(context=context, cqe=cqe, cq_context=cq_context,
                   channel=channel, comp_vector=comp_vector, cq_addr=cq_addr)

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = ctx.get_cq(self.cq_addr)
        return f"""
    /* ibv_create_cq */
    {cq_name} = ibv_create_cq({self.context}, {self.cqe}, 
                              {self.cq_context}, {self.channel}, 
                              {self.comp_vector});
    if (!{cq_name}) {{
        fprintf(stderr, "Failed to create completion queue\\n");
        return -1;
    }}
"""

class CreateCQEx(VerbCall):
    def __init__(self, cq_addr: str, cqe: int, wc_flags: int, comp_vector: int = 0, channel: Optional[str] = None, comp_mask: int = 0, flags: int = 0, parent_domain: Optional[str] = None, ctx: CodeGenContext = None):
        self.cq_addr = cq_addr
        self.cqe = cqe
        self.wc_flags = wc_flags
        self.comp_vector = comp_vector
        self.channel = channel or "NULL"
        self.comp_mask = comp_mask
        self.flags = flags
        self.parent_domain = parent_domain or "NULL"
        if ctx:
            ctx.alloc_cq(cq_addr)  # Register the CQ address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq = kv.get("cq", "unknown")
        cqe = int(kv.get("cqe", 1))
        wc_flags = int(kv.get("wc_flags", 0))
        comp_vector = int(kv.get("comp_vector", 0))
        channel = kv.get("channel")
        comp_mask = int(kv.get("comp_mask", 0))
        flags = int(kv.get("flags", 0))
        parent_domain = kv.get("parent_domain")
        return cls(cq_addr=cq, cqe=cqe, wc_flags=wc_flags, comp_vector=comp_vector, channel=channel, comp_mask=comp_mask, flags=flags, parent_domain=parent_domain, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = ctx.get_cq(self.cq_addr)
        return f"""
    /* ibv_create_cq_ex */
    struct ibv_cq_init_attr_ex cq_attr_ex;
    memset(&cq_attr_ex, 0, sizeof(cq_attr_ex));
    cq_attr_ex.cqe = {self.cqe};
    cq_attr_ex.cq_context = NULL; /* No specific context */
    cq_attr_ex.channel = {self.channel};
    cq_attr_ex.comp_vector = {self.comp_vector};
    cq_attr_ex.wc_flags = {self.wc_flags};
    cq_attr_ex.comp_mask = {self.comp_mask};
    cq_attr_ex.flags = {self.flags};
    cq_attr_ex.parent_domain = {self.parent_domain};

    {cq_name} = ibv_create_cq_ex({ctx.ib_ctx}, &cq_attr_ex);
    if (!{cq_name}) {{
        fprintf(stderr, "Failed to create extended completion queue\\n");
        return -1;
    }}
"""

class CreateFlow(VerbCall):
    def __init__(self, qp_addr: str, flow_attr: dict):
        self.qp_addr = qp_addr
        self.flow_attr = flow_attr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        # Convert flow attributes from the trace into a dict
        flow_attr = {
            "comp_mask": kv.get("comp_mask", "0"),
            "type": kv.get("type", "IBV_FLOW_ATTR_NORMAL"),
            "size": kv.get("size", "sizeof(flow_attr)"),
            "priority": kv.get("priority", "0"),
            "num_of_specs": kv.get("num_of_specs", "0"),
            "port": kv.get("port", "1"),
            "flags": kv.get("flags", "0"),
            # Additional specs should be parsed as needed
        }
        ctx.use_qp(qp)  # Ensure the QP is used before generating code
        return cls(qp_addr=qp, flow_attr=flow_attr)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        attr_name = f"flow_attr_{qp_name.replace('qp[', '').replace(']', '')}"
        flow_attr_lines = "\n    ".join(
            f".{key} = {value}," for key, value in self.flow_attr.items()
        )
        return f"""
    /* ibv_create_flow */
    struct raw_eth_flow_attr {attr_name} = {{
        .attr = {{
            {flow_attr_lines}
        }},
        /* Add additional flow specs here as needed */
    }};
    struct ibv_flow *flow = ibv_create_flow({qp_name}, (struct ibv_flow_attr *)&{attr_name});
    if (!flow) {{
        fprintf(stderr, "Failed to create flow\\n");
        return -1;
    }}
"""

class CreateQP(VerbCall):
    """Create a Queue Pair (QP) using the given attributes."""
    def __init__(self, pd_addr="pd[0]", qp_addr="unknown", cq_addr="cq[0]", qp_type="IBV_QPT_RC", cap_params=None, ctx=None):
        self.pd_addr = pd_addr
        self.qp_addr = qp_addr
        self.cq_addr = cq_addr  # Completion queue address, used for code generation
        self.qp_type = qp_type
        self.cap_params = cap_params or {}
        ctx.alloc_qp(self.qp_addr)

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cap_keys = {"max_send_wr", "max_recv_wr", "max_send_sge", "max_recv_sge", "max_inline_data"}
        cap_params = {k: kv[k] for k in cap_keys if k in kv}
        pd = kv.get("pd", "pd[0]")
        qp = kv.get("qp", "unknown")
        cq = kv.get("cq", "cq[0]")  # Default CQ address
        
        return cls(pd_addr=pd, qp_addr=qp, cq_addr=cq, qp_type="IBV_QPT_RC", cap_params=cap_params, ctx=ctx)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        pd_name = ctx.get_pd(self.pd_addr)
        cq_name = ctx.get_cq(self.cq_addr)
        cap = self.cap_params
        cap_lines = "\n    ".join(
            f"{qp_name}_init_attr.cap.{k} = {v};" for k, v in cap.items()
        )
        return f"""
    /* ibv_create_qp */
    struct ibv_qp_init_attr {qp_name}_init_attr = {{0}};
    {qp_name}_init_attr.qp_context = NULL;
    {qp_name}_init_attr.send_cq = {cq_name};
    {qp_name}_init_attr.recv_cq = {cq_name};
    {qp_name}_init_attr.srq = NULL;
    {qp_name}_init_attr.qp_type = {self.qp_type};
    {cap_lines}
    {qp_name} = ibv_create_qp({pd_name}, &{qp_name}_init_attr);
    if (!{qp_name}) {{
        fprintf(stderr, "Failed to create QP\\n");
        return -1;
    }}
"""

class CreateQPEx(VerbCall):
    def __init__(self, ctx: CodeGenContext, qp_addr: str, pd_addr: str, send_cq_addr: str,
                 recv_cq_addr: str, srq_addr: Optional[str], qp_type: str = "IBV_QPT_RC", 
                 cap_params: Optional[Dict[str, int]] = None, comp_mask: int = 0,
                 create_flags: int = 0):
        self.qp_addr = qp_addr
        self.pd_addr = pd_addr
        self.send_cq_addr = send_cq_addr
        self.recv_cq_addr = recv_cq_addr
        self.srq_addr = srq_addr
        self.qp_type = qp_type
        self.cap_params = cap_params or {}
        self.comp_mask = comp_mask
        self.create_flags = create_flags
        ctx.alloc_qp(qp_addr)  # Register the QP in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        pd = kv.get("pd", "pd[0]")
        send_cq = kv.get("send_cq", "cq[0]")
        recv_cq = kv.get("recv_cq", "cq[0]")
        srq = kv.get("srq", None)
        cap_keys = {"max_send_wr", "max_recv_wr", "max_send_sge", "max_recv_sge", "max_inline_data"}
        cap_params = {k: int(kv[k]) for k in cap_keys if k in kv}
        qp_type = kv.get("qp_type", "IBV_QPT_RC")
        comp_mask = int(kv.get("comp_mask", "0"))
        create_flags = int(kv.get("create_flags", "0"))
        return cls(ctx, qp, pd, send_cq, recv_cq, srq, qp_type, cap_params, comp_mask, create_flags)
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        pd_name = ctx.get_pd(self.pd_addr)
        send_cq_name = ctx.get_cq(self.send_cq_addr)
        recv_cq_name = ctx.get_cq(self.recv_cq_addr)
        srq_name = ctx.get_srq(self.srq_addr) if self.srq_addr else "NULL"
        attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
        attr_name = f"attr_ex{attr_suffix}"
        cap = self.cap_params
        cap_lines = "\n    ".join(
            f"{attr_name}.cap.{k} = {v};" for k, v in cap.items()
        )
        return f"""
    /* ibv_create_qp_ex */
    struct ibv_qp_init_attr_ex {attr_name} = {{}};
    {attr_name}.qp_context = NULL;
    {attr_name}.send_cq = {send_cq_name};
    {attr_name}.recv_cq = {recv_cq_name};
    {attr_name}.srq = {srq_name};
    {attr_name}.qp_type = {self.qp_type};
    {attr_name}.comp_mask = {self.comp_mask};
    {attr_name}.create_flags = {self.create_flags};
    {cap_lines}
    {qp_name} = ibv_create_qp_ex({ctx.ib_ctx}, &{attr_name});
    if (!{qp_name}) {{
        fprintf(stderr, "Failed to create QP\\n");
        return -1;
    }}
"""

class CreateRWQIndTable(VerbCall):
    def __init__(self, context_addr: str, log_ind_tbl_size: int = 0, ind_tbl_addrs: list = []):
        self.context_addr = context_addr
        self.log_ind_tbl_size = log_ind_tbl_size
        self.ind_tbl_addrs = ind_tbl_addrs or []

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        context = kv.get("context", "unknown")
        ctx.use_context(context)
        log_size = int(kv.get("log_ind_tbl_size", 0))
        ind_tbl_addrs = kv.get("ind_tbl", "").split()
        return cls(context_addr=context, log_ind_tbl_size=log_size, ind_tbl_addrs=ind_tbl_addrs)

    def generate_c(self, ctx: CodeGenContext) -> str:
        context_name = ctx.get_context(self.context_addr)
        ind_tbl_name = f"ind_tbl[{len(self.ind_tbl_addrs)}]"
        init_attr_name = f"init_attr_{self.context_addr}"

        ind_tbl_entries = ", ".join(f"wq[{i}]" for i in range(len(self.ind_tbl_addrs)))
        init_attr_struct = f"""
    struct ibv_rwq_ind_table_init_attr {init_attr_name};
    {init_attr_name}.log_ind_tbl_size = {self.log_ind_tbl_size};
    {init_attr_name}.ind_tbl = {ind_tbl_name};
    {init_attr_name}.comp_mask = 0; // Comp mask can be modified based on requirements
"""

        return f"""
    /* ibv_create_rwq_ind_table */
    struct ibv_rwq_ind_table *rwq_ind_table;
    struct ibv_wq *{ind_tbl_name}[] = {{{ind_tbl_entries}}};
    {init_attr_struct}
    rwq_ind_table = ibv_create_rwq_ind_table({context_name}, &{init_attr_name});
    if (!rwq_ind_table) {{
        fprintf(stderr, "Failed to create RWQ indirection table\\n");
        return -1;
    }}
"""

class CreateSRQ(VerbCall):
    """Create a shared receive queue (SRQ)"""

    def __init__(self, pd_addr: str, srq_addr: str, srq_attr_params: Optional[Dict[str, int]] = None, ctx: CodeGenContext = None):
        self.pd_addr = pd_addr
        self.srq_addr = srq_addr
        self.srq_attr_params = srq_attr_params or {
            "max_wr": 32,
            "max_sge": 1,
            "srq_limit": 0
        }
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
        
        attr_name = f"srq_init_attr_{srq_name.replace('srq', '').replace('[', '').replace(']', '')}"
        cap_lines = ", ".join(
            f"{k} = {v}" for k, v in self.srq_attr_params.items()
        )

        return f"""
    /* ibv_create_srq */
    struct ibv_srq_init_attr {attr_name} = {{
        .srq_context = NULL,
        .attr = {{ {cap_lines} }}
    }};
    {srq_name} = ibv_create_srq({pd_name}, &{attr_name});
    if (!{srq_name}) {{
        fprintf(stderr, "Failed to create SRQ\\n");
        return -1;
    }}
"""

class CreateSRQEx(VerbCall):
    def __init__(self, srq_addr: str, pd_addr: str, cq_addr: str, srq_type: str = "IBV_SRQT_BASIC", max_wr: int = 10, max_sge: int = 1, srq_limit: int = 0, ctx = None):
        self.srq_addr = srq_addr
        self.pd_addr = pd_addr
        self.cq_addr = cq_addr
        self.srq_type = srq_type
        self.max_wr = max_wr
        self.max_sge = max_sge
        self.srq_limit = srq_limit
        ctx.alloc_srq(srq_addr)  # Register the SRQ address in the context

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        return cls(
            srq_addr=kv.get("srq", "unknown"),
            pd_addr=kv.get("pd", "unknown"),
            cq_addr=kv.get("cq", "unknown"),
            srq_type=kv.get("srq_type", "IBV_SRQT_BASIC"),
            max_wr=int(kv.get("max_wr", 10)),
            max_sge=int(kv.get("max_sge", 1)),
            srq_limit=int(kv.get("srq_limit", 0)),
            ctx=ctx
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        srq_name = ctx.get_srq(self.srq_addr)
        pd_name = ctx.get_pd(self.pd_addr)
        cq_name = ctx.get_cq(self.cq_addr)
        srq_init_attr_ex = f"srq_init_attr_ex_{srq_name.replace('srq[', '').replace(']', '')}"

        return f"""
    /* ibv_create_srq_ex */
    struct ibv_srq_init_attr_ex {srq_init_attr_ex} = {{0}};
    {srq_init_attr_ex}.srq_context = NULL;
    {srq_init_attr_ex}.attr.max_wr = {self.max_wr};
    {srq_init_attr_ex}.attr.max_sge = {self.max_sge};
    {srq_init_attr_ex}.attr.srq_limit = {self.srq_limit};
    {srq_init_attr_ex}.srq_type = {self.srq_type};
    {srq_init_attr_ex}.pd = {pd_name};
    {srq_init_attr_ex}.cq = {cq_name};
    {srq_name} = ibv_create_srq_ex({ctx.ib_ctx}, &{srq_init_attr_ex});
    if (!{srq_name}) {{
        fprintf(stderr, "Failed to create SRQ\\n");
        return -1;
    }}
"""

# Register the created VerbCall with VERB_FACTORY
VERB_FACTORY["ibv_create_srq_ex"] = CreateSRQEx.from_trace

class CreateWQ(VerbCall):
    def __init__(self, wq_addr: str, pd_addr: str, cq_addr: str, wq_type: str = "IBV_WQT_RQ", max_wr: int = 1, max_sge: int = 1, comp_mask: int = 0, create_flags: int = 0):
        self.wq_addr = wq_addr
        self.pd_addr = pd_addr
        self.cq_addr = cq_addr
        self.wq_type = wq_type
        self.max_wr = max_wr
        self.max_sge = max_sge
        self.comp_mask = comp_mask
        self.create_flags = create_flags

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        wq = kv.get("wq", "unknown")
        pd = kv.get("pd", "unknown")
        cq = kv.get("cq", "unknown")
        return cls(
            wq_addr=wq,
            pd_addr=pd,
            cq_addr=cq,
            wq_type=kv.get("wq_type", "IBV_WQT_RQ"),
            max_wr=int(kv.get("max_wr", 1)),
            max_sge=int(kv.get("max_sge", 1)),
            comp_mask=int(kv.get("comp_mask", 0)),
            create_flags=int(kv.get("create_flags", 0))
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        wq_name = ctx.alloc_wq(self.wq_addr)
        pd_name = ctx.get_pd(self.pd_addr)
        cq_name = ctx.get_cq(self.cq_addr)
        attr_name = f"wq_init_attr_{wq_name.replace('wq[', '').replace(']', '')}"
        return f"""
    /* ibv_create_wq */
    struct ibv_wq_init_attr {attr_name} = {{0}};
    {attr_name}.wq_context = NULL;
    {attr_name}.wq_type = {self.wq_type};
    {attr_name}.max_wr = {self.max_wr};
    {attr_name}.max_sge = {self.max_sge};
    {attr_name}.pd = {pd_name};
    {attr_name}.cq = {cq_name};
    {attr_name}.comp_mask = {self.comp_mask};
    {attr_name}.create_flags = {self.create_flags};
    {wq_name} = ibv_create_wq({ctx.ib_ctx}, &{attr_name});
    if (!{wq_name}) {{
        fprintf(stderr, "Failed to create Work Queue\\n");
        return -1;
    }}
"""
# Mapping verb -> constructor
VERB_FACTORY.update({
    "ibv_create_wq": CreateWQ.from_trace
})

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
    int result = ibv_dealloc_pd({pd_name});
    if (result != 0) {{
        fprintf(stderr, "Failed to deallocate PD: errno %d\\n", result);
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

# Mapping verb -> constructor (extend the existing mapping)
VERB_FACTORY.update({
    "ibv_dealloc_td": DeallocTD.from_trace
})

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
    int ret = ibv_dereg_mr({mr_name});
    if (ret) {{
        fprintf(stderr, "Failed to deregister MR\\n");
        return ret;
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
    int rc_detach = ibv_detach_mcast({qp_name}, &{self.gid}, {self.lid});
    if (rc_detach) {{
        fprintf(stderr, "Failed to detach multicast group with rc: %d\\n", rc_detach);
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

class FlowActionESP(VerbCall):
    def __init__(self, ctx: str = "ctx", esp_params: Dict[str, any] = {}):
        self.ctx = ctx
        self.esp_params = esp_params
    
    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        esp_params = {
            "esp_attr": kv.get("esp_attr"),
            "keymat_proto": kv.get("keymat_proto"),
            "keymat_len": kv.get("keymat_len"),
            "keymat_ptr": kv.get("keymat_ptr"),
            "replay_proto": kv.get("replay_proto"),
            "replay_len": kv.get("replay_len"),
            "replay_ptr": kv.get("replay_ptr"),
            "esp_encap": kv.get("esp_encap"),
            "comp_mask": kv.get("comp_mask"),
            "esn": kv.get("esn")
        }
        return cls(ctx=ctx.ib_ctx, esp_params=esp_params)
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        esp_var = "esp_params"
        esp_lines = "\n    ".join(
            f"{esp_var}.{key} = {value};" for key, value in self.esp_params.items()
        )
        
        return f"""
    struct ibv_flow_action_esp {esp_var};
    memset(&{esp_var}, 0, sizeof({esp_var}));
    {esp_lines}
    struct ibv_flow_action *esp_action = ibv_create_flow_action_esp({self.ctx}, &{esp_var});
    if (!esp_action) {{
        fprintf(stderr, "Failed to create ESP flow action\\n");
        return -1;
    }}
"""

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

# Add this function to VERB_FACTORY for mapping
VERB_FACTORY["ibv_free_dm"] = FreeDM.from_trace

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

    def __init__(self, device="dev_list[0]"):
        self.device = device

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        device = kv.get("device", "dev_list[0]")
        return cls(device=device)

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_get_device_guid */
    __be64 guid = ibv_get_device_guid({self.device});
    printf("Device GUID: %llx\\n", (unsigned long long)be64toh(guid));
"""

class GetDeviceIndex(VerbCall):
    """Retrieve the device index for the specified IB device."""
    
    def __init__(self, device_name: str):
        self.device_name = device_name

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        device_name = kv.get("device", "unknown")
        ctx.use_device(device_name)  # Register the device in the context
        return cls(device_name=device_name)

    def generate_c(self, ctx: CodeGenContext) -> str:
        device = ctx.get_device(self.device_name)
        index_var = f"device_index_{self.device_name}"
        return f"""
    /* Retrieve IB device index */
    int {index_var} = ibv_get_device_index({device});
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

class GetDeviceName(VerbCall):
    def __init__(self, device: str = "dev_list[0]"):
        self.device = device

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        device = kv.get("device", "dev_list[0]")
        return cls(device=device)

    def generate_c(self, ctx: CodeGenContext) -> str:
        dev_name = f"device_name"
        return f"""
    /* ibv_get_device_name */
    const char *{dev_name} = ibv_get_device_name({self.device});
    if (!{dev_name}) {{
        fprintf(stderr, "Failed to get device name\\n");
        return -1;
    }} else {{
        printf("Device name: %s\\n", {dev_name});
    }}
"""

class GetPKeyIndex(VerbCall):
    def __init__(self, port_num: int, pkey: int):
        self.port_num = port_num
        self.pkey = pkey

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        port_num = int(kv.get("port_num", 1))
        pkey = int(kv.get("pkey", 0))
        return cls(port_num=port_num, pkey=pkey)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = ctx.ib_ctx
        return f"""
    /* ibv_get_pkey_index */
    int pkey_index;
    if ((pkey_index = ibv_get_pkey_index({ib_ctx}, {self.port_num}, {self.pkey})) < 0) {{
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
        return f"""
    /* ibv_get_srq_num */
    uint32_t {self.srq_num_var};
    if (ibv_get_srq_num({srq_name}, &{self.srq_num_var})) {{
        fprintf(stderr, "Failed to get SRQ number\\n");
        return -1;
    }}
"""

class ImportDevice(VerbCall):
    def __init__(self, cmd_fd: int):
        self.cmd_fd = cmd_fd

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cmd_fd = int(kv.get("cmd_fd", "-1"))  # Default to -1 if not found
        return cls(cmd_fd=cmd_fd)

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_import_device */
    ctx = ibv_import_device({self.cmd_fd});
    if (!ctx) {{
        fprintf(stderr, "Failed to import device\\n");
        return -1;
    }}
"""

class ImportDM(VerbCall):
    def __init__(self, dm_handle: int):
        self.dm_handle = dm_handle

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        dm_handle = int(kv.get("dm_handle", "0"))
        return cls(dm_handle=dm_handle)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = ctx.ib_ctx
        return f"""
    /* ibv_import_dm */
    struct ibv_dm *dm = ibv_import_dm({ib_ctx}, {self.dm_handle});
    if (!dm) {{
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

    def __init__(self, rkey: str):
        self.rkey = rkey

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        rkey = kv.get("rkey", "unknown")
        return cls(rkey=rkey)

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_inc_rkey */
    uint32_t new_rkey = ibv_inc_rkey({self.rkey});
    fprintf(stdout, "Old RKey: %u, New RKey: %u\\n", {self.rkey}, new_rkey);
"""

# Add the new verb to the VERB_FACTORY
VERB_FACTORY["ibv_inc_rkey"] = IncRKey.from_trace

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

    def __init__(self):
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        return cls()

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* Check if fork support is initialized */
    enum ibv_fork_status fork_status = ibv_is_fork_initialized();
    switch (fork_status) {{
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

VERB_FACTORY["ibv_memcpy_to_dm"] = MemcpyToDM.from_trace

class ModifyCQ(VerbCall):
    """Modify a Completion Queue (CQ) attributes.
    
    This verb modifies a CQ with new moderation attributes 
    like number of completions per event and period in microseconds.
    The `attr_mask` field in `ibv_modify_cq_attr` specifies which 
    attributes to modify.
    """

    def __init__(self, cq_addr: str, cq_count: int, cq_period: int, attr_mask: int):
        self.cq_addr = cq_addr
        self.cq_count = cq_count
        self.cq_period = cq_period
        self.attr_mask = attr_mask

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq = kv.get("cq", "unknown")
        ctx.use_cq(cq)
        return cls(
            cq_addr=cq,
            cq_count=int(kv.get("cq_count", 1)),
            cq_period=int(kv.get("cq_period", 0)),
            attr_mask=int(kv.get("attr_mask", 0))
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = ctx.get_cq(self.cq_addr)
        attr_name = f"attr_modify_cq_{cq_name.replace('cq[', '').replace(']', '')}"
        return f"""
    /* ibv_modify_cq */
    struct ibv_modify_cq_attr {attr_name} = {{0}};
    {attr_name}.attr_mask = {self.attr_mask};
    {attr_name}.moderate.cq_count = {self.cq_count};
    {attr_name}.moderate.cq_period = {self.cq_period};
    int modify_cq_result = ibv_modify_cq({cq_name}, &{attr_name});
    if (modify_cq_result) {{
        fprintf(stderr, "Failed to modify CQ\\n");
        return modify_cq_result;
    }}
"""

class IbvModifyQP(VerbCall):
    def __init__(self, qp_addr: str, attr_mask: int, attr_values: Dict[str, str]):
        self.qp_addr = qp_addr
        self.attr_mask = attr_mask
        self.attr_values = attr_values  # Dictionary containing ibv_qp_attr values.

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        attr_mask = int(kv.get("attr_mask", "0"))
        attr_values = {k: kv[k] for k in kv if k not in {"qp", "attr_mask"}}
        ctx.use_qp(qp)  # Ensure the QP is used before generating code
        return cls(qp_addr=qp, attr_mask=attr_mask, attr_values=attr_values)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
        attr_name = f"attr_modify{attr_suffix}"
        attr_lines = "\n    ".join(f"{attr_name}.{k} = {v};" for k, v in self.attr_values.items())
        
        return f"""
    /* ibv_modify_qp */
    struct ibv_qp_attr {attr_name} = {{0}};
    {attr_lines}
    if (ibv_modify_qp({qp_name}, &{attr_name}, {self.attr_mask}) != 0) {{
        fprintf(stderr, "Failed to modify QP\\n");
        return -1;
    }}
"""

class ModifyQPRateLimit(VerbCall):
    """Modify the send rate limits attributes of a queue pair (QP)."""
    def __init__(self, qp_addr: str, rate_limit: int, max_burst_sz: int, typical_pkt_sz: int):
        self.qp_addr = qp_addr
        self.rate_limit = rate_limit
        self.max_burst_sz = max_burst_sz
        self.typical_pkt_sz = typical_pkt_sz

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        rate_limit = int(kv.get("rate_limit", 0))
        max_burst_sz = int(kv.get("max_burst_sz", 0))
        typical_pkt_sz = int(kv.get("typical_pkt_sz", 0))
        ctx.use_qp(qp)  # Ensure the QP is used before generating code
        return cls(qp_addr=qp, rate_limit=rate_limit, max_burst_sz=max_burst_sz, typical_pkt_sz=typical_pkt_sz)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        attr_suffix = "_" + qp_name.replace("qp[", "").replace("]", "")  # e.g., "_0" for qp[0]
        attr_name = f"attr_rate_limit{attr_suffix}"
        return f"""
    /* ibv_modify_qp_rate_limit */
    struct ibv_qp_rate_limit_attr {attr_name} = {{
        .rate_limit = {self.rate_limit},
        .max_burst_sz = {self.max_burst_sz},
        .typical_pkt_sz = {self.typical_pkt_sz}
    }};
    int ret = ibv_modify_qp_rate_limit({qp_name}, &{attr_name});
    if (ret) {{
        fprintf(stderr, "Failed to modify QP rate limit\\n");
        return -1;
    }}
"""

class ModifySRQ(VerbCall):
    def __init__(self, srq_addr: str, max_wr: int, srq_limit: int, srq_attr_mask: int):
        self.srq_addr = srq_addr
        self.max_wr = max_wr
        self.srq_limit = srq_limit
        self.srq_attr_mask = srq_attr_mask

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        srq = kv.get("srq", "unknown")
        max_wr = int(kv.get("max_wr", "0"))
        srq_limit = int(kv.get("srq_limit", "0"))
        srq_attr_mask = int(kv.get("srq_attr_mask", "0"))
        ctx.use_srq(srq)  # Ensure the SRQ is used before generating code
        return cls(srq_addr=srq, max_wr=max_wr, srq_limit=srq_limit, srq_attr_mask=srq_attr_mask)

    def generate_c(self, ctx: CodeGenContext) -> str:
        srq_name = ctx.get_srq(self.srq_addr)
        attr_name = f"srq_attr_{srq_name.replace('srq[', '').replace(']', '')}"
        return f"""
    /* ibv_modify_srq */
    struct ibv_srq_attr {attr_name} = {{0}};
    {attr_name}.max_wr = {self.max_wr};
    {attr_name}.srq_limit = {self.srq_limit};
    if (ibv_modify_srq({srq_name}, &{attr_name}, {self.srq_attr_mask})) {{
        fprintf(stderr, "Failed to modify SRQ\\n");
        return -1;
    }}
"""

class ModifyWQ(VerbCall):
    def __init__(self, wq_addr: str, attr_mask: int, wq_state: str, curr_wq_state: str, flags: int, flags_mask: int):
        self.wq_addr = wq_addr
        self.attr_mask = attr_mask
        self.wq_state = wq_state
        self.curr_wq_state = curr_wq_state
        self.flags = flags
        self.flags_mask = flags_mask

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        wq = kv.get("wq", "unknown")
        attr_mask = int(kv.get("attr_mask", 0))
        wq_state = kv.get("wq_state", "IBV_WQS_RDY")
        curr_wq_state = kv.get("curr_wq_state", "IBV_WQS_UNKNOWN")
        flags = int(kv.get("flags", 0))
        flags_mask = int(kv.get("flags_mask", 0))
        ctx.use_wq(wq)  # Ensure the WQ is used before generating code
        return cls(wq, attr_mask, wq_state, curr_wq_state, flags, flags_mask)
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        wq_name = ctx.get_wq(self.wq_addr)
        attr_suffix = "_" + wq_name.replace("wq[", "").replace("]", "")  # e.g., "_0" for wq[0]
        attr_name = f"wq_attr_modify{attr_suffix}"
        return f"""
    /* ibv_modify_wq */
    struct ibv_wq_attr {attr_name} = {{0}};
    {attr_name}.attr_mask = {self.attr_mask};
    {attr_name}.wq_state = {self.wq_state};
    {attr_name}.curr_wq_state = {self.curr_wq_state};
    {attr_name}.flags = {self.flags};
    {attr_name}.flags_mask = {self.flags_mask};
    if (ibv_modify_wq({wq_name}, &{attr_name})) {{
        fprintf(stderr, "Failed to modify WQ\\n");
        return -1;
    }}
"""

# Add to the VERB_FACTORY
VERB_FACTORY["ibv_modify_wq"] = ModifyWQ.from_trace

class OpenDevice(VerbCall):
    """Open an RDMA device and create a context for use."""
    
    def __init__(self):
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
    """Opens an existing Queue Pair associated with an extended protection domain xrcd."""

    def __init__(self, qp_num: int, qp_type: str):
        self.qp_num = qp_num
        self.qp_type = qp_type

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp_num = kv.get("qp_num", 0)
        qp_type = kv.get("qp_type", "IBV_QPT_RC")
        return cls(qp_num=qp_num, qp_type=qp_type)

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_open_qp */
    struct ibv_qp_open_attr open_attr = {{0}};
    open_attr.comp_mask = IBV_QP_OPEN_ATTR_MASK_XRCD;  // Example mask for valid fields
    open_attr.qp_num = {self.qp_num};
    open_attr.qp_type = {self.qp_type};

    struct ibv_qp *qp = ibv_open_qp({ctx.ib_ctx}, &open_attr);
    if (!qp) {{
        fprintf(stderr, "Failed to open QP\\n");
        return NULL;
    }}
"""

class OpenXRCD(VerbCall):
    """Open an XRC Domain and associate it with a device context."""

    def __init__(self, context: str, xrcd_init_attr: Dict[str, Union[int, str]]):
        self.context = context
        self.xrcd_init_attr = xrcd_init_attr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        context = kv.get("context", "ctx")
        xrcd_init_attr = {
            "comp_mask": int(kv.get("comp_mask", 0)),
            "fd": int(kv.get("fd", -1)),
            "oflags": int(kv.get("oflags", 0))
        }
        return cls(context=context, xrcd_init_attr=xrcd_init_attr)

    def generate_c(self, ctx: CodeGenContext) -> str:
        xrcd_name = f"xrcd{ctx.qp_cnt}"  # Example: xrcd0 for the first call
        return f"""
    /* ibv_open_xrcd */
    struct ibv_xrcd_init_attr xrcd_init_attr = {{0}};
    xrcd_init_attr.comp_mask = {self.xrcd_init_attr['comp_mask']};
    xrcd_init_attr.fd = {self.xrcd_init_attr['fd']};
    xrcd_init_attr.oflags = {self.xrcd_init_attr['oflags']};

    struct ibv_xrcd *{xrcd_name} = ibv_open_xrcd({self.context}, &xrcd_init_attr);
    if (!{xrcd_name}) {{
        fprintf(stderr, "Failed to open XRCD\\n");
        return -1;
    }}
"""

class PollCQ(VerbCall):
    def __init__(self, cq_addr: str, num_entries: int = 1):
        self.cq_addr = cq_addr
        self.num_entries = num_entries

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        cq = kv.get("cq", "unknown")
        num_entries = kv.get("num_entries", 1)
        ctx.use_cq(cq)
        return cls(cq_addr=cq, num_entries=int(num_entries))

    def generate_c(self, ctx: CodeGenContext) -> str:
        cq_name = ctx.get_cq(self.cq_addr)
        return f"""
    /* Poll completion queue */
    struct ibv_wc wc[{self.num_entries}];
    int num_completions = ibv_poll_cq({cq_name}, {self.num_entries}, wc);

    if (num_completions < 0) {{
        fprintf(stderr, "Error polling CQ\\n");
        return -1;
    }} else {{
        fprintf(stdout, "Found %d completions\\n", num_completions);
    }}

    for (int i = 0; i < num_completions; ++i) {{
        if (wc[i].status != IBV_WC_SUCCESS) {{
            fprintf(stderr, "Completion with error: %d, vendor error: %d\\n", wc[i].status, wc[i].vendor_err);
        }} else {{
            fprintf(stdout, "Completion successful, opcode: %d, byte_len: %d\\n", wc[i].opcode, wc[i].byte_len);
        }}
    }}
"""

class PostRecv(VerbCall):
    """Posts a list of work requests to a receive queue."""
    def __init__(self, qp_addr: str, mr_addr: str, wr_id: str = "0", length: str = "MSG_SIZE"):
        self.qp_addr = qp_addr
        self.mr_addr = mr_addr
        self.wr_id = wr_id
        self.length = length

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        mr = kv.get("mr", "MR")
        ctx.use_qp(qp)
        ctx.use_mr(mr)
        return cls(
            qp_addr=qp,
            mr_addr=mr,
            wr_id=kv.get("wr_id", "0"),
            length=kv.get("length", "MSG_SIZE")
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        qpn = qp_name.replace("qp[", "").replace("]", "")
        suffix = "_" + qp_name.replace("qp[", "").replace("]", "")
        rr = f"rr{suffix}"
        mr = ctx.get_mr(self.mr_addr)
        buf = "bufs[" + qpn + "]"
        sge = f"sge_recv{suffix}"
        bad_wr = f"bad_wr_recv{suffix}"

        return f"""
    /* ibv_post_recv */
    struct ibv_recv_wr {rr};
    struct ibv_sge {sge};
    struct ibv_recv_wr *{bad_wr} = NULL;

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

class PostSend(VerbCall):
    """Post Send Work Request to a Queue Pair's Send Queue.

    This class generates the code for the `ibv_post_send` verb, which posts a linked list of
    work requests (WRs) to the send queue of a specified Queue Pair (QP). 

    The `ibv_post_send` function interface:

class PostSRQOps(VerbCall):
    """Perform operations on a special shared receive queue (SRQ)."""

    def __init__(self, srq_addr: str, wr_id: str, opcode: str, flags: str, tm_params: Dict):
        self.srq_addr = srq_addr
        self.wr_id = wr_id
        self.opcode = opcode
        self.flags = flags
        self.tm_params = tm_params

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        srq = kv.get("srq", "unknown")
        ctx.use_srq(srq)  # Ensure the SRQ is used before generating code
        return cls(
            srq_addr=srq,
            wr_id=kv.get("wr_id", "0"),
            opcode=kv.get("opcode", "IBV_WR_TAG_ADD"),
            flags=kv.get("flags", "0"),
            tm_params={
                "unexpected_cnt": kv.get("unexpected_cnt", "0"),
                "handle": kv.get("handle", "0"),
                "recv_wr_id": kv.get("recv_wr_id", "0"),
                "sg_list": kv.get("sg_list", "NULL"),
                "num_sge": kv.get("num_sge", "0"),
                "tag": kv.get("tag", "0"),
                "mask": kv.get("mask", "0")
            }
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        srq_name = ctx.get_srq(self.srq_addr)
        op_wr_suffix = "_" + self.srq_addr.replace("srq[", "").replace("]", "")
        op_wr_name = f"op_wr{op_wr_suffix}"
        bad_op_name = f"bad_op{op_wr_suffix}"
        tm_params = self.tm_params

        return f"""
    /* ibv_post_srq_ops */
    struct ibv_ops_wr {op_wr_name};
    struct ibv_ops_wr *{bad_op_name};

    memset(&{op_wr_name}, 0, sizeof({op_wr_name}));
    {op_wr_name}.wr_id = {self.wr_id};
    {op_wr_name}.opcode = {self.opcode};
    {op_wr_name}.flags = {self.flags};
    {op_wr_name}.tm.unexpected_cnt = {tm_params.get("unexpected_cnt")};
    {op_wr_name}.tm.handle = {tm_params.get("handle")};
    {op_wr_name}.tm.add.recv_wr_id = {tm_params.get("recv_wr_id")};
    {op_wr_name}.tm.add.sg_list = {tm_params.get("sg_list")};
    {op_wr_name}.tm.add.num_sge = {tm_params.get("num_sge")};
    {op_wr_name}.tm.add.tag = {tm_params.get("tag")};
    {op_wr_name}.tm.add.mask = {tm_params.get("mask")};

    if (ibv_post_srq_ops({srq_name}, &{op_wr_name}, &{bad_op_name})) {{
        fprintf(stderr, "Failed to post srq ops\\n");
        return -1;
    }}
"""

class PostSRQRecv(VerbCall):
    def __init__(self, srq_addr: str, wr_id: str = "0", num_sge: int = 1, addr: str = "0", length: str = "0", lkey: str = "0"):
        self.srq_addr = srq_addr
        self.wr_id = wr_id
        self.num_sge = num_sge
        self.addr = addr
        self.length = length
        self.lkey = lkey

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        srq = kv.get("srq", "unknown")
        ctx.use_srq(srq)
        return cls(
            srq_addr=srq,
            wr_id=kv.get("wr_id", "0"),
            num_sge=int(kv.get("num_sge", "1")),
            addr=kv.get("addr", "0"),
            length=kv.get("length", "0"),
            lkey=kv.get("lkey", "0")
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        srq_name = ctx.get_srq(self.srq_addr)
        wr_suffix = "_" + srq_name.replace("srq[", "").replace("]", "")
        recv_wr_name = f"recv_wr{wr_suffix}"
        sge_name = f"sge_recv{wr_suffix}"
        bad_recv_wr_name = f"bad_recv_wr{wr_suffix}"

        return f"""
    /* ibv_post_srq_recv */
    struct ibv_recv_wr {recv_wr_name};
    struct ibv_sge {sge_name};
    struct ibv_recv_wr *{bad_recv_wr_name};

    memset(&{sge_name}, 0, sizeof({sge_name}));
    {sge_name}.addr = (uintptr_t){self.addr};
    {sge_name}.length = {self.length};
    {sge_name}.lkey = {self.lkey};

    memset(&{recv_wr_name}, 0, sizeof({recv_wr_name}));
    {recv_wr_name}.wr_id = {self.wr_id};
    {recv_wr_name}.num_sge = {self.num_sge};
    {recv_wr_name}.sg_list = &{sge_name};
    {recv_wr_name}.next = NULL;

    ibv_post_srq_recv({srq_name}, &{recv_wr_name}, &{bad_recv_wr_name});
"""

class QueryDeviceAttr(VerbCall):
    """Query the attributes of an RDMA device using its context."""

    def __init__(self):
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
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

class QueryDeviceExAttr(VerbCall):
    """Query extended device attributes using ibv_query_device_ex."""
    def __init__(self):
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        return cls()

    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = ctx.ib_ctx
        dev_attr_ex = "dev_attr_ex"  # Define a name for attribute struct
        input_struct = "input"
        return f"""
    /* ibv_query_device_ex */
    struct ibv_device_attr_ex {dev_attr_ex} = {{0}};
    struct ibv_query_device_ex_input {input_struct} = {{0}};
    {input_struct}.comp_mask = 0;  // Compatibility mask

    if (ibv_query_device_ex({ib_ctx}, &{input_struct}, &{dev_attr_ex})) {{
        fprintf(stderr, "Failed to query device extended attributes\\n");
        return -1;
    }}
"""

class QueryECE(VerbCall):
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
    /* ibv_query_ece */
    struct ibv_ece ece = {{0}};
    int query_result = ibv_query_ece({qp_name}, &ece);
    if (query_result) {{
        fprintf(stderr, "Failed to query ECE options, error code: %d\\n", query_result);
        return -1;
    }}
    fprintf(stdout, "ECE options for QP: vendor_id=0x%x, options=0x%x, comp_mask=0x%x\\n",
            ece.vendor_id, ece.options, ece.comp_mask);
"""

class QueryGID(VerbCall):
    def __init__(self, port_num: int = 1, index: int = 0):
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
    if (ibv_query_gid({ctx.ib_ctx}, {self.port_num}, {self.index}, &{gid_var})) {{
        fprintf(stderr, "Failed to query GID\\n");
        return -1;
    }}
"""

class QueryGIDEx(VerbCall):
    def __init__(self, port_num: int = 1, gid_index: int = 0, flags: int = 0):
        self.port_num = port_num
        self.gid_index = gid_index
        self.flags = flags

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        port_num = int(kv.get("port_num", 1))
        gid_index = int(kv.get("gid_index", 0))
        flags = int(kv.get("flags", 0))
        return cls(port_num=port_num, gid_index=gid_index, flags=flags)

    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = ctx.ib_ctx
        return f"""
    /* ibv_query_gid_ex */
    struct ibv_gid_entry entry = {{0}};
    int ret = ibv_query_gid_ex({ib_ctx}, {self.port_num}, {self.gid_index}, &entry, {self.flags});
    if (ret) {{
        fprintf(stderr, "Failed to query GID\\n");
        return -1;
    }}
"""

class QueryGIDTable(VerbCall):
    """Query GID table of a given RDMA device context."""
    def __init__(self, max_entries: int = 10):
        self.max_entries = max_entries

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        return cls(max_entries=int(kv.get("max_entries", 10)))

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_query_gid_table */
    struct ibv_gid_entry entries[{self.max_entries}];
    ssize_t num_gids = ibv_query_gid_table({ctx.ib_ctx}, entries, {self.max_entries}, 0);
    if (num_gids < 0) {{
        fprintf(stderr, "Failed to query GID table\\n");
        return -1;
    }} else {{
        fprintf(stdout, "Queried %zd GID table entries successfully\\n", num_gids);
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
        return f"""
    /* ibv_query_qp */
    struct ibv_qp_attr {attr_name} = {{0}};
    struct ibv_qp_init_attr {init_attr_name} = {{0}};
    int rc = ibv_query_qp({qp_name}, &{attr_name}, {self.attr_mask}, &{init_attr_name});
    if (rc) {{
        fprintf(stderr, "Failed to query QP\\n");
        return -1;
    }}
"""

class QueryQPDataInOrder(VerbCall):
    def __init__(self, qp_addr: str, opcode: str, flags: int):
        self.qp_addr = qp_addr
        self.opcode = opcode
        self.flags = flags

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        opcode = kv.get("opcode", "IBV_WR_SEND")
        flags = int(kv.get("flags", "0"), 0)
        ctx.use_qp(qp)  # Ensure the QP is used before generating code
        return cls(qp_addr=qp, opcode=opcode, flags=flags)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        return f"""
    /* ibv_query_qp_data_in_order */
    int in_order = ibv_query_qp_data_in_order({qp_name}, {self.opcode}, {self.flags});
    if (in_order < 0) {{
        fprintf(stderr, "Failed to query QP data in order\\n");
        return -1;
    }}
    printf("QP data in order query result: %d\\n", in_order);
"""

class QueryRTValuesEx(VerbCall):
    def __init__(self):
        pass

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        return cls()
    
    def generate_c(self, ctx: CodeGenContext) -> str:
        ib_ctx = ctx.ib_ctx
        return f"""
    /* ibv_query_rt_values_ex */
    struct ibv_values_ex values;
    values.comp_mask = IBV_VALUES_MASK_RAW_CLOCK; /* Request to query the raw clock */
    if (ibv_query_rt_values_ex({ib_ctx}, &values)) {{
        fprintf(stderr, "Failed to query real time values\\n");
        return -1;
    }}
    fprintf(stdout, "HW raw clock queried successfully\\n");
"""

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
        return f"""
    /* ibv_query_srq */
    struct ibv_srq_attr {attr_name};
    if (ibv_query_srq({srq_name}, &{attr_name})) {{
        fprintf(stderr, "Failed to query SRQ\\n");
        return -1;
    }}
    fprintf(stdout, "SRQ max_wr: %u, max_sge: %u, srq_limit: %u\\n", 
            {attr_name}.max_wr, {attr_name}.max_sge, {attr_name}.srq_limit);
"""

class RateToMbps(VerbCall):
    """Convert IB rate enumeration to Mbps."""
    def __init__(self, rate: str):
        self.rate = rate  # IB rate enumeration

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext = None):
        kv = _parse_kv(info)
        rate = kv.get("rate", "IBV_RATE_MAX")
        return cls(rate=rate)

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_rate_to_mbps */
    int mbps = ibv_rate_to_mbps({self.rate});
    printf("Rate: %s, Mbps: %d\\n", "{self.rate}", mbps);
"""

# Extend VERB_FACTORY with the ibv_rate_to_mbps mapping
VERB_FACTORY["ibv_rate_to_mbps"] = RateToMbps.from_trace

class IbvRateToMult(VerbCall):
    """Convert IB rate enumeration to multiplier of 2.5 Gbit/sec (IBV_RATE_TO_MULT)"""
    
    def __init__(self, rate: str):
        self.rate = rate

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        rate = kv.get("rate", "IBV_RATE_MAX")
        return cls(rate=rate)

    def generate_c(self, ctx: CodeGenContext) -> str:
        return f"""
    /* ibv_rate_to_mult */
    int multiplier = ibv_rate_to_mult({self.rate});
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

# Add to VERB_FACTORY
VERB_FACTORY.update({
    "ibv_req_notify_cq": ReqNotifyCQ.from_trace
})

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
    def __init__(self, qp_addr: str, vendor_id: int, options: int, comp_mask: int):
        self.qp_addr = qp_addr
        self.vendor_id = vendor_id
        self.options = options
        self.comp_mask = comp_mask

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp = kv.get("qp", "unknown")
        vendor_id = int(kv.get("vendor_id", "0"))
        options = int(kv.get("options", "0"))
        comp_mask = int(kv.get("comp_mask", "0"))
        ctx.use_qp(qp)  # Ensure the QP is used before generating code
        return cls(qp_addr=qp, vendor_id=vendor_id, options=options, comp_mask=comp_mask)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_name = ctx.get_qp(self.qp_addr)
        ece_name = f"ece_{self.qp_addr.replace('[', '_').replace(']', '')}"
        return f"""
    struct ibv_ece {ece_name} = {{
        .vendor_id = {self.vendor_id},
        .options = {self.options},
        .comp_mask = {self.comp_mask}
    }};
    if (ibv_set_ece({qp_name}, &{ece_name}) != 0) {{
        fprintf(stderr, "Failed to set ECE on QP {qp_name}\\n");
        return -1;
    }}
"""

# Add this to the VERB_FACTORY mapping
VERB_FACTORY["ibv_set_ece"] = SetECE.from_trace

class AbortWR(VerbCall):
    """Abort all prepared work requests since wr_start."""
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
        qp_ex_name = f"{qp_name}_ex"
        return f"""
    /* Abort all work requests */
    struct ibv_qp_ex *{qp_ex_name} = ibv_qp_to_qp_ex({qp_name});
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
        qp_ex_name = ctx.get_qp(self.qp_ex_addr)
        return f"""
    /* ibv_wr_complete */
    if (ibv_wr_complete({qp_ex_name}) != 0) {{
        fprintf(stderr, "Failed to complete work request\\n");
        return -1;
    }}
"""

class IbvWrStart(VerbCall):
    def __init__(self, qp_ex_addr: str):
        self.qp_ex_addr = qp_ex_addr

    @classmethod
    def from_trace(cls, info: str, ctx: CodeGenContext):
        kv = _parse_kv(info)
        qp_ex = kv.get("qp_ex", "unknown")
        ctx.use_qp(qp_ex)  # Ensure the QP extension is used before generating code
        return cls(qp_ex_addr=qp_ex)

    def generate_c(self, ctx: CodeGenContext) -> str:
        qp_ex_name = ctx.get_qp(self.qp_ex_addr)
        return f"""
    /* ibv_wr_start */
    ibv_wr_start({qp_ex_name});
"""

