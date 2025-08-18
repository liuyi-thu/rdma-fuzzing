import importlib
import re
import sys
import types
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


# --- ensure lib pseudo-package (so lib.* relative imports in ibv_all.py work) ---
def _ensure_lib_pkg():
    if "lib" not in sys.modules:
        libpkg = types.ModuleType("lib")
        libpkg.__path__ = ["/mnt/data"]
        sys.modules["lib"] = libpkg
    return (
        importlib.import_module("lib.ibv_all"),
        importlib.import_module("lib.verbs"),
        importlib.import_module("lib.contracts"),
    )


ibv_all, verbs, contracts = _ensure_lib_pkg()
State = contracts.State

# Try to import concrete spec classes (fall back to lightweight ones if unavailable)
RequireSpec = getattr(contracts, "RequireSpec", None)
ProduceSpec = getattr(contracts, "ProduceSpec", None)
TransitionSpec = getattr(contracts, "TransitionSpec", None)
InstantiatedContract = getattr(contracts, "InstantiatedContract", None)

# lightweight spec as fallback
if RequireSpec is None:

    @dataclass
    class RequireSpec:
        rtype: str
        state: Optional[State]
        name_attr: str


if ProduceSpec is None:

    @dataclass
    class ProduceSpec:
        rtype: str
        state: Optional[State]
        name_attr: str


if TransitionSpec is None:

    @dataclass
    class TransitionSpec:
        rtype: str
        from_state: Optional[State]
        to_state: State
        name_attr: str


if InstantiatedContract is None:

    @dataclass
    class InstantiatedContract:
        requires: List[RequireSpec] = field(default_factory=list)
        produces: List[ProduceSpec] = field(default_factory=list)
        transitions: List[TransitionSpec] = field(default_factory=list)


# --- pointer token extraction ("MR0->lkey" → ("mr","MR0")) ---
PTR_PAT = re.compile(r"\b(?P<rtype>MR|PD|CQ|QP|SRQ|WQ)(?P<idx>\d+)->")


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
            for m in PTR_PAT.finditer(o.upper()):
                rtype = m.group("rtype").lower()
                name = f"{m.group('rtype')}{m.group('idx')}"
                toks.append((rtype, name))
        elif isinstance(o, (list, tuple, set)):
            q.extend(list(o))
        elif hasattr(o, "__dict__"):
            q.extend(list(o.__dict__.values()))
    return toks


# --- augmented instantiate: upgrade implicit data deps (MR pointers) into formal requires ---
def instantiate_augmented(v: Any) -> InstantiatedContract:
    base = v.instantiate_contract()
    reqs = list(getattr(base, "requires", []))  # shallow copy
    prods = list(getattr(base, "produces", []))
    trans = list(getattr(base, "transitions", []))

    # Upgrade pointers in both send/recv WR (e.g., MR0->lkey)
    ptrs = extract_pointer_tokens(v)
    for rtype, name in ptrs:
        if rtype == "mr":
            # avoid duplicates
            if not any((r.rtype == "mr" and r.name_attr == name) for r in reqs):
                reqs.append(RequireSpec(rtype="mr", state=getattr(State, "ALLOCATED", None), name_attr=name))

    return InstantiatedContract(requires=reqs, produces=prods, transitions=trans)


# --- per-guard policy (hard / warn / ignore) ---
@dataclass
class GuardMode:
    mode: str = "hard"  # "hard", "warn", "ignore"


@dataclass
class Policy:
    # Contract violations always hard block.
    modifyqp_transition: GuardMode = field(default_factory=lambda: GuardMode("hard"))
    postsend_qp_min: GuardMode = field(default_factory=lambda: GuardMode("hard"))
    postrecv_qp_min: GuardMode = field(default_factory=lambda: GuardMode("warn"))
    pollcq_exists: GuardMode = field(default_factory=lambda: GuardMode("hard"))
    destroycq_clean: GuardMode = field(default_factory=lambda: GuardMode("hard"))
    destroyqp_clean: GuardMode = field(default_factory=lambda: GuardMode("hard"))
    deallocpd_no_deps: GuardMode = field(default_factory=lambda: GuardMode("hard"))
    cqe_pairing: GuardMode = field(default_factory=lambda: GuardMode("warn"))  # ReqNotifyCQ / AckCQEvents pairing


