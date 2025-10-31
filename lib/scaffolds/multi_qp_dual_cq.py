# -*- coding: utf-8 -*-
"""
multi_qp_dual_cq.py
-------------------
Create two RC QPs that share the same PD but use *different* CQs. This exercises:
- Multiple CQs under the same PD
- A second QP brought up manually (INIT→RTR→RTS) without re-allocating PD
- Cross-QP data path with simple SEND/RECV pairs (no CQ notify/poll APIs)

No I/O, sleep or threads are used. All verbs and struct signatures align with CLASSES_IN_LIB.md.
The scaffold returns (verbs, hotspots). The build() entry auto-fills resource names.

Flow:
  1) base_connect() for qp1 (alloc PD+CQ1 and bring qp1 to RTS)
  2) Create CQ2 and a second QP (qp2) bound to CQ2, then INIT→RTR→RTS
  3) Register a single MR and post one RECV on qp1, SEND from qp2 (repeat once)
"""

from __future__ import annotations

from typing import List, Tuple

from lib.fuzz_mutate import _pick_unused_from_snap, gen_name
from lib.IbvAHAttr import IbvAHAttr, IbvGlobalRoute
from lib.IbvQPAttr import IbvQPAttr
from lib.IbvQPCap import IbvQPCap
from lib.IbvQPInitAttr import IbvQPInitAttr
from lib.IbvRecvWR import IbvRecvWR
from lib.IbvSendWR import IbvSendWR
from lib.IbvSge import IbvSge
from lib.scaffolds.base_connect import base_connect
from lib.verbs import (
    CreateCQ,
    CreateQP,
    ModifyQP,
    PostRecv,
    PostSend,
    RegMR,
    VerbCall,
)


def _init_attr(
    send_cq: str, recv_cq: str, *, qp_type: str = "IBV_QPT_RC", cap: IbvQPCap | None = None, sq_sig_all: int = 1
) -> IbvQPInitAttr:
    """Helper to construct IbvQPInitAttr with sane defaults (no SRQ)."""
    return IbvQPInitAttr(
        send_cq=send_cq,
        recv_cq=recv_cq,
        srq=None,
        cap=cap
        or IbvQPCap(
            max_send_wr=64,
            max_recv_wr=64,
            max_send_sge=4,
            max_recv_sge=4,
            max_inline_data=256,
        ),
        qp_type=qp_type,
        sq_sig_all=sq_sig_all,
    )


