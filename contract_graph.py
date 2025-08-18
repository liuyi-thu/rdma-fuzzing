
from dataclasses import dataclass, field
from typing import Optional, Set, Dict, List, Tuple, Any
import inspect

# ---- Node types ----

@dataclass(frozen=True)
class RSNode:
    rtype: str                # resource type, e.g. "qp", "pd", "mr", "cq"
    state: Optional[str]      # specific state string, or None as wildcard

    def __str__(self) -> str:
        s = self.state if self.state is not None else "*"
        return f"{self.rtype}[{s}]"

@dataclass
class VerbSpec:
    name: str
    cls: Any
    requires: Set[RSNode] = field(default_factory=set)
    produces: Set[RSNode] = field(default_factory=set)

    def __str__(self):
        req = ", ".join(sorted(map(str, self.requires)))
        pro = ", ".join(sorted(map(str, self.produces)))
        return f\"{self.name}: requires({req}) -> produces({pro})\"


@dataclass
class ContractGraph:
    # verb name -> spec
    verbs: Dict[str, VerbSpec]
    # convenience reverse index
    require_index: Dict[RSNode, Set[str]]  = field(default_factory=dict)  # who needs this state
    produce_index: Dict[RSNode, Set[str]]  = field(default_factory=dict)  # who produces this state

    def pretty(self) -> str:
        lines = []
        for name in sorted(self.verbs.keys()):
            lines.append(str(self.verbs[name]))
        return "\\n".join(lines)


def _add_index(idx: Dict[RSNode, Set[str]], key: RSNode, verb_name: str):
    idx.setdefault(key, set()).add(verb_name)


def _rsnode(rtype: Optional[str], state: Optional[str]) -> Optional[RSNode]:
    if rtype is None:
        return None
    return RSNode(rtype=str(rtype), state=str(state) if state is not None else None)


def build_graph_from_contracts(verbs_module) -> ContractGraph:
    \"\"\"Scan classes in lib.verbs (or a similar module), extract CONTRACTs, and
    build a bipartite graph (verb ↔ resource-state).\"\"\"
    verbs: Dict[str, VerbSpec] = {}
    require_index: Dict[RSNode, Set[str]] = {}
    produce_index: Dict[RSNode, Set[str]] = {}

    for name, obj in inspect.getmembers(verbs_module, inspect.isclass):
        # Only consider classes defined in this module (skip imports)
        if obj.__module__ != verbs_module.__name__:
            continue

        contract = getattr(obj, "CONTRACT", None)
        if contract is None:
            continue

        spec = VerbSpec(name=name, cls=obj)

        # requires
        for rq in getattr(contract, "requires", []) or []:
            node = _rsnode(getattr(rq, "rtype", None), getattr(rq, "state", None))
            if node:
                spec.requires.add(node)

        # produces
        for pr in getattr(contract, "produces", []) or []:
            node = _rsnode(getattr(pr, "rtype", None), getattr(pr, "state", None))
            if node:
                spec.produces.add(node)

        # transitions: treat as requires(old) + produces(new)
        for tr in getattr(contract, "transitions", []) or []:
            n_from = _rsnode(getattr(tr, "rtype", None), getattr(tr, "from_state", None))
            n_to   = _rsnode(getattr(tr, "rtype", None), getattr(tr, "to_state", None))
            if n_from:
                spec.requires.add(n_from)
            if n_to:
                spec.produces.add(n_to)

        if spec.requires or spec.produces:
            verbs[name] = spec
            for r in spec.requires:
                _add_index(require_index, r, name)
            for p in spec.produces:
                _add_index(produce_index, p, name)

    return ContractGraph(verbs=verbs, require_index=require_index, produce_index=produce_index)


# ---------- Planning utilities ----------

def snapshot_to_available_rs(snapshot: Dict[Tuple[str,str], str]) -> Set[RSNode]:
    \"\"\"Convert your ctx.contracts.snapshot() into a set of available RSNode
    (type-level, ignoring instance names).\"\"\"
    avail: Set[RSNode] = set()
    for (rtype, _name), state in snapshot.items():
        if state is None:
            continue
        avail.add(RSNode(rtype=str(rtype), state=str(state)))
    return avail


def _requires_satisfied(spec: VerbSpec, avail: Set[RSNode]) -> bool:
    \"\"\"Check whether a verb's requires are satisfied by current available states.
    wildcard state in requires (state=None) means any state of that resource type is fine.\"\"\"
    # For each requirement, we need a matching avail RSNode with same rtype and (state matches or is wildcard)
    for rq in spec.requires:
        if rq.state is None:
            # any state for this rtype is acceptable, check presence of any RSNode with this rtype
            if not any(a.rtype == rq.rtype for a in avail):
                return False
        else:
            if not any(a.rtype == rq.rtype and a.state == rq.state for a in avail):
                return False
    return True


def plan_chain_to_enable(target: VerbSpec, graph: ContractGraph, avail: Set[RSNode], max_depth: int = 6) -> Optional[List[VerbSpec]]:
    \"\"\"Find a short list of verbs that, when executed, will make target.requires satisfied.
    Simple BFS on the verb-layer; type-level (no instance binding).\"\"\"
    from collections import deque

    if _requires_satisfied(target, avail):
        return []

    # BFS over (avail_set) space; we track path as list of verb names
    State = Tuple[frozenset, Tuple[str, ...]]  # (avail_rs, path of verb names)
    start = (frozenset(avail), ())
    q = deque([start])
    seen = {start[0]}

    while q:
        cur_avail_fs, path = q.popleft()
        cur_avail = set(cur_avail_fs)

        if len(path) > max_depth:
            continue

        # try all verbs that could add something
        for vname, vspec in graph.verbs.items():
            # skip if verb adds nothing new
            if not vspec.produces:
                continue
            # can we currently fire it (type-level)?
            if not _requires_satisfied(vspec, cur_avail):
                continue
            # compute new avail
            new_avail = set(cur_avail)
            new_avail.update(vspec.produces)  # optimistic: we don't remove states here
            new_fs = frozenset(new_avail)

            new_path = path + (vname,)

            # goal?
            if _requires_satisfied(target, new_avail):
                return [graph.verbs[n] for n in new_path]

            if new_fs not in seen:
                seen.add(new_fs)
                q.append((new_fs, new_path))

    return None  # not found within depth


def pretty_plan(plan: Optional[List[VerbSpec]]) -> str:
    if plan is None:
        return "(no plan found)"
    if not plan:
        return "(already satisfied)"
    return " -> ".join(v.name for v in plan)
