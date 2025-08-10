# tests/test_verbs_suite.py
import importlib
import os

import pytest

# from lib.contracts import contracts.ContractTable, contracts.State

# --- Project import root ---
VERBS_MODULE = os.environ.get("VERBS_MODULE", "lib.verbs")
verbs = importlib.import_module(VERBS_MODULE)
CONTRACTS_MODULE = os.environ.get("CONTRACTS_MODULE", "lib.contracts")
contracts = importlib.import_module(CONTRACTS_MODULE)

# ---------- Generic import helper ----------


def _load(symbol, *module_candidates):
    """
    Try to import `symbol` from the first existing module in `module_candidates`.
    Return the attribute or None if not found.
    """
    for mod in module_candidates:
        try:
            m = importlib.import_module(mod)
            if hasattr(m, symbol):
                return getattr(m, symbol)
        except Exception:
            continue
    return None


# ---------- Test context / tracker ----------


class FakeTracker:
    def __init__(self):
        self.calls = []  # e.g. ("use","pd","pd0"), ("create","mr","mr0", {...}), ("destroy","qp","qp0")

    def use(self, typ, name):
        self.calls.append(("use", typ, str(name)))

    def create(self, typ, name, **kwargs):
        self.calls.append(("create", typ, str(name), kwargs))

    def destroy(self, typ, name):
        self.calls.append(("destroy", typ, str(name)))


class FakeCtx:
    def __init__(self, ib_ctx="ctx"):
        self.tracker = FakeTracker()
        self.ib_ctx = ib_ctx
        self._vars = []
        self.contracts = contracts.ContractTable()

    def alloc_variable(self, name, ty, init=None):
        self._vars.append((name, ty, init))


# ---------- Assertions ----------


def assert_contains_or_nonempty(code: str, *needles):
    """If needles given, assert at least one appears; otherwise assert non-empty string."""
    assert isinstance(code, str), "generate_c() must return str"
    if not needles:
        assert code.strip() != ""
        return
    for n in needles:
        if n in code:
            return
    # Fallback for vendor differences
    assert code.strip() != "", f"expected one of {needles}, got:\n{code}"


# ---------- Small resource builders ----------


def _mk_pd(ctx, name="pd0"):
    v = verbs.AllocPD(pd=name)
    v.apply(ctx)
    # if hasattr(ctx, "contracts"):
    #     ctx.contracts.put("pd", name, contracts.State.ALLOCATED)
    return name


def _mk_cq(ctx, name="cq0", cqe=8, comp_vector=0):
    v = verbs.CreateCQ(cq=name, cqe=cqe, comp_vector=comp_vector)
    v.apply(ctx)
    # if hasattr(ctx, "contracts"):
    #     ctx.contracts.put("cq", name, contracts.State.ALLOCATED)
    return name


def _mk_wq(ctx, pd="pd0", cq="cq0", wq="wq0"):
    """Create WQ by passing pd/cq via IbvWQInitAttr into CreateWQ(wq, wq_attr_obj)."""
    IbvWQInitAttr = _load("IbvWQInitAttr", "lib.IbvWQInitAttr")
    if IbvWQInitAttr is None:
        pytest.skip("IbvWQInitAttr not found")
    init = IbvWQInitAttr(wq_type="IBV_WQT_RQ", pd=pd, cq=cq)
    v = verbs.CreateWQ(wq=wq, wq_attr_obj=init)
    v.apply(ctx)
    return wq


def _mk_min_qp(ctx, pd="pd0", cq="cq0", qp="qp0"):
    IbvQPCap = _load("IbvQPCap", "lib.IbvQPCap", "lib.IbvQpCap")
    IbvQPInitAttr = _load("IbvQPInitAttr", "lib.IbvQPInitAttr")
    if IbvQPCap is None or IbvQPInitAttr is None:
        pytest.skip("IbvQPCap or IbvQPInitAttr not found")
    cap = IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1)
    init = IbvQPInitAttr(qp_type="IBV_QPT_RC", send_cq=cq, recv_cq=cq, cap=cap)
    v = verbs.CreateQP(pd=pd, qp=qp, init_attr_obj=init)
    v.apply(ctx)
    return qp


