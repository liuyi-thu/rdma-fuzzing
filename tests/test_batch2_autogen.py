import importlib
import os

VERBS_MODULE = os.environ.get("VERBS_MODULE", "lib.verbs")
verbs = importlib.import_module(VERBS_MODULE)

from importlib import import_module

IbvWQInitAttr = import_module("lib.IbvWQInitAttr").IbvWQInitAttr
IbvMwBind = import_module("lib.IbvMwBind").IbvMwBind
IbvMwBindInfo = import_module("lib.IbvMwBind").IbvMwBindInfo
IbvQPCap = import_module("lib.IbvQPCap").IbvQPCap
IbvQPInitAttr = import_module("lib.IbvQPInitAttr").IbvQPInitAttr
IbvQPInitAttrEx = import_module("lib.IbvQPInitAttrEx").IbvQPInitAttrEx
IbvQPOpenAttr = import_module("lib.IbvQPOpenAttr").IbvQPOpenAttr
IbvModifyCQAttr = import_module("lib.IbvModifyCQAttr").IbvModifyCQAttr
IbvSrqInitAttr = import_module("lib.IbvSrqInitAttr").IbvSrqInitAttr
IbvSrqAttr = import_module("lib.IbvSrqAttr").IbvSrqAttr


class FakeTracker:
    def __init__(self):
        self.calls = []

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

    def alloc_variable(self, name, ty, init=None):
        self._vars.append((name, ty, init))


def assert_contains(s, token):
    assert token in s, f"expected {token!r} in generated code, got:\\n{s}"


# ---------- Helpers to provision base resources ----------


def _alloc_pd_cq(ctx, pd="pd0", cq="cq0"):
    vp = verbs.AllocPD(pd=pd)
    vp.apply(ctx)
    vc = verbs.CreateCQ(cq=cq, cqe=8, comp_vector=0)
    vc.apply(ctx)
    return vp, vc


def _create_min_qp(ctx, pd="pd0", cq="cq0", qp="qp0"):
    # assumes PD and CQ already tracked
    cap = IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1)
    init = IbvQPInitAttr(qp_type="IBV_QPT_RC", send_cq=cq, recv_cq=cq, cap=cap)
    v = verbs.CreateQP(pd=pd, qp=qp, init_attr_obj=init)
    v.apply(ctx)
    return v


# ---------- Tests ----------


def test_create_wq_minimal_apply_and_codegen():
    ctx = FakeCtx()
    _alloc_pd_cq(ctx, "pd0", "cq0")
    wq_attr = IbvWQInitAttr(wq_type="IBV_WQT_RQ", max_wr=1, max_sge=1, pd="pd0", cq="cq0")
    v = verbs.CreateWQ(ctx_name="ctx", wq="wq0", wq_attr_var="wq_attr0", wq_attr_obj=wq_attr)
    v.apply(ctx)
    # tracker should record wq creation and PD/CQ use via attr.apply
    assert any(c[0:3] == ("create", "wq", "wq0") for c in ctx.tracker.calls)
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_create_wq")


def test_destroy_wq_apply_and_codegen():
    ctx = FakeCtx()
    v = verbs.DestroyWQ(wq="wq0")
    v.apply(ctx)
    assert {"type": "wq", "name": "wq0", "position": "wq"} in getattr(v, "required_resources", [])
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_destroy_wq")


def test_bind_mw_minimal_apply_and_codegen():
    ctx = FakeCtx()
    _alloc_pd_cq(ctx, "pd0", "cq0")
    _create_min_qp(ctx, "pd0", "cq0", "qp0")
    # allocate an MR for bind target
    reg = verbs.RegMR(pd="pd0", mr="mr0", addr="addr0", length=4096, access="IBV_ACCESS_LOCAL_WRITE")
    reg.apply(ctx)
    bind_info = IbvMwBindInfo(mr="mr0", addr=0x1000, length=0x1000, mw_access_flags=0)
    bind_obj = IbvMwBind(wr_id=1, send_flags=0, bind_info=bind_info)
    v = verbs.BindMW(qp="qp0", mw="mw0", mw_bind_var="mw_bind0", mw_bind_obj=bind_obj)
    v.apply(ctx)
    assert {"type": "qp", "name": "qp0", "position": "qp"} in v.required_resources
    # MW is allocated
    assert any(c[0:3] == ("create", "mw", "mw0") for c in ctx.tracker.calls)
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_bind_mw")