def _apply_guard(policy: Policy, key: str, msg: str, reasons: List[str], warnings: List[str]):
    gm = getattr(policy, key)
    if gm.mode == "hard":
        reasons.append(msg)
    elif gm.mode == "warn":
        warnings.append(msg)
    # ignore => no-op


# --- name normalization helper (verbs may wrap identifiers as Value(...)) ---
def _norm_name(x: Any) -> Optional[str]:
    if x is None:
        return None
    if isinstance(x, str):
        return x
    # Some lib wrappers expose .value
    v = getattr(x, "value", None)
    if isinstance(v, str):
        return v
    # fallback to string
    try:
        return str(x)
    except Exception:
        return None


# --- engine state ---
@dataclass
class Snapshot:
    res_states: Dict[Tuple[str, str], Optional[State]] = field(default_factory=dict)  # (rtype,name) -> state
    qp_bind: Dict[str, Dict[str, str]] = field(default_factory=dict)  # qp -> {"send_cq":..., "recv_cq":...}
    cq_dirty: Dict[str, bool] = field(default_factory=dict)  # cq -> True if there was a PostSend since last PollCQ
    parents: Dict[Tuple[str, str], Set[Tuple[str, str]]] = field(
        default_factory=dict
    )  # resource -> direct parent resources
    cq_event_pending: Dict[str, bool] = field(
        default_factory=dict
    )  # CQ -> pending notify events (ReqNotifyCQ not yet Ack'ed)
    coverage_transitions: Set[Tuple[str, Optional[State], State]] = field(default_factory=set)  # (rtype, from, to)


def add_parent_edge(snap: Snapshot, child: Tuple[str, str], parents: List[Tuple[str, str]]):
    snap.parents.setdefault(child, set()).update(parents)


def apply_to_snapshot(snap: Snapshot, v: Any) -> Snapshot:
    rs = dict(snap.res_states)
    qp_bind = {k: dict(v) for k, v in snap.qp_bind.items()}
    cq_dirty = dict(snap.cq_dirty)
    parents = {k: set(v) for k, v in snap.parents.items()}
    cq_event_pending = dict(snap.cq_event_pending)
    coverage = set(snap.coverage_transitions)
    out = Snapshot(rs, qp_bind, cq_dirty, parents, cq_event_pending, coverage)

    ic = instantiate_augmented(v)
    direct_parents = [(r.rtype, r.name_attr) for r in ic.requires]

    # Bindings / side-effect trackers
    if isinstance(v, verbs.CreateQP):
        qp_name = _norm_name(getattr(v, "qp", None))
        if qp_name and hasattr(v, "init_attr_obj") and v.init_attr_obj is not None:
            send_cq = getattr(v, "init_attr_obj").__dict__.get("send_cq", None)
            recv_cq = getattr(v, "init_attr_obj").__dict__.get("recv_cq", None)
            if isinstance(send_cq, str):
                out.qp_bind.setdefault(qp_name, {})["send_cq"] = send_cq
                out.cq_dirty.setdefault(send_cq, False)
                out.cq_event_pending.setdefault(send_cq, False)
            if isinstance(recv_cq, str):
                out.qp_bind.setdefault(qp_name, {})["recv_cq"] = recv_cq
                out.cq_dirty.setdefault(recv_cq, False)
                out.cq_event_pending.setdefault(recv_cq, False)

    if isinstance(v, verbs.PostSend):
        qp_name = _norm_name(getattr(v, "qp", None))
        if qp_name and qp_name in out.qp_bind and "send_cq" in out.qp_bind[qp_name]:
            cq = out.qp_bind[qp_name]["send_cq"]
            out.cq_dirty[cq] = True

    # Optional verbs if present: ReqNotifyCQ / AckCQEvents
    if hasattr(verbs, "ReqNotifyCQ") and isinstance(v, getattr(verbs, "ReqNotifyCQ")):
        cq = getattr(v, "cq", None)
        if isinstance(cq, str):
            out.cq_event_pending[cq] = True
    if hasattr(verbs, "AckCQEvents") and isinstance(v, getattr(verbs, "AckCQEvents")):
        cq = getattr(v, "cq", None)
        if isinstance(cq, str):
            out.cq_event_pending[cq] = False

    if isinstance(v, verbs.PollCQ):
        cq_name = _norm_name(getattr(v, "cq", None))
        if isinstance(cq_name, str):
            out.cq_dirty[cq_name] = False

    # Apply effects
    for p in ic.produces:
        key = (p.rtype, p.name_attr)
        out.res_states[key] = p.state
        add_parent_edge(out, key, direct_parents)
    for t in ic.transitions:
        key = (t.rtype, t.name_attr)
        # record coverage
        out.coverage_transitions.add((t.rtype, None if t.from_state is None else t.from_state, t.to_state))
        out.res_states[key] = t.to_state

    return out