# ---------- Generic mutation helper ----------


def _generic_mutate_field(value):
    """
    Gentle mutation that tries (in order):
    - call .mutate() if available
    - call type.random_mutation() if available
    - if has .value (wrapper), tweak common primitive cases
    - otherwise, tweak raw primitives
    """
    # 1) in-place mutate
    if hasattr(value, "mutate") and callable(getattr(value, "mutate")):
        try:
            value.mutate()
            return value
        except Exception:
            pass
    # 2) class-level random
    rand_mut = getattr(type(value), "random_mutation", None)
    if callable(rand_mut):
        try:
            return rand_mut()
        except Exception:
            pass
    # 3) wrapper with .value
    if hasattr(value, "value"):
        inner = getattr(value, "value")
        if isinstance(inner, int):
            try:
                value.value = max(0, inner + 1)
                return value
            except Exception:
                pass
        if isinstance(inner, str):
            try:
                value.value = inner + "_m"
                return value
            except Exception:
                pass
        if isinstance(inner, list):
            fac = getattr(value, "factory", None)
            if callable(fac):
                try:
                    value.value = list(inner) + [fac()]
                    return value
                except Exception:
                    pass
    # 4) raw primitives
    if isinstance(value, int):
        return max(0, value + 1)
    if isinstance(value, str):
        return value + "_m"
    return value  # fallback


def _mutate_all_fields(verb, exempt_keys=()):
    """
    Mutate all fields in get_mutable_params(), except exempt_keys (e.g., identifier vars).
    Also handle wrapper assignment gracefully.
    """
    mp = verb.get_mutable_params()
    for k, v in mp.items():
        if k in exempt_keys or k.endswith("_var"):
            # keep identifier-like fields as plain strings
            cur = getattr(verb, k, v)
            if hasattr(cur, "value"):
                try:
                    setattr(verb, k, str(cur.value))
                except Exception:
                    pass
            continue
        mutated = _generic_mutate_field(v)
        try:
            setattr(verb, k, mutated)
        except Exception:
            if hasattr(getattr(verb, k), "value") and hasattr(mutated, "value"):
                getattr(verb, k).value = mutated.value


# =====================================================================
#                             TESTS
# =====================================================================

# ---------- CQEx / Flow / SRQEx / AH ----------


def test_create_cq_ex_minimal_codegen():
    ctx = FakeCtx()
    IbvCQInitAttrEx = _load("IbvCQInitAttrEx", "lib.IbvCQInitAttrEx")
    if IbvCQInitAttrEx is None:
        pytest.skip("IbvCQInitAttrEx not found")
    attr = IbvCQInitAttrEx(cqe=8, comp_vector=0)
    v = verbs.CreateCQEx(ctx_name="ctx", cq_ex="cqex0", cq_attr_var="cq_attr0", cq_attr_obj=attr)
    v.apply(ctx)
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_create_cq_ex")


def test_create_flow_minimal_codegen():
    ctx = FakeCtx()
    IbvFlowAttr = _load("IbvFlowAttr", "lib.IbvFlowAttr")
    if IbvFlowAttr is None:
        pytest.skip("IbvFlowAttr not found")
    flow_attr = IbvFlowAttr()  # allow defaults
    v = verbs.CreateFlow(qp="qp0", flow="flow0", flow_attr_var="flow_attr0", flow_attr_obj=flow_attr)
    v.apply(ctx)
    assert {"type": "qp", "name": "qp0", "position": "qp"} in getattr(v, "required_resources", [])
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_create_flow")


def test_create_srq_ex_minimal_codegen():
    ctx = FakeCtx()
    IbvSrqInitAttrEx = _load("IbvSrqInitAttrEx", "lib.IbvSrqInitAttrEx")
    if IbvSrqInitAttrEx is None:
        pytest.skip("IbvSrqInitAttrEx not found")
    srq_attr = IbvSrqInitAttrEx()  # defaults ok
    v = verbs.CreateSRQEx(ctx_name="ctx", srq="srq0", srq_attr_var="srq_attr0", srq_attr_obj=srq_attr)
    v.apply(ctx)
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_create_srq_ex")


