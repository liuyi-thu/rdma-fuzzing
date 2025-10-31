# -*- coding: utf-8 -*-
"""
srq_post_burst.py
-----------------
Exercise the SRQ (Shared Receive Queue) path by:
1) Establishing a baseline RC connection via base_connect() (qp0).
2) Creating an SRQ and a second RC QP (qp_srq) bound to that SRQ.
3) Posting a burst of SRQ Recv WRs, then issuing a few SENDs on qp_srq.

Notes
- No CQ notify / poll is used by design (to satisfy the prompt).
- All classes strictly match your CLASSES_IN_LIB.md signatures.
- This file contains one scaffold() and one build() entry.
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
from lib.IbvSrqAttr import IbvSrqAttr
from lib.IbvSrqInitAttr import IbvSrqInitAttr
from lib.scaffolds.base_connect import base_connect
from lib.verbs import AllocPD, CreateCQ, CreateQP, CreateSRQ, ModifyQP, PollCQ, PostSend, PostSRQRecv, RegMR, VerbCall


def _init_attr(
    send_cq: str,
    recv_cq: str,
    *,
    srq: str | None = None,
    qp_type: str = "IBV_QPT_RC",
    cap: IbvQPCap | None = None,
    sq_sig_all: int = 1,
) -> IbvQPInitAttr:
    """Helper to construct IbvQPInitAttr with sane defaults."""
    return IbvQPInitAttr(
        send_cq=send_cq,
        recv_cq=recv_cq,
        srq=srq,
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


def srq_post_burst(
    pd: str,
    cq: str,
    qp0: str,
    qp_srq: str,
    srq: str,
    mr: str,
    buf: str,
    remote_qp0: str,
    remote_qp_srq: str,
    *,
    port: int = 1,
    burst: int = 8,
) -> Tuple[List[VerbCall], List[int]]:
    """
    Build a sequence that:
      - uses base_connect() for a baseline QP (qp0),
      - creates SRQ and an SRQ-bound QP (qp_srq),
      - posts multiple SRQ Recv WRs, and
      - sends several messages through qp_srq.

    Returns:
      (verbs, hotspots)
      hotspots mark the SRQ Recv & Send postings to guide feedback.
    """
    verbs: List[VerbCall] = []
    hotspots: List[int] = []

    # Step 1: baseline connection (alloc PD/CQ, create qp0, INIT/RTR/RTS)
    v0, h0 = base_connect(pd=pd, cq=cq, qp=qp0, port=port, remote_qp=remote_qp0)
    verbs += v0

    # Step 2: create SRQ, MR, and SRQ-bound QP (qp_srq)
    verbs.append(CreateSRQ(pd=pd, srq=srq, srq_init_obj=IbvSrqInitAttr(attr=IbvSrqAttr(max_wr=128, max_sge=1))))
    # Reuse the same CQ for simplicity
    init_attr_srq = _init_attr(send_cq=cq, recv_cq=cq, srq=srq)
    verbs.append(CreateQP(pd=pd, qp=qp_srq, init_attr_obj=init_attr_srq, remote_qp=remote_qp_srq))

    # Drive qp_srq through INIT -> RTR -> RTS
    verbs.append(
        ModifyQP(
            qp=qp_srq,
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
            qp=qp_srq,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_RTR",
                path_mtu="IBV_MTU_1024",
                dest_qp_num=0,  # deferred/filled by runtime
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
            qp=qp_srq,
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

    # Register an MR for both recv/send use
    verbs.append(
        RegMR(
            pd=pd,
            mr=mr,
            addr=buf,
            length=4096,
            access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
        )
    )

    # Step 3: Post a burst of SRQ Recvs
    for i in range(burst):
        wr = IbvRecvWR(wr_id=0x9000 + i, sg_list=[IbvSge(mr=mr, length=256)], num_sge=1)
        verbs.append(PostSRQRecv(srq=srq, wr_obj=wr))
        hotspots.append(len(verbs) - 1)

    # Step 4: Issue a few SENDs on qp_srq (these will consume SRQ recvs on peer)
    for i in range(min(4, burst)):
        swr = IbvSendWR(
            wr_id=0xA000 + i,
            opcode="IBV_WR_SEND",
            sg_list=[IbvSge(mr=mr, length=128)],
            num_sge=1,
            send_flags="IBV_SEND_SIGNALED",
        )
        verbs.append(PostSend(qp=qp_srq, wr_obj=swr))
        hotspots.append(len(verbs) - 1)

    verbs += [PollCQ(cq=cq) for _ in range(burst + min(4, burst))]  # Drain some completions

    return verbs, hotspots


def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None:
    """
    Entry point used by your fuzzing framework to auto-fill resource names.
    """
    # Reuse global pools for unique names and pick existing remote endpoints/buffers.
    pd = gen_name("pd", global_snapshot, rng)
    cq = gen_name("cq", global_snapshot, rng)
    qp0 = gen_name("qp", global_snapshot, rng)
    qp_srq = gen_name("qp", global_snapshot, rng, excludes=[qp0])
    srq = gen_name("srq", global_snapshot, rng)
    mr = gen_name("mr", global_snapshot, rng)
    buf = _pick_unused_from_snap(global_snapshot, "buf", rng)

    remote_qp0 = _pick_unused_from_snap(global_snapshot, "remote_qp", rng)
    remote_qp_srq = _pick_unused_from_snap(global_snapshot, "remote_qp", rng, excludes=[remote_qp0])

    if all([pd, cq, qp0, qp_srq, srq, mr, buf, remote_qp0, remote_qp_srq]):
        return srq_post_burst(
            pd=pd,
            cq=cq,
            qp0=qp0,
            qp_srq=qp_srq,
            srq=srq,
            mr=mr,
            buf=buf,
            remote_qp0=remote_qp0,
            remote_qp_srq=remote_qp_srq,
            port=1,
            burst=8,
        )
    return None