def build_prefix_snapshots(seq: List[Any]) -> List[Snapshot]:
    snaps = [Snapshot()]
    cur = snaps[0]
    for v in seq:
        cur = apply_to_snapshot(cur, v)
        snaps.append(cur)
    return snaps


def state_geq(a: Optional[State], b: Optional[State]) -> bool:
    if b is None:  # nothing required
        return True
    if a is None:
        return False
    try:
        return a.value >= b.value
    except Exception:
        return a == b


def check_contract_requirements(candidate: Any, snap: Snapshot) -> List[str]:
    fails: List[str] = []
    ic = instantiate_augmented(candidate)
    for r in ic.requires:
        cur = snap.res_states.get((r.rtype, r.name_attr))
        if cur is None:
            fails.append(f"require {r.rtype}:{r.name_attr} missing")
        elif cur == State.DESTROYED:
            fails.append(f"require {r.rtype}:{r.name_attr} is DESTROYED")
        elif getattr(r, "state", None) is not None and not state_geq(cur, r.state):
            fails.append(f"require {r.rtype}:{r.name_attr} needs {r.state.name}, got {cur.name}")
    return fails


# Dynamic ALLOWED_PREV for ModifyQP
ALLOWED_PREV = {}
if hasattr(State, "INIT") and hasattr(State, "RESET"):
    ALLOWED_PREV[State.INIT] = {State.RESET, State.INIT}
if hasattr(State, "RTR") and hasattr(State, "INIT"):
    ALLOWED_PREV[State.RTR] = {State.INIT, getattr(State, "RTR")}
if hasattr(State, "RTS") and hasattr(State, "RTR"):
    ALLOWED_PREV[State.RTS] = {State.RTR, getattr(State, "RTS")}
if hasattr(State, "ERR"):
    ALLOWED_PREV[State.ERR] = {s for s in State}


# --- transitive dependency: is target an ancestor (via parents edges) of res? ---
def _is_ancestor(
    parents: Dict[Tuple[str, str], Set[Tuple[str, str]]], res: Tuple[str, str], target: Tuple[str, str]
) -> bool:
    seen: Set[Tuple[str, str]] = set()
    stack = [res]
    while stack:
        cur = stack.pop()
        if cur == target:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        for p in parents.get(cur, set()):
            stack.append(p)
    return False


def _live_dependents_of(snap: Snapshot, target: Tuple[str, str]) -> List[Tuple[str, str]]:
    out = []
    for (rtype, name), st in snap.res_states.items():
        if st is None or st == State.DESTROYED:
            continue
        if _is_ancestor(snap.parents, (rtype, name), target):
            out.append((rtype, name))
    return out


