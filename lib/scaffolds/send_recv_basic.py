from __future__ import annotations

from typing import List, Tuple

from lib.fuzz_mutate import _pick_unused_from_snap, gen_name
from lib.IbvRecvWR import IbvRecvWR
from lib.IbvSendWR import IbvSendWR
from lib.IbvSge import IbvSge
from lib.scaffolds.base_connect import base_connect

# ---- Imports aligned with your package layout ----
from lib.verbs import PollCQ, PostRecv, PostSend, RegMR, VerbCall


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
        verbs2, hotspots2 = send_recv_basic(pd, cq, qp, mr, buf)  # 为了保证成功，其实qp和cq需要绑定
        verbs += verbs2
        hotspots += hotspots2
        return verbs, hotspots
    else:
        return None
