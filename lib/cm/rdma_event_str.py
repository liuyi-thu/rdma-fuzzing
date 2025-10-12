# -*- coding: utf-8 -*-
"""
Model for RDMA CM API: rdma_event_str

Semantics:
- rdma_event_str maps an enum rdma_cm_event_type value to a human-readable const char*.
- The returned pointer refers to a static, read-only string and must not be freed by the caller.
- This API is pure: no side effects, does not allocate or mutate RDMA/CM resources.
- Typical usage: logging or branching on event kinds after rdma_get_cm_event.

This plugin wraps rdma_event_str as a VerbCall for code generation within the RDMA verbs/CM fuzzing framework.
"""

from typing import Optional, Union

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract
from lib.value import (
    ConstantValue,
    EnumValue,
    IntValue,
)
from lib.verbs import VerbCall


class RdmaEventStr(VerbCall):
    """
    Python-side modeling for the CM API:
        const char *rdma_event_str(enum rdma_cm_event_type event);

    Parameters:
    - event: the CM event value. Accepts:
        * EnumValue for enum rdma_cm_event_type (e.g., EnumValue("rdma_cm_event_type", "RDMA_CM_EVENT_ESTABLISHED"))
        * ConstantValue for raw C expressions (e.g., ConstantValue("cm_event->event"))
        * IntValue or int for numeric enum values
        * str for macro/identifier or expression (will be treated as a raw C expression)
    - out_var: name of the C variable (const char *) to store the returned string.

    Notes:
    - The produced string is a static constant; do not free() it.
    - This call has no resource requirements or productions; contract is effectively empty.
    """

    MUTABLE_FIELDS = ["event", "out_var"]

    CONTRACT = Contract(
        requires=[],
        produces=[],
        transitions=[],
    )

    def __init__(
        self,
        event: Union[EnumValue, ConstantValue, IntValue, int, str],
        out_var: Optional[str] = None,
    ):
        if event is None:
            raise ValueError("event must be provided for RdmaEventStr")

        # Normalize event to a Value-like object that can render to a C expression via str()
        if isinstance(event, (EnumValue, ConstantValue, IntValue)):
            self.event = event
        elif isinstance(event, int):
            self.event = IntValue(value=event)
        elif isinstance(event, str):
            # Treat as a raw C expression token (e.g., "cm_event->event" or "RDMA_CM_EVENT_ESTABLISHED")
            self.event = ConstantValue(event)
        else:
            raise TypeError(f"Unsupported type for event: {type(event)}")

        if not out_var:
            raise ValueError("out_var (C variable name for const char *) must be provided")
        self.out_var = str(out_var)

    def apply(self, ctx: CodeGenContext):
        self.context = ctx  # store for potential downstream usage
        if self.context:
            # Declare the output variable in generated C
            self.context.alloc_variable(self.out_var, "const char *", "NULL")

        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext) -> str:
        event_expr = str(self.event)
        out_var = self.out_var

        # Generate minimal, side-effect free invocation; add a safety check even though rdma_event_str normally returns non-NULL.
        return f"""
    /* rdma_event_str */
    {out_var} = rdma_event_str({event_expr});
    if (!{out_var}) {{
        fprintf(stderr, "rdma_event_str returned NULL for event expression: {event_expr}\\n");
    }}
"""
