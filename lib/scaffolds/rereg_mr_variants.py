from __future__ import annotations

from typing import List, Tuple

from lib.fuzz_mutate import _pick_unused_from_snap, gen_name
from lib.IbvSendWR import IbvSendWR
from lib.IbvSge import IbvSge
from lib.scaffolds.base_connect import base_connect

# ---- Imports aligned with your package layout ----
from lib.verbs import AllocPD, PollCQ, PostSend, RegMR, ReRegMR, VerbCall


def rereg_mr_variants(
    pd="pd0", other_pd="pd1", cq="cq0", qp="qp0", mr="mrRR", buf="bufRR", length=4096
) -> Tuple[List[VerbCall], List[int]]:
    """RegMR → ReRegMR 多种 flags；中间穿插一次 send 验证每次变更后可用性。"""
    seq: List[VerbCall] = [
        AllocPD(other_pd),  # 用于换 PD 的一例
        RegMR(pd=pd, mr=mr, addr=buf, length=length, access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ"),
        # 1) 改 access
        ReRegMR(
            mr=mr,
            flags="IBV_REREG_MR_CHANGE_ACCESS",
            access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
        ),
    ]
    wr_ok = IbvSendWR(
        wr_id=0xB001,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=128)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
    )
    seq += [PostSend(qp=qp, wr_obj=wr_ok), PollCQ(cq=cq)]
    # 2) 改 translation（地址/长度）
    seq.append(ReRegMR(mr=mr, flags="IBV_REREG_MR_CHANGE_TRANSLATION", addr=buf, length=length))
    seq += [PostSend(qp=qp, wr_obj=wr_ok), PollCQ(cq=cq)]
    # 3) 改 PD
    seq.append(ReRegMR(mr=mr, flags="IBV_REREG_MR_CHANGE_PD", pd=other_pd))
    seq += [PostSend(qp=qp, wr_obj=wr_ok), PollCQ(cq=cq)]
    hotspots = [2, 4, 6, 8]  # 三次 ReRegMR 之后的 PostSend 紧邻处
    return seq, hotspots


def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None:
    pd = gen_name("pd", global_snapshot, rng)
    other_pd = gen_name("pd", global_snapshot, rng, excludes=[pd])
    cq = gen_name("cq", global_snapshot, rng)
    qp = gen_name("qp", global_snapshot, rng)
    remote_qp = _pick_unused_from_snap(global_snapshot, "remote_qp", rng)
    if not (pd and other_pd and cq and qp and remote_qp):
        return None
    verbs, hotspots = base_connect(pd, cq, qp, port=1, remote_qp=remote_qp)

    mr = gen_name("mr", global_snapshot, rng)
    buf = _pick_unused_from_snap(global_snapshot, "buf", rng)
    if not (mr and buf):
        return None

    v2, h2 = rereg_mr_variants(pd, other_pd, cq, qp, mr, buf, length=4096)
    base = len(verbs)
    verbs += v2
    hotspots += [base + i for i in h2]
    return verbs, hotspots
