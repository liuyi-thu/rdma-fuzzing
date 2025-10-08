from __future__ import annotations

from typing import List, Tuple

from lib.fuzz_mutate import _pick_unused_from_snap, gen_name
from lib.scaffolds.base_connect import base_connect

# ---- Imports aligned with your package layout ----
from lib.verbs import QueryGID, QueryPKey, QueryPortAttr, QueryQP, VerbCall


def query_suite(pd="pd0", cq="cq0", qp="qp0", port=1) -> Tuple[List[VerbCall], List[int]]:
    """RTS 后查询一把，覆盖 query 分支（适配 RXE 环境）。"""
    seq: List[VerbCall] = [
        QueryQP(qp=qp, attr_mask="IBV_QP_STATE | IBV_QP_CAP | IBV_QP_PATH_MTU", out_init_attr=True),
        QueryPortAttr(port=port),
        QueryGID(port=port, index=0),
        QueryPKey(port=port, index=0),
    ]
    return seq, [0, 1, 2, 3]


def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None:
    pd = gen_name("pd", global_snapshot, rng)
    cq = gen_name("cq", global_snapshot, rng)
    qp = gen_name("qp", global_snapshot, rng)
    remote_qp = _pick_unused_from_snap(global_snapshot, "remote_qp", rng)
    if not (pd and cq and qp and remote_qp):
        return None
    verbs, hotspots = base_connect(pd, cq, qp, port=1, remote_qp=remote_qp)

    v2, h2 = query_suite(pd, cq, qp, port=1)
    base = len(verbs)
    verbs += v2
    hotspots += [base + i for i in h2]
    return verbs, hotspots
