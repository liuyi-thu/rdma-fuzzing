# Class & `__init__` 索引（扫描目录：`lib`）

- 生成时间：2025-09-24 21:52:46
- 说明：如果类未定义 `__init__`，则使用父类默认构造函数。带 `@overload` 的构造将尽量显示对应实现；若只有 overload 也会列出。

## 📄 `IbvAHAttr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvAHAttr` | `__init__(self, grh = None, dlid = None, sl = None, src_path_bits = None, static_rate = None, is_global = None, port_num = None)` |  |
| `IbvGID` | `__init__(self, raw = None, src_var = None)` |  |
| `IbvGlobalRoute` | `__init__(self, dgid = None, flow_label = None, sgid_index = None, hop_limit = None, traffic_class = None)` |  |

## 📄 `IbvAllocDmAttr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvAllocDmAttr` | `__init__(self, length = None, log_align_req = None, comp_mask = None)` |  |

## 📄 `IbvCQInitAttrEx.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvCQInitAttrEx` | `__init__(self, cqe = None, cq_context = None, channel = None, comp_vector = None, wc_flags = None, comp_mask = None, flags = None, parent_domain = None)` |  |

## 📄 `IbvECE.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvECE` | `__init__(self, vendor_id = None, options = None, comp_mask = None)` |  |

## 📄 `IbvFlowAttr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvFlowAttr` | `__init__(self, comp_mask = None, type = None, size = None, priority = None, num_of_specs = None, port = None, flags = None)` |  |

## 📄 `IbvModerateCQ.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvModerateCQ` | `__init__(self, cq_count = None, cq_period = None)` |  |

## 📄 `IbvModifyCQAttr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvModifyCQAttr` | `__init__(self, attr_mask = None, moderate = None)` |  |

## 📄 `IbvMwBind.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvMwBind` | `__init__(self, wr_id = None, send_flags = None, bind_info = None)` |  |
| `IbvMwBindInfo` | `__init__(self, mr = None, addr = None, length = None, mw_access_flags = None)` |  |

## 📄 `IbvParentDomainInitAttr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvParentDomainInitAttr` | `__init__(self, pd = None, td = None, comp_mask = None, alloc = None, free = None, pd_context = None)` |  |

## 📄 `IbvQPAttr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvQPAttr` | `__init__(self, qp_state = None, cur_qp_state = None, path_mtu = None, path_mig_state = None, qkey = None, rq_psn = None, sq_psn = None, dest_qp_num = None, qp_access_flags = None, cap = None, ah_attr = None, alt_ah_attr = None, pkey_index = None, alt_pkey_index = None, en_sqd_async_notify = None, sq_draining = None, max_rd_atomic = None, max_dest_rd_atomic = None, min_rnr_timer = None, port_num = None, timeout = None, retry_cnt = None, rnr_retry = None, alt_port_num = None, alt_timeout = None, rate_limit = None)` |  |

## 📄 `IbvQPCap.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvQPCap` | `__init__(self, max_send_wr = None, max_recv_wr = None, max_send_sge = None, max_recv_sge = None, max_inline_data = None)` |  |

## 📄 `IbvQPInitAttr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvQPInitAttr` | `__init__(self, qp_context = None, send_cq = None, recv_cq = None, srq = None, cap = None, qp_type = None, sq_sig_all = None)` |  |

## 📄 `IbvQPInitAttrEx.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvQPInitAttrEx` | `__init__(self, qp_context = None, send_cq = None, recv_cq = None, srq = None, cap = None, qp_type = None, sq_sig_all = None, comp_mask = None, pd = None, xrcd = None, create_flags = None, max_tso_header = None, rwq_ind_tbl = None, rx_hash_conf = None, source_qpn = None, send_ops_flags = None)` |  |
| `IbvRxHashConf` | `__init__(self, rx_hash_function = None, rx_hash_key_len = None, rx_hash_key = None, rx_hash_fields_mask = None)` |  |

