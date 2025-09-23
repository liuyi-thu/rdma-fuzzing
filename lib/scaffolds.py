# scaffolds.py
"""
最小可行序列（scaffold）集合：返回 List[VerbCall] + hotspots（允许变异/插入的位置索引）
注意：
- 这里引用的 VerbCall（AllocPD/CreateCQ/CreateQP/ModifyQP/PostRecv/PostSend/PollCQ/RegMR）
  请按你现有实现导入；下面仅示意 import。
- Ibv* 结构体完全使用你当前定义（IbvQPInitAttr/IbvQPAttr/IbvSendWR/IbvRecvWR/IbvSge）。
"""

from typing import List, Tuple

from .verbs import AllocPD, CreateCQ, CreateQP, ModifyQP, RegMR, PostRecv, PostSend, PollCQ, VerbCall

from .IbvQPInitAttr import IbvQPInitAttr
from .IbvQPAttr import IbvQPAttr
from .IbvSendWR import IbvSendWR, IBV_WR_OPCODE_ENUM
from .IbvRecvWR import IbvRecvWR
from .IbvSge import IbvSge
from .IbvQPCap import IbvQPCap
from .IbvAHAttr import IbvAHAttr, IbvGlobalRoute


def sc_base_connect(pd="pd0", cq="cq0", qp="qp0", port=1, remote_qp_sym="peer0") -> Tuple[List[object], List[int]]:
    """
    目标：RESET→INIT→RTR→RTS，打通控制面（不触发数据面 WR）
    - IbvQPInitAttr：显式把 srq 设为 None，避免 contract 误要求 SRQ 资源
    - 三个 ModifyQP：按 INIT → RTR → RTS 顺序设置必要字段
    """
    init_attr = IbvQPInitAttr(  # 最好能把 qp 和 cq 绑定上，implicit dependency
        send_cq=cq,
        recv_cq=cq,
        srq=None,  # 显式 None，避免 SRQ 依赖
        qp_type="IBV_QPT_RC",  # RC
        cap=IbvQPCap(max_send_wr=10, max_recv_wr=10, max_send_sge=10, max_recv_sge=10),
        sq_sig_all=0,
    )

    verbs: List[object] = [
        AllocPD(pd),
        CreateCQ(cq=cq, cqe=256),
        CreateQP(pd=pd, qp=qp, init_attr_obj=init_attr, remote_qp=remote_qp_sym),
        # → INIT
        ModifyQP(
            qp=qp,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_INIT",
                pkey_index=0,
                port_num=port,
                qp_access_flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
            ),
            # 你的 ModifyQP 支持 attr_mask 字符串/bitmask；按你现有风格传关键位
            attr_mask="IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS",
        ),
        # → RTR
        ModifyQP(
            qp=qp,
            attr_obj=IbvQPAttr(
                qp_state="IBV_QPS_RTR",
                path_mtu="IBV_MTU_1024",  # 先取一个稳妥的 MTU 档
                dest_qp_num=0,  # 由 DeferredValue 绑定到 remote.QP（见 IbvQPAttr.dest_qp_num）  :contentReference[oaicite:11]{index=11}
                rq_psn=0,
                max_dest_rd_atomic=1,
                min_rnr_timer=12,
                # ah_attr 可用默认工厂生成，也可以在外部按你的拓扑准备
                ah_attr=IbvAHAttr(
                    is_global=1,
                    dlid="",  # DeferredValue
                    sl=0,
                    src_path_bits=0,
                    port_num=1,
                    grh=IbvGlobalRoute(
                        sgid_index=1,
                        hop_limit=1,
                        traffic_class=0,
                        flow_label=0,
                        dgid="",  # DeferredValue
                    ),
                ),
            ),
            attr_mask="IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_RQ_PSN | IBV_QP_DEST_QPN | IBV_QP_MIN_RNR_TIMER | IBV_QP_MAX_DEST_RD_ATOMIC",
        ),
        # → RTS
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

    hotspots = [3, 4, 5]  # 三个 ModifyQP
    return verbs, hotspots


