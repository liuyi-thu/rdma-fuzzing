# Insertion-point calculator for RDMA verbs using the uploaded lib/
# It simulates resource states across the existing verb sequence and checks both
# contract-level requirements and extra semantic guards (e.g., PostSend needs QP≥RTS).
#
# It will output a CSV + a nicely formatted table for a few example candidates.
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.append("/mnt/data")
import lib.contracts as contracts
import lib.ibv_all as ibv_all
import lib.verbs as verbs

State = contracts.State

# === Build the baseline verb list exactly as in the user's example ===
buf_size = 1024
verb_list = [
    verbs.AllocPD(pd="PD0"),
    verbs.CreateCQ(cq="CQ0"),
    verbs.RegMR(
        pd="PD0",
        buf="bufs[0]",
        length=buf_size,
        mr="MR0",
        flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
    ),
    verbs.CreateQP(
        qp="QP0",
        pd="PD0",
        init_attr_obj=ibv_all.IbvQPInitAttr(
            send_cq="CQ0",
            recv_cq="CQ0",
            cap=ibv_all.IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1),
            qp_type="IBV_QPT_RC",
            sq_sig_all=1,
        ),
    ),
    verbs.ModifyQP(
        qp="QP0",
        attr_mask="IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS",
        attr_obj=ibv_all.IbvQPAttr(
            qp_state="IBV_QPS_INIT",
            pkey_index=0,
            port_num=1,
            qp_access_flags="IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE",
        ),
    ),
    verbs.ModifyQP(
        qp="QP0",
        attr_mask="IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER",
        attr_obj=ibv_all.IbvQPAttr(
            qp_state="IBV_QPS_RTR",
            path_mtu="IBV_MTU_1024",
            dest_qp_num="local_remote_qp_map[QP0->qp_num]",
            rq_psn=0,
            max_dest_rd_atomic=1,
            min_rnr_timer=12,
            ah_attr=ibv_all.IbvAHAttr(
                is_global=1,
                dlid="remote_info.lid",
                sl=0,
                src_path_bits=0,
                port_num=1,
                grh=ibv_all.IbvGlobalRoute(
                    sgid_index=1,
                    hop_limit=1,
                    traffic_class=0,
                    flow_label=0,
                    dgid=ibv_all.IbvGID(src_var="remote_info.gid"),
                ),
            ),
        ),
    ),
    verbs.ModifyQP(
        qp="QP0",
        attr_mask="IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC",
        attr_obj=ibv_all.IbvQPAttr(
            qp_state="IBV_QPS_RTS", timeout=14, retry_cnt=7, rnr_retry=7, sq_psn=0, max_rd_atomic=1
        ),
    ),
    verbs.PostSend(
        qp="QP0",
        wr_obj=ibv_all.IbvSendWR(
            wr_id=1,
            num_sge=1,
            opcode="IBV_WR_SEND",
            send_flags="IBV_SEND_SIGNALED",
            sg_list=[ibv_all.IbvSge(addr="(uintptr_t)bufs[0]", length="MSG_SIZE", lkey="MR0->lkey")],
        ),
    ),
    verbs.PollCQ(cq="CQ0"),
    verbs.DestroyQP(qp="QP0"),
    verbs.DestroyCQ(cq="CQ0"),
    verbs.DeallocPD(pd="PD0"),
    verbs.DeregMR(mr="MR0"),
]


# === Utilities: small state lattice & helpers ===
# For PD/CQ/MR: ALLOCATED < DESTROYED
# For QP: RESET < INIT < RTR < RTS < SQD? < ERR < DESTROYED (we'll keep unknown states at their enum value)
# We'll simply compare Enum value order.
def state_geq(a: Optional[State], b: Optional[State]) -> bool:
    if b is None:  # nothing required
        return True
    if a is None:
        return False
    try:
        return a.value >= b.value
    except Exception:
        return a == b


@dataclass
class Snapshot:
    # res_states[(rtype, name)] = State or None
    res_states: Dict[Tuple[str, str], Optional[State]]


def apply_instantiated_contract(snap: Snapshot, ic) -> Snapshot:
    rs = dict(snap.res_states)
    # produces override/create
    for p in ic.produces:
        rs[(p.rtype, p.name_attr)] = p.state
    # transitions update state
    for t in ic.transitions:
        rs[(t.rtype, t.name_attr)] = t.to_state
    return Snapshot(rs)


def build_prefix_snapshots(verbs_list: List[Any]) -> List[Snapshot]:
    snaps = [Snapshot(res_states={})]
    cur = snaps[0]
    for v in verbs_list:
        ic = v.instantiate_contract()
        cur = apply_instantiated_contract(cur, ic)
        snaps.append(cur)
    return snaps  # length = len(verbs_list)+1, index i = state before inserting at i


# Extract "MR0" from "MR0->lkey" style strings to model data deps
ptr_pat = re.compile(r"\b(?P<rtype>MR|PD|CQ|QP|SRQ|WQ)(?P<idx>\d+)->")


def extract_pointer_tokens(obj: Any) -> List[Tuple[str, str]]:
    seen, q = set(), [obj]
    toks: List[Tuple[str, str]] = []
    while q:
        o = q.pop()
        oid = id(o)
        if oid in seen:
            continue
        seen.add(oid)
        if o is None:
            continue
        if hasattr(o, "value"):
            q.append(getattr(o, "value"))
            continue
        if isinstance(o, str):
            for m in ptr_pat.finditer(o.upper()):
                rtype = m.group("rtype").lower()
                name = f"{m.group('rtype')}{m.group('idx')}"
                toks.append((rtype, name))
        elif isinstance(o, (list, tuple, set)):
            q.extend(list(o))
        elif hasattr(o, "__dict__"):
            q.extend(list(o.__dict__.values()))
    return toks


