# -*- coding: utf-8 -*-
"""
建模 RDMA CM API: rdma_post_writev

语义与用途:
- rdma_post_writev 通过 RDMA CM ID 关联的 QP，向远端地址 remote_addr 和远端 RKey rkey 发起一次 RDMA WRITE 操作。
- “writev” 表示该操作接受一个 scatter-gather list (struct ibv_sge 数组)，一次性提交多个本地段。
- 该调用是非阻塞的，成功返回 0，失败返回错误码；完成通知依赖 QP 的 CQ/Completion 机制与 flags（如 IBV_SEND_SIGNALED）。
- 使用前通常要求 CM ID 已完成路由解析与连接，且 QP 已处于 RTS 状态；SGE 的 lkey 应来源于已注册的本地 MR。

本插件将该 CM API 抽象为一个 VerbCall 子类，用于在 Python 层构造调用，并生成相应 C 代码片段。
"""

from typing import Any, Dict, List, Optional, Union

from lib.codegen_context import CodeGenContext
from lib.contracts import Contract, RequireSpec, State
from lib.value import (
    ConstantValue,
    FlagValue,
    IntValue,
    ListValue,
    OptionalValue,
    ResourceValue,
)
from lib.verbs import VerbCall


class RdmaPostWritev(VerbCall):
    """
    对 rdma_post_writev 的封装。

    参数说明（Python 层）:
      - id: CM ID 名称（资源名，已在上下文创建并连接）
      - context: 应用层上下文指针变量名（或 "NULL"），将作为 wr_id/用户上下文传回
      - sgl: 支持两种形式：
          1) 字符串变量名（已在上下文中声明为 'struct ibv_sge *' 或数组名）
          2) Python list，用于内联生成一个 ibv_sge 数组。列表元素可为：
             - dict: {"addr": "<ptr_or_expr>", "length": <int_or_expr>, "lkey": <int_or_expr>}
             - 或三元组/列表: (addr, length, lkey)
      - nsge: SGE 数量；若 sgl 为 list 且未显式给出 nsge，则自动等于 len(sgl)
      - flags: 发送标志（如 IBV_SEND_SIGNALED 等的位与），默认 0
      - remote_addr: 远端虚拟地址 (uint64_t)
      - rkey: 远端内存区域的 rkey (uint32_t)

    约束假设（Contract）:
      - 需要一个已连接（CONNECTED）的 cm_id 资源。
      - 不声明产出资源，也不改变资源状态，仅视作对已连接会话的使用。

    代码生成（C）:
      - 根据 sgl 的形式生成或引用 SGE 数组。
      - 调用 rdma_post_writev，并打印出错误码（若非 0）。
    """

    MUTABLE_FIELDS = ["id", "context", "sgl", "nsge", "flags", "remote_addr", "rkey"]

    CONTRACT = Contract(
        requires=[
            RequireSpec(rtype="cm_id", state=State.CONNECTED, name_attr="id"),
        ],
        produces=[],
        transitions=[],
    )

    def __init__(
        self,
        id: str,
        context: Optional[str] = None,
        sgl: Optional[Union[str, List[Union[Dict[str, Any], List[Any], tuple]]]] = None,
        nsge: Optional[int] = None,
        flags: Union[int, FlagValue] = 0,
        remote_addr: Union[int, IntValue] = 0,
        rkey: Union[int, IntValue] = 0,
    ):
        if not id:
            raise ValueError("id (cm_id resource name) must be provided for RdmaPostWritev")

        # 资源/值封装
        self.id = ResourceValue(resource_type="cm_id", value=id, mutable=False)
        self.context = OptionalValue(value=context if context else "NULL")

        # sgl 可以是字符串指针/数组名，也可以是列表（自动生成）
        self._sgl_is_list = isinstance(sgl, list)
        if self._sgl_is_list:
            # 存储为 ListValue，便于后续处理
            self.sgl = ListValue(values=sgl)
            # 若未设置 nsge，则使用列表长度
            self.nsge = IntValue(value=len(sgl)) if nsge is None else IntValue(value=nsge)
        else:
            # 直接引用已有指针/数组名
            self.sgl = sgl if sgl else "NULL"
            self.nsge = IntValue(value=nsge if nsge is not None else 0)

        # flags、remote_addr、rkey
        self.flags = flags if isinstance(flags, FlagValue) else IntValue(value=int(flags))
        self.remote_addr = IntValue(value=int(remote_addr))
        self.rkey = IntValue(value=int(rkey))

    def apply(self, ctx: CodeGenContext):
        # 触发合约检查
        if hasattr(ctx, "contracts"):
            ctx.contracts.apply_contract(self, self.CONTRACT if hasattr(self, "CONTRACT") else self._contract())

    def _gen_sge_initializer(self, item: Union[Dict[str, Any], List[Any], tuple]) -> str:
        """
        将一个 Python 层的 SGE 描述转换为 C 结构初始化器。
        支持:
          - dict: {"addr": "...", "length": ..., "lkey": ...}
          - tuple/list: (addr, length, lkey)
        其中 addr/length/lkey 可为数值或 C 表达式（字符串）。
        """
        if isinstance(item, dict):
            addr = item.get("addr", "NULL")
            length = item.get("length", 0)
            lkey = item.get("lkey", 0)
        elif isinstance(item, (list, tuple)) and len(item) == 3:
            addr, length, lkey = item
        else:
            raise ValueError(f"Unsupported SGE item format: {item}")

        def as_expr(x):
            return x if isinstance(x, str) else str(int(x))

        return f"{{ .addr = (uintptr_t){as_expr(addr)}, .length = {as_expr(length)}, .lkey = {as_expr(lkey)} }}"

    def generate_c(self, ctx: CodeGenContext) -> str:
        id_name = str(self.id)
        context_expr = str(self.context) if isinstance(self.context, (str, ConstantValue, OptionalValue)) else "NULL"

        sgl_ptr_expr = None
        sge_array_decl = ""
        nsge_expr = str(self.nsge)
        flags_expr = str(self.flags) if isinstance(self.flags, (FlagValue, IntValue)) else str(int(self.flags))
        raddr_expr = str(self.remote_addr)
        rkey_expr = str(self.rkey)

        # 生成 SGE 数组（若传入的是列表）
        if self._sgl_is_list:
            # 基于 id_name 生成唯一的数组名
            suffix = id_name.replace("[", "_").replace("]", "_").replace(".", "_")
            sge_arr_name = f"sge_arr_{suffix}"

            # 生成每个元素的初始化器
            items = self.sgl.values if isinstance(self.sgl, ListValue) else (self.sgl or [])
            initializers = ",\n            ".join(self._gen_sge_initializer(it) for it in items)

            # 声明本地数组
            sge_array_decl = f"""
        struct ibv_sge {sge_arr_name}[{nsge_expr}] = {{
            {initializers}
        }};
"""
            sgl_ptr_expr = sge_arr_name
        else:
            # 直接使用传入的指针/数组名；若未提供，则为 NULL
            sgl_ptr_expr = self.sgl if isinstance(self.sgl, str) else "NULL"

        code = f"""
    /* rdma_post_writev */
    IF_OK_PTR({id_name}, {{
        {sge_array_decl}
        int __ret_writev = rdma_post_writev({id_name}, {context_expr}, {sgl_ptr_expr}, {nsge_expr}, {flags_expr}, (uint64_t){raddr_expr}, (uint32_t){rkey_expr});
        if (__ret_writev) {{
            fprintf(stderr,
                    "rdma_post_writev(id=%p) failed: ret=%d, nsge=%d, flags=0x%x, raddr=0x%llx, rkey=0x%x\\n",
                    (void*){id_name},
                    __ret_writev,
                    {nsge_expr},
                    {flags_expr},
                    (unsigned long long){raddr_expr},
                    (unsigned int){rkey_expr});
        }} else {{
            // posted RDMA WRITEv successfully
        }}
    }});
"""
        return code
