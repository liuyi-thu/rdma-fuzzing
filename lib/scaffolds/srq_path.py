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

# ---- Imports aligned with your package layout ----
from lib.verbs import (
    AllocPD,
    CreateCQ,
    CreateQP,
    CreateSRQ,
    ModifyQP,
    PollCQ,
    PostSend,
    PostSRQRecv,
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
                    grh=IbvGlobalRoute(sgid_index=3, hop_limit=1, traffic_class=0, flow_label=0, dgid=""),
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


def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None:
    pd = gen_name("pd", global_snapshot, rng)
    cq = gen_name("cq", global_snapshot, rng)
    srq = gen_name("srq", global_snapshot, rng)
    qp = gen_name("qp", global_snapshot, rng)
    mr = gen_name("mr", global_snapshot, rng)
    buf = _pick_unused_from_snap(global_snapshot, "buf", rng)
    remote_qp = _pick_unused_from_snap(global_snapshot, "remote_qp", rng)
    if pd and cq and srq and qp and mr and buf and remote_qp:
        return srq_path(pd, cq, srq, qp, mr, buf, remote_qp)
    return None