## 📄 `IbvQPOpenAttr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvQPOpenAttr` | `__init__(self, comp_mask = None, qp_num = None, xrcd = None, qp_context = None, qp_type = None)` |  |

## 📄 `IbvQPRateLimitAttr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvQPRateLimitAttr` | `__init__(self, rate_limit = None, max_burst_sz = None, typical_pkt_sz = None, comp_mask = None)` |  |

## 📄 `IbvRecvWR.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvRecvWR` | `__init__(self, wr_id = None, next_wr = None, sg_list = None, num_sge = None)` |  |

## 📄 `IbvSendWR.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvAtomicInfo` | `__init__(self, remote_addr = None, compare_add = None, swap = None, rkey = None)` |  |
| `IbvBindMwInfo` | `__init__(self, mw = None, rkey = None, bind_info = None)` |  |
| `IbvMwBindInfo` | `__init__(self, mr = None, addr = None, length = None, mw_access_flags = None)` |  |
| `IbvRdmaInfo` | `__init__(self, remote_addr = None, rkey = None, remote_mr = None)` |  |
| `IbvSendWR` | `__init__(self, wr_id = None, next_wr = None, sg_list = None, num_sge = None, opcode = None, send_flags = None, imm_data = None, invalidate_rkey = None, rdma = None, atomic = None, ud = None, xrc = None, bind_mw = None, tso = None)` |  |
| `IbvTsoInfo` | `__init__(self, hdr = None, hdr_sz = None, mss = None)` |  |
| `IbvUdInfo` | `__init__(self, ah = None, remote_qpn = None, remote_qkey = None)` |  |
| `IbvXrcInfo` | `__init__(self, remote_srqn = None)` |  |

## 📄 `IbvSge.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvSge` | `__init__(self, addr = None, length = None, lkey = None, mr = None)` |  |

## 📄 `IbvSrqAttr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvSrqAttr` | `__init__(self, max_wr = None, max_sge = None, srq_limit = None)` |  |

## 📄 `IbvSrqInitAttr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvSrqInitAttr` | `__init__(self, srq_context = None, attr = None)` |  |

## 📄 `IbvSrqInitAttrEx.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvSrqInitAttrEx` | `__init__(self, srq_context = None, attr = None, comp_mask = None, srq_type = None, pd = None, xrcd = None, cq = None, tm_cap = None)` |  |
| `IbvTMCap` | `__init__(self, max_num_tags = None, max_ops = None)` |  |

## 📄 `IbvTdInitAttr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvTdInitAttr` | `__init__(self, comp_mask = None)` |  |

## 📄 `IbvWQAttr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvWQAttr` | `__init__(self, attr_mask = None, wq_state = None, curr_wq_state = None, flags = None, flags_mask = None)` |  |

## 📄 `IbvWQInitAttr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvWQInitAttr` | `__init__(self, wq_context = None, wq_type = None, max_wr = None, max_sge = None, pd = None, cq = None, comp_mask = None, create_flags = None)` |  |

## 📄 `IbvXRCDInitAttr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `IbvXRCDInitAttr` | `__init__(self, comp_mask = None, fd = None, oflags = None)` |  |

## 📄 `attr.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `Attr` | `(no __init__ defined)` |  |

## 📄 `auto_run.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `ClientCapture` | `__init__(self, index: str)` |  |

## 📄 `codegen_context.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `CodeGenContext` | `__init__(self)` |  |

## 📄 `contracts.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `Contract` | `(no __init__ defined)` |  |
| `ContractError` | `(no __init__ defined)` |  |
| `ContractTable` | `__init__(self)` |  |
| `InstantiatedContract` | `(no __init__ defined)` |  |
| `ProduceSpec` | `(no __init__ defined)` |  |
| `RequireSpec` | `(no __init__ defined)` |  |
| `ResourceKey` | `(no __init__ defined)` |  |
| `ResourceRec` | `(no __init__ defined)` |  |
| `State` | `(no __init__ defined)` |  |
| `TransitionSpec` | `(no __init__ defined)` |  |

## 📄 `corpus.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `Corpus` | `__init__(self, root: str)` |  |

