from __future__ import annotations

from typing import List, Tuple

from lib.fuzz_mutate import _pick_unused_from_snap, gen_name
from lib.IbvSendWR import IbvSendWR
from lib.IbvSge import IbvSge
from lib.scaffolds.base_connect import base_connect

# ---- Imports aligned with your package layout ----
from lib.verbs import PollCQ, PostSend, RegMR, VerbCall


def wr_chain_16(
    pd="pd0", cq="cq0", qp="qp0", mr="mrC", buf="bufC", chain_len: int = 16
) -> Tuple[List[VerbCall], List[int]]:
    """Post a linked list of Send WRs (next_wr) to exercise batched posting paths."""
    head = None
    for i in reversed(range(chain_len)):
        head = IbvSendWR(
            wr_id=0x6000 + i,
            opcode="IBV_WR_SEND",
            sg_list=[IbvSge(mr=mr, length=64)],
            num_sge=1,
            send_flags="IBV_SEND_SIGNALED",
            next_wr=head,
        )
    seq = [
        RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE"),
        PostSend(qp=qp, wr_obj=head),
        PollCQ(cq=cq),
    ]
    return seq, [1]


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
        verbs2, hotspots2 = wr_chain_16(pd, cq, qp, mr, buf)  # 为了保证成功，其实qp和cq需要绑定
        verbs += verbs2
        hotspots += hotspots2
        # print(verbs)
        return verbs, hotspots
    else:
        return None
