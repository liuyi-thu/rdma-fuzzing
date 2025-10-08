# -*- coding: utf-8 -*-
"""
Augmented scaffold set: translate high-value seed ideas into concrete, runnable
lists of VerbCall objects (plus hotspots).

All classes referenced below exist in your lib (see CLASSES_IN_LIB.md) and were
chosen to match their __init__ signatures. This file keeps the same import style
and public API as your original scaffolds.py, but adds many more scaffolds and a
registry for easy discovery.

Usage (example):
    from .scaffolds import ScaffoldBuilder, SCAFFOLD_REGISTRY
    verbs, hotspots = ScaffoldBuilder.send_recv_basic(pd="pd0", cq="cq0", qp="qp0")
    # or
    verbs, hotspots = SCAFFOLD_REGISTRY["inline_boundary_pair"]()

Notes:
- Data-plane scaffolds expect the QP to be in RTS; prepend base_connect() (or run
  it once) before these if needed.
- For RDMA/atomic scaffolds, replace remote placeholders (REMOTE_ADDR/RKEY) via
  your DeferredValue flow, or use the import tool's --replace.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Tuple

from .IbvAHAttr import IbvAHAttr, IbvGlobalRoute
from .IbvQPAttr import IbvQPAttr
from .IbvQPCap import IbvQPCap
from .IbvQPInitAttr import IbvQPInitAttr
from .IbvRecvWR import IbvRecvWR
from .IbvSendWR import IbvAtomicInfo, IbvRdmaInfo, IbvSendWR
from .IbvSge import IbvSge
from .IbvSrqAttr import IbvSrqAttr
from .IbvSrqInitAttr import IbvSrqInitAttr

# ---- Imports aligned with your package layout ----
from .verbs import (
    AckCQEvents,
    AllocMW,
    AllocPD,
    BindMW,
    CreateCQ,
    CreateQP,
    CreateSRQ,
    DeallocMW,
    ModifyQP,
    ModifySRQ,
    PollCQ,
    PostRecv,
    PostSend,
    PostSRQRecv,
    QueryGID,
    QueryPKey,
    QueryPortAttr,
    QueryQP,
    RegMR,
    ReqNotifyCQ,
    ReRegMR,
    ResizeCQ,
    VerbCall,
)

# ---------------------------------------------------------------------------
# Core building blocks
# ---------------------------------------------------------------------------


def _init_attr(
    send_cq: str,
    recv_cq: str,
    *,
    srq: str | None = None,
    qp_type: str = "IBV_QPT_RC",
    cap: IbvQPCap | None = None,
    sq_sig_all: int = 1,
) -> IbvQPInitAttr:
    return IbvQPInitAttr(
        send_cq=send_cq,
        recv_cq=recv_cq,
        srq=srq,
        cap=cap or IbvQPCap(max_send_wr=64, max_recv_wr=64, max_send_sge=4, max_recv_sge=4, max_inline_data=256),
        qp_type=qp_type,
        sq_sig_all=sq_sig_all,
    )


def base_connect(
    pd: str = "pd0", cq: str = "cq0", qp: str = "qp0", *, port: int = 1, remote_qp: str = "peer0"
) -> Tuple[List[VerbCall], List[int]]:
    """RESET→INIT→RTR→RTS, control-plane only."""
    init_attr = _init_attr(cq, cq, srq=None)

    verbs: List[VerbCall] = [
        AllocPD(pd),
        CreateCQ(cq=cq, cqe=256),
        CreateQP(pd=pd, qp=qp, init_attr_obj=init_attr, remote_qp=remote_qp),
        # INIT
        ModifyQP(
            qp=qp,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_INIT",
                pkey_index=0,
                port_num=port,
                qp_access_flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
            ),
            attr_mask="IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS",
        ),
        # RTR
        ModifyQP(
            qp=qp,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_RTR",
                path_mtu="IBV_MTU_1024",
                dest_qp_num=0,  # Deferred/filled by your runtime
                rq_psn=0,
                max_dest_rd_atomic=1,
                min_rnr_timer=12,
                ah_attr=IbvAHAttr(
                    is_global=1,
                    port_num=port,
                    grh=IbvGlobalRoute(sgid_index=1, hop_limit=1, traffic_class=0, flow_label=0, dgid=""),
                ),
            ),
            attr_mask=(
                "IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_RQ_PSN | "
                "IBV_QP_DEST_QPN | IBV_QP_MIN_RNR_TIMER | IBV_QP_MAX_DEST_RD_ATOMIC"
            ),
        ),
        # RTS
        ModifyQP(
            qp=qp,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_RTS",
                sq_psn=0,
                timeout=14,
                retry_cnt=7,
                rnr_retry=7,
                max_rd_atomic=1,
            ),
            attr_mask="IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC",
        ),
    ]
    hotspots = [3, 4, 5]
    return verbs, hotspots


# ---------------------------------------------------------------------------
# Data-path scaffolds
# ---------------------------------------------------------------------------


def send_recv_basic(
    pd="pd0", cq="cq0", qp="qp0", mr="mr0", buf="buf0", recv_len=256, send_len=128, inline=False, build_mr=True
) -> Tuple[List[VerbCall], List[int]]:
    recv_wr = IbvRecvWR(wr_id=0x1001, sg_list=[IbvSge(mr=mr, length=recv_len)], num_sge=1, next_wr=None)
    send_wr = IbvSendWR(
        wr_id=0x2001,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=send_len)],
        num_sge=1,
        send_flags=("IBV_SEND_SIGNALED | IBV_SEND_INLINE" if inline else "IBV_SEND_SIGNALED"),
    )
    seq: List[VerbCall] = []
    if build_mr:
        seq.append(
            RegMR(
                pd=pd,
                mr=mr,
                addr=buf,
                length=max(recv_len, send_len, 4096),
                access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
            )
        )
    seq += [PostRecv(qp=qp, wr_obj=recv_wr), PostSend(qp=qp, wr_obj=send_wr), PollCQ(cq=cq)]
    return seq, [len(seq) - 3, len(seq) - 2]


def rdma_write_basic(
    pd="pd0", cq="cq0", qp="qp0", mr="mr0", buf="buf0", remote_mr="mr1", length=128, inline=False
) -> Tuple[List[VerbCall], List[int]]:
    wr = IbvSendWR(
        wr_id=0x3001,
        opcode="IBV_WR_RDMA_WRITE",
        sg_list=[IbvSge(mr=mr, length=length)],
        num_sge=1,
        send_flags=("IBV_SEND_SIGNALED | IBV_SEND_INLINE" if inline else "IBV_SEND_SIGNALED"),
        rdma=IbvRdmaInfo(
            remote_mr=remote_mr,
            # remote_addr="REMOTE_ADDR", rkey="REMOTE_RKEY" --- IGNORE ---
        ),
    )
    seq = [
        RegMR(pd=pd, mr=mr, addr=buf, length=max(length, 4096), access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=wr),
        PollCQ(cq=cq),
    ]
    return seq, [1]


def rdma_read_basic(
    pd="pd0", cq="cq0", qp="qp0", mr="mr0", buf="buf0", remote_mr="mr1", length=128
) -> Tuple[List[VerbCall], List[int]]:
    wr = IbvSendWR(
        wr_id=0x3002,
        opcode="IBV_WR_RDMA_READ",
        sg_list=[IbvSge(mr=mr, length=length)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
        rdma=IbvRdmaInfo(remote_mr=remote_mr),
    )
    seq = [
        RegMR(pd=pd, mr=mr, addr=buf, length=max(length, 4096), access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=wr),
        PollCQ(cq=cq),
    ]
    return seq, [1]


# ---------------------------------------------------------------------------
# Coverage-oriented scaffolds (boundary & error/repair pairs)
# ---------------------------------------------------------------------------


def inline_boundary_pair(
    pd="pd0", cq="cq0", qp="qp0", mr="mrI", buf="bufI", inline_cap: int = 256
) -> Tuple[List[VerbCall], List[int]]:
    """Two sends around max_inline_data boundary: one INLINE at cap, one non-inline above cap."""
    s1 = IbvSendWR(
        wr_id=0x5001,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=inline_cap)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED | IBV_SEND_INLINE",
    )
    s2 = IbvSendWR(
        wr_id=0x5002,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=inline_cap + 1)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
    )
    seq = [
        RegMR(pd=pd, mr=mr, addr=buf, length=max(inline_cap + 1, 2048), access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=s1),
        PollCQ(cq=cq),
        PostSend(qp=qp, wr_obj=s2),
        PollCQ(cq=cq),
    ]
    return seq, [1, 3]


def sge_boundary(
    pd="pd0", cq="cq0", qp="qp0", mr="mrS", buf="bufS", max_send_sge: int = 4
) -> Tuple[List[VerbCall], List[int]]:
    """One WR with num_sge=1, another with num_sge=max_send_sge (scatter/gather path)."""
    sg_list_big = [IbvSge(mr=mr, length=64 * (i + 1)) for i in range(max(1, max_send_sge))]
    sg_list_overflow = sg_list_big + [IbvSge(mr=mr, length=64)]  # one more than max
    w1 = IbvSendWR(
        wr_id=0x4001,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=64)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
    )
    w2 = IbvSendWR(
        wr_id=0x4002,
        opcode="IBV_WR_SEND",
        sg_list=sg_list_big,
        num_sge=len(sg_list_big),
        send_flags="IBV_SEND_SIGNALED",
    )
    w3 = IbvSendWR(
        wr_id=0x4003,
        opcode="IBV_WR_SEND",
        sg_list=sg_list_overflow,
        num_sge=len(sg_list_overflow),
        send_flags="IBV_SEND_SIGNALED",
    )
    seq = [
        RegMR(pd=pd, mr=mr, addr=buf, length=8192, access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=w1),
        PollCQ(cq=cq),
        PostSend(qp=qp, wr_obj=w2),
        PollCQ(cq=cq),
        PostSend(qp=qp, wr_obj=w3),
        PollCQ(cq=cq),
    ]
    return seq, [1, 3]


def wr_chain_16(
    pd="pd0", cq="cq0", qp="qp0", mr="mrC", buf="bufC", chain_len: int = 16
) -> Tuple[List[VerbCall], List[int]]:
    """Post a linked list of Send WRs (next_wr) to exercise batched posting paths."""
    head = None
    for i in reversed(range(chain_len)):
        head = IbvSendWR(
            wr_id=0x6000 + i,
            opcode="IBV_WR_SEND",
            sg_list=[IbvSge(mr=mr, length=64)],
            num_sge=1,
            send_flags="IBV_SEND_SIGNALED",
            next_wr=head,
        )
    seq = [
        RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=head),
        PollCQ(cq=cq),
    ]
    return seq, [1]


def cq_pressure(
    pd="pd0", cq="cqP", qp="qpP", mr="mrP", buf="bufP", burst: int = 64, reuse_cq: bool = False
) -> Tuple[List[VerbCall], List[int]]:
    """
    Stress CQ with many completions.
    If reuse_cq=True, will NOT create a new CQ and will reuse the provided `cq` name.
    Otherwise, creates a fresh CQ sized for the burst.
    """
    seq: List[VerbCall] = []
    if not reuse_cq:
        seq.append(CreateCQ(cq=cq, cqe=max(256, burst * 2)))

    # Ensure MR exists for WRs
    seq.append(RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE"))

    # Post N sends (separate WRs, not linked), then poll multiple times
    for i in range(burst):
        wr = IbvSendWR(
            wr_id=0x7000 + i,
            opcode="IBV_WR_SEND",
            sg_list=[IbvSge(mr=mr, length=64)],
            num_sge=1,
            send_flags="IBV_SEND_SIGNALED",
        )
        seq.append(PostSend(qp=qp, wr_obj=wr))

    seq += [PollCQ(cq=cq) for _ in range(3)]

    # Hotspots: the PostSend range we appended（根据是否创建CQ来对齐索引）
    first_ps = 2 if not reuse_cq else 1
    return seq, list(range(first_ps, first_ps + burst))


def rnr_then_recover(
    pd="pd0", cq="cq0", qp="qp0", mr="mrR", buf="bufR", send_len=128
) -> Tuple[List[VerbCall], List[int]]:
    """Simulate RNR: send before recv, expect RNR/timeout path, then post recv and resend."""
    s_bad = IbvSendWR(
        wr_id=0x8001,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=send_len)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
    )
    s_ok = IbvSendWR(
        wr_id=0x8002,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=send_len)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
    )
    r_ok = IbvRecvWR(wr_id=0x8101, sg_list=[IbvSge(mr=mr, length=send_len)], num_sge=1)
    seq = [
        RegMR(pd=pd, mr=mr, addr=buf, length=max(4096, send_len), access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=s_bad),  # likely RNR or retry path
        PostRecv(qp=qp, wr_obj=r_ok),
        PostSend(qp=qp, wr_obj=s_ok),
        PollCQ(cq=cq),
    ]
    return seq, [1, 3]


def failure_then_fix(
    pd="pd0", cq="cq0", qp="qp0", mr="mrF", buf="bufF", bad_len=4096, good_len=64
) -> Tuple[List[VerbCall], List[int]]:
    """First a too-large inline send (likely fail), then a small valid send."""
    bad = IbvSendWR(
        wr_id=0x9001,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=bad_len)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED | IBV_SEND_INLINE",
    )
    good = IbvSendWR(
        wr_id=0x9002,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=good_len)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
    )
    seq = [
        RegMR(pd=pd, mr=mr, addr=buf, length=max(bad_len, 4096), access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=bad),
        PollCQ(cq=cq),
        PostSend(qp=qp, wr_obj=good),
        PollCQ(cq=cq),
    ]
    return seq, [1, 3]


# ---------------------------------------------------------------------------
# Multi-QP / Shared CQ / SRQ / Atomic
# ---------------------------------------------------------------------------


def multi_qp_shared_cq(
    pd="pd0",
    cq="cqS",
    qp1="qp1",
    qp2="qp2",
    mr1="mr1",
    mr2="mr2",
    buf1="buf1",
    buf2="buf2",
    remote_qp1="peer1",
    remote_qp2="peer2",
) -> Tuple[List[VerbCall], List[int]]:
    """
    Two QPs share one CQ, each driven to RTS, then interleaved Recv/Send, finally poll.
    This scaffold is self-sufficient (includes INIT→RTR→RTßS for both QPs).
    """

    cap = IbvQPCap(max_send_wr=64, max_recv_wr=64, max_send_sge=4, max_recv_sge=4, max_inline_data=256)
    init1 = _init_attr(cq, cq, cap=cap)
    init2 = _init_attr(cq, cq, cap=cap)

    seq: List[VerbCall] = [
        AllocPD(pd),
        CreateCQ(cq=cq, cqe=256),
        CreateQP(pd=pd, qp=qp1, init_attr_obj=init1, remote_qp=remote_qp1),
        CreateQP(pd=pd, qp=qp2, init_attr_obj=init2, remote_qp=remote_qp2),
        # qp1: INIT → RTR → RTS
        ModifyQP(
            qp=qp1,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_INIT",
                pkey_index=0,
                port_num=1,
                qp_access_flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
            ),
            attr_mask="IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS",
        ),
        ModifyQP(
            qp=qp1,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_RTR",
                path_mtu="IBV_MTU_1024",
                dest_qp_num=0,
                rq_psn=0,
                max_dest_rd_atomic=1,
                min_rnr_timer=12,
                ah_attr=IbvAHAttr(
                    is_global=1,
                    port_num=1,
                    grh=IbvGlobalRoute(sgid_index=1, hop_limit=1, traffic_class=0, flow_label=0, dgid=""),
                ),
            ),
            attr_mask=(
                "IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_RQ_PSN | "
                "IBV_QP_DEST_QPN | IBV_QP_MIN_RNR_TIMER | IBV_QP_MAX_DEST_RD_ATOMIC"
            ),
        ),
        ModifyQP(
            qp=qp1,
            attr_obj=IbvQPAttr(qp_state="IBV_QPS_RTS", sq_psn=0, timeout=14, retry_cnt=7, rnr_retry=7, max_rd_atomic=1),
            attr_mask="IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC",
        ),
        # qp2: INIT → RTR → RTS
        ModifyQP(
            qp=qp2,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_INIT",
                pkey_index=0,
                port_num=1,
                qp_access_flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
            ),
            attr_mask="IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS",
        ),
        ModifyQP(
            qp=qp2,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_RTR",
                path_mtu="IBV_MTU_1024",
                dest_qp_num=0,
                rq_psn=0,
                max_dest_rd_atomic=1,
                min_rnr_timer=12,
                ah_attr=IbvAHAttr(
                    is_global=1,
                    port_num=1,
                    grh=IbvGlobalRoute(sgid_index=1, hop_limit=1, traffic_class=0, flow_label=0, dgid=""),
                ),
            ),
            attr_mask=(
                "IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_RQ_PSN | "
                "IBV_QP_DEST_QPN | IBV_QP_MIN_RNR_TIMER | IBV_QP_MAX_DEST_RD_ATOMIC"
            ),
        ),
        ModifyQP(
            qp=qp2,
            attr_obj=IbvQPAttr(qp_state="IBV_QPS_RTS", sq_psn=0, timeout=14, retry_cnt=7, rnr_retry=7, max_rd_atomic=1),
            attr_mask="IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC",
        ),
        # MRs + data path
        RegMR(pd=pd, mr=mr1, addr=buf1, length=2048, access="IBV_ACCESS_LOCAL_WRITE"),
        RegMR(pd=pd, mr=mr2, addr=buf2, length=2048, access="IBV_ACCESS_LOCAL_WRITE"),
    ]

    s1 = IbvSendWR(
        wr_id=0x2101,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr1, length=64)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
    )
    s2 = IbvSendWR(
        wr_id=0x2201,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr2, length=64)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
    )
    r1 = IbvRecvWR(wr_id=0x1101, sg_list=[IbvSge(mr=mr1, length=128)], num_sge=1)
    r2 = IbvRecvWR(wr_id=0x1201, sg_list=[IbvSge(mr=mr2, length=128)], num_sge=1)

    seq += [
        PostRecv(qp=qp1, wr_obj=r1),
        PostRecv(qp=qp2, wr_obj=r2),
        PostSend(qp=qp1, wr_obj=s1),
        PostSend(qp=qp2, wr_obj=s2),
        PollCQ(cq=cq),
        PollCQ(cq=cq),
    ]

    # 热点：两次 PostSend + 也可把 Recv 当作热点
    hotspots = [len(seq) - 6, len(seq) - 5, len(seq) - 4, len(seq) - 3]
    return seq, hotspots


def srq_path(
    pd="pd0", cq="cqSRQ", srq="srq0", qp="qpSRQ", mr="mrSRQ", buf="bufSRQ", remote_qp="peer0"
) -> Tuple[List[VerbCall], List[int]]:
    """
    Create SRQ, attach a QP to SRQ, drive QP to RTS, then exercise SRQ Recv + Send + Poll.
    """

    seq: List[VerbCall] = [
        AllocPD(pd),
        CreateSRQ(pd=pd, srq=srq, srq_init_obj=IbvSrqInitAttr(attr=IbvSrqAttr(max_wr=128, max_sge=1))),
        CreateCQ(cq=cq, cqe=128),
        CreateQP(pd=pd, qp=qp, init_attr_obj=_init_attr(cq, cq, srq=srq), remote_qp=remote_qp),
        # QP to RTS
        ModifyQP(
            qp=qp,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_INIT",
                pkey_index=0,
                port_num=1,
                qp_access_flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
            ),
            attr_mask="IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS",
        ),
        ModifyQP(
            qp=qp,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_RTR",
                path_mtu="IBV_MTU_1024",
                dest_qp_num=0,
                rq_psn=0,
                max_dest_rd_atomic=1,
                min_rnr_timer=12,
                ah_attr=IbvAHAttr(
                    is_global=1,
                    port_num=1,
                    grh=IbvGlobalRoute(sgid_index=1, hop_limit=1, traffic_class=0, flow_label=0, dgid=""),
                ),
            ),
            attr_mask=(
                "IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_RQ_PSN | "
                "IBV_QP_DEST_QPN | IBV_QP_MIN_RNR_TIMER | IBV_QP_MAX_DEST_RD_ATOMIC"
            ),
        ),
        ModifyQP(
            qp=qp,
            attr_obj=IbvQPAttr(qp_state="IBV_QPS_RTS", sq_psn=0, timeout=14, retry_cnt=7, rnr_retry=7, max_rd_atomic=1),
            attr_mask="IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC",
        ),
        # Data-path via SRQ
        RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE"),
        PostSRQRecv(srq=srq, wr_obj=IbvRecvWR(wr_id=0x7001, sg_list=[IbvSge(mr=mr, length=128)], num_sge=1)),
        PostSend(
            qp=qp,
            wr_obj=IbvSendWR(
                wr_id=0x7101,
                opcode="IBV_WR_SEND",
                sg_list=[IbvSge(mr=mr, length=64)],
                num_sge=1,
                send_flags="IBV_SEND_SIGNALED",
            ),
        ),
        PollCQ(cq=cq),
    ]
    hotspots = [len(seq) - 3, len(seq) - 2]
    return seq, hotspots


def atomic_pair(
    pd="pd0", cq="cq0", qp="qp0", mr="mrA", buf="bufA", remote_mr="mrB"
) -> Tuple[List[VerbCall], List[int]]:
    """Try CAS then FetchAdd (8B). If caps unsupported, these should expose error paths."""
    cas = IbvSendWR(
        wr_id=0xA001,
        opcode="IBV_WR_ATOMIC_CMP_AND_SWP",
        sg_list=[IbvSge(mr=mr, length=8)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
        atomic=IbvAtomicInfo(
            remote_mr=remote_mr,
            compare_add=0,
            swap=1,
        ),
    )
    fad = IbvSendWR(
        wr_id=0xA002,
        opcode="IBV_WR_ATOMIC_FETCH_AND_ADD",
        sg_list=[IbvSge(mr=mr, length=8)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
        atomic=IbvAtomicInfo(remote_mr=remote_mr, compare_add=1, swap=None),
    )
    seq = [
        RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=cas),
        PollCQ(cq=cq),
        PostSend(qp=qp, wr_obj=fad),
        PollCQ(cq=cq),
    ]
    return seq, [1, 3]


def inline_zero_and_cap_pair(
    pd="pd0", cq="cq0", qp="qp0", mr="mrIZ", buf="bufIZ", inline_cap: int = 256
) -> Tuple[List[VerbCall], List[int]]:
    """
    0 字节 INLINE 与 cap 字节 INLINE 成对，覆盖长度边界与 fast-path 分支。
    假设 QP=RTS，仅 RegMR + PostSend* + PollCQ。
    """
    s0 = IbvSendWR(
        wr_id=0xD101,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=0)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED | IBV_SEND_INLINE",
    )
    sc = IbvSendWR(
        wr_id=0xD102,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=inline_cap)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED | IBV_SEND_INLINE",
    )
    seq = [
        RegMR(pd=pd, mr=mr, addr=buf, length=max(4096, inline_cap), access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=s0),
        PollCQ(cq=cq),
        PostSend(qp=qp, wr_obj=sc),
        PollCQ(cq=cq),
    ]
    return seq, [1, 3]


def rdma_len_edge_pairs(
    pd="pd0", cq="cq0", qp="qp0", mr="mrLE", buf="bufLE", small: int = 0, large: int = 4096
) -> Tuple[List[VerbCall], List[int]]:
    """
    RDMA WRITE 的长度边界：0 字节（合法的 no-op）与较大长度（跨页机会）成对。
    远端占位 REMOTE_* 由协调器替换。
    """
    w0 = IbvSendWR(
        wr_id=0xD201,
        opcode="IBV_WR_RDMA_WRITE",
        sg_list=[IbvSge(mr=mr, length=small)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
        rdma=IbvRdmaInfo(remote_addr="REMOTE_ADDR", rkey="REMOTE_RKEY"),
    )
    w1 = IbvSendWR(
        wr_id=0xD202,
        opcode="IBV_WR_RDMA_WRITE",
        sg_list=[IbvSge(mr=mr, length=large)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
        rdma=IbvRdmaInfo(remote_addr="REMOTE_ADDR", rkey="REMOTE_RKEY"),
    )
    seq = [
        RegMR(pd=pd, mr=mr, addr=buf, length=max(large, 4096), access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=w0),
        PollCQ(cq=cq),
        PostSend(qp=qp, wr_obj=w1),
        PollCQ(cq=cq),
    ]
    return seq, [1, 3]


def sge_max_vs_overflow(
    pd="pd0", cq="cq0", qp="qp0", mr="mrSG", buf="bufSG", max_send_sge: int = 4
) -> Tuple[List[VerbCall], List[int]]:
    """
    SGE 边界与超界成对：一条合法（=max_send_sge），一条超界（=max_send_sge+1，期望 EINVAL）。
    这能稳定打到 validate_send_wr 的失败分支，而不会把进程打崩。
    """
    # 合法：=max_send_sge
    sg_ok = [IbvSge(mr=mr, length=32) for _ in range(max(1, max_send_sge))]
    w_ok = IbvSendWR(
        wr_id=0xD301, opcode="IBV_WR_SEND", sg_list=sg_ok, num_sge=len(sg_ok), send_flags="IBV_SEND_SIGNALED"
    )
    # 超界：=max_send_sge+1
    sg_bad = [IbvSge(mr=mr, length=32) for _ in range(max_send_sge + 1)]
    w_bad = IbvSendWR(
        wr_id=0xD302, opcode="IBV_WR_SEND", sg_list=sg_bad, num_sge=len(sg_bad), send_flags="IBV_SEND_SIGNALED"
    )
    seq = [
        RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=w_ok),
        PollCQ(cq=cq),
        PostSend(qp=qp, wr_obj=w_bad),
        PollCQ(cq=cq),
    ]
    return seq, [1, 3]


def srq_post_burst(pd="pd0", srq="srqB", mr="mrSB", buf="bufSB", burst: int = 64) -> Tuple[List[VerbCall], List[int]]:
    """
    纯 SRQ 管理面压力：批量 PostSRQRecv（不依赖对端发送也能覆盖 SRQ 队列处理路径）。
    适合与你的 runner 中“对端主动发包”的 case 组合使用；单独运行也能覆盖创建与 post 路径。
    """
    seq: List[VerbCall] = [
        CreateSRQ(pd=pd, srq=srq, srq_init_obj=IbvSrqInitAttr(attr=IbvSrqAttr(max_wr=max(128, burst), max_sge=1))),
        RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE"),
    ]
    for i in range(burst):
        wr = IbvRecvWR(wr_id=0xD400 + i, sg_list=[IbvSge(mr=mr, length=128)], num_sge=1)
        seq.append(PostSRQRecv(srq=srq, wr_obj=wr))
    # 不 poll，因为这是 Recv 队列；是否产生 CQE 取决于对端是否发送
    hotspots = list(range(2, 2 + burst))  # 所有 PostSRQRecv
    return seq, hotspots


def notify_cq_basic(
    pd="pd0", cq="cq0", qp="qp0", mr="mrN", buf="bufN", recv_len=256, send_len=128
) -> Tuple[List[VerbCall], List[int]]:
    """触发一次完成，走 ReqNotifyCQ / AckCQEvents 分支，再 PollCQ 验证。"""
    recv_wr = IbvRecvWR(wr_id=0x9101, sg_list=[IbvSge(mr=mr, length=recv_len)], num_sge=1)
    send_wr = IbvSendWR(
        wr_id=0x9201,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=send_len)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
    )
    seq: List[VerbCall] = [
        RegMR(pd=pd, mr=mr, addr=buf, length=max(recv_len, send_len, 4096), access="IBV_ACCESS_LOCAL_WRITE"),
        PostRecv(qp=qp, wr_obj=recv_wr),
        ReqNotifyCQ(cq=cq, solicited_only=0),  # 允许任何完成唤醒
        PostSend(qp=qp, wr_obj=send_wr),
        AckCQEvents(cq=cq, nevents=1),
        PollCQ(cq=cq),
    ]
    # 热点：PostSend、Ack、Poll
    return seq, [3, 4, 5]


def resize_cq_flow(
    pd="pd0", cq="cqR", qp="qpR", mr="mrRZ", buf="bufRZ", old_cqe=128, new_cqe=512, burst=8
) -> Tuple[List[VerbCall], List[int]]:
    """先用较小 cqe 跑一波完成，再 ResizeCQ，之后再发一批 WR 验证。"""
    seq: List[VerbCall] = [
        CreateCQ(cq=cq, cqe=old_cqe),
        RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE"),
    ]
    for i in range(burst):
        wr = IbvSendWR(
            wr_id=0xA000 + i,
            opcode="IBV_WR_SEND",
            sg_list=[IbvSge(mr=mr, length=64)],
            num_sge=1,
            send_flags="IBV_SEND_SIGNALED",
        )
        seq.append(PostSend(qp=qp, wr_obj=wr))
    seq += [PollCQ(cq=cq)]
    seq.append(ResizeCQ(cq=cq, cqe=new_cqe))
    for i in range(burst):
        wr = IbvSendWR(
            wr_id=0xA100 + i,
            opcode="IBV_WR_SEND",
            sg_list=[IbvSge(mr=mr, length=64)],
            num_sge=1,
            send_flags="IBV_SEND_SIGNALED",
        )
        seq.append(PostSend(qp=qp, wr_obj=wr))
    seq += [PollCQ(cq=cq)]
    # 热点：ResizeCQ 前后的 PostSend 区段
    first_send = 2
    after_resize = first_send + burst + 2  # Poll + Resize
    hotspots = list(range(first_send, first_send + burst)) + list(range(after_resize, after_resize + burst))
    return seq, hotspots


def rereg_mr_variants(
    pd="pd0", other_pd="pd1", cq="cq0", qp="qp0", mr="mrRR", buf="bufRR", length=4096
) -> Tuple[List[VerbCall], List[int]]:
    """RegMR → ReRegMR 多种 flags；中间穿插一次 send 验证每次变更后可用性。"""
    seq: List[VerbCall] = [
        AllocPD(other_pd),  # 用于换 PD 的一例
        RegMR(pd=pd, mr=mr, addr=buf, length=length, access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ"),
        # 1) 改 access
        ReRegMR(
            mr=mr,
            flags="IBV_REREG_MR_CHANGE_ACCESS",
            access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
        ),
    ]
    wr_ok = IbvSendWR(
        wr_id=0xB001,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=128)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
    )
    seq += [PostSend(qp=qp, wr_obj=wr_ok), PollCQ(cq=cq)]
    # 2) 改 translation（地址/长度）
    seq.append(ReRegMR(mr=mr, flags="IBV_REREG_MR_CHANGE_TRANSLATION", addr=buf, length=length))
    seq += [PostSend(qp=qp, wr_obj=wr_ok), PollCQ(cq=cq)]
    # 3) 改 PD
    seq.append(ReRegMR(mr=mr, flags="IBV_REREG_MR_CHANGE_PD", pd=other_pd))
    seq += [PostSend(qp=qp, wr_obj=wr_ok), PollCQ(cq=cq)]
    hotspots = [2, 4, 6, 8]  # 三次 ReRegMR 之后的 PostSend 紧邻处
    return seq, hotspots


def query_suite(pd="pd0", cq="cq0", qp="qp0", port=1) -> Tuple[List[VerbCall], List[int]]:
    """RTS 后查询一把，覆盖 query 分支（适配 RXE 环境）。"""
    seq: List[VerbCall] = [
        QueryQP(qp=qp, attr_mask="IBV_QP_STATE | IBV_QP_CAP | IBV_QP_PATH_MTU", out_init_attr=True),
        QueryPortAttr(port=port),
        QueryGID(port=port, index=0),
        QueryPKey(port=port, index=0),
    ]
    return seq, [0, 1, 2, 3]


def mw_bind_cycle(
    pd="pd0", cq="cq0", qp="qp0", mr="mrMW", buf="bufMW", mw="mw0", mw_type="IBV_MW_TYPE_1"
) -> Tuple[List[VerbCall], List[int]]:
    """覆盖 MW 的发放/违规/修复路径。"""
    seq: List[VerbCall] = [
        RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ"),
        AllocMW(pd=pd, mw=mw, mw_type=mw_type),
        # 合法绑定
        BindMW(mw=mw, mr=mr, access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ"),
    ]
    # 触发一次使用
    wr_ok = IbvSendWR(
        wr_id=0xC001,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=64)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
    )
    seq += [PostSend(qp=qp, wr_obj=wr_ok), PollCQ(cq=cq)]
    # 故意非法再次绑定（例如去掉必须权限）
    seq.append(BindMW(mw=mw, mr=mr, access="0"))
    # 修复为合法
    seq.append(BindMW(mw=mw, mr=mr, access="IBV_ACCESS_LOCAL_WRITE"))
    seq += [DeallocMW(mw=mw)]
    hotspots = [2, 3, 5]  # 首次合法 bind + 首次使用 + 修复后的 bind
    return seq, hotspots


def srq_limit_pressure(
    pd="pd0", cq="cqS", srq="srqL", qp="qpS", mr="mrS", buf="bufS", port=1, n_post=32
) -> Tuple[List[VerbCall], List[int]]:
    """建 SRQ → 先小量 Recv → 降低 limit → 连续发送 → Poll 完成，触发 SRQ 边界/事件分支。"""
    init = _init_attr(cq, cq, srq=srq)
    rwr = IbvRecvWR(wr_id=0xD101, sg_list=[IbvSge(mr=mr, length=256)], num_sge=1)
    swr = IbvSendWR(
        wr_id=0xD201,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=64)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
    )
    seq: List[VerbCall] = [
        CreateSRQ(pd=pd, srq=srq, srq_init_obj=IbvSrqInitAttr(attr=IbvSrqAttr(max_wr=128, max_sge=1))),
        CreateCQ(cq=cq, cqe=max(256, n_post * 2)),
        CreateQP(pd=pd, qp=qp, init_attr_obj=init, remote_qp="peerS"),
        RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE"),
        # 先填充少量 SRQ Recv
        PostSRQRecv(srq=srq, wr_obj=rwr),
        PostSRQRecv(srq=srq, wr_obj=IbvRecvWR(wr_id=0xD102, sg_list=[IbvSge(mr=mr, length=256)], num_sge=1)),
        # 降低 limit
        ModifySRQ(srq=srq, srq_attr_obj=IbvSrqAttr(srqlimit=1)),
    ]
    # 连续发送，施压 SRQ
    for i in range(n_post):
        wr = IbvSendWR(
            wr_id=0xD300 + i,
            opcode="IBV_WR_SEND",
            sg_list=[IbvSge(mr=mr, length=64)],
            num_sge=1,
            send_flags="IBV_SEND_SIGNALED",
        )
        seq.append(PostSend(qp=qp, wr_obj=wr))
    seq += [PollCQ(cq=cq), PollCQ(cq=cq)]
    hotspots = list(range(8, 8 + n_post))  # 连续发送段
    return seq, hotspots


# ---------------------------------------------------------------------------
# Public builder API + registry
# ---------------------------------------------------------------------------
class ScaffoldBuilder:
    """Back-compat callable methods + more variants."""

    # Original set
    base_connect = staticmethod(base_connect)
    send_recv_basic = staticmethod(send_recv_basic)
    rdma_write_basic = staticmethod(rdma_write_basic)
    rdma_read_basic = staticmethod(rdma_read_basic)

    # New high-coverage variants
    inline_boundary_pair = staticmethod(inline_boundary_pair)
    sge_boundary = staticmethod(sge_boundary)
    wr_chain_16 = staticmethod(wr_chain_16)
    cq_pressure = staticmethod(cq_pressure)
    rnr_then_recover = staticmethod(rnr_then_recover)
    failure_then_fix = staticmethod(failure_then_fix)
    multi_qp_shared_cq = staticmethod(multi_qp_shared_cq)
    srq_path = staticmethod(srq_path)
    atomic_pair = staticmethod(atomic_pair)

    inline_zero_and_cap_pair = staticmethod(inline_zero_and_cap_pair)
    rdma_len_edge_pairs = staticmethod(rdma_len_edge_pairs)
    sge_max_vs_overflow = staticmethod(sge_max_vs_overflow)
    srq_post_burst = staticmethod(srq_post_burst)
    notify_cq_basic = staticmethod(notify_cq_basic)
    resize_cq_flow = staticmethod(resize_cq_flow)
    rereg_mr_variants = staticmethod(rereg_mr_variants)
    query_suite = staticmethod(query_suite)
    mw_bind_cycle = staticmethod(mw_bind_cycle)
    srq_limit_pressure = staticmethod(srq_limit_pressure)


# A uniform registry for discovery/testing/CLI integration
SCAFFOLD_REGISTRY: Dict[str, Callable[[], Tuple[List[VerbCall], List[int]]]] = {
    # control-plane
    "base_connect": base_connect,
    # data-plane basics
    "send_recv_basic": send_recv_basic,
    "rdma_write_basic": rdma_write_basic,
    "rdma_read_basic": rdma_read_basic,
    # coverage-oriented
    "inline_boundary_pair": inline_boundary_pair,
    "sge_boundary": sge_boundary,
    "wr_chain_16": wr_chain_16,
    "cq_pressure": cq_pressure,
    "rnr_then_recover": rnr_then_recover,
    "failure_then_fix": failure_then_fix,
    # multi-qp / srq / atomic
    "multi_qp_shared_cq": multi_qp_shared_cq,
    "srq_path": srq_path,
    "atomic_pair": atomic_pair,
    "notify_cq_basic": notify_cq_basic,
    "resize_cq_flow": resize_cq_flow,
    "rereg_mr_variants": rereg_mr_variants,
    "query_suite": query_suite,
    "mw_bind_cycle": mw_bind_cycle,
    "srq_limit_pressure": srq_limit_pressure,
}


if __name__ == "__main__":
    # Demo: print one scaffold
    verbs, hotspots = send_recv_basic()
    for i, v in enumerate(verbs):
        print(f"{i:02d}: {v}")
    print("Hotspots:", hotspots)
