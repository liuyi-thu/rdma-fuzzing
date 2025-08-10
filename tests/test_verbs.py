import importlib
import os
import re

# Allow users to override the module name via env var (default: "verbs").
VERBS_MODULE = os.environ.get("VERBS_MODULE", "lib.verbs")

verbs = importlib.import_module(VERBS_MODULE)

# --- Test Helpers ---


class FakeTracker:
    def __init__(self):
        self.calls = []  # tuples like ("use","pd","pd0"), ("create","mr","mr0"), ("destroy","qp","qp0")

    def use(self, typ, name):
        self.calls.append(("use", typ, name))

    def create(self, typ, name, **kwargs):
        self.calls.append(("create", typ, name))

    def destroy(self, typ, name):
        self.calls.append(("destroy", typ, name))


class FakeCtx:
    def __init__(self, ib_ctx="ctx"):
        self.tracker = FakeTracker()
        self.ib_ctx = ib_ctx  # used by generate_c for some verbs
        self._vars = []

    # some generate_c paths may attempt to register variables
    def alloc_variable(self, name, ty):
        self._vars.append((name, ty))


# simple assert helper
def assert_contains(s, token):
    assert token in s, f"expected to find {token!r} in generated code:\n{s}"


# --- Unit Tests ---


def test_allocpd_apply_and_codegen():
    ctx = FakeCtx()
    v = verbs.AllocPD(pd="pd0")
    # Before apply
    assert hasattr(v, "MUTABLE_FIELDS")
    assert set(v.MUTABLE_FIELDS) == {"pd"}
    mp = v.get_mutable_params()
    assert set(mp.keys()) == {"pd"}

    v.apply(ctx)
    # alloc should be recorded
    assert ("create", "pd", "pd0") in ctx.tracker.calls
    # allocated_resources should include ("pd","pd0")
    assert ("pd", "pd0") in getattr(v, "allocated_resources", [])

    code = v.generate_c(ctx)
    assert_contains(code, "ibv_alloc_pd")
    assert_contains(code, "pd0")


def test_createcq_apply_and_codegen():
    ctx = FakeCtx()
    v = verbs.CreateCQ(cq="cq0", cqe=16, comp_vector=0)
    # MUTABLE_FIELDS present and sane
    assert set(v.get_mutable_params().keys()) >= {"cq", "cqe", "comp_vector"}

    v.apply(ctx)
    # track a new cq
    assert ("create", "cq", "cq0") in ctx.tracker.calls
    assert ("cq", "cq0") in getattr(v, "allocated_resources", [])

    code = v.generate_c(ctx)
    assert_contains(code, "ibv_create_cq")
    assert_contains(code, "cq0")
    # should reference ctx.ib_ctx via v.context.ib_ctx
    assert "ctx" in code


def test_regmr_apply_and_codegen():
    ctx = FakeCtx()
    v = verbs.RegMR(pd="pd0", mr="mr0", buf="buf", length=1024, flags="IBV_ACCESS_LOCAL_WRITE")
    # basic mutability exposure
    assert set(v.get_mutable_params().keys()) >= {"pd", "mr", "buf", "length", "flags"}

    v.apply(ctx)
    # uses pd and creates mr
    assert ("use", "pd", "pd0") in ctx.tracker.calls
    assert ("create", "mr", "mr0") in ctx.tracker.calls
    assert {"type": "pd", "name": "pd0", "position": "pd"} in getattr(v, "required_resources", [])
    assert ("mr", "mr0") in getattr(v, "allocated_resources", [])

    code = v.generate_c(ctx)
    assert_contains(code, "ibv_reg_mr")
    assert_contains(code, "mr0")
    assert_contains(code, "pd0")


def test_deregmr_apply_and_codegen():
    ctx = FakeCtx()
    v = verbs.DeregMR(mr="mr0")
    mp = v.get_mutable_params()
    assert set(mp.keys()) == {"mr"}

    v.apply(ctx)
    # deregistration should record mr required
    assert {"type": "mr", "name": "mr0", "position": "mr"} in getattr(v, "required_resources", [])

    code = v.generate_c(ctx)
    assert_contains(code, "ibv_dereg_mr")
    assert_contains(code, "mr0")


def test_reqnotifycq_apply_and_codegen():
    ctx = FakeCtx()
    v = verbs.ReqNotifyCQ(cq="cq0", solicited_only=1)
    assert set(v.get_mutable_params().keys()) == {"cq", "solicited_only"}

    v.apply(ctx)
    assert {"type": "cq", "name": "cq0", "position": "cq"} in getattr(v, "required_resources", [])

    code = v.generate_c(ctx)
    assert_contains(code, "ibv_req_notify_cq")
    assert_contains(code, "cq0")


def test_ackcqevents_apply_and_codegen():
    ctx = FakeCtx()
    v = verbs.AckCQEvents(cq="cq0", nevents=2)
    assert set(v.get_mutable_params().keys()) == {"cq", "nevents"}

    v.apply(ctx)
    # should register use of cq
    assert ("use", "cq", "cq0") in ctx.tracker.calls
    assert {"type": "cq", "name": "cq0", "position": "cq"} in getattr(v, "required_resources", [])

    code = v.generate_c(ctx)
    assert_contains(code, "ibv_ack_cq_events")
    assert_contains(code, "cq0")


def test_pollcq_apply_and_codegen():
    ctx = FakeCtx()
    v = verbs.PollCQ(cq="cq0")
    assert set(v.get_mutable_params().keys()) == {"cq"}

    v.apply(ctx)
    assert ("use", "cq", "cq0") in ctx.tracker.calls
    assert {"type": "cq", "name": "cq0", "position": "cq"} in getattr(v, "required_resources", [])

    code = v.generate_c(ctx)
    assert_contains(code, "ibv_poll_cq")
    assert_contains(code, "cq0")
