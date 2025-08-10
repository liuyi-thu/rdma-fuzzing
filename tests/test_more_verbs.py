import importlib
import os

VERBS_MODULE = os.environ.get("VERBS_MODULE", "lib.verbs")
verbs = importlib.import_module(VERBS_MODULE)


class FakeTracker:
    def __init__(self):
        self.calls = []

    def use(self, typ, name):
        self.calls.append(("use", typ, name))

    def create(self, typ, name, **kwargs):
        self.calls.append(("create", typ, name, kwargs))

    def destroy(self, typ, name):
        self.calls.append(("destroy", typ, name))


class FakeCtx:
    def __init__(self, ib_ctx="ctx"):
        self.tracker = FakeTracker()
        self.ib_ctx = ib_ctx
        self.port_attr = "port_attr"
        self._vars = []

    def alloc_variable(self, name, ty, init=None):
        self._vars.append((name, ty, init))


def assert_contains(s, token):
    assert token in s, f"expected {token!r} in generated code, got:\\n{s}"


# ---------- AH / Flow / SRQ ----------


def test_create_destroy_ah_apply_and_codegen():
    ctx = FakeCtx()
    v = verbs.CreateAH(pd="pd0", attr_var="ah_attr0", ah="ah0", attr_obj=None)
    v.apply(ctx)
    assert ("use", "pd", "pd0") in ctx.tracker.calls
    assert ("create", "ah", "ah0", {}) in ctx.tracker.calls or any(
        x[0:3] == ("create", "ah", "ah0") for x in ctx.tracker.calls
    )
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_create_ah")

    d = verbs.DestroyAH(ah="ah0")
    d.apply(ctx)
    assert {"type": "ah", "name": "ah0", "position": "ah"} in getattr(d, "required_resources", [])
    dcode = d.generate_c(ctx)
    assert_contains(dcode, "ibv_destroy_ah")


def test_create_destroy_flow_apply_and_codegen():
    ctx = FakeCtx()
    v = verbs.CreateFlow(qp="qp0", flow="flow0", flow_attr_var="flow_attr0", flow_attr_obj=None)
    v.apply(ctx)
    assert ("use", "qp", "qp0") in ctx.tracker.calls
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_create_flow")

    d = verbs.DestroyFlow(flow="flow0")
    d.apply(ctx)
    assert {"type": "flow", "name": "flow0", "position": "flow"} in getattr(d, "required_resources", [])
    dcode = d.generate_c(ctx)
    assert_contains(dcode, "ibv_destroy_flow")


def test_create_destroy_srq_apply_and_codegen():
    ctx = FakeCtx()
    v = verbs.CreateSRQ(pd="pd0", srq="srq0", srq_init_obj=None)
    v.apply(ctx)
    assert ("use", "pd", "pd0") in ctx.tracker.calls
    assert any(c[0:3] == ("create", "srq", "srq0") for c in ctx.tracker.calls)
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_create_srq")

    d = verbs.DestroySRQ(srq="srq0")
    d.apply(ctx)
    assert {"type": "srq", "name": "srq0", "position": "srq"} in getattr(d, "required_resources", [])
    dcode = d.generate_c(ctx)
    assert_contains(dcode, "ibv_destroy_srq")


# ---------- Modify / Post ----------


def test_modify_cq_apply_and_codegen_smoke():
    ctx = FakeCtx()
    v = verbs.ModifyCQ(cq="cq0", attr_obj=None)
    v.apply(ctx)
    assert {"type": "cq", "name": "cq0", "position": "cq"} in getattr(v, "required_resources", [])
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_modify_cq")


def test_modify_qp_apply_only():
    ctx = FakeCtx()
    # attr_obj 需要 IbvQPAttr；这里仅测试 apply 的资源追踪，不做 codegen
    v = verbs.ModifyQP(qp="qp0", attr_obj=None, attr_mask="IBV_QP_STATE")
    v.apply(ctx)
    assert {"type": "qp", "name": "qp0", "position": "qp"} in getattr(v, "required_resources", [])


def test_post_send_apply_and_codegen_smoke():
    ctx = FakeCtx()
    v = verbs.PostSend(qp="qp0", wr_obj=None)  # 无 wr_obj 时只做最小 codegen 烟雾
    v.apply(ctx)
    assert {"type": "qp", "name": "qp0", "position": "qp"} in getattr(v, "required_resources", [])
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_post_send")


def test_post_recv_apply_and_codegen_smoke():
    ctx = FakeCtx()
    v = verbs.PostRecv(qp="qp0", wr_obj=None, wr_var="recv_wr0", bad_wr_var="bad_recv_wr0")
    v.apply(ctx)
    assert {"type": "qp", "name": "qp0", "position": "qp"} in getattr(v, "required_resources", [])
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_post_recv")


# ---------- Misc fetch/query ----------


def test_query_qp_and_port_apply_and_codegen():
    ctx = FakeCtx()
    v1 = verbs.QueryQP(qp="qp0")
    v1.apply(ctx)
    assert {"type": "qp", "name": "qp0", "position": "qp"} in getattr(v1, "required_resources", [])
    c1 = v1.generate_c(ctx)
    assert_contains(c1, "ibv_query_qp")

    # v2 = verbs.QueryPortAttr(ctx_name="ctx", port_num=1, attr_var="port_attr")
    v2 = verbs.QueryPortAttr(port_num=1)
    # QueryPortAttr may not require tracker calls; just codegen smoke
    c2 = v2.generate_c(ctx)
    assert_contains(c2, "ibv_query_port")


def test_attach_detach_mcast_apply_and_codegen():
    ctx = FakeCtx()
    v = verbs.AttachMcast(qp="qp0", gid="gid0", lid=1)
    v.apply(ctx)
    assert {"type": "qp", "name": "qp0", "position": "qp"} in getattr(v, "required_resources", [])
    c = v.generate_c(ctx)
    assert_contains(c, "ibv_attach_mcast")

    d = verbs.DetachMcast(qp="qp0", gid="gid0", lid=1)
    d.apply(ctx)
    assert {"type": "qp", "name": "qp0", "position": "qp"} in getattr(d, "required_resources", [])
    dc = d.generate_c(ctx)
    assert_contains(dc, "ibv_detach_mcast")