def sc_send_recv(
    pd="pd0", cq="cq0", qp="qp0", mr="mr0", buf="buf0", recv_len=256, send_len=128, inline=False, build_mr=True
) -> Tuple[List[object], List[int]]:
    """
    目标：最短成功 SEND/RECV 路径（先 Recv 后 Send，再 PollCQ 成功）
    - IbvRecvWR/IbvSendWR: sg_list 用 IbvSge(mr=...)，你这边会自动把 addr/length/lkey 绑定到 MR  :contentReference[oaicite:12]{index=12}
    - IbvRecvWR: on_after_mutate 会把 num_sge 维护为 len(sg_list)  :contentReference[oaicite:13]{index=13}
    - IbvSendWR: opcode 用 "IBV_WR_SEND"，send_flags 可含 SIGNALED/INLINE  :contentReference[oaicite:14]{index=14}
    """
    recv_wr = IbvRecvWR(
        wr_id=0x1001,
        sg_list=[IbvSge(mr=mr, length=recv_len)],
        num_sge=1,
        next_wr=None,
    )

    send_wr = IbvSendWR(
        wr_id=0x2001,
        opcode="IBV_WR_SEND",  # 见 IBV_WR_OPCODE_ENUM  :contentReference[oaicite:15]{index=15}
        sg_list=[IbvSge(mr=mr, length=send_len)],
        num_sge=1,
        send_flags=("IBV_SEND_SIGNALED | IBV_SEND_INLINE" if inline else "IBV_SEND_SIGNALED"),
        next_wr=None,
    )

    if build_mr:
        verbs: List[object] = [
            # 连接前缀建议用 sc_base_connect() 的前 3+3 步先到 RTS；此处只列数据面动作
            RegMR(
                pd=pd,
                mr=mr,
                addr=buf,
                length=max(recv_len, send_len, 4096),
                access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
            ),
            PostRecv(qp=qp, wr_obj=recv_wr),
            PostSend(qp=qp, wr_obj=send_wr),
            PollCQ(cq=cq),  # 你的 PollCQ 只要 CQ 存在即可轮询出 CQE  :contentReference[oaicite:16]{index=16}
        ]
    else:
        verbs: List[object] = [
            PostRecv(qp=qp, wr_obj=recv_wr),
            PostSend(qp=qp, wr_obj=send_wr),
            PollCQ(cq=cq),  # 你的 PollCQ 只要 CQ 存在即可轮询出 CQE  :contentReference[oaicite:16]{index=16}
        ]
    hotspots = [1, 2]  # 两个 WR 非常适合做 bandit（len、flags、num_sge）
    return verbs, hotspots


def sc_rdma_write(
    pd="pd0", cq="cq0", qp="qp0", mr="mr0", buf="buf0", rkey_sym="remote_mr0", length=128, inline=True
) -> Tuple[List[object], List[int]]:
    """
    目标：最短 RDMA WRITE → Poll 成功
    - IbvSendWR.rdma 使用 IbvRdmaInfo（内部从 remote.MR 取 remote_addr/rkey 的 DeferredValue）  :contentReference[oaicite:17]{index=17}
    """
    wr = IbvSendWR(
        wr_id=0x3001,
        opcode="IBV_WR_RDMA_WRITE",
        sg_list=[IbvSge(mr=mr, length=length)],
        num_sge=1,
        send_flags=("IBV_SEND_SIGNALED | IBV_SEND_INLINE" if inline else "IBV_SEND_SIGNALED"),
        rdma=None,  # 让 IbvSendWR 的 OptionalValue factory 生成 IbvRdmaInfo（绑定 remote.MR）  :contentReference[oaicite:18]{index=18}
        next_wr=None,
    )

    verbs: List[object] = [
        RegMR(pd=pd, mr=mr, addr=buf, length=max(length, 4096), access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=wr),
        PollCQ(cq=cq),
    ]
    hotspots = [1]  # 这条 RDMA_WRITE（len/inline 等字段）
    return verbs, hotspots


class ScaffoldBuilder:
    def __init__(self):
        pass
        # self.port = port
        # self.caps = caps or {}

    @staticmethod
    def base_connect(pd="pd0", cq="cq0", qp="qp0", port=1, remote_qp=0) -> Tuple[List[VerbCall], List[int]]:
        return sc_base_connect(pd=pd, cq=cq, qp=qp, port=port, remote_qp_sym=remote_qp)

    @staticmethod
    def send_recv(
        pd="pd0", cq="cq0", qp="qp0", mr="mr0", buf="buf0", build_mr=True
    ) -> Tuple[List[VerbCall], List[int]]:
        return sc_send_recv(pd=pd, cq=cq, qp=qp, mr=mr, buf=buf, build_mr=build_mr)

    @staticmethod
    def rdma_write(pd="pd0", cq="cq0", qp="qp0", mr="mr0", buf="buf0", raddr=0, rkey=0):
        return sc_rdma_write(pd=pd, cq=cq, qp=qp, mr=mr, buf=buf, raddr=raddr, rkey=rkey)


if __name__ == "__main__":
    # 直接运行本脚本时，打印一个示例 Scaffold
    verbs, hotspots = ScaffoldBuilder.send_recv()
    for i, v in enumerate(verbs):
        print(f"{i:02d}: {v}")
    print("Hotspots:", hotspots)