## 📄 `fingerprint.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `FingerprintManager` | `__init__(self)` |  |

## 📄 `fuzz_mutate.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `ContractAwareMutator` | `__init__(self, rng: random.Random | None = None, *, cfg: MutatorConfig | None = None)` |  |
| `ContractError` | `(no __init__ defined)` |  |
| `ErrKind` | `(no __init__ defined)` |  |
| `FakeCtx` | `__init__(self, ib_ctx = "ctx")` |  |
| `FakeCtx._DummyContracts` | `(no __init__ defined)` |  |
| `MutatorConfig` | `(no __init__ defined)` |  |
| `State` | `(no __init__ defined)` |  |
| `_FakeTracker` | `__init__(self)` |  |

## 📄 `objtracker.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `ObjectTracker` | `__init__(self)` |  |

## 📄 `scaffolds.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `ScaffoldBuilder` | `__init__(self)` |  |

## 📄 `value.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `BoolValue` | `__init__(self, value: bool = None, mutable: bool = True)` |  |
| `ConstantValue` | `__init__(self, value: str = None)` |  |
| `DeferredValue` | `__init__(self, key: str, c_type: str = "uint32_t", source: str = "runtime", default = None, by_id = None)` |  |
| `EnumValue` | `__init__(self, value: str = None, enum_type: str = None, mutable: bool = True)` |  |
| `FlagValue` | `__init__(self, value: int | None = None, flag_type = None, mutable = True)` |  |
| `IntValue` | `__init__(self, value: int | None = None, range: Range | list | None = None, step: int | None = None, rng: random.Random = None, mutable = True)` |  |
| `ListValue` | `__init__(self, value: list[Value] = None, factory = None, mutable: bool = True, on_after_mutate = None)` |  |
| `LocalResourceValue` | `__init__(self, value: str = None, resource_type: str = None, mutable: bool = True)` |  |
| `OptionalValue` | `__init__(self, value: Value = None, factory = None, mutable: bool = True)` |  |
| `Range` | `__init__(self, min_value, max_value)` |  |
| `ResourceValue` | `__init__(self, value: str = None, resource_type: str = None, mutable: bool = True)` |  |
| `Value` | `__init__(self, value, mutable: bool = True)` |  |

## 📄 `verbs.py`

