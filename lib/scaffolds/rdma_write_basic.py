from __future__ import annotations

from typing import List, Tuple

from lib.fuzz_mutate import _pick_live_from_snap, _pick_unused_from_snap, gen_name
from lib.IbvSendWR import IbvRdmaInfo, IbvSendWR
from lib.IbvSge import IbvSge
from lib.scaffolds.base_connect import base_connect

# ---- Imports aligned with your package layout ----
from lib.verbs import PollCQ, PostSend, RegMR, VerbCall


def rdma_write_basic(
    pd="pd0", cq="cq0", qp="qp0", mr="mr0", buf="buf0", remote_mr="mr1", length=128, inline=False
) -> Tuple[List[VerbCall], List[int]]:
    wr = IbvSendWR(
        wr_id=0x3001,
        opcode="IBV_WR_RDMA_WRITE",
        sg_list=[IbvSge(mr=mr, length=length)],
        num_sge=1,
        send_flags=("IBV_SEND_SIGNALED | IBV_SEND_INLINE" if inline else "IBV_SEND_SIGNALED"),
        rdma=IbvRdmaInfo(
            remote_mr=remote_mr,
            # remote_addr="REMOTE_ADDR", rkey="REMOTE_RKEY" --- IGNORE ---
        ),
    )
    seq = [
        RegMR(pd=pd, mr=mr, addr=buf, length=max(length, 4096), access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=wr),
        PollCQ(cq=cq),
    ]
    return seq, [1]


def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None:
    pd = gen_name("pd", global_snapshot, rng)
    cq = gen_name("cq", global_snapshot, rng)
    qp = gen_name("qp", global_snapshot, rng)
    remote_qp = _pick_unused_from_snap(global_snapshot, "remote_qp", rng)
    if pd and cq and qp and remote_qp:
        verbs, hotspots = base_connect(pd, cq, qp, port=1, remote_qp=remote_qp)
    else:
        return None
    mr = gen_name("mr", global_snapshot, rng)
    buf = _pick_unused_from_snap(global_snapshot, "buf", rng)
    remote_mr = _pick_live_from_snap(local_snapshot, "remote_mr", rng)
    if pd and mr and cq and qp and buf:
        verbs2, hotspots2 = rdma_write_basic(pd, cq, qp, mr, buf, remote_mr=remote_mr)
        verbs += verbs2
        hotspots += hotspots2
        return verbs, hotspots
    else:
        return None
