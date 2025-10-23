from __future__ import annotations

from typing import List, Tuple

from lib.fuzz_mutate import _pick_unused_from_snap, gen_name
from lib.IbvSendWR import IbvSendWR
from lib.IbvSge import IbvSge
from lib.scaffolds.base_connect import base_connect

# ---- Imports aligned with your package layout ----
from lib.verbs import PollCQ, PostSend, RegMR, VerbCall


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
        RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=w1),
        PollCQ(cq=cq),
        PostSend(qp=qp, wr_obj=w2),
        PollCQ(cq=cq),
        PostSend(qp=qp, wr_obj=w3),
        PollCQ(cq=cq),
    ]
    return seq, [1, 3]


def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None:
    pd = gen_name("pd", global_snapshot, rng)
    cq = gen_name("cq", global_snapshot, rng)
    qp = gen_name("qp", global_snapshot, rng)
    remote_qp = _pick_unused_from_snap(global_snapshot, "remote_qp", rng)
    if pd and cq and qp and remote_qp:
        verbs, hotspots = base_connect(pd, cq, qp, port=1, remote_qp=remote_qp)  # remote_qpn TBD
    else:
        return None

    mr = gen_name("mr", global_snapshot, rng)
    buf = _pick_unused_from_snap(global_snapshot, "buf", rng)
    if pd and mr and cq and qp and buf:
        verbs2, hotspots2 = sge_boundary(pd, cq, qp, mr, buf)  # 为了保证成功，其实qp和cq需要绑定
        verbs += verbs2
        hotspots += hotspots2
        # print(verbs)
        return verbs, hotspots
    else:
        return None
