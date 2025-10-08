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

# ---- Imports aligned with your package layout ----
from lib.verbs import (
    AllocPD,
    CreateCQ,
    CreateQP,
    ModifyQP,
    PollCQ,
    PostRecv,
    PostSend,
    RegMR,
    VerbCall,
)


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


def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None:
    pd = gen_name("pd", global_snapshot, rng)
    cq = gen_name("cq", global_snapshot, rng)
    qp1 = gen_name("qp", global_snapshot, rng)
    qp2 = gen_name("qp", global_snapshot, rng, excludes=[qp1])
    mr1 = gen_name("mr", global_snapshot, rng)
    mr2 = gen_name("mr", global_snapshot, rng, excludes=[mr1])
    buf1 = _pick_unused_from_snap(global_snapshot, "buf", rng)
    buf2 = _pick_unused_from_snap(global_snapshot, "buf", rng, excludes=[buf1])
    remote_qp1 = _pick_unused_from_snap(global_snapshot, "remote_qp", rng)
    remote_qp2 = _pick_unused_from_snap(global_snapshot, "remote_qp", rng, excludes=[remote_qp1])
    if pd and cq and qp1 and qp2 and mr1 and mr2 and buf1 and buf2 and remote_qp1 and remote_qp2:
        return multi_qp_shared_cq(pd, cq, qp1, qp2, mr1, mr2, buf1, buf2, remote_qp1, remote_qp2)
    return None
