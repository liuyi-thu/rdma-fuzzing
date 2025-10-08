from __future__ import annotations

from typing import List, Tuple

from lib.fuzz_mutate import _pick_unused_from_snap, gen_name
from lib.IbvSendWR import IbvSendWR
from lib.IbvSge import IbvSge
from lib.scaffolds.base_connect import base_connect

# ---- Imports aligned with your package layout ----
from lib.verbs import CreateCQ, PollCQ, PostSend, RegMR, VerbCall


def cq_pressure(
    pd="pd0", cq="cqP", qp="qpP", mr="mrP", buf="bufP", burst: int = 64, reuse_cq: bool = False
) -> Tuple[List[VerbCall], List[int]]:
    """
    Stress CQ with many completions.
    If reuse_cq=True, will NOT create a new CQ and will reuse the provided `cq` name.
    Otherwise, creates a fresh CQ sized for the burst.
    """
    seq: List[VerbCall] = []
    if not reuse_cq:
        seq.append(CreateCQ(cq=cq, cqe=max(256, burst * 2)))

    # Ensure MR exists for WRs
    seq.append(RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE"))

    # Post N sends (separate WRs, not linked), then poll multiple times
    for i in range(burst):
        wr = IbvSendWR(
            wr_id=0x7000 + i,
            opcode="IBV_WR_SEND",
            sg_list=[IbvSge(mr=mr, length=64)],
            num_sge=1,
            send_flags="IBV_SEND_SIGNALED",
        )
        seq.append(PostSend(qp=qp, wr_obj=wr))

    seq += [PollCQ(cq=cq) for _ in range(3)]

    # Hotspots: the PostSend range we appended（根据是否创建CQ来对齐索引）
    first_ps = 2 if not reuse_cq else 1
    return seq, list(range(first_ps, first_ps + burst))


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
        verbs2, hotspots2 = cq_pressure(pd, cq, qp, mr, buf, reuse_cq=True)  # 为了保证成功，其实qp和cq需要绑定
        verbs += verbs2
        hotspots += hotspots2
        # print(verbs)
        return verbs, hotspots
    else:
        return None