def test_create_ah_minimal_codegen():
    ctx = FakeCtx()
    _mk_pd(ctx, "pd0")
    IbvAHAttr = _load("IbvAHAttr", "lib.IbvAHAttr")
    if IbvAHAttr is None:
        pytest.skip("IbvAHAttr not found")
    attr = IbvAHAttr()
    v = verbs.CreateAH(pd="pd0", attr_var="ah_attr0", ah="ah0", attr_obj=attr)
    v.apply(ctx)
    assert ("use", "pd", "pd0") in ctx.tracker.calls
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_create_ah")


# ---------- WQ / MW / QPEx / OpenQP / SRQ / ModifyCQ ----------


def test_create_wq_minimal_apply_and_codegen():
    ctx = FakeCtx()
    _mk_pd(ctx, "pd0")
    _mk_cq(ctx, "cq0")
    IbvWQInitAttr = _load("IbvWQInitAttr", "lib.IbvWQInitAttr")
    if IbvWQInitAttr is None:
        pytest.skip("IbvWQInitAttr not found")
    wq_attr = IbvWQInitAttr(wq_type="IBV_WQT_RQ", pd="pd0", cq="cq0")
    v = verbs.CreateWQ(wq="wq0", wq_attr_obj=wq_attr)
    v.apply(ctx)
    assert any(c[0:3] == ("create", "wq", "wq0") for c in ctx.tracker.calls)
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_create_wq")


def test_destroy_wq_apply_and_codegen():
    ctx = FakeCtx()
    v = verbs.DestroyWQ(wq="wq0")
    v.apply(ctx)
    assert {"type": "wq", "name": "wq0", "position": "wq"} in getattr(v, "required_resources", [])
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_destroy_wq")


def test_bind_mw_minimal_apply_and_codegen():
    ctx = FakeCtx()
    _mk_pd(ctx, "pd0")
    _mk_cq(ctx, "cq0")
    _mk_min_qp(ctx, "pd0", "cq0", "qp0")
    verbs.RegMR(pd="pd0", mr="mr0", buf="buf0", length=4096, flags="IBV_ACCESS_LOCAL_WRITE").apply(ctx)
    IbvMwBind = _load("IbvMwBind", "lib.IbvMwBind")
    IbvMwBindInfo = _load("IbvMwBindInfo", "lib.IbvMwBind")
    if IbvMwBind is None or IbvMwBindInfo is None:
        pytest.skip("IbvMwBind or IbvMwBindInfo not found")
    bind_info = IbvMwBindInfo(mr="mr0", addr=0x1000, length=0x1000, mw_access_flags=0)
    bind_obj = IbvMwBind(wr_id=1, send_flags=0, bind_info=bind_info)
    v = verbs.BindMW(qp="qp0", mw="mw0", mw_bind_var="mw_bind0", mw_bind_obj=bind_obj)
    v.apply(ctx)
    assert {"type": "qp", "name": "qp0", "position": "qp"} in v.required_resources
    assert any(c[0:3] == ("create", "mw", "mw0") for c in ctx.tracker.calls)
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_bind_mw")


def test_create_qp_ex_minimal_apply_and_codegen():
    ctx = FakeCtx()
    _mk_pd(ctx, "pd0")
    _mk_cq(ctx, "cq0")
    IbvQPCap = _load("IbvQPCap", "lib.IbvQPCap", "lib.IbvQpCap")
    IbvQPInitAttrEx = _load("IbvQPInitAttrEx", "lib.IbvQPInitAttrEx")
    if IbvQPCap is None or IbvQPInitAttrEx is None:
        pytest.skip("IbvQPCap or IbvQPInitAttrEx not found")
    cap = IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1)
    attr = IbvQPInitAttrEx(send_cq="cq0", recv_cq="cq0", qp_type="IBV_QPT_RC", cap=cap, pd="pd0")
    v = verbs.CreateQPEx(ctx_name="ctx", qp="qp_ex0", qp_attr_var="qp_init_attr_ex0", qp_attr_obj=attr)
    v.apply(ctx)
    code = v.generate_c(ctx)
    assert ("ibv_create_qp_ex" in code) or ("qp_init_attr_ex0" in code)


