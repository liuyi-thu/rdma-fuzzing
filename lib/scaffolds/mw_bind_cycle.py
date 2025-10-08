from __future__ import annotations

from typing import List, Tuple

from lib.fuzz_mutate import _pick_unused_from_snap, gen_name
from lib.IbvSendWR import IbvSendWR
from lib.IbvSge import IbvSge
from lib.scaffolds.base_connect import base_connect

# ---- Imports aligned with your package layout ----
from lib.verbs import AllocMW, BindMW, DeallocMW, PollCQ, PostSend, RegMR, VerbCall


def mw_bind_cycle(
    pd="pd0", cq="cq0", qp="qp0", mr="mrMW", buf="bufMW", mw="mw0", mw_type="IBV_MW_TYPE_1"
) -> Tuple[List[VerbCall], List[int]]:
    """覆盖 MW 的发放/违规/修复路径。"""
    seq: List[VerbCall] = [
        RegMR(pd=pd, mr=mr, addr=buf, length=4096, access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ"),
        AllocMW(pd=pd, mw=mw, mw_type=mw_type),
        # 合法绑定
        BindMW(mw=mw, mr=mr, access="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ"),
    ]
    # 触发一次使用
    wr_ok = IbvSendWR(
        wr_id=0xC001,
        opcode="IBV_WR_SEND",
        sg_list=[IbvSge(mr=mr, length=64)],
        num_sge=1,
        send_flags="IBV_SEND_SIGNALED",
    )
    seq += [PostSend(qp=qp, wr_obj=wr_ok), PollCQ(cq=cq)]
    # 故意非法再次绑定（例如去掉必须权限）
    seq.append(BindMW(mw=mw, mr=mr, access="0"))
    # 修复为合法
    seq.append(BindMW(mw=mw, mr=mr, access="IBV_ACCESS_LOCAL_WRITE"))
    seq += [DeallocMW(mw=mw)]
    hotspots = [2, 3, 5]  # 首次合法 bind + 首次使用 + 修复后的 bind
    return seq, hotspots


def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None:
    pd = gen_name("pd", global_snapshot, rng)
    cq = gen_name("cq", global_snapshot, rng)
    qp = gen_name("qp", global_snapshot, rng)
    remote_qp = _pick_unused_from_snap(global_snapshot, "remote_qp", rng)
    if not (pd and cq and qp and remote_qp):
        return None
    verbs, hotspots = base_connect(pd, cq, qp, port=1, remote_qp=remote_qp)

    mr = gen_name("mr", global_snapshot, rng)
    mw = gen_name("mw", global_snapshot, rng)
    buf = _pick_unused_from_snap(global_snapshot, "buf", rng)
    if not (mr and mw and buf):
        return None

    v2, h2 = mw_bind_cycle(pd, cq, qp, mr, buf, mw=mw, mw_type="IBV_MW_TYPE_1")
    base = len(verbs)
    verbs += v2
    hotspots += [base + i for i in h2]
    return verbs, hotspots
