from __future__ import annotations

from typing import List, Tuple

from lib.fuzz_mutate import _pick_unused_from_snap, gen_name
from lib.IbvRecvWR import IbvRecvWR
from lib.IbvSendWR import IbvSendWR
from lib.IbvSge import IbvSge
from lib.scaffolds.base_connect import base_connect

# ---- Imports aligned with your package layout ----
from lib.verbs import PollCQ, PostRecv, PostSend, RegMR, VerbCall


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
        verbs2, hotspots2 = rnr_then_recover(pd, cq, qp, mr, buf)  # 为了保证成功，其实qp和cq需要绑定
        verbs += verbs2
        hotspots += hotspots2
        # print(verbs)
        return verbs, hotspots
    else:
        return None