def semantic_checks(candidate: Any, snap: Snapshot, policy: Policy) -> Tuple[List[str], List[str]]:
    reasons: List[str] = []
    warnings: List[str] = []
    rs = snap.res_states

    def cur(rtype: str, name: str) -> Optional[State]:
        return rs.get((rtype, name))

    # ModifyQP legality
    if isinstance(candidate, verbs.ModifyQP):
        qp_name = _norm_name(getattr(candidate, "qp", None))
        ic = instantiate_augmented(candidate)
        dst = None
        for t in ic.transitions:
            if t.rtype == "qp" and (qp_name is None or t.name_attr == qp_name):
                dst = t.to_state
                break
        if qp_name is None:
            _apply_guard(policy, "modifyqp_transition", "ModifyQP missing qp", reasons, warnings)
        else:
            s = cur("qp", qp_name)
            if s is None:
                _apply_guard(policy, "modifyqp_transition", f"QP {qp_name} not created", reasons, warnings)
            else:
                allowed = ALLOWED_PREV.get(dst, None)
                if allowed is not None and s not in allowed:
                    _apply_guard(
                        policy,
                        "modifyqp_transition",
                        f"ModifyQP {qp_name} to {dst.name} not allowed from {s.name}",
                        reasons,
                        warnings,
                    )

    # PostSend: QP≥RTS
    if isinstance(candidate, verbs.PostSend):
        qp_name = _norm_name(getattr(candidate, "qp", None))
        s = cur("qp", qp_name) if qp_name else None
        if not qp_name:
            _apply_guard(policy, "postsend_qp_min", "PostSend missing qp name", reasons, warnings)
        elif s is None:
            _apply_guard(policy, "postsend_qp_min", f"QP {qp_name} not created", reasons, warnings)
        elif hasattr(State, "RTS") and not state_geq(s, State.RTS):
            _apply_guard(policy, "postsend_qp_min", f"QP {qp_name} state {s.name} < RTS", reasons, warnings)

    # PostRecv (if exists): QP≥INIT
    if hasattr(verbs, "PostRecv") and isinstance(candidate, getattr(verbs, "PostRecv")):
        qp_name = _norm_name(getattr(candidate, "qp", None))
        s = cur("qp", qp_name) if qp_name else None
        if not qp_name:
            _apply_guard(policy, "postrecv_qp_min", "PostRecv missing qp name", reasons, warnings)
        elif s is None:
            _apply_guard(policy, "postrecv_qp_min", f"QP {qp_name} not created", reasons, warnings)
        elif hasattr(State, "INIT") and not state_geq(s, State.INIT):
            _apply_guard(policy, "postrecv_qp_min", f"QP {qp_name} state {s.name} < INIT", reasons, warnings)

    # PollCQ: CQ exists and not destroyed
    if isinstance(candidate, verbs.PollCQ):
        cq_name = _norm_name(getattr(candidate, "cq", None))
        s = cur("cq", cq_name) if cq_name else None
        if not cq_name:
            _apply_guard(policy, "pollcq_exists", "PollCQ missing cq name", reasons, warnings)
        elif s is None:
            _apply_guard(policy, "pollcq_exists", f"CQ {cq_name} not created", reasons, warnings)
        elif s == State.DESTROYED:
            _apply_guard(policy, "pollcq_exists", f"CQ {cq_name} destroyed", reasons, warnings)

    # DestroyCQ: forbid if dirty or pending events
    if isinstance(candidate, verbs.DestroyCQ):
        cq_name = _norm_name(getattr(candidate, "cq", None))
        s = cur("cq", cq_name) if cq_name else None
        if not cq_name:
            _apply_guard(policy, "destroycq_clean", "DestroyCQ missing cq name", reasons, warnings)
        elif s is None:
            _apply_guard(policy, "destroycq_clean", f"CQ {cq_name} not created", reasons, warnings)
        elif s == State.DESTROYED:
            _apply_guard(policy, "destroycq_clean", f"CQ {cq_name} already destroyed", reasons, warnings)
        else:
            if snap.cq_dirty.get(cq_name, False):
                _apply_guard(
                    policy, "destroycq_clean", f"CQ {cq_name} has unpolled completions (dirty)", reasons, warnings
                )
            if snap.cq_event_pending.get(cq_name, False):
                _apply_guard(
                    policy, "cqe_pairing", f"CQ {cq_name} has pending notify events (not Ack'ed)", reasons, warnings
                )

    # DestroyQP: block if its send_cq is dirty
    if isinstance(candidate, verbs.DestroyQP):
        qp_name = _norm_name(getattr(candidate, "qp", None))
        s = cur("qp", qp_name) if qp_name else None
        if not qp_name:
            _apply_guard(policy, "destroyqp_clean", "DestroyQP missing qp name", reasons, warnings)
        elif s is None:
            _apply_guard(policy, "destroyqp_clean", f"QP {qp_name} not created", reasons, warnings)
        elif s == State.DESTROYED:
            _apply_guard(policy, "destroyqp_clean", f"QP {qp_name} already destroyed", reasons, warnings)
        else:
            if qp_name in snap.qp_bind and "send_cq" in snap.qp_bind[qp_name]:
                cq = snap.qp_bind[qp_name]["send_cq"]
                if snap.cq_dirty.get(cq, False):
                    _apply_guard(
                        policy,
                        "destroyqp_clean",
                        f"QP {qp_name}'s send CQ {cq} has unpolled completions (dirty)",
                        reasons,
                        warnings,
                    )

    # DeallocPD: no live dependents (transitive)
    if isinstance(candidate, verbs.DeallocPD):
        pd_name = _norm_name(getattr(candidate, "pd", None))
        s = cur("pd", pd_name) if pd_name else None
        if not pd_name:
            _apply_guard(policy, "deallocpd_no_deps", "DeallocPD missing pd name", reasons, warnings)
        elif s is None:
            _apply_guard(policy, "deallocpd_no_deps", f"PD {pd_name} not created", reasons, warnings)
        elif s == State.DESTROYED:
            _apply_guard(policy, "deallocpd_no_deps", f"PD {pd_name} already destroyed", reasons, warnings)
        else:
            deps = _live_dependents_of(snap, ("pd", pd_name))
            if deps:
                _apply_guard(
                    policy,
                    "deallocpd_no_deps",
                    f"PD {pd_name} has live dependents (transitive): {', '.join(sorted([f'{r}:{n}' for r, n in deps]))}",
                    reasons,
                    warnings,
                )

    return reasons, warnings


