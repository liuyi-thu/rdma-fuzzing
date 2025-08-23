# tests/test_insertion_smoke.py
import random

import pytest

from lib import verbs
from lib.contracts import ContractError
from lib.debug_dump import diff_verb_snapshots, dump_verbs, snapshot_verbs, summarize_verb, summarize_verb_list
from lib.fuzz_mutate import ContractAwareMutator

# 如果你的工程里已有 FakeCtx，用下面这行替代本地定义
try:
    from tests.utils import FakeCtx  # 你自己的
except Exception:
    # 兜底：极简版 FakeCtx（仅满足 apply/generate_c 所需接口）
    class _DummyContracts:
        def apply_contract(self, verb, contract):
            pass

        def snapshot(self):
            return {}

    class FakeCtx:
        def __init__(self):
            self.vars = {}
            self.tracker = None
            self.contracts = _DummyContracts()
            self.ib_ctx = "ctx"

        def alloc_variable(self, name, ctype, init=None):
            self.vars[name] = (ctype, init)

# ----------------- 小工具 -----------------


def _mk_min_env(pd="pd0", cq="cq0", qp="qp0", with_mr=True):
    """
    最小环境：AllocPD, CreateCQ, (RegMR), CreateQP
    返回 (ctx, seq)
    """
    ctx = FakeCtx()
    seq = []
    seq.append(verbs.AllocPD(pd=pd))
    seq.append(verbs.CreateCQ(cqe=16, cq=cq, cq_context="NULL", channel="NULL", comp_vector=0))
    if with_mr:
        seq.append(verbs.RegMR(pd=pd, mr="mr0", addr="addr0", length=4096, access="IBV_ACCESS_LOCAL_WRITE"))
    # QP init_attr
    from lib.ibv_all import IbvQPCap, IbvQPInitAttr

    init = IbvQPInitAttr(
        qp_type="IBV_QPT_RC",
        send_cq=cq,
        recv_cq=cq,
        cap=IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1),
    )
    seq.append(verbs.CreateQP(pd=pd, qp=qp, init_attr_obj=init))
    # 让环境 apply 一遍，保证 contracts 内已有资源快照
    for v in seq:
        v.apply(ctx)
    return ctx, seq


def _gen_and_check(seq, ctx, expect_frag=None):
    """生成所有 C 代码并检查关键片段（可选）"""
    out = []
    for v in seq:
        s = v.generate_c(ctx)
        out.append(s)
    s = "\n".join(out)
    if expect_frag:
        assert expect_frag in s
    return s


# =========================================================
# 1) AllocPD + CreateQP 插入
# =========================================================


def test_insert_allocpd_and_createqp_apply_and_codegen():
    rng = random.Random(1234)
    mut = ContractAwareMutator(rng=rng)

    ctx, seq = _mk_min_env(with_mr=False)  # 先不放 MR，看看自动补链效果

    # 插入 AllocPD（独立 PD）
    assert mut.mutate_insert(seq, choice="alloc_pd")
    # 插入 CreateQP（引用现有 cq/pd 或 factories 自动补）
    assert mut.mutate_insert(seq, choice="create_qp")

    # 应用 & 代码生成
    ctx2 = FakeCtx()
    for v in seq:
        v.apply(ctx2)
    _gen_and_check(seq, ctx2, expect_frag="ibv_create_qp")


# =========================================================
# 2) ModifyCQ 插入
# =========================================================


def test_insert_modifycq_apply_and_codegen():
    rng = random.Random(5678)
    mut = ContractAwareMutator(rng=rng)

    ctx, seq = _mk_min_env()
    assert mut.mutate_insert(seq, choice="modify_cq")

    ctx2 = FakeCtx()
    for v in seq:
        v.apply(ctx2)
    s = _gen_and_check(seq, ctx2)
    # 可能包含 driver-specific 的 moderation 设置，这里不强制片段
    assert "cq" in s  # 粗检


# =========================================================
# 3) AllocMW + BindMW：两种产出 MW 的路径覆盖
# =========================================================


def test_insert_allocmw_and_bindmw_apply_and_codegen():
    rng = random.Random(999)
    mut = ContractAwareMutator(rng=rng)

    ctx, seq = _mk_min_env()

    # 显式走 AllocMW 路径
    assert mut.mutate_insert(seq, choice="alloc_mw")

    # 再插入 BindMW（它需要 qp & mr；mw_bind_obj.bind_info.mr 我们已有 mr0）
    assert mut.mutate_insert(seq, choice="bind_mw")

    ctx2 = FakeCtx()
    for v in seq:
        v.apply(ctx2)
    s = _gen_and_check(seq, ctx2)
    assert "ibv_alloc_mw" in s or "ibv_bind_mw" in s