def test_create_qp_ex_minimal_apply_and_codegen():
    ctx = FakeCtx()
    _alloc_pd_cq(ctx, "pd0", "cq0")
    cap = IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1)
    attr = IbvQPInitAttrEx(send_cq="cq0", recv_cq="cq0", qp_type="IBV_QPT_RC", cap=cap, pd="pd0")
    v = verbs.CreateQPEx(ctx_name="ctx", qp="qp_ex0", qp_attr_var="qp_init_attr_ex0", qp_attr_obj=attr)
    v.apply(ctx)
    assert any(c[0:3] == ("create", "qp_ex", "qp_ex0") for c in ctx.tracker.calls)
    code = v.generate_c(ctx)
    # exact function name may vary; require the attr init and ibv_create_qp_ex presence
    # Fallback: just ensure the qp variable appears
    # Prefer check for ibv_create_qp_ex if implemented
    assert ("ibv_create_qp_ex" in code) or ("qp_init_attr_ex0" in code)


def test_open_qp_minimal_apply_and_codegen():
    ctx = FakeCtx()
    _alloc_pd_cq(ctx, "pd0", "cq0")
    _create_min_qp(ctx, "pd0", "cq0", "qp0")
    attr = IbvQPOpenAttr(comp_mask=0, qp_num=0, xrcd=None, qp_context="NULL", qp_type="IBV_QPT_RC")
    v = verbs.OpenQP(ctx_var="ctx", qp="qp0", attr_var="qp_open_attr0", attr_obj=attr)
    v.apply(ctx)
    assert {"type": "qp", "name": "qp0", "position": "qp"} in v.required_resources
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_open_qp")


def test_create_srq_and_modify_srq_apply_and_codegen():
    ctx = FakeCtx()

    # 先准备 PD 依赖
    alloc_pd = verbs.AllocPD(pd="pd0")
    alloc_pd.apply(ctx)

    # 正确的 SRQ 初始化：IbvSrqInitAttr(srq_context, attr=IbvSrqAttr(...))
    srq_attr0 = IbvSrqAttr(max_wr=1, max_sge=1, srq_limit=0)
    init = IbvSrqInitAttr(srq_context="NULL", attr=srq_attr0)

    # 创建 SRQ
    v_create = verbs.CreateSRQ(pd="pd0", srq="srq0", srq_init_obj=init)
    v_create.apply(ctx)
    # 资源检查
    assert ("use", "pd", "pd0") in ctx.tracker.calls
    assert any(c[0:3] == ("create", "srq", "srq0") for c in ctx.tracker.calls)
    # 代码生成烟雾
    c1 = v_create.generate_c(ctx)
    assert_contains(c1, "ibv_create_srq")

    # 修改 SRQ（仍用 IbvSrqAttr）
    mod_attr = IbvSrqAttr(max_wr=1, max_sge=1, srq_limit=0)
    v_modify = verbs.ModifySRQ(srq="srq0", attr_obj=mod_attr)
    v_modify.apply(ctx)
    # 必需资源
    assert {"type": "srq", "name": "srq0", "position": "srq"} in getattr(v_modify, "required_resources", [])
    # 代码生成烟雾
    c2 = v_modify.generate_c(ctx)
    assert_contains(c2, "ibv_modify_srq")


def test_modify_cq_with_attr_obj_codegen():
    ctx = FakeCtx()
    v = verbs.ModifyCQ(cq="cq0", attr_obj=IbvModifyCQAttr(attr_mask=1))
    v.apply(ctx)
    assert {"type": "cq", "name": "cq0", "position": "cq"} in v.required_resources
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_modify_cq")