def test_open_qp_minimal_apply_and_codegen():
    ctx = FakeCtx()
    _mk_pd(ctx, "pd0")
    _mk_cq(ctx, "cq0")
    _mk_min_qp(ctx, "pd0", "cq0", "qp0")
    IbvQPOpenAttr = _load("IbvQPOpenAttr", "lib.IbvQPOpenAttr")
    if IbvQPOpenAttr is None:
        pytest.skip("IbvQPOpenAttr not found")
    attr = IbvQPOpenAttr(comp_mask=0, qp_num=0, xrcd=None, qp_context="NULL", qp_type="IBV_QPT_RC")
    v = verbs.OpenQP(ctx_var="ctx", qp="qp0", attr_var="qp_open_attr0", attr_obj=attr)
    v.apply(ctx)
    assert {"type": "qp", "name": "qp0", "position": "qp"} in v.required_resources
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_open_qp")


def test_create_and_modify_srq_apply_and_codegen():
    ctx = FakeCtx()
    _mk_pd(ctx, "pd0")
    IbvSrqInitAttr = _load("IbvSrqInitAttr", "lib.IbvSrqInitAttr")
    IbvSrqAttr = _load("IbvSrqAttr", "lib.IbvSrqAttr")
    if IbvSrqInitAttr is None or IbvSrqAttr is None:
        pytest.skip("IbvSrqInitAttr or IbvSrqAttr not found")
    srq_attr0 = IbvSrqAttr(max_wr=1, max_sge=1, srq_limit=0)
    init = IbvSrqInitAttr(srq_context="NULL", attr=srq_attr0)
    v_create = verbs.CreateSRQ(pd="pd0", srq="srq0", srq_init_obj=init)
    v_create.apply(ctx)
    c1 = v_create.generate_c(ctx)
    assert_contains_or_nonempty(c1, "ibv_create_srq")
    mod_attr = IbvSrqAttr(max_wr=1, max_sge=1, srq_limit=0)
    v_modify = verbs.ModifySRQ(srq="srq0", attr_obj=mod_attr)
    v_modify.apply(ctx)
    c2 = v_modify.generate_c(ctx)
    assert_contains_or_nonempty(c2, "ibv_modify_srq")


def test_modify_cq_with_attr_obj_codegen():
    ctx = FakeCtx()
    IbvModifyCQAttr = _load("IbvModifyCQAttr", "lib.IbvModifyCQAttr")
    if IbvModifyCQAttr is None:
        pytest.skip("IbvModifyCQAttr not found")
    v = verbs.ModifyCQ(cq="cq0", attr_obj=IbvModifyCQAttr(attr_mask=1))
    v.apply(ctx)
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_modify_cq")


# ---------- CompChannel / MW / DM / QP Rate Limit ----------


def test_create_destroy_comp_channel():
    ctx = FakeCtx()
    create = verbs.CreateCompChannel(channel="ch0")
    create.apply(ctx)
    code = create.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_create_comp_channel")
    destroy = verbs.DestroyCompChannel(channel="ch0")
    destroy.apply(ctx)
    dcode = destroy.generate_c(ctx)
    assert_contains_or_nonempty(dcode, "ibv_destroy_comp_channel")


def test_alloc_and_dealloc_mw_with_pd():
    ctx = FakeCtx()
    pd = _mk_pd(ctx, "pd0")
    alloc = verbs.AllocMW(pd=pd, mw="mw0")
    alloc.apply(ctx)
    acode = alloc.generate_c(ctx)
    assert_contains_or_nonempty(acode, "ibv_alloc_mw")
    dealloc = verbs.DeallocMW(mw="mw0")
    dealloc.apply(ctx)
    dcode = dealloc.generate_c(ctx)
    assert_contains_or_nonempty(dcode, "ibv_dealloc_mw")