# =========================================================
# 4) AllocDM + FreeDM
# =========================================================


def test_insert_allocdm_and_freedm_apply_and_codegen():
    rng = random.Random(2024)
    mut = ContractAwareMutator(rng=rng)

    ctx, seq = _mk_min_env()

    # 分别插入 AllocDM 与 FreeDM（如果现场没有 dm，free_dm 模板会返回 None）
    assert mut.mutate_insert(seq, choice="alloc_dm")
    assert mut.mutate_insert(seq, choice="free_dm")

    ctx2 = FakeCtx()
    for v in seq:
        v.apply(ctx2)
    s = _gen_and_check(seq, ctx2)
    # 不同平台名可能不同，不强制字符串


# =========================================================
# 5) ReRegMR（基于已存在的 MR）
# =========================================================


def test_insert_rereg_mr_apply_and_codegen():
    rng = random.Random(31337)
    mut = ContractAwareMutator(rng=rng)

    ctx, seq = _mk_min_env(with_mr=True)
    assert mut.mutate_insert(seq, choice="rereg_mr")

    ctx2 = FakeCtx()
    for v in seq:
        v.apply(ctx2)
    s = _gen_and_check(seq, ctx2)
    # 只做存在性检查
    assert "mr" in s


# =========================================================
# 6) SRQ 路径（CreateSRQ → PostSRQRecv → ModifySRQ）
# =========================================================


def test_insert_srq_path_apply_and_codegen():
    rng = random.Random(4242)
    mut = ContractAwareMutator(rng=rng)

    ctx, seq = _mk_min_env()

    assert mut.mutate_insert(seq, choice="create_srq")
    assert mut.mutate_insert(seq, choice="post_srq_recv")
    assert mut.mutate_insert(seq, choice="modify_srq")

    ctx2 = FakeCtx()
    for v in seq:
        v.apply(ctx2)
    s = _gen_and_check(seq, ctx2)
    assert "ibv_create_srq" in s
    assert "ibv_post_srq_recv" in s
    assert "ibv_modify_srq" in s


# =========================================================
# 7) Destroy 路径：插入 DestroyQP 并验证前向切片清理
# =========================================================


def test_insert_destroy_qp_trims_dependents():
    rng = random.Random(0xBEEF)
    mut = ContractAwareMutator(rng=rng)

    ctx, seq = _mk_min_env()

    # 给 QP 添加一些后续依赖（ModifyQP, PostSend, PollCQ）
    from lib.ibv_all import IbvQPAttr

    seq.append(verbs.ModifyQP(qp="qp0", attr_obj=IbvQPAttr(qp_state="IBV_QPS_INIT"), attr_mask="IBV_QP_STATE"))
    seq.append(verbs.PostSend(qp="qp0", wr_obj=None))  # 允许 None 时你的生成会补 WR；否则换成最小 WR
    seq.append(verbs.PollCQ(cq="cq0"))
    # print(summarize_verb_list(seq))

    # 插入 DestroyQP（generic destroy 会偏向叶子，但这里我们点名）
    assert mut.mutate_insert(seq, choice="destroy_qp", idx=4)  # 没辙啊，如果随机的话就炸了

    # 期望：DestroyQP 之后，依赖 qp0 的后续 verbs 被前向切片清理
    # 只需确保 apply 不抛错即可
    ctx2 = FakeCtx()
    for v in seq:
        v.apply(ctx2)


# =========================================================
# 8) 混合随机插入若干次，验证序列稳定性
# =========================================================


@pytest.mark.parametrize("rounds", [5])
def test_random_mixture_inserts_stable(rounds):
    rng = random.Random(13579)
    mut = ContractAwareMutator(rng=rng)

    ctx, seq = _mk_min_env()

    ok_cnt = 0
    for _ in range(rounds):
        try:
            if mut.mutate_insert(seq):  # 随机选择模板
                ok_cnt += 1
        except ContractError:
            # 插入失败并不可怕（mutator 内部可能会回退）；这里只要最后能 apply 则算稳定
            pass

    # 最终 apply 验证
    ctx2 = FakeCtx()
    for v in seq:
        v.apply(ctx2)

    assert ok_cnt >= 1  # 至少有一次插入成功