def build_prefix(seq: List[Any]) -> List[Snapshot]:
    return build_prefix_snapshots(seq)


def find_insertion_points(seq: List[Any], candidate: Any, policy: Optional[Policy] = None) -> List[Dict[str, str]]:
    if policy is None:
        policy = Policy()  # defaults: mostly hard
    snaps = build_prefix_snapshots(seq)
    rows: List[Dict[str, str]] = []
    for i, snap in enumerate(snaps):
        reasons = []
        warnings: List[str] = []
        reasons += check_contract_requirements(candidate, snap)
        sem_reasons, sem_warnings = semantic_checks(candidate, snap, policy)
        reasons += sem_reasons
        warnings += sem_warnings
        row = {"insert_index": i, "ok": "yes" if not reasons else "no", "reasons": "; ".join(reasons)}
        if warnings:
            row["warnings"] = "; ".join(warnings)
        rows.append(row)
    return rows


# --- Graph builder using augmented contracts ---
@dataclass(frozen=True)
class _GNode:
    kind: str  # "verb" or "res"
    id: str
    label: str


@dataclass(frozen=True)
class _GEdge:
    src: str
    dst: str
    label: Optional[str] = None
    style: Optional[str] = None


def _vid(i: int) -> str:
    return f"v{i}"


def _rid(rt: str, name: str) -> str:
    return f"r_{rt}_{name}"


def build_graph_dot(seq: List[Any]) -> str:
    nodes: Dict[str, _GNode] = {}
    edges: List[_GEdge] = []

    def add_res(rt, name):
        rid = _rid(rt, name)
        nodes.setdefault(rid, _GNode("res", rid, f"{rt}:{name}"))

    def add_verb(i, v):
        nid = _vid(i)
        nodes.setdefault(nid, _GNode("verb", nid, f"{i}. {v.__class__.__name__}"))

    # Pre-collect all resources that will be produced so their nodes exist
    for v in seq:
        ic = instantiate_augmented(v)
        for p in ic.produces:
            add_res(p.rtype, p.name_attr)

    for i, v in enumerate(seq):
        add_verb(i, v)
        ic = instantiate_augmented(v)
        for r in ic.requires:
            add_res(r.rtype, r.name_attr)
            edges.append(
                _GEdge(
                    _rid(r.rtype, r.name_attr),
                    _vid(i),
                    label=(r.state.name if getattr(r, "state", None) else None),
                    style="dashed",
                )
            )
        for p in ic.produces:
            add_res(p.rtype, p.name_attr)
            edges.append(
                _GEdge(_vid(i), _rid(p.rtype, p.name_attr), label=(p.state.name if getattr(p, "state", None) else None))
            )
        for t in ic.transitions:
            add_res(t.rtype, t.name_attr)
            edges.append(_GEdge(_vid(i), _rid(t.rtype, t.name_attr), label=f"→ {t.to_state.name}", style="dashed"))

    lines = ["digraph RDMA {", "  rankdir=LR;", '  node [shape=box, style="rounded"];']
    for n in nodes.values():
        shape = "ellipse" if n.kind == "verb" else "box"
        lines.append(f'  {n.id} [label="{n.label}", shape={shape}];')
    for e in edges:
        attrs = []
        if e.label:
            attrs.append(f'label="{e.label}"')
        if e.style:
            attrs.append(f'style="{e.style}"')
        s = f" [{', '.join(attrs)}]" if attrs else ""
        lines.append(f"  {e.src} -> {e.dst}{s};")
    lines.append("}")
    return "\n".join(lines)


# --- Coverage report ---
@dataclass
class CoverageReport:
    transitions: Set[Tuple[str, Optional[State], State]]