| Class | `__init__` | Doc (first line) |
|---|---|---|
| `AbortWR` | `__init__(self, qp_ex: str = None)` |  |
| `AckCQEvents` | `__init__(self, cq: str | None = None, nevents: int | None = None)` |  |
| `AdviseMR` | `__init__(self, pd: str = None, advice: int = None, flags: int = None, sg_list: list[IbvSge] = [], num_sge: int = None, sg_var: str = None)` |  |
| `AllocDM` | `__init__(self, ctx_name: str = None, dm: str = None, attr_obj: IbvAllocDmAttr = None)` |  |
| `AllocMW` | `__init__(self, pd: str = None, mw: str = None, mw_type: str = None)` |  |
| `AllocNullMR` | `__init__(self, pd: str = None, mr: str = None)` |  |
| `AllocPD` | `__init__(self, pd: str = None)` |  |
| `AllocParentDomain` | `__init__(self, context = None, pd: str = None, parent_pd: str = None, attr_var: str = None, attr_obj: IbvParentDomainInitAttr = None)` |  |
| `AllocTD` | `__init__(self, td: str = None, attr_var: str = None, attr_obj: IbvTdInitAttr = None)` |  |
| `AttachMcast` | `__init__(self, qp: str = None, gid: str = None, lid: int = None)` |  |
| `BindMW` | `__init__(self, qp: str = None, mw: str = None, mw_bind_var: str = None, mw_bind_obj: IbvMwBind = None)` |  |
| `CloseDevice` | `__init__(self)` |  |
| `CloseXRCD` | `__init__(self, xrcd: str = None)` |  |
| `CreateAH` | `__init__(self, pd: str = None, attr_var: str = None, ah: str = None, attr_obj: IbvAHAttr = None)` |  |
| `CreateAHFromWC` | `__init__(self, pd: str = None, wc: str = None, grh: str = None, port_num: int = None, ah: str = None)` |  |
| `CreateCQ` | `__init__(self, cqe: int = 32, cq_context: str = "NULL", channel: str = "NULL", comp_vector: int = 0, cq: str = None)` |  |
| `CreateCQEx` | `__init__(self, ctx_name: str = None, cq_ex: str = None, cq_attr_var: str = None, cq_attr_obj: IbvCQInitAttrEx = None)` |  |
| `CreateCompChannel` | `__init__(self, channel: str = None)` |  |
| `CreateFlow` | `__init__(self, qp: str = None, flow: str = None, flow_attr_var: str = None, flow_attr_obj: IbvFlowAttr = None)` |  |
| `CreateQP` | `__init__(self, pd: str = None, qp: str = None, init_attr_obj: IbvQPInitAttr = None, remote_qp: str = None)` |  |
| `CreateQPEx` | `__init__(self, ctx_name: str = None, qp: str = None, qp_attr_var: str = None, qp_attr_obj: IbvQPInitAttrEx = None)` |  |
| `CreateSRQ` | `__init__(self, pd: str = None, srq: str = None, srq_init_obj: IbvSrqInitAttr = None)` |  |
| `CreateSRQEx` | `__init__(self, ctx_name: str = None, srq: str = None, srq_attr_var: str = None, srq_attr_obj: "IbvSrqInitAttrEx" = None)` |  |
| `CreateWQ` | `__init__(self, ctx_name: str = None, wq: str = None, wq_attr_var: str = None, wq_attr_obj: "IbvWQInitAttr" = None)` |  |
| `DeallocMW` | `__init__(self, mw: str = None)` |  |
| `DeallocPD` | `__init__(self, pd: str = None)` |  |
| `DeallocTD` | `__init__(self, td: str = None)` |  |
| `DeregMR` | `__init__(self, mr: str = None)` |  |
| `DestroyAH` | `__init__(self, ah: str = None)` |  |
| `DestroyCQ` | `__init__(self, cq: str = None)` |  |
| `DestroyCompChannel` | `__init__(self, channel: str = None)` |  |
| `DestroyFlow` | `__init__(self, flow: str = None)` |  |
| `DestroyQP` | `__init__(self, qp: str = None)` |  |
| `DestroySRQ` | `__init__(self, srq: str = None)` |  |
| `DestroyWQ` | `__init__(self, wq: str = None)` |  |
| `DetachMcast` | `__init__(self, qp: str = None, gid: str = None, lid: int = None)` |  |
| `ForkInit` | `__init__(self)` |  |
| `FreeDM` | `__init__(self, dm: str = None)` |  |
| `FreeDeviceList` | `__init__(self, dev_list: str = None)` |  |
| `GetDeviceGUID` | `__init__(self, device: str = None, output: str = None)` |  |
| `GetDeviceIndex` | `__init__(self, device_name: str = None, output: str = None)` |  |
| `GetDeviceList` | `__init__(self, dev_list: str = "dev_list")` |  |
| `GetPKeyIndex` | `__init__(self, port_num: int = None, pkey: int = None, output: str = None)` |  |
| `GetSRQNum` | `__init__(self, srq: str = None, srq_num_var: str = None)` |  |
| `ImportDM` | `__init__(self, dm_handle: int = None, dm: str = None)` |  |
| `ImportMR` | `__init__(self, pd: str = None, mr_handle: int = None, mr: str = None)` |  |
| `ImportPD` | `__init__(self, pd: str = None, pd_handle: int = None)` |  |
| `MemcpyFromDM` | `__init__(self, host: str = None, dm: str = None, dm_offset: int = None, length: int = None)` |  |
| `MemcpyToDM` | `__init__(self, dm: str = None, dm_offset: int = None, host: str = None, length: int = None)` |  |
| `ModifyCQ` | `__init__(self, cq: str = None, attr_obj: IbvModifyCQAttr = None, attr_var: str = None)` |  |
| `ModifyQP` | `__init__(self, qp: str = None, attr_obj: IbvQPAttr = None, attr_mask: str = None)` |  |
| `ModifyQPRateLimit` | `__init__(self, qp: str = None, attr_var: str = None, attr_obj: "IbvQPRateLimitAttr" = None)` |  |
| `ModifySRQ` | `__init__(self, srq: str = None, attr_var: str = None, attr_obj: IbvSrqAttr = None, attr_mask: int = 0)` |  |
| `ModifyWQ` | `__init__(self, wq: str = None, attr_var: str = None, attr_obj: "IbvWQAttr" = None)` |  |
| `OpenDevice` | `__init__(self, device: str = None, ctx_name: str = None)` |  |
| `OpenQP` | `__init__(self, ctx_var = None, qp: str = None, attr_var: str = None, attr_obj: IbvQPOpenAttr = None)` |  |
| `OpenXRCD` | `__init__(self, ctx_var: str = None, xrcd: str = None, attr_var: str = None, attr_obj: IbvXRCDInitAttr = None)` |  |
| `PollCQ` | `__init__(self, cq: str = None)` |  |
| `PostRecv` | `__init__(self, qp: str = None, wr_obj: IbvRecvWR = None, wr_var: str = None, bad_wr_var: str = None)` |  |
| `PostSRQRecv` | `__init__(self, srq: str = None, wr_obj: IbvRecvWR = None, wr_var: str = None, bad_wr_var: str = None)` |  |
| `PostSend` | `__init__(self, qp: str = None, wr_obj: IbvSendWR = None, wr_var = None, bad_wr_var = None)` |  |
| `QueryDeviceAttr` | `__init__(self, output: str = None)` |  |
| `QueryDeviceEx` | `__init__(self, ctx_var: str = None, attr_var: str = None, comp_mask: int = None, input_var: str = None)` |  |
| `QueryECE` | `__init__(self, qp: str = None, output: str = None)` |  |
| `QueryGID` | `__init__(self, port_num: int = None, index: int = None, gid_var: str = None)` |  |
| `QueryGIDEx` | `__init__(self, port_num: int = None, gid_index: int = None, flags: int = None, output: str = None)` |  |
| `QueryGIDTable` | `__init__(self, max_entries: int = None, output: str = None)` |  |
| `QueryPKey` | `__init__(self, port_num: int = None, index: int = None, pkey: str = None)` |  |
| `QueryPortAttr` | `__init__(self, port_num: int = None, port_attr: str = None)` |  |
| `QueryQP` | `__init__(self, qp: str = None, attr_mask: str = None)` |  |
| `QuerySRQ` | `__init__(self, srq: str = None)` |  |
| `ReRegMR` | `__init__(self, mr: str = None, flags: int = None, pd: str | None = None, addr: str | None = None, length: int = 0, access: int = 0)` |  |
| `RegDmaBufMR` | `__init__(self, pd: str = None, mr: str = None, offset: int = None, length: int = None, iova: int = None, fd: int = None, access: int = None)` |  |
| `RegMR` | `__init__(self, pd: str = None, mr: str = None, addr: str = None, length: int = None, access: str = None)` |  |
| `RegMRIova` | `__init__(self, pd: str = None, mr: str = None, buf: str = None, length: int = None, iova: int = None, access: str = None)` |  |
| `ReqNotifyCQ` | `__init__(self, cq: str = None, solicited_only: int = None)` |  |
| `ResizeCQ` | `__init__(self, cq: str = None, cqe: int = None)` |  |
| `SetECE` | `__init__(self, qp: str = None, ece_obj: "IbvECE" = None, ece_var: str = None)` |  |
| `UtilityCall` | `__init__(self)` |  |
| `VerbCall` | `__init__(self)` |  |
| `WRComplete` | `__init__(self, qp_ex: str)` |  |
| `WrStart` | `__init__(self, qp_ex: str = None)` |  |
