
# Demo: build a graph from your lib.verbs CONTRACTs and plan a prefix to enable a target verb.
# Usage inside your repo (PYTHONPATH including project root):
#   from planner_demo import demo
#   demo()
#
# It prints a small plan (sequence of verbs) at type-level. You can then map each VerbSpec
# to your actual constructor (AllocPD/CreateCQ/CreateQP/ModifyQP/RegMR/...)

from contract_graph import build_graph_from_contracts, snapshot_to_available_rs, plan_chain_to_enable, pretty_plan

def demo(verbs_module, initial_snapshot):
    graph = build_graph_from_contracts(verbs_module)
    print("[Graph built] Verbs indexed:", len(graph.verbs))

    avail = snapshot_to_available_rs(initial_snapshot)

    # Example target: find a verb that produces qp[RTS]
    target = None
    for v in graph.verbs.values():
        for rs in v.produces:
            if rs.rtype == "qp" and str(rs.state).upper() == "RTS":
                target = v
                break
        if target:
            break

    if not target:
        print("Could not find a verb that produces qp[RTS] in CONTRACTs.")
        return

    plan = plan_chain_to_enable(target, graph, avail, max_depth=8)
    print("Target:", target)
    print("Plan:", pretty_plan(plan))