def coverage_report(seq: List[Any]) -> CoverageReport:
    snaps = build_prefix_snapshots(seq)
    if snaps:
        return CoverageReport(transitions=snaps[-1].coverage_transitions)
    return CoverageReport(transitions=set())


# --- Sequence validator (for swap/delete proposals) ---
def validate_sequence(seq: List[Any], policy: Optional[Policy] = None) -> Tuple[bool, List[str]]:
    if policy is None:
        policy = Policy()
    cur = Snapshot()
    for idx, v in enumerate(seq):
        # base contract against current snapshot
        reasons = check_contract_requirements(v, cur)
        sem_reasons, _ = semantic_checks(v, cur, policy)
        reasons += sem_reasons
        if reasons:
            return False, [f"@{idx}:{v.__class__.__name__} => " + "; ".join(reasons)]
        # advance
        cur = apply_to_snapshot(cur, v)
    return True, []


# --- Mutation suggestions ---
def suggest_insertions(seq: List[Any], candidates: List[Any], policy: Optional[Policy] = None) -> Dict[str, List[int]]:
    if policy is None:
        policy = Policy()
    out: Dict[str, List[int]] = {}
    for cand in candidates:
        rows = find_insertion_points(seq, cand, policy=policy)
        key = cand.__class__.__name__
        out[key] = [int(r["insert_index"]) for r in rows if r["ok"] == "yes"]
    return out


def suggest_swaps(seq: List[Any], policy: Optional[Policy] = None) -> List[Tuple[int, int]]:
    if policy is None:
        policy = Policy()
    ok_swaps: List[Tuple[int, int]] = []
    for i in range(len(seq) - 1):
        new_seq = list(seq)
        new_seq[i], new_seq[i + 1] = new_seq[i + 1], new_seq[i]
        ok, _ = validate_sequence(new_seq, policy=policy)
        if ok:
            ok_swaps.append((i, i + 1))
    return ok_swaps


def suggest_deletes(seq: List[Any], policy: Optional[Policy] = None) -> List[int]:
    if policy is None:
        policy = Policy()
    ok_deletes: List[int] = []
    for i in range(len(seq)):
        new_seq = seq[:i] + seq[i + 1 :]
        ok, _ = validate_sequence(new_seq, policy=policy)
        if ok:
            ok_deletes.append(i)
    return ok_deletes


# === Planning helpers & auto-repair insertion ==================================


def _collect_existing_names(snap: Snapshot) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {}
    for (rt, name), st in snap.res_states.items():
        out.setdefault(rt, set()).add(name)
    return out


def _next_name(existing: Set[str], prefix: str) -> str:
    i = 0
    pat = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    # start from max existing suffix + 1
    max_suf = -1
    for n in existing:
        m = pat.match(n)
        if m:
            try:
                max_suf = max(max_suf, int(m.group(1)))
            except Exception:
                pass
    i = max_suf + 1
    while True:
        cand = f"{prefix}{i}"
        if cand not in existing:
            return cand
        i += 1


# Constructors with sensible defaults (using only fields contracts care about)
def _mk_alloc_pd(name: str):
    return verbs.AllocPD(pd=name)


def _mk_create_cq(name: str):
    return verbs.CreateCQ(cq=name)


def _mk_reg_mr(pd_name: str, mr_name: str):
    # Minimal args; contracts only track MR allocated
    return verbs.RegMR(
        pd=pd_name,
        buf="buf_auto",
        length=4096,
        mr=mr_name,
        flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
    )


def _mk_create_qp(qp_name: str, pd_name: str, send_cq: str, recv_cq: str):
    cap = ibv_all.IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1)
    init_attr = ibv_all.IbvQPInitAttr(send_cq=send_cq, recv_cq=recv_cq, cap=cap, qp_type="IBV_QPT_RC", sq_sig_all=1)
    return verbs.CreateQP(qp=qp_name, pd=pd_name, init_attr_obj=init_attr)


def _mk_mqp_state(qp_name: str, state_token: str):
    return verbs.ModifyQP(qp=qp_name, attr_mask="IBV_QP_STATE", attr_obj=ibv_all.IbvQPAttr(qp_state=state_token))


def _mk_poll_cq(cq_name: str):
    return verbs.PollCQ(cq=cq_name)


def _mk_destroy_qp(qp_name: str):
    return verbs.DestroyQP(qp=qp_name)


def _mk_destroy_cq(cq_name: str):
    return verbs.DestroyCQ(cq=cq_name)