def multi_qp_dual_cq(
    *,
    pd: str,
    cq1: str,
    cq2: str,
    qp1: str,
    qp2: str,
    mr: str,
    buf: str,
    remote_qp1: str,
    remote_qp2: str,
    port: int = 1,
) -> Tuple[List[VerbCall], List[int]]:
    """
    Build a sequence where:
      - base_connect() brings (pd,cq1,qp1) to RTS
      - Create cq2 and a second qp2 bound to cq2, then INIT→RTR→RTS
      - RegMR once and exercise simple RECV/SEND pairs across the two QPs

    Returns:
      verbs: List[VerbCall]
      hotspots: indices of PostRecv/PostSend that should produce completions
    """
    verbs: List[VerbCall] = []
    hotspots: List[int] = []

    # 1) Baseline connection for qp1 (alloc PD, CQ1, QP1 and transition to RTS)
    v0, _ = base_connect(pd=pd, cq=cq1, qp=qp1, port=port, remote_qp=remote_qp1)
    verbs += v0

    # 2) Create CQ2 and QP2 (bound to CQ2), then transition QP2 to RTS
    verbs.append(CreateCQ(cq=cq2, cqe=256))
    init_attr_qp2 = _init_attr(send_cq=cq2, recv_cq=cq2)
    verbs.append(CreateQP(pd=pd, qp=qp2, init_attr_obj=init_attr_qp2, remote_qp=remote_qp2))

    verbs.append(
        ModifyQP(
            qp=qp2,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_INIT",
                pkey_index=0,
                port_num=port,
                qp_access_flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
            ),
            attr_mask="IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS",
        )
    )
    verbs.append(
        ModifyQP(
            qp=qp2,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_RTR",
                path_mtu="IBV_MTU_1024",
                dest_qp_num=0,  # runtime fills peer qpn
                rq_psn=0,
                max_dest_rd_atomic=1,
                min_rnr_timer=12,
                ah_attr=IbvAHAttr(
                    is_global=1,
                    port_num=port,
                    grh=IbvGlobalRoute(sgid_index=3, hop_limit=1, traffic_class=0, flow_label=0, dgid=""),
                ),
            ),
            attr_mask=(
                "IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_RQ_PSN | "
                "IBV_QP_DEST_QPN | IBV_QP_MIN_RNR_TIMER | IBV_QP_MAX_DEST_RD_ATOMIC"
            ),
        )
    )
    verbs.append(
        ModifyQP(
            qp=qp2,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_RTS",
                sq_psn=0,
                timeout=14,
                retry_cnt=7,
                rnr_retry=7,
                max_rd_atomic=1,
            ),
            attr_mask="IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC",
        )
    )

    # 3) Register one MR; use it for both RECV and SEND payloads
    verbs.append(
        RegMR(
            pd=pd,
            mr=mr,
            addr=buf,
            length=4096,
            access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
        )
    )

    # Post one RECV on qp1, then SEND from qp2 (twice to drive both paths)
    rwr1 = IbvRecvWR(wr_id=0x1101, sg_list=[IbvSge(mr=mr, length=256)], num_sge=1)
    verbs.append(PostRecv(qp=qp1, wr_obj=rwr1))
    hotspots.append(len(verbs) - 1)

    swr1 = IbvSendWR(
        wr_id=0x2101,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=128)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
    )
    verbs.append(PostSend(qp=qp2, wr_obj=swr1))
    hotspots.append(len(verbs) - 1)

    # A second round to exercise repeated posting with dual CQs
    rwr2 = IbvRecvWR(wr_id=0x1102, sg_list=[IbvSge(mr=mr, length=256)], num_sge=1)
    verbs.append(PostRecv(qp=qp1, wr_obj=rwr2))
    hotspots.append(len(verbs) - 1)

    swr2 = IbvSendWR(
        wr_id=0x2102,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=64)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
    )
    verbs.append(PostSend(qp=qp2, wr_obj=swr2))
    hotspots.append(len(verbs) - 1)

    return verbs, hotspots


def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None:
    """
    Auto-fill resource names and construct the scaffold.
    Requires two remote endpoints (remote_qp1, remote_qp2) and one buffer handle.
    """
    pd = gen_name("pd", global_snapshot, rng)
    cq1 = gen_name("cq", global_snapshot, rng)
    cq2 = gen_name("cq", global_snapshot, rng, excludes=[cq1])
    qp1 = gen_name("qp", global_snapshot, rng)
    qp2 = gen_name("qp", global_snapshot, rng, excludes=[qp1])
    mr = gen_name("mr", global_snapshot, rng)
    buf = _pick_unused_from_snap(global_snapshot, "buf", rng)

    remote_qp1 = _pick_unused_from_snap(global_snapshot, "remote_qp", rng)
    remote_qp2 = _pick_unused_from_snap(global_snapshot, "remote_qp", rng, excludes=[remote_qp1])

    if all([pd, cq1, cq2, qp1, qp2, mr, buf, remote_qp1, remote_qp2]):
        return multi_qp_dual_cq(
            pd=pd,
            cq1=cq1,
            cq2=cq2,
            qp1=qp1,
            qp2=qp2,
            mr=mr,
            buf=buf,
            remote_qp1=remote_qp1,
            remote_qp2=remote_qp2,
            port=1,
        )
    return None
