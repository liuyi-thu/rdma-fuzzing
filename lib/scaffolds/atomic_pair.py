from __future__ import annotations

from typing import List, Tuple

from lib.fuzz_mutate import _pick_live_from_snap, _pick_unused_from_snap, gen_name
from lib.IbvSendWR import IbvAtomicInfo, IbvSendWR
from lib.IbvSge import IbvSge
from lib.scaffolds.base_connect import base_connect

# ---- Imports aligned with your package layout ----
from lib.verbs import (
    PollCQ,
    PostSend,
    RegMR,
    VerbCall,
)


def atomic_pair(
    pd="pd0", cq="cq0", qp="qp0", mr="mrA", buf="bufA", remote_mr="mrB"
) -> Tuple[List[VerbCall], List[int]]:
    """Try CAS then FetchAdd (8B). If caps unsupported, these should expose error paths."""
    cas = IbvSendWR(
        wr_id=0xA001,
        opcode="IBV_WR_ATOMIC_CMP_AND_SWP",
        sg_list=[IbvSge(mr=mr, length=8)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
        atomic=IbvAtomicInfo(
            remote_mr=remote_mr,
            compare_add=0,
            swap=1,
        ),
    )
    fad = IbvSendWR(
        wr_id=0xA002,
        opcode="IBV_WR_ATOMIC_FETCH_AND_ADD",
        sg_list=[IbvSge(mr=mr, length=8)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
        atomic=IbvAtomicInfo(remote_mr=remote_mr, compare_add=1, swap=None),
    )
    seq = [
        RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=cas),
        PollCQ(cq=cq),
        PostSend(qp=qp, wr_obj=fad),
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
    remote_mr = _pick_live_from_snap(local_snapshot, "remote_mr", rng)
    if pd and mr and cq and qp and buf:
        verbs2, hotspots2 = atomic_pair(pd, cq, qp, mr, buf, remote_mr)  # 为了保证成功，其实qp和cq需要绑定
        verbs += verbs2
        hotspots += hotspots2
        # print(verbs)
        return verbs, hotspots
    else:
        return None