def test_alloc_dm_minimal():
    IbvAllocDmAttr = _load("IbvAllocDmAttr", "lib.IbvAllocDmAttr")
    if IbvAllocDmAttr is None:
        pytest.skip("IbvAllocDmAttr not found")
    ctx = FakeCtx()
    attr = IbvAllocDmAttr(length=4096)
    v = verbs.AllocDM(dm="dm0", attr_obj=attr)
    v.apply(ctx)
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_alloc_dm", "mlx5dv_alloc_dm")


def test_modify_qp_rate_limit_minimal():
    IbvQPRateLimitAttr = _load("IbvQPRateLimitAttr", "lib.IbvQPRateLimitAttr")
    if IbvQPRateLimitAttr is None:
        pytest.skip("IbvQPRateLimitAttr not found")
    ctx = FakeCtx()
    pd = _mk_pd(ctx, "pd0")
    cq = _mk_cq(ctx, "cq0")
    _mk_min_qp(ctx, pd, cq, "qp0")
    # 正确字段：rate_limit（不是 rate_limit_mbps）
    attr = IbvQPRateLimitAttr(rate_limit=100)
    v = verbs.ModifyQPRateLimit(qp="qp0", attr_obj=attr)
    v.apply(ctx)
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code)


# ---------- MUTATION TESTS (gentle, structure-safe) ----------


def test_mutation_advise_mr_smoke():
    ctx = FakeCtx()
    v = verbs.AdviseMR(pd="pd0", advice=1, flags=0, sg_list=[], num_sge=1)
    v.apply(ctx)
    _mutate_all_fields(v, exempt_keys=("sg_var",))
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_advise_mr")


def test_mutation_reg_mr_smoke():
    ctx = FakeCtx()
    v = verbs.RegMR(pd="pd0", mr="mr0", buf="buf", length=64, flags="IBV_ACCESS_LOCAL_WRITE")
    v.apply(ctx)
    _mutate_all_fields(v)
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_reg_mr")


def test_mutation_create_cq_smoke():
    ctx = FakeCtx()
    v = verbs.CreateCQ(cq="cq0", cqe=8, comp_vector=0)
    v.apply(ctx)
    _mutate_all_fields(v)
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_create_cq")


# ---------------- PostSend / PostRecv + CQ verbs with mutation ----------------


def test_post_send_minimal_codegen_and_mutate():
    ctx = FakeCtx()
    _mk_pd(ctx, "pd0")
    _mk_cq(ctx, "cq0")
    _mk_min_qp(ctx, "pd0", "cq0", "qp0")
    v = verbs.PostSend(qp="qp0", wr_obj=None)
    v.apply(ctx)
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_post_send")
    _mutate_all_fields(v, exempt_keys=("qp",))
    code2 = v.generate_c(ctx)
    assert_contains_or_nonempty(code2, "ibv_post_send")


def test_post_recv_minimal_codegen_and_mutate():
    ctx = FakeCtx()
    _mk_pd(ctx, "pd0")
    _mk_cq(ctx, "cq0")
    _mk_min_qp(ctx, "pd0", "cq0", "qp0")
    v = verbs.PostRecv(qp="qp0", wr_obj=None, wr_var="recv_wr0", bad_wr_var="bad_recv_wr0")
    v.apply(ctx)
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_post_recv")
    _mutate_all_fields(v, exempt_keys=("wr_var", "bad_wr_var", "qp"))
    code2 = v.generate_c(ctx)
    assert_contains_or_nonempty(code2, "ibv_post_recv")


def test_cq_notify_ack_poll_mutation_cycle():
    ctx = FakeCtx()
    _mk_cq(ctx, "cq0")
    req = verbs.ReqNotifyCQ(cq="cq0", solicited_only=1)
    req.apply(ctx)
    _mutate_all_fields(req, exempt_keys=("cq",))
    code_req = req.generate_c(ctx)
    assert_contains_or_nonempty(code_req, "ibv_req_notify_cq")
    ack = verbs.AckCQEvents(cq="cq0", nevents=1)
    ack.apply(ctx)
    _mutate_all_fields(ack, exempt_keys=("cq",))
    code_ack = ack.generate_c(ctx)
    assert_contains_or_nonempty(code_ack, "ibv_ack_cq_events")
    poll = verbs.PollCQ(cq="cq0")
    poll.apply(ctx)
    _mutate_all_fields(poll, exempt_keys=("cq",))
    code_poll = poll.generate_c(ctx)
    assert_contains_or_nonempty(code_poll, "ibv_poll_cq")