def _mk_dereg_mr(mr_name: str):
    return verbs.DeregMR(mr=mr_name)


def _mk_dealloc_pd(pd_name: str):
    return verbs.DeallocPD(pd=pd_name)


# State token names as strings used by ibv_all.IbvQPAttr
_QP_STATE_TOK = {
    "INIT": "IBV_QPS_INIT",
    "RTR": "IBV_QPS_RTR",
    "RTS": "IBV_QPS_RTS",
}


def _qp_upgrade_plan(current: Optional[State], target: Optional[State], qp_name: str) -> List[Any]:
    """Return a list of ModifyQP to move from current to at least target, using a simple ladder INIT->RTR->RTS."""
    steps: List[Any] = []
    if target is None:
        return steps
    ladder = []
    # Build ladder in order depending on available enums
    if hasattr(State, "INIT"):
        ladder.append(("INIT", getattr(State, "INIT")))
    if hasattr(State, "RTR"):
        ladder.append(("RTR", getattr(State, "RTR")))
    if hasattr(State, "RTS"):
        ladder.append(("RTS", getattr(State, "RTS")))

    # Figure current index
    def idx_of(st: Optional[State]) -> int:
        if st is None:
            return -1
        for i, (_, s) in enumerate(ladder):
            if s == st:
                return i
        return -1

    ci = idx_of(current)
    ti = idx_of(target)

    # If current is beyond target, no need
    if ti == -1:
        return steps
    # Move up from ci+1 to ti inclusive
    for i in range(ci + 1, ti + 1):
        name, _ = ladder[i]
        tok = _QP_STATE_TOK[name]
        steps.append(_mk_mqp_state(qp_name, tok))
    return steps


