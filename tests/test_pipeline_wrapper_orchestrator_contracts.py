import importlib
import random

import pytest

# ===== 你的工程模块 =====
verbs = importlib.import_module("lib.verbs")
contracts_mod = importlib.import_module("lib.contracts")
State = contracts_mod.State

# 可选：如果按我之前给的名字放了 mutator
try:
    mutate_mod = importlib.import_module("lib.fuzz_mutate")
    ContractAwareMutator = mutate_mod.ContractAwareMutator
except Exception:
    ContractAwareMutator = None

# 结构体类
IbvQPCap = importlib.import_module("lib.IbvQPCap").IbvQPCap
IbvQPInitAttr = importlib.import_module("lib.IbvQPInitAttr").IbvQPInitAttr
IbvQPAttr = importlib.import_module("lib.IbvQPAttr").IbvQPAttr
IbvSge = importlib.import_module("lib.IbvSge").IbvSge
IbvSendWR = importlib.import_module("lib.IbvSendWR").IbvSendWR


# ====== 简易 ctx：挂 contracts（契约表）即可；tracker 用你现有的 ======
class FakeTracker:
    def __init__(self):
        self.calls = []

    def use(self, t, n):
        self.calls.append(("use", t, n))

    def create(self, t, n, **k):
        self.calls.append(("create", t, n, k))

    def destroy(self, t, n):
        self.calls.append(("destroy", t, n))


class FakeCtx:
    def __init__(self, ib_ctx="ctx"):
        self.tracker = FakeTracker()
        self.ib_ctx = ib_ctx
        self.contracts = contracts_mod.ContractTable()  # 关键：契约表
        self._vars = []

    def alloc_variable(self, name, ty, init=None):
        self._vars.append((name, ty, init))


# ====== 小工具 ======
def _mk_pd(ctx, name="pd0"):
    v = verbs.AllocPD(pd=name)
    v.apply(ctx)  # 你已经给 AllocPD 加了 CONTRACT，这里会自动登记 pd
    return name


def _mk_cq(ctx, name="cq0"):
    v = verbs.CreateCQ(cq=name, cqe=8, comp_vector=0)
    v.apply(ctx)  # 同理，CreateCQ 的 CONTRACT 会登记 cq
    return name


def _mk_min_qp(ctx, pd="pd0", cq="cq0", qp="qp0"):
    cap = IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1)
    init = IbvQPInitAttr(qp_type="IBV_QPT_RC", send_cq=cq, recv_cq=cq, cap=cap)
    v = verbs.CreateQP(pd=pd, qp=qp, init_attr_obj=init)
    v.apply(ctx)  # CONTRACT: require pd, produce qp(RESET)
    return qp


def _assert_codegen_has(code: str, token: str):
    assert isinstance(code, str) and code.strip(), "generate_c() must return non-empty str"
    assert token in code, f"expected {token!r} in generated code:\n{code}"


# ====== 这里开始是“闭环”演示 ======


@pytest.mark.skipif(ContractAwareMutator is None, reason="lib.fuzz_mutate not found")
def test_full_pipeline_wrapper_orchestrator_contracts_rc_path():
    rng = random.Random(0xC0FFEE)
    mut = ContractAwareMutator(rng=rng)

    ctx = FakeCtx()

    # 1) 资源准备（由 verbs 的 CONTRACT 自动登记到 ctx.contracts）
    pd = _mk_pd(ctx, "pd0")
    cq = _mk_cq(ctx, "cq0")

    # 2) CreateQP：CONTRACT 要求 pd 已存在，并产出 qp=RESET
    qp = _mk_min_qp(ctx, pd, cq, "qp0")
    snap = ctx.contracts.snapshot()
    assert ("pd", "pd0") in snap and snap[("pd", "pd0")] == "ALLOCATED"
    assert ("cq", "cq0") in snap and snap[("cq", "cq0")] == "ALLOCATED"
    assert ("qp", "qp0") in snap and snap[("qp", "qp0")] in {"RESET", "ALLOCATED"}  # 取决于你定义

    # 3) ModifyQP：用 wrapper 对 attr 做建模；让编排器 mutate（会参考契约选合法 qp 等）
    #    ——目标：INIT -> RTR -> RTS
    # 3.1 INIT
    attr_init = IbvQPAttr(qp_state="IBV_QPS_INIT")
    v_init = verbs.ModifyQP(qp=qp, attr_obj=attr_init, attr_mask="IBV_QP_STATE")

    # 关键：调用编排器的 mutate（它会优先用 CONTRACT 里合法资源修复/引导）
    assert mut.mutate(v_init, ctx)
    v_init.apply(ctx)
    code_init = v_init.generate_c(ctx)
    _assert_codegen_has(code_init, "ibv_modify_qp")

    # 3.2 RTR
    attr_rtr = IbvQPAttr(qp_state="IBV_QPS_RTR")
    v_rtr = verbs.ModifyQP(qp=qp, attr_obj=attr_rtr, attr_mask="IBV_QP_STATE")
    assert mut.mutate(v_rtr, ctx)
    v_rtr.apply(ctx)
    code_rtr = v_rtr.generate_c(ctx)
    _assert_codegen_has(code_rtr, "ibv_modify_qp")

    # 3.3 RTS
    attr_rts = IbvQPAttr(qp_state="IBV_QPS_RTS")
    v_rts = verbs.ModifyQP(qp=qp, attr_obj=attr_rts, attr_mask="IBV_QP_STATE")
    assert mut.mutate(v_rts, ctx)
    v_rts.apply(ctx)
    code_rts = v_rts.generate_c(ctx)
    _assert_codegen_has(code_rts, "ibv_modify_qp")

    # QP 已到 RTS（如果你在 ModifyQP 里把状态写进 contracts）
    snap = ctx.contracts.snapshot()
    if ("qp", "qp0") in snap:
        assert snap[("qp", "qp0")] in {"RTS", "RTR", "INIT", "RESET"}  # 视你的 CONTRACT 严格度

    # 4) PostSend：WR/SGE 由 wrapper 建模，编排器会保持 num_sge ↔ sge_list 一致
    wr = IbvSendWR(opcode="IBV_WR_SEND")
    # 最小 1 个 SGE（用 wrapper 类，便于它自己的 mutate）
    sge0 = IbvSge(addr=0x1000, length=64, lkey=0)
    # 不同实现里字段可能叫 sg_list/sge/sgl，任选其一（下方 mutator 会识别并修正 num_sge）
    if hasattr(wr, "sg_list"):
        wr.sg_list = [sge0]
    elif hasattr(wr, "sge"):
        wr.sge = [sge0]
    else:
        setattr(wr, "sg_list", [sge0])
    if hasattr(wr, "num_sge"):
        wr.num_sge = 1
    elif hasattr(wr, "num_sges"):
        wr.num_sges = 1

    v_ps = verbs.PostSend(qp=qp, wr_obj=wr)
    # 让编排器做一次契约感知 mutate：它会保持 WR 不变式、并确保 qp 来自合法资源池
    assert mut.mutate(v_ps, ctx)
    v_ps.apply(ctx)
    code_ps = v_ps.generate_c(ctx)
    _assert_codegen_has(code_ps, "ibv_post_send")

    # 5) 再 mutate 一次 PostSend（会尝试把 1 个 SGE -> 2 个 SGE，且同步 num_sge）
    assert mut.mutate(v_ps, ctx)
    code_ps2 = v_ps.generate_c(ctx)
    _assert_codegen_has(code_ps2, "ibv_post_send")
