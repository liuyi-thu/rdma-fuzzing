# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Tuple

# 资源名选择：沿用你已有的工具函数
from lib.fuzz_mutate import _pick_unused_from_snap, gen_name

# --- 结构体/属性类（签名见 CLASSES_IN_LIB.md） ---
from lib.IbvAHAttr import IbvAHAttr, IbvGlobalRoute
from lib.IbvQPAttr import IbvQPAttr
from lib.IbvQPCap import IbvQPCap
from lib.IbvQPInitAttr import IbvQPInitAttr
from lib.IbvRecvWR import IbvRecvWR
from lib.IbvSendWR import IbvSendWR
from lib.IbvSge import IbvSge

# --- verbs（签名见 CLASSES_IN_LIB.md） ---
from lib.verbs import (
    AllocPD,
    CreateCQ,
    CreateQP,
    ModifyQP,
    PollCQ,
    PostRecv,
    PostSend,
    RegMR,
    ReqNotifyCQ,
    VerbCall,
)

# ---------------------------------------------------------------------------
# 内联的 base_connect：RESET→INIT→RTR→RTS
# * 仅构建控制面，数据面由外层 scaffold 追加
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
    pd: str = "pd0",
    cq: str = "cq0",
    qp: str = "qp0",
    *,
    port: int = 1,
    remote_qp: str = "peer0",
) -> Tuple[List[VerbCall], List[int]]:
    init_attr = _init_attr(cq, cq, srq=None)

    verbs: List[VerbCall] = [
        AllocPD(pd=pd),
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
                dest_qp_num=0,  # 由你的运行时在对端握手后填充
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
# notify_cq_basic：请求 CQ 通知 + 触发一次完成，覆盖 CQ 通知路径
# 要点：
# - 先 ReqNotifyCQ，再 PostRecv/PostSend，随后 PollCQ
# - 不使用 completion channel（兼容你当前 runner）
# ---------------------------------------------------------------------------


def notify_cq_basic(
    pd: str = "pd0",
    cq: str = "cq0",
    qp: str = "qp0",
    mr: str = "mr0",
    buf: str = "buf0",
    recv_len: int = 256,
    send_len: int = 64,
) -> Tuple[List[VerbCall], List[int]]:
    """请求 CQ 通知并通过一次 SEND/RECV 触发，适合 RXE/RC-only 环境。"""

    # 1) 注册 MR（本地写即可；也可包含远程读写权限以便后续复用）
    seq: List[VerbCall] = [
        RegMR(
            pd=pd,
            mr=mr,
            addr=buf,
            length=max(recv_len, send_len, 4096),
            access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
        )
    ]

    # 2) 先请求 CQ 通知（solicited_only=0：所有完成都通知）
    seq.append(ReqNotifyCQ(cq=cq, solicited_only=0))

    # 3) 预投一个 RECV，然后发一个 SEND 触发完成
    recv_wr = IbvRecvWR(wr_id=0x1001, next_wr=None, sg_list=[IbvSge(mr=mr, length=recv_len)], num_sge=1)
    send_wr = IbvSendWR(
        wr_id=0x2001,
        next_wr=None,
        sg_list=[IbvSge(mr=mr, length=send_len)],
        num_sge=1,
        opcode="IBV_WR_SEND",
        send_flags="IBV_SEND_SIGNALED",
    )
    seq.extend(
        [
            PostRecv(qp=qp, wr_obj=recv_wr),
            PostSend(qp=qp, wr_obj=send_wr),
            PollCQ(cq=cq),
        ]
    )

    # 将热点放在会产生日志/完成路径的几个点：ReqNotify、PostSend、PollCQ
    hotspots = [1, 3, 4]
    return seq, hotspots


# ---------------------------------------------------------------------------
# build：自动补齐资源名；必要时内联建链
# ---------------------------------------------------------------------------


def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None:
    # 生成或选择资源名
    pd = gen_name("pd", global_snapshot, rng)
    cq = gen_name("cq", global_snapshot, rng)
    qp = gen_name("qp", global_snapshot, rng)
    mr = gen_name("mr", global_snapshot, rng)
    buf = _pick_unused_from_snap(global_snapshot, "buf", rng)
    remote_qp = _pick_unused_from_snap(global_snapshot, "remote_qp", rng)

    if not (pd and cq and qp and mr and buf and remote_qp):
        return None

    # 先建链（RESET→INIT→RTR→RTS）
    verbs, hotspots = base_connect(pd=pd, cq=cq, qp=qp, port=1, remote_qp=remote_qp)

    # 追加通知 + 一发一收
    v2, h2 = notify_cq_basic(pd=pd, cq=cq, qp=qp, mr=mr, buf=buf)
    verbs.extend(v2)

    # 调整热点索引（追加段的偏移）
    base_len = len(verbs) - len(v2)
    hotspots = hotspots + [base_len + i for i in h2]
    return verbs, hotspots
