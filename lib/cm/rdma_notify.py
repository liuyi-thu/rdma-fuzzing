# rdma_notify CM API modeling plugin
# This plugin models the rdma_notify() call, which informs librdmacm of an asynchronous
# device event (typically IBV_EVENT_COMM_EST) that occurred on a QP associated with a
# given rdma_cm_id. This can force the CM connection state into established when the
# connection was formed out-of-band.

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, InstantiatedContract, RequireSpec, State, TransitionSpec
from lib.value import (
    ConstantValue,
    EnumValue,
    IntValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaNotify(VerbCall):
    """
    Model of rdma_notify(struct rdma_cm_id *id, enum ibv_event_type event)

    Semantics:
    - Notifies librdmacm about an asynchronous event associated with a QP bound to
      the provided rdma_cm_id.
    - In most cases this call is not needed, but for out-of-band connection establishment
      (e.g., via native InfiniBand CM), notifying IBV_EVENT_COMM_EST may force the CM
      into an established state to handle rare cases where the connection never forms on
      its own inside librdmacm.

    Contract:
    - Requires: a cm_id resource must exist (ALLOCATED).
    - Transition: if event == IBV_EVENT_COMM_EST (or IB_EVENT_COMM_EST),
                  transition cm_id state from ALLOCATED to USED (representing established).
    """

    MUTABLE_FIELDS = ["id", "event"]

    # Base static contract: require cm_id; transitions are determined dynamically in _contract()
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.ALLOCATED, name_attr="id"),
        ],
        produces=[],
        transitions=[],
    )

    def __init__(self, id: str = None, event=None):
        """
        Initialize RdmaNotify.

        Parameters:
        - id: The identifier name of an existing rdma_cm_id resource.
        - event: The event to notify. Can be:
            * str: e.g., "IBV_EVENT_COMM_EST" (preferred) or "IB_EVENT_COMM_EST"
            * EnumValue: with enum_type="ibv_event_type"
            * IntValue: numeric value of the enum
            * ConstantValue: string constant of the enum
          Defaults to "IBV_EVENT_COMM_EST".
        """
        if not id:
            raise ValueError("id (cm_id resource name) must be provided for RdmaNotify")

        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)

        # Normalize event to an EnumValue if a string is provided, otherwise accept given Value types.
        if event is None:
            self.event = EnumValue(enum_type="ibv_event_type", value="IBV_EVENT_COMM_EST")
        elif isinstance(event, (EnumValue, IntValue, ConstantValue)):
            self.event = event
        elif isinstance(event, str):
            # Accept both IBV_EVENT_COMM_EST and legacy IB_EVENT_COMM_EST naming
            normalized = event.strip()
            if normalized == "IB_EVENT_COMM_EST":
                normalized = "IBV_EVENT_COMM_EST"
            self.event = EnumValue(enum_type="ibv_event_type", value=normalized)
        else:
            # Fallback: attempt to wrap as IntValue
            self.event = IntValue(value=int(event))

    def _is_comm_est(self) -> bool:
        """Return True if event denotes COMM_EST."""
        try:
            v = str(self.event)
        except Exception:
            return False
        s = v.strip()
        return s == "IBV_EVENT_COMM_EST" or s == "IB_EVENT_COMM_EST"

    def apply(self, ctx: CodeGenContext):
        # Apply dynamic contract based on the event value.
        if hasattr(ctx, "contracts"):
            dyn = self._contract()
            ctx.contracts.apply_contract(self, dyn if dyn else self.CONTRACT)

    def _contract(self) -> InstantiatedContract:
        """
        Instantiate contract dynamically: if COMM_EST, transition cm_id to USED to reflect
        established connection. Otherwise, only requires the cm_id.
        """
        transitions = []
        if self._is_comm_est():
            transitions.append(
                TransitionSpec(rtype="cm_id", from_state=State.ALLOCATED, to_state=State.USED, name_attr="id")
            )
        return InstantiatedContract(
            requires=self.CONTRACT.requires,
            produces=self.CONTRACT.produces,
            transitions=transitions,
        )

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)
        event_code = str(self.event)

        return f"""
    /* rdma_notify */
    IF_OK_PTR({id_name}, {{
        int notify_rc = rdma_notify({id_name}, {event_code});
        if (notify_rc) {{
            fprintf(stderr, "rdma_notify({id_name}, {event_code}) failed: %d\\n", notify_rc);
        }} else {{
            /* On success, CM may be forced into an established state if event is COMM_EST. */
        }}
    }});
"""
