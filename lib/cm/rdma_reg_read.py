# rdma_reg_read plugin
# 语义：使用给定的 rdma_cm_id 的关联 PD 对一段用户内存进行注册，使该内存可被远端执行 RDMA READ。
# 用途：该 CM 辅助函数封装了 ibv_reg_mr 的常用访问标志组合（IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ），
#       简化远端读（READ）数据路径的 MR 注册流程。成功时返回 struct ibv_mr*。
# 前置条件：cm_id 必须已经关联到有效的 PD（通常通过 rdma_create_qp 或 rdma_create_ep 完成）；addr 非空且 length > 0。
# 效果：产生一个 MR 资源；不改变 cm_id 的状态；后续可用于接收远端的 RDMA READ。

"""
Python plugin modeling RDMA CM API: rdma_reg_read

This plugin encapsulates rdma_reg_read(struct rdma_cm_id *id, void *addr, size_t length)
into a VerbCall subclass for the RDMA verbs fuzzing framework. It generates C code that
invokes the CM helper to register a memory region with remote-read capability.

Function semantics:
- Registers user buffer [addr, length] into the PD associated with 'id'.
- Returns an ibv_mr* with access flags equivalent to IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ.

Contract:
- Requires:
  - cm_id (USED/CONNECTED or generally valid) bound to a PD.
  - buffer/address must be available and a positive length.
- Produces:
  - mr in ALLOCATED state.

The class will:
- Validate input (mr variable name, addr, length).
- Allocate the MR pointer variable in the C context.
- Emit C code calling rdma_reg_read and basic logging of lkey/rkey.
"""

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, ProduceSpec, RequireSpec, State
from lib.value import (
    IntValue,
    LocalResourceValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaRegRead(VerbCall):
    """
    Model of rdma_reg_read CM API.

    rdma_reg_read(struct rdma_cm_id *id, void *addr, size_t length) -> struct ibv_mr *

    Registers the memory region pointed by 'addr' with size 'length' into the PD
    associated with 'id', enabling remote peer to perform RDMA READ on it.
    """

    MUTABLE_FIELDS = ["id", "mr", "addr", "length"]

    # Contract captures the need for a valid cm_id and a buffer,
    # and the production of an MR in ALLOCATED state.
    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.USED, name_attr="id"),
            # If the framework tracks buffers as resources:
            RequireSpec(rtype="buffer", state=State.ALLOCATED, name_attr="addr"),
        ],
        produces=[
            ProduceSpec(
                rtype="mr",
                state=State.ALLOCATED,
                name_attr="mr",
                metadata_fields=["id", "addr", "length"],
            ),
        ],
        transitions=[
            # rdma_reg_read does not alter cm_id state; no transitions required.
        ],
    )

    def __init__(self, id: str = None, mr: str = None, addr: str = None, length: int = None):
        """
        Args:
            id: Variable name of struct rdma_cm_id* (must be valid and bound to a PD).
            mr: Variable name to store the resulting struct ibv_mr* (required).
            addr: Variable name or expression of the buffer base address (required).
            length: Size of the buffer in bytes (required, > 0).
        """
        # cm_id resource reference
        self.id = ResourceValue(resource_type="cm_id", value=id) if id else "NULL"

        # the MR output must be a named resource
        if not mr:
            raise ValueError("mr must be provided for RdmaRegRead")
        self.mr = ResourceValue(resource_type="mr", value=mr, mutable=False)

        if not addr:
            raise ValueError("addr must be provided for RdmaRegRead")
        # Treat addr as a local resource name (buffer); framework may track it.
        self.addr = LocalResourceValue(resource_type="buffer", value=addr)

        if length is None or int(length) <= 0:
            raise ValueError("length must be a positive integer for RdmaRegRead")
        self.length = IntValue(value=int(length))

    def apply(self, ctx: CodeGenContext):
        # Register variable in codegen context
        if ctx:
            ctx.alloc_variable(str(self.mr), "struct ibv_mr *", "NULL")

        # Apply the contract through the context if available
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def generate_c(self, ctx: CodeGenContext):
        id_name = str(self.id)
        mr_name = str(self.mr)
        addr_name = self.addr.value
        length_expr = str(self.length)

        # Generate C code to invoke rdma_reg_read and log MR keys
        return f"""
    /* rdma_reg_read */
    IF_OK_PTR({id_name}, {{
        {mr_name} = rdma_reg_read({id_name}, (void *)({addr_name}), (size_t)({length_expr}));
        if (!{mr_name}) {{
            fprintf(stderr, "rdma_reg_read failed: id=%p addr=%p len=%zu (mr={mr_name})\\n",
                    (void*){id_name}, (void*)({addr_name}), (size_t)({length_expr}));
        }} else {{
            fprintf(stdout, "rdma_reg_read OK: addr=%p len=%zu lkey=0x%x rkey=0x%x -> {mr_name}\\n",
                    (void*)({addr_name}), (size_t)({length_expr}), {mr_name}->lkey, {mr_name}->rkey);
            /* Optionally track MR in global registry if available */
            IF_DEFINED(mrs, {{
                mrs[mrs_size++] = (PR_MR){{
                    .id = "{mr_name}",
                    .addr = (uintptr_t)({addr_name}),
                    .length = (size_t)({length_expr}),
                    .lkey = {mr_name}->lkey,
                    .rkey = {mr_name}->rkey
                }};
            }});
        }}
    }});
"""
