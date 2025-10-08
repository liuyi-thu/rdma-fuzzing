from __future__ import annotations

from typing import List, Tuple

from lib.fuzz_mutate import _pick_unused_from_snap, gen_name
from lib.IbvSendWR import IbvSendWR
from lib.IbvSge import IbvSge
from lib.scaffolds.base_connect import base_connect

# ---- Imports aligned with your package layout ----
from lib.verbs import CreateCQ, PollCQ, PostSend, RegMR, ResizeCQ, VerbCall


def resize_cq_flow(
    pd="pd0", cq="cqR", qp="qpR", mr="mrRZ", buf="bufRZ", old_cqe=128, new_cqe=512, burst=8
) -> Tuple[List[VerbCall], List[int]]:
    """先用较小 cqe 跑一波完成，再 ResizeCQ，之后再发一批 WR 验证。"""
    seq: List[VerbCall] = [
        CreateCQ(cq=cq, cqe=old_cqe),
        RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE"),
    ]
    for i in range(burst):
        wr = IbvSendWR(
            wr_id=0xA000 + i,
            opcode="IBV_WR_SEND",
            sg_list=[IbvSge(mr=mr, length=64)],
            num_sge=1,
            send_flags="IBV_SEND_SIGNALED",
        )
        seq.append(PostSend(qp=qp, wr_obj=wr))
    seq += [PollCQ(cq=cq)]
    seq.append(ResizeCQ(cq=cq, cqe=new_cqe))
    for i in range(burst):
        wr = IbvSendWR(
            wr_id=0xA100 + i,
            opcode="IBV_WR_SEND",
            sg_list=[IbvSge(mr=mr, length=64)],
            num_sge=1,
            send_flags="IBV_SEND_SIGNALED",
        )
        seq.append(PostSend(qp=qp, wr_obj=wr))
    seq += [PollCQ(cq=cq)]
    # 热点：ResizeCQ 前后的 PostSend 区段
    first_send = 2
    after_resize = first_send + burst + 2  # Poll + Resize
    hotspots = list(range(first_send, first_send + burst)) + list(range(after_resize, after_resize + burst))
    return seq, hotspots


def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None:
    pd = gen_name("pd", global_snapshot, rng)
    cq = gen_name("cq", global_snapshot, rng)
    qp = gen_name("qp", global_snapshot, rng)
    remote_qp = _pick_unused_from_snap(global_snapshot, "remote_qp", rng)
    if not (pd and cq and qp and remote_qp):
        return None
    verbs, hotspots = base_connect(pd, cq, qp, port=1, remote_qp=remote_qp)

    # 建 MR
    mr = gen_name("mr", global_snapshot, rng)
    buf = _pick_unused_from_snap(global_snapshot, "buf", rng)
    if not (mr and buf):
        return None
    verbs.append(RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE"))

    # 先发一批
    burst = 8
    first_batch_idx = []
    for i in range(burst):
        wr = IbvSendWR(
            wr_id=0xCA00 + i,
            opcode="IBV_WR_SEND",
            sg_list=[IbvSge(mr=mr, length=64)],
            num_sge=1,
            send_flags="IBV_SEND_SIGNALED",
        )
        first_batch_idx.append(len(verbs))
        verbs.append(PostSend(qp=qp, wr_obj=wr))
    verbs.append(PollCQ(cq=cq))

    # Resize 到更大
    verbs.append(ResizeCQ(cq=cq, cqe=512))

    # 再发一批
    second_batch_idx = []
    for i in range(burst):
        wr = IbvSendWR(
            wr_id=0xCB00 + i,
            opcode="IBV_WR_SEND",
            sg_list=[IbvSge(mr=mr, length=64)],
            num_sge=1,
            send_flags="IBV_SEND_SIGNALED",
        )
        second_batch_idx.append(len(verbs))
        verbs.append(PostSend(qp=qp, wr_obj=wr))
    verbs.append(PollCQ(cq=cq))

    hotspots += first_batch_idx + second_batch_idx
    return verbs, hotspots