# === Semantic guards (beyond bare contracts) ===
def semantic_checks(candidate: Any, snap: Snapshot) -> List[str]:
    """Return list of failure reasons; empty list means ok"""
    fails: List[str] = []
    res = snap.res_states

    def cur(rtype: str, name: str) -> Optional[State]:
        return res.get((rtype, name))

    # PostSend: require qp≥RTS and all MR tokens exist (ALLOCATED and not DESTROYED)
    if isinstance(candidate, verbs.PostSend):
        # QP
        qp_name = getattr(candidate, "qp", None)
        if not qp_name:
            fails.append("PostSend missing qp name")
        else:
            s = cur("qp", qp_name)
            if s is None:
                fails.append(f"QP {qp_name} not created")
            else:
                # require >= RTS
                if not state_geq(s, State.RTS):
                    fails.append(f"QP {qp_name} state {s.name if s else None} < RTS")
        # MR via lkey pointers
        mr_tokens = [(rtype, name) for rtype, name in extract_pointer_tokens(candidate) if rtype == "mr"]
        for _, mr_name in mr_tokens:
            s = cur("mr", mr_name)
            if s is None:
                fails.append(f"MR {mr_name} not available")
            elif s == State.DESTROYED:
                fails.append(f"MR {mr_name} destroyed")
    # PollCQ: require cq exists and not destroyed
    if isinstance(candidate, verbs.PollCQ):
        cq_name = getattr(candidate, "cq", None)
        if not cq_name:
            fails.append("PollCQ missing cq name")
        else:
            s = cur("cq", cq_name)
            if s is None:
                fails.append(f"CQ {cq_name} not created")
            elif s == State.DESTROYED:
                fails.append(f"CQ {cq_name} destroyed")
    # DestroyQP/DestroyCQ/DeregMR/DeallocPD: resource must exist and not yet destroyed
    destroy_map = {
        verbs.DestroyQP: "qp",
        verbs.DestroyCQ: "cq",
        verbs.DeregMR: "mr",
        verbs.DeallocPD: "pd",
    }
    for klass, rtype in destroy_map.items():
        if isinstance(candidate, klass):
            name = getattr(candidate, rtype, None)
            s = cur(rtype, name) if name else None
            if not name:
                fails.append(f"{klass.__name__} missing {rtype} name")
            elif s is None:
                fails.append(f"{rtype.upper()} {name} not created")
            elif s == State.DESTROYED:
                fails.append(f"{rtype.upper()} {name} already destroyed")

    return fails


def check_contract_requirements(candidate: Any, snap: Snapshot) -> List[str]:
    """Validate basic requires in candidate.instantiate_contract() against snapshot."""
    fails: List[str] = []
    ic = candidate.instantiate_contract()
    res = snap.res_states

    for r in ic.requires:
        cur = res.get((r.rtype, r.name_attr))
        if cur is None:
            fails.append(f"require {r.rtype}:{r.name_attr} missing")
        else:
            # if a state is specified, require current >= required
            if getattr(r, "state", None) is not None and not state_geq(cur, r.state):
                fails.append(f"require {r.rtype}:{r.name_attr} needs {r.state.name}, got {cur.name}")
    # Optional: also forbid using DESTROYED
    for r in ic.requires:
        cur = res.get((r.rtype, r.name_attr))
        if cur == State.DESTROYED:
            fails.append(f"require {r.rtype}:{r.name_attr} is DESTROYED")
    return fails


def insertion_report(verbs_list: List[Any], candidate: Any) -> List[Dict[str, str]]:
    snaps = build_prefix_snapshots(verbs_list)
    report: List[Dict[str, str]] = []
    for i, snap in enumerate(snaps):
        # Evaluate requirements at position i (before verbs_list[i])
        fails = []
        fails += check_contract_requirements(candidate, snap)
        fails += semantic_checks(candidate, snap)

        ok = len(fails) == 0
        report.append(
            {
                "insert_index": i,
                "ok": "yes" if ok else "no",
                "reasons": "; ".join(fails) if fails else "",
            }
        )
    return report


# === Try with a couple of candidates ===
cand1 = verbs.PostSend(
    qp="QP0",
    wr_obj=ibv_all.IbvSendWR(
        wr_id=999,
        num_sge=1,
        opcode="IBV_WR_SEND",
        send_flags="IBV_SEND_SIGNALED",
        sg_list=[ibv_all.IbvSge(addr="(uintptr_t)bufs[0]", length="MSG_SIZE", lkey="MR0->lkey")],
    ),
)
cand2 = verbs.PollCQ(cq="CQ0")

rep1 = insertion_report(verb_list, cand1)
rep2 = insertion_report(verb_list, cand2)

# Export CSVs and show as dataframes
import pandas as pd

df1 = pd.DataFrame(rep1)
df2 = pd.DataFrame(rep2)

from caas_jupyter_tools import display_dataframe_to_user

display_dataframe_to_user("PostSend(QP0, MR0->lkey) 插入点", df1)
display_dataframe_to_user("PollCQ(CQ0) 插入点", df2)

p1 = Path("/mnt/data/insertion_report_postsend.csv")
df1.to_csv(p1, index=False)
p2 = Path("/mnt/data/insertion_report_pollcq.csv")
df2.to_csv(p2, index=False)

print("Saved:")
print(str(p1))
print(str(p2))
