import importlib
import os

# Ensure we import from user's project layout: lib.*
VERBS_MODULE = os.environ.get("VERBS_MODULE", "lib.verbs")
verbs = importlib.import_module(VERBS_MODULE)

from importlib import import_module

IbvFlowAttr = import_module("lib.IbvFlowAttr").IbvFlowAttr
IbvCQInitAttrEx = import_module("lib.IbvCQInitAttrEx").IbvCQInitAttrEx
IbvSrqInitAttrEx_mod = import_module("lib.IbvSrqInitAttrEx")
IbvSrqInitAttrEx = getattr(IbvSrqInitAttrEx_mod, "IbvSrqInitAttrEx")
IbvAHAttr = import_module("lib.IbvAHAttr").IbvAHAttr


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


def test_create_cq_ex_minimal_codegen():
    ctx = FakeCtx()
    attr = IbvCQInitAttrEx(cqe=8, comp_vector=0)  # other fields optional
    v = verbs.CreateCQEx(ctx_name="ctx", cq_ex="cqex0", cq_attr_var="cq_attr0", cq_attr_obj=attr)
    v.apply(ctx)
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_create_cq_ex")
    assert ("create", "cq_ex", "cqex0", {}) in ctx.tracker.calls or any(
        c[0:3] == ("create", "cq_ex", "cqex0") for c in ctx.tracker.calls
    )


def test_create_flow_minimal_codegen():
    ctx = FakeCtx()
    # Require a QP resource (we just reference it; tracker doesn't validate existence)
    flow_attr = IbvFlowAttr()  # all OptionalValue -> allow defaults
    v = verbs.CreateFlow(qp="qp0", flow="flow0", flow_attr_var="flow_attr0", flow_attr_obj=flow_attr)
    v.apply(ctx)
    assert {"type": "qp", "name": "qp0", "position": "qp"} in getattr(v, "required_resources", [])
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_create_flow")


def test_create_srq_ex_minimal_codegen():
    ctx = FakeCtx()
    srq_attr = IbvSrqInitAttrEx()  # defaults should be fine
    v = verbs.CreateSRQEx(ctx_name="ctx", srq="srq0", srq_attr_var="srq_attr0", srq_attr_obj=srq_attr)
    v.apply(ctx)
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_create_srq_ex")


def test_create_ah_minimal_codegen():
    ctx = FakeCtx()
    # Need a PD resource
    alloc = verbs.AllocPD(pd="pd0")
    alloc.apply(ctx)
    attr = IbvAHAttr()  # optional fields
    v = verbs.CreateAH(pd="pd0", attr_var="ah_attr0", ah="ah0", attr_obj=attr)
    v.apply(ctx)
    assert ("use", "pd", "pd0") in ctx.tracker.calls
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_create_ah")