def plan_requirements(candidate: Any, snap: Snapshot, policy: Optional[Policy] = None) -> List[Any]:
    """Given a candidate and a snapshot, synthesize a minimal patch (verbs list) to satisfy base requires and common semantics.
    Strategy: create missing PD/CQ/MR/QP, upgrade QP to needed state, clear CQ dirtiness before destroy, and remove PD dependents when deallocating PD.
    """
    if policy is None:
        policy = Policy()
    patch: List[Any] = []

    # Base requirements from augmented contract
    ic = instantiate_augmented(candidate)
    existing = _collect_existing_names(snap)

    # Helpers to ensure a resource exists, recursively adding parents as needed
    def ensure_pd(pd_name: str):
        if "pd" not in existing or pd_name not in existing["pd"]:
            patch.append(_mk_alloc_pd(pd_name))
            existing.setdefault("pd", set()).add(pd_name)

    def ensure_cq(cq_name: str):
        if "cq" not in existing or cq_name not in existing["cq"]:
            patch.append(_mk_create_cq(cq_name))
            existing.setdefault("cq", set()).add(cq_name)

    def ensure_mr(mr_name: str):
        if "mr" in existing and mr_name in existing["mr"]:
            return
        # Need a PD
        pd_pool = list(existing.get("pd", set()))
        if not pd_pool:
            # create a default PD
            pd_name = _next_name(existing.get("pd", set()), "PD")
            ensure_pd(pd_name)
        else:
            pd_name = pd_pool[0]
        patch.append(_mk_reg_mr(pd_name, mr_name))
        existing.setdefault("mr", set()).add(mr_name)

    def ensure_qp(qp_name: str):
        if "qp" in existing and qp_name in existing["qp"]:
            return
        # Need PD and two CQs
        pd_pool = list(existing.get("pd", set()))
        if not pd_pool:
            pd_name = _next_name(existing.get("pd", set()), "PD")
            ensure_pd(pd_name)
        else:
            pd_name = pd_pool[0]
        cq_pool = list(existing.get("cq", set()))
        if len(cq_pool) < 2:
            # create enough CQs
            need = 2 - len(cq_pool)
            for _ in range(need):
                new_cq = _next_name(existing.get("cq", set()), "CQ")
                ensure_cq(new_cq)
                cq_pool.append(new_cq)
        send_cq, recv_cq = cq_pool[0], cq_pool[1]
        patch.append(_mk_create_qp(qp_name, pd_name, send_cq, recv_cq))
        existing.setdefault("qp", set()).add(qp_name)

    # 1) Satisfy explicit requires (and minimal states)
    for r in ic.requires:
        rt, name, need_state = r.rtype, r.name_attr, getattr(r, "state", None)
        cur = snap.res_states.get((rt, name))
        if cur is None:
            if rt == "pd":
                ensure_pd(name)
            elif rt == "cq":
                ensure_cq(name)
            elif rt == "mr":
                ensure_mr(name)
            elif rt == "qp":
                ensure_qp(name)
            else:
                # Unknown type: best effort no-op
                pass
            cur = snap.res_states.get((rt, name))  # None in snapshot, but we updated 'existing' to prevent duplicates
        # Minimal state upgrades for QP
        if rt == "qp" and need_state is not None:
            steps = _qp_upgrade_plan(cur, need_state, name)
            patch.extend(steps)

    # 2) Semantic repairs for specific verbs
    # PostSend needs QP ≥ RTS (already augmented MR requires handled in step1)
    if isinstance(candidate, verbs.PostSend):
        qp_name = _norm_name(getattr(candidate, "qp", None))
        if qp_name:
            # Ensure QP exists (semantic need)
            if "qp" not in existing or qp_name not in existing.get("qp", set()):
                ensure_qp(qp_name)
            cur = snap.res_states.get(("qp", qp_name))
            target = getattr(State, "RTS", None)
            patch.extend(_qp_upgrade_plan(cur, target, qp_name))

    # DestroyCQ / DestroyQP need clean CQ
    if isinstance(candidate, verbs.DestroyCQ):
        cq_name = _norm_name(getattr(candidate, "cq", None))
        if cq_name and snap.cq_dirty.get(cq_name, False):
            patch.append(_mk_poll_cq(cq_name))
    if isinstance(candidate, verbs.DestroyQP):
        qp_name = _norm_name(getattr(candidate, "qp", None))
        if qp_name and qp_name in snap.qp_bind and "send_cq" in snap.qp_bind[qp_name]:
            cq = snap.qp_bind[qp_name]["send_cq"]
            if snap.cq_dirty.get(cq, False):
                patch.append(_mk_poll_cq(cq))

    # DeallocPD: destroy transitive dependents first（按：先清CQ→DestroyQP，再DestroyCQ，再DeregMR）
    if isinstance(candidate, verbs.DeallocPD):
        pd_name = _norm_name(getattr(candidate, "pd", None))
        if pd_name:
            deps = _live_dependents_of(snap, ("pd", pd_name))
            # Sort: handle QP first (may touch CQ), then CQ, then MR
            qps = [n for (r, n) in deps if r == "qp"]
            cqs = [n for (r, n) in deps if r == "cq"]
            mrs = [n for (r, n) in deps if r == "mr"]
            for q in qps:
                if q in snap.qp_bind and "send_cq" in snap.qp_bind[q]:
                    cq = snap.qp_bind[q]["send_cq"]
                    if snap.cq_dirty.get(cq, False):
                        patch.append(_mk_poll_cq(cq))
                patch.append(_mk_destroy_qp(q))
            for c in cqs:
                if snap.cq_dirty.get(c, False):
                    patch.append(_mk_poll_cq(c))
                patch.append(_mk_destroy_cq(c))
            for m in mrs:
                patch.append(_mk_dereg_mr(m))

    return patch


def auto_repair_insert(
    seq: List[Any], idx: int, candidate: Any, policy: Optional[Policy] = None, max_iters: int = 4
) -> Tuple[bool, List[Any], List[str]]:
    """Try to insert candidate at idx by synthesizing a minimal patch before it.
    Returns (ok, new_seq, reasons_if_failed).
    """
    if policy is None:
        policy = Policy()
    # Build prefix snapshot at idx
    snaps = build_prefix_snapshots(seq)
    snap = snaps[idx]
    cumulative_patch: List[Any] = []
    for _ in range(max_iters):
        # Check current snapshot against candidate
        reasons = check_contract_requirements(candidate, snap)
        sem_reasons, _ = semantic_checks(candidate, snap, policy)
        reasons += sem_reasons
        if not reasons:
            break
        patch = plan_requirements(candidate, snap, policy=policy)
        if not patch:
            # Cannot repair with our planners; fail fast
            return False, seq, reasons
        cumulative_patch.extend(patch)
        # advance snapshot by applying the patch verbally
        for v in patch:
            snap = apply_to_snapshot(snap, v)
    # Try the insertion in the full sequence and validate
    new_seq = seq[:idx] + cumulative_patch + [candidate] + seq[idx:]
    ok, errs = validate_sequence(new_seq, policy=policy)
    if not ok:
        return False, new_seq, errs
    return True, new_seq, []