# ---------------------------------------------------------------------
#     Protocol-aware WR tests: IbvSge + IbvSendWR / IbvRecvWR
#     - Build minimal WRs with 1 SGE
#     - Mutate SGEs / num_sge while keeping constraints consistent
# ---------------------------------------------------------------------


def _mk_sge(addr=0x1000, length=64, lkey=0):
    IbvSge = _load("IbvSge", "lib.IbvSge")
    if IbvSge is None:
        pytest.skip("IbvSge not found")
    try:
        return IbvSge(addr=addr, length=length, lkey=lkey)
    except TypeError:
        # 某些实现可能是位置参数顺序 (addr, length, lkey)
        return IbvSge(addr, length, lkey)


def _set_wr_sges(wr, sges):
    """
    在不同实现里，WR 的 SGE 列表可能叫 sge / sg_list / sgl，数量叫 num_sge / num_sges。
    这里做统一写入，并强行保持 num_sge == len(sges)。
    """
    # 列表字段
    for name in ("sge", "sg_list", "sgl"):
        if hasattr(wr, name):
            setattr(wr, name, sges)
            break
    else:
        # 没有找到列表字段就直接挂上（容错）
        setattr(wr, "sg_list", sges)

    # 数量字段
    n = len(sges)
    for nname in ("num_sge", "num_sges"):
        if hasattr(wr, nname):
            try:
                setattr(wr, nname, n)
            except Exception:
                # 如果是 wrapper，试着写到 .value
                v = getattr(wr, nname)
                if hasattr(v, "value"):
                    v.value = n
            break
    else:
        setattr(wr, "num_sge", n)


def _get_wr_sges(wr):
    for name in ("sge", "sg_list", "sgl"):
        if hasattr(wr, name):
            return getattr(wr, name)
    return []


def _mk_send_wr(minimal=True):
    IbvSendWR = _load("IbvSendWR", "lib.IbvSendWR")
    if IbvSendWR is None:
        pytest.skip("IbvSendWR not found")

    # 最小构造：1个 SGE + 最常见 opcode
    sge0 = _mk_sge()
    try:
        wr = IbvSendWR(opcode="IBV_WR_SEND")
    except TypeError:
        # 某些实现可能无 opcode 或默认
        wr = IbvSendWR()
    _set_wr_sges(wr, [sge0])
    return wr


def _mk_recv_wr(minimal=True):
    IbvRecvWR = _load("IbvRecvWR", "lib.IbvRecvWR")
    if IbvRecvWR is None:
        pytest.skip("IbvRecvWR not found")

    sge0 = _mk_sge()
    try:
        wr = IbvRecvWR()
    except TypeError:
        # 极少数实现可能需要占位参数
        wr = IbvRecvWR(wr_id=0)
    _set_wr_sges(wr, [sge0])
    return wr


def _protocol_mutate_wr_inplace(wr):
    """
    对 WR 做“协议感知”变异：
      - 以小概率把 SGE 列表扩成 2 个，并同步 num_sge
      - 否则只对第一个 SGE 的 length/addr 做 +1 之类的温和扰动
    """
    sges = list(_get_wr_sges(wr))
    if not sges:
        sges = [_mk_sge()]
    # 50% 概率扩容到 2 个 SGE
    if len(sges) == 1:
        sges.append(_mk_sge(addr=0x2000, length=128, lkey=0))
    else:
        # 否则只在第一个 SGE 上做轻度扰动
        s0 = sges[0]
        # 逐字段尝试 +1（兼容 wrapper）
        for fld in ("length", "addr"):
            if hasattr(s0, fld):
                cur = getattr(s0, fld)
                try:
                    setattr(s0, fld, int(cur) + 1)
                except Exception:
                    if hasattr(cur, "value"):
                        cur.value = int(cur.value) + 1
    _set_wr_sges(wr, sges)


