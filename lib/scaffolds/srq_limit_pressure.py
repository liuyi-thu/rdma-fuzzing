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
    ModifySRQ,
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


def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None:
    # 目标：创建 SRQ 并绑定到 QP，完成建链后降低 srqlimit，然后连续发送施压
    pd = gen_name("pd", global_snapshot, rng)
    cq = gen_name("cq", global_snapshot, rng)
    srq = gen_name("srq", global_snapshot, rng)
    qp = gen_name("qp", global_snapshot, rng)
    mr = gen_name("mr", global_snapshot, rng)
    buf = _pick_unused_from_snap(global_snapshot, "buf", rng)
    remote_qp = _pick_unused_from_snap(global_snapshot, "remote_qp", rng)
    if not (pd and cq and srq and qp and mr and buf and remote_qp):
        return None

    verbs = []
    hotspots = []

    # 1) 控制面：PD/SRQ/CQ/QP (QP 与 SRQ 绑定)
    verbs.append(AllocPD(pd))
    verbs.append(CreateSRQ(pd=pd, srq=srq, srq_init_obj=IbvSrqInitAttr(attr=IbvSrqAttr(max_wr=128, max_sge=1))))
    verbs.append(CreateCQ(cq=cq, cqe=512))

    # QP 初始化属性（绑定 SRQ），cap 保守一些，确保可跑通
    init_attr = IbvQPInitAttr(
        send_cq=cq,
        recv_cq=cq,
        srq=srq,
        cap=IbvQPCap(
            max_send_wr=128,
            max_recv_wr=0,  # SRQ 模式下 recv_wr=0
            max_send_sge=4,
            max_recv_sge=0,
            max_inline_data=256,
        ),
        qp_type="IBV_QPT_RC",
        sq_sig_all=0,
    )
    verbs.append(CreateQP(pd=pd, qp=qp, init_attr_obj=init_attr, remote_qp=remote_qp))

    # 2) INIT -> RTR -> RTS
    verbs.append(
        ModifyQP(
            qp=qp,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_INIT",
                pkey_index=0,
                port_num=1,
                qp_access_flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
            ),
            attr_mask="IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS",
        )
    )

    verbs.append(
        ModifyQP(
            qp=qp,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_RTR",
                path_mtu="IBV_MTU_1024",
                dest_qp_num=0,  # 由你的运行时/导入脚本填充
                rq_psn=0,
                max_dest_rd_atomic=1,
                min_rnr_timer=12,
                ah_attr=IbvAHAttr(
                    is_global=1,
                    port_num=1,
                    grh=IbvGlobalRoute(sgid_index=0, hop_limit=1, traffic_class=0, flow_label=0, dgid=""),
                ),
            ),
            attr_mask=(
                "IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | "
                "IBV_QP_RQ_PSN | IBV_QP_DEST_QPN | "
                "IBV_QP_MIN_RNR_TIMER | IBV_QP_MAX_DEST_RD_ATOMIC"
            ),
        )
    )

    verbs.append(
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
            attr_mask=(
                "IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | "
                "IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC"
            ),
        )
    )
    hotspots += [len(verbs) - 3, len(verbs) - 2, len(verbs) - 1]  # 三次状态迁移

    # 3) 数据面：注册 MR，预填 SRQ Recv，降低 srqlimit
    verbs.append(RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE"))
    # 先投两个 SRQ Recv
    verbs.append(PostSRQRecv(srq=srq, wr_obj=IbvRecvWR(wr_id=0xD101, sg_list=[IbvSge(mr=mr, length=256)], num_sge=1)))
    verbs.append(PostSRQRecv(srq=srq, wr_obj=IbvRecvWR(wr_id=0xD102, sg_list=[IbvSge(mr=mr, length=256)], num_sge=1)))
    # 降低 srqlimit，制造回压
    verbs.append(ModifySRQ(srq=srq, srq_attr_obj=IbvSrqAttr(srq_limit=1)))

    # 4) 连续发送施压 + Poll
    burst = 32
    send_start = len(verbs)
    for i in range(burst):
        wr = IbvSendWR(
            wr_id=0xD300 + i,
            opcode="IBV_WR_SEND",
            sg_list=[IbvSge(mr=mr, length=64)],
            num_sge=1,
            send_flags="IBV_SEND_SIGNALED",
        )
        verbs.append(PostSend(qp=qp, wr_obj=wr))

    verbs.append(PollCQ(cq=cq))
    verbs.append(PollCQ(cq=cq))

    hotspots += list(range(send_start, send_start + burst))
    return verbs, hotspots
