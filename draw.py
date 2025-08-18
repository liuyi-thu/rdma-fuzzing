# Build an illustrative "Contract-based Resource & State Graph" and render it.
# We'll model it as a Petri-net-like typed multigraph:
# - Places (circles): (ResourceType, State) e.g., QP[RESET], PD[ALLOCATED], CQ[ALLOCATED], MR[REGISTERED]
# - Transitions (boxes): Verbs e.g., CreateQP, ModifyQP(RESET->INIT), ModifyQP(INIT->RTR), ModifyQP(RTR->RTS)
# - Input arcs from required places to a transition; output arcs from transition to produced places.
#
# This is a minimal, didactic example you can drop into your paper/PPT.

from graphviz import Digraph

dot = Digraph("rdma_contract_graph", format="png")
dot.attr(rankdir="LR")

# Styles
place_style = {"shape": "circle", "style": "filled", "fillcolor": "#e6f2ff"}
trans_style = {"shape": "box", "style": "rounded,filled", "fillcolor": "#ffe6cc"}


# Helper to add places and transitions
def place(name):
    dot.node(f"P_{name}", name, **place_style)


def trans(name, label=None):
    dot.node(f"T_{name}", label or name, **trans_style)


def arc(src, dst, label=""):
    dot.edge(src, dst, label)


# ----- Places (resource,state) -----
place("PD[ALLOCATED]")
place("CQ[ALLOCATED]")
place("QP[RESET]")
place("QP[INIT]")
place("QP[RTR]")
place("QP[RTS]")

# ----- Transitions (verbs) -----
trans("CreateQP", "CreateQP")
trans("ModifyQP_RESET_INIT", "ModifyQP(qp_state=INIT)")
trans("ModifyQP_INIT_RTR", "ModifyQP(qp_state=RTR)")
trans("ModifyQP_RTR_RTS", "ModifyQP(qp_state=RTS)")

# ----- Arcs based on contracts -----
# CreateQP: requires PD[ALLOCATED], CQ[ALLOCATED] -> produces QP[RESET]
arc("P_PD[ALLOCATED]", "T_CreateQP")
arc("P_CQ[ALLOCATED]", "T_CreateQP")
arc("T_CreateQP", "P_QP[RESET]")

# ModifyQP transitions (requires current QP state, produces next state)
arc("P_QP[RESET]", "T_ModifyQP_RESET_INIT")
arc("T_ModifyQP_RESET_INIT", "P_QP[INIT]")

arc("P_QP[INIT]", "T_ModifyQP_INIT_RTR")
arc("T_ModifyQP_INIT_RTR", "P_QP[RTR]")

arc("P_QP[RTR]", "T_ModifyQP_RTR_RTS")
arc("T_ModifyQP_RTR_RTS", "P_QP[RTS]")

# Render
out_path = "rdma_contract_graph.png"
dot.render(out_path)
out_path