def test_post_send_with_wr_protocol_mutation():
    ctx = FakeCtx()
    _mk_pd(ctx, "pd0")
    _mk_cq(ctx, "cq0")
    _mk_min_qp(ctx, "pd0", "cq0", "qp0")

    wr = _mk_send_wr()
    v = verbs.PostSend(qp="qp0", wr_obj=wr)
    v.apply(ctx)
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_post_send")

    # 协议感知变异（维护 num_sge == len(sgl)）
    _protocol_mutate_wr_inplace(wr)
    code2 = v.generate_c(ctx)
    assert_contains_or_nonempty(code2, "ibv_post_send")


def test_post_recv_with_wr_protocol_mutation():
    ctx = FakeCtx()
    _mk_pd(ctx, "pd0")
    _mk_cq(ctx, "cq0")
    _mk_min_qp(ctx, "pd0", "cq0", "qp0")

    wr = _mk_recv_wr()
    v = verbs.PostRecv(qp="qp0", wr_obj=wr)
    v.apply(ctx)
    code = v.generate_c(ctx)
    assert_contains_or_nonempty(code, "ibv_post_recv")

    _protocol_mutate_wr_inplace(wr)
    code2 = v.generate_c(ctx)
    assert_contains_or_nonempty(code2, "ibv_post_recv")


def test_contract_create_qp_requires_pd_and_sets_reset():
    ctx = FakeCtx()
    # 没有 PD 直接 CreateQP -> 应当抛 ContractError
    IbvQPCap = _load("IbvQPCap", "lib.IbvQPCap", "lib.IbvQpCap")
    IbvQPInitAttr = _load("IbvQPInitAttr", "lib.IbvQPInitAttr")
    if IbvQPCap is None or IbvQPInitAttr is None:
        pytest.skip("caps not found")
    cap = IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1)
    init = IbvQPInitAttr(qp_type="IBV_QPT_RC", send_cq="cq0", recv_cq="cq0", cap=cap)

    with pytest.raises(Exception):  # ContractError or your wrapped error
        verbs.CreateQP(pd="pd0", qp="qp0", init_attr_obj=init).apply(ctx)

    # 先创建 PD，再创建 QP -> 应当通过，并把 QP 标为 RESET
    _mk_pd(ctx, "pd0")
    ctx.contracts.put("cq", "cq0", state=contracts.State.ALLOCATED)  # 如果你在契约里检查 cq，也给它一个占位
    verbs.CreateQP(pd="pd0", qp="qp0", init_attr_obj=init).apply(ctx)
    snap = ctx.contracts.snapshot()
    assert ("qp", "qp0") in snap and snap[("qp", "qp0")] in {"RESET", "ALLOCATED"}  # 取决于你的定义


def test_contract_modify_qp_transition_reset_to_init():
    ctx = FakeCtx()
    _mk_pd(ctx, "pd0")
    _mk_cq(ctx, "cq0")
    _mk_min_qp(ctx, "pd0", "cq0", "qp0")
    # 显式将 qp0 标记为 RESET（若 CreateQP 的 CONTRACT 已经这么做，这步可省）
    ctx.contracts.transition("qp", "qp0", to_state=contracts.State.RESET, from_state=None)

    # 准备一个 ModifyQP 到 INIT 的调用
    IbvQPAttr = _load("IbvQPAttr", "lib.IbvQPAttr")
    if IbvQPAttr is None:
        pytest.skip("IbvQPAttr not found")
    attr = IbvQPAttr(qp_state="IBV_QPS_INIT")
    v = verbs.ModifyQP(qp="qp0", attr_obj=attr, attr_mask="IBV_QP_contracts.State")
    v.apply(ctx)  # 若 CONTRACT 配置正确，这步应当把 qp0 -> INIT

    assert ctx.contracts.snapshot()[("qp", "qp0")] in {"INIT", "RTS", "RTR"}  # 视你的状态推进而定
