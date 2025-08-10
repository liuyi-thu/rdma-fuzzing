import importlib
import os

# Import verbs (CreateQP/ModifyQP/etc.) from lib.verbs
verbs = importlib.import_module(os.environ.get("VERBS_MODULE", "lib.verbs"))

# Import the struct classes from their own modules
IbvQPInitAttr = importlib.import_module("lib.IbvQPInitAttr").IbvQPInitAttr
IbvQPCap = importlib.import_module("lib.IbvQPCap").IbvQPCap
IbvQPAttr = importlib.import_module("lib.IbvQPAttr").IbvQPAttr


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
        self._vars = []

    def alloc_variable(self, name, ty, init=None):
        self._vars.append((name, ty, init))


def assert_contains(s, token):
    assert token in s, f"expected {token!r} in generated code, got:\\n{s}"


def _setup_pd_cq(ctx):
    # Minimal PD and CQ so CreateQP dependencies exist
    pd = verbs.AllocPD(pd="pd0")
    pd.apply(ctx)
    cq = verbs.CreateCQ(cq="cq0", cqe=8, comp_vector=0)
    cq.apply(ctx)
    return pd, cq


def test_create_qp_minimal_apply_and_codegen():
    ctx = FakeCtx()
    _setup_pd_cq(ctx)

    init_attr = IbvQPInitAttr(
        qp_type="IBV_QPT_RC",
        send_cq="cq0",
        recv_cq="cq0",
        cap=IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1),
    )
    v = verbs.CreateQP(pd="pd0", qp="qp0", init_attr_obj=init_attr)

    v.apply(ctx)
    # Resource usage/creation checks
    assert ("use", "pd", "pd0") in ctx.tracker.calls
    assert any(c[0:3] == ("create", "qp", "qp0") for c in ctx.tracker.calls)

    code = v.generate_c(ctx)
    assert_contains(code, "ibv_create_qp")
    assert_contains(code, "qp0")
    assert_contains(code, "cq0")


def test_modify_qp_minimal_apply_and_codegen():
    ctx = FakeCtx()
    _setup_pd_cq(ctx)

    # Create a QP first
    init_attr = IbvQPInitAttr(
        qp_type="IBV_QPT_RC",
        send_cq="cq0",
        recv_cq="cq0",
        cap=IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1),
    )
    cq = verbs.CreateQP(pd="pd0", qp="qp0", init_attr_obj=init_attr)
    cq.apply(ctx)

    # Now modify it
    attr = IbvQPAttr(qp_state="IBV_QPS_RTS", cur_qp_state="IBV_QPS_INIT", path_mtu="IBV_MTU_1024")
    m = verbs.ModifyQP(qp="qp0", attr_obj=attr, attr_mask="IBV_QP_STATE")
    m.apply(ctx)
    assert {"type": "qp", "name": "qp0", "position": "qp"} in getattr(m, "required_resources", [])

    code = m.generate_c(ctx)
    assert_contains(code, "ibv_modify_qp")


def test_qp_cap_mutation_smoke():
    ctx = FakeCtx()
    _setup_pd_cq(ctx)

    cap = IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1)
    init_attr = IbvQPInitAttr(qp_type="IBV_QPT_RC", send_cq="cq0", recv_cq="cq0", cap=cap)
    v = verbs.CreateQP(pd="pd0", qp="qp0", init_attr_obj=init_attr)
    v.apply(ctx)

    # Mild, always-valid mutation: bump the numeric caps (keep >=1)
    cap.max_send_wr = max(1, int(getattr(cap, "max_send_wr", 1)) + 1)
    cap.max_recv_wr = max(1, int(getattr(cap, "max_recv_wr", 1)) + 1)
    cap.max_send_sge = max(1, int(getattr(cap, "max_send_sge", 1)) + 1)
    cap.max_recv_sge = max(1, int(getattr(cap, "max_recv_sge", 1)) + 1)

    # Ensure codegen still ok
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_create_qp")
