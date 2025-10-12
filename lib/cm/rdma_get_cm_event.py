# -*- coding: utf-8 -*-
# 模型说明：
# 本插件对 RDMA CM API 的 rdma_get_cm_event 进行建模。该调用从给定的 rdma_event_channel 中
# 获取下一个待处理的通信事件（struct rdma_cm_event）。若无事件，默认阻塞直到有事件到来。
# 获取到的事件必须随后通过 rdma_ack_cm_event 进行确认（ack），否则相关资源的销毁将会阻塞。
# 本类用于在 fuzzing 框架中生成对应的 C 代码片段，并在资源/状态系统中产出一个“cm_event”资源实例。

"""
RdmaGetCmEvent plugin

Semantics:
- Wrap RDMA CM API `rdma_get_cm_event(struct rdma_event_channel *channel, struct rdma_cm_event **event)`
- Retrieves the next pending communication event from an event channel.
- Blocks by default if no events are pending (behavior can be changed by modifying the channel's FD).
- All reported events must be acknowledged via `rdma_ack_cm_event`.

Contract:
- Requires: an allocated cm_event_channel resource (channel).
- Produces: a cm_event resource in ALLOCATED state (pending acknowledgment).
- Transitions: none in this call; ack is modeled by a separate plugin (e.g., RdmaAckCmEvent).

Usage:
- Provide an existing event channel resource name and a target event variable name.
- The generated C will declare the event var and invoke `rdma_get_cm_event`.
- On success, logs the event type via `rdma_event_str(ev->event)`.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, RequireSpec, State
from lib.value import (
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaGetCmEvent(VerbCall):
    MUTABLE_FIELDS = ["channel", "event"]

    # Resource and state modeling:
    # - rtype "cm_event_channel": the rdma_event_channel used to receive events.
    # - rtype "cm_event": the received rdma_cm_event that must be acked later.
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_event_channel", state=State.ALLOCATED, name_attr="channel"),
        ],
        produces=[
            ProduceSpec(rtype="cm_event", state=State.ALLOCATED, name_attr="event", metadata_fields=["channel"]),
        ],
        transitions=[
            # No state transitions here; rdma_ack_cm_event will transition cm_event state.
        ],
    )

    def __init__(self, channel: str = None, event: str = None):
        """
        Args:
            channel: name of the rdma_event_channel resource.
            event: name of the cm_event resource variable to receive the event pointer.
        """
        # Channel can be fuzzed to NULL, but normally it should be a valid event channel resource.
        self.channel = ResourceValue(resource_type="cm_event_channel", value=channel) if channel else "NULL"

        if not event:
            raise ValueError("event must be provided for RdmaGetCmEvent (variable name to store the received event).")
        # The produced cm_event resource handle (variable) is not mutable.
        self.event = ResourceValue(resource_type="cm_event", value=event, mutable=False)

    def apply(self, ctx: CodeGenContext):
        # Allocate/declare the event variable in the generated C context.
        # rdma_get_cm_event writes to a pointer-to-pointer, so we must declare a struct rdma_cm_event *.
        ctx.alloc_variable(str(self.event), "struct rdma_cm_event *", "NULL")

        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext):
        channel_name = str(self.channel)
        event_name = str(self.event)

        # C code emission:
        # - Calls rdma_get_cm_event(channel, &event_name)
        # - On error, prints errno; on success, prints event type string.
        code = f"""
    /* rdma_get_cm_event */
    IF_OK_PTR({channel_name}, {{
        int __ret_get_ev = rdma_get_cm_event({channel_name}, &{event_name});
        if (__ret_get_ev) {{
            fprintf(stderr, "rdma_get_cm_event failed on channel %p: %s\\n", (void*){channel_name}, strerror(errno));
        }} else {{
            if ({event_name}) {{
                const char *ev_str = rdma_event_str({event_name}->event);
                fprintf(stderr, "CM event received: %s (id=%p) on channel %p\\n",
                        ev_str ? ev_str : "UNKNOWN", (void*){event_name}->id, (void*){channel_name});
            }} else {{
                fprintf(stderr, "rdma_get_cm_event returned success but event is NULL?\\n");
            }}
        }}
    }});
"""
        return code
