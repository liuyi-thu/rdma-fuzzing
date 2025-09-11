# lib/debug_dump.py
from __future__ import annotations
import json
import difflib
from typing import Any
from termcolor import colored

# ========== 基础：值层序列化（支持 OptionalValue / ResourceValue / EnumValue / FlagValue 等） ==========


def _unwrap_for_debug(x: Any) -> Any:
    """
    把各种 wrapper（OptionalValue/ResourceValue/ConstantValue/...）摊平成可序列化/可读对象。
    - OptionalValue(None)         -> {"__opt__": None}
    - OptionalValue(inner!=None)  -> {"__opt__": <inner-serialized>}
    - ResourceValue(name, type)   -> {"__res__": {"type": "...", "name": "..."}}
    - EnumValue / FlagValue       -> {"__enum__"/"__flag__": {"type":"...", "value": 原始值, "str": "..."}}
    - 普通标量 / list / dict 递归处理
    """
    if x is None:
        return None

    # OptionalValue
    inner = getattr(x, "inner", None)
    if inner is not None and hasattr(x, "is_none"):
        return {"__opt__": _unwrap_for_debug(inner) if not x.is_none() else None}

    # ResourceValue
    if hasattr(x, "resource_type") and hasattr(x, "name"):
        return {"__res__": {"type": getattr(x, "resource_type"), "name": str(getattr(x, "name"))}}

    # EnumValue / FlagValue
    if hasattr(x, "enum_type"):
        v = getattr(x, "value", None)
        return {"__enum__": {"type": getattr(x, "enum_type"), "value": _unwrap_for_debug(v), "str": str(v)}}
    if hasattr(x, "flag_type"):
        v = getattr(x, "value", None)
        return {"__flag__": {"type": getattr(x, "flag_type"), "value": _unwrap_for_debug(v), "str": str(v)}}

    # ConstantValue / IntValue / BoolValue 等统一当作有 .value 的壳
    if hasattr(x, "value"):
        return _unwrap_for_debug(getattr(x, "value"))

    # Attr/结构体类（有 FIELD_LIST 或 MUTABLE_FIELDS）
    fields = getattr(x.__class__, "FIELD_LIST", None) or getattr(x.__class__, "MUTABLE_FIELDS", None)
    if fields:
        out = {"__attr__": x.__class__.__name__}
        for f in fields:
            if hasattr(x, f):
                out[f] = _unwrap_for_debug(getattr(x, f))
        return out

    # 一般对象：尝试遍历 __dict__
    if hasattr(x, "__dict__"):
        out = {"__obj__": x.__class__.__name__}
        for k, v in x.__dict__.items():
            if k.startswith("tracker") or k.startswith("_"):
                continue
            out[k] = _unwrap_for_debug(v)
        return out

    # 容器
    if isinstance(x, (list, tuple)):
        return [_unwrap_for_debug(e) for e in x]
    if isinstance(x, dict):
        return {str(k): _unwrap_for_debug(v) for k, v in x.items()}

    # 标量
    return x


# ========== verb 层序列化/打印 ==========


def verb_to_dict(v: Any) -> dict[str, Any]:
    """把单个 verb 摊平成结构化 dict。"""
    d: dict[str, Any] = {
        "__verb__": v.__class__.__name__,
    }
    # 优先用类字段列表；否则用 __dict__
    fields = getattr(v.__class__, "MUTABLE_FIELDS", None) or getattr(v.__class__, "FIELD_LIST", None)
    if not fields:
        fields = [k for k in getattr(v, "__dict__", {}).keys() if not k.startswith("_") and not k.startswith("tracker")]
    for f in fields:
        if hasattr(v, f):
            d[f] = _unwrap_for_debug(getattr(v, f))
    return d


def verbs_to_dict_list(verbs: list[Any]) -> list[dict[str, Any]]:
    return [verb_to_dict(v) for v in verbs]


def dump_verbs(verbs: list[Any], *, indent: int = 2) -> str:
    """
    美观打印 verb list（JSON 树），含 verb 种类与参数。
    - 用于人工 debug
    - 也可以把该输出传给 diff 做文本级对比
    """
    payload = {
        "count": len(verbs),
        "verbs": verbs_to_dict_list(verbs),
    }
    return json.dumps(payload, ensure_ascii=False, indent=indent, sort_keys=True)


# ========== 快照与对比（前后 diff） ==========


def snapshot_verbs(verbs: list[Any]) -> list[dict[str, Any]]:
    """结构化快照，可持久保存或后续做深度对比。"""
    return verbs_to_dict_list(verbs)


def diff_verb_snapshots(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> str:
    """
    结构化快照的文本 diff（统一 diff 样式），适合快速查看“mutate 改了啥”。
    备注：这里用 JSON 行文本做 diff，足够直观且实现简单。
    """
    a = json.dumps({"verbs": before}, ensure_ascii=False, indent=2, sort_keys=True).splitlines(keepends=True)
    b = json.dumps({"verbs": after}, ensure_ascii=False, indent=2, sort_keys=True).splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, fromfile="before", tofile="after"))


def diff_verb_lists(before_verbs: list[Any], after_verbs: list[Any]) -> str:
    """直接对两个 verb 列表做 diff（内部先做快照）。"""
    return diff_verb_snapshots(snapshot_verbs(before_verbs), snapshot_verbs(after_verbs))


# ===== Deep summarize helpers =====

# 针对常见 Attr 类型的“优先字段”顺序（可继续按需补充）
_PREFERRED_FIELDS = {
    "IbvQPAttr": [
        "qp_state",
        "path_mtu",
        "dest_qp_num",
        "port_num",
        "qp_access_flags",
        "rq_psn",
        "sq_psn",
        "timeout",
        "retry_cnt",
        "rnr_retry",
        "max_rd_atomic",
        "max_dest_rd_atomic",
        "min_rnr_timer",
        "cap",
        "ah_attr",
    ],
    "IbvQPInitAttr": ["send_cq", "recv_cq", "srq", "qp_type", "cap", "sq_sig_all"],
    "IbvQPCap": ["max_send_wr", "max_recv_wr", "max_send_sge", "max_recv_sge", "max_inline_data"],
    "IbvAHAttr": ["dlid", "is_global", "port_num", "grh", "sl", "src_path_bits", "static_rate"],
    "IbvGlobalRoute": ["sgid_index", "hop_limit", "traffic_class", "flow_label", "dgid"],
    "IbvSendWR": ["opcode", "num_sge", "sg_list"],
    "IbvRecvWR": ["num_sge", "sg_list"],
    "IbvSge": ["addr", "length", "lkey"],
}


def _is_attr_obj(x: Any) -> bool:
    cls = x.__class__
    return bool(getattr(cls, "FIELD_LIST", None) or getattr(cls, "MUTABLE_FIELDS", None))


def _string_of_enum_or_flag(x: Any) -> str | None:
    # 你的 EnumValue/FlagValue 通常有 .value 和 .enum_type/.flag_type；用 str(value) 更直观（如 "IBV_QPS_RTS"）
    if hasattr(x, "enum_type") and hasattr(x, "value"):
        return str(getattr(x, "value"))
    if hasattr(x, "flag_type") and hasattr(x, "value"):
        return str(getattr(x, "value"))
    return None


def _short_scalar(x: Any) -> str:
    s = str(x)
    return s if len(s) <= 48 else s[:45] + "..."


def _summarize_value_short(v: Any, *, depth: int = 0, max_items: int = 4) -> str:
    """把任意值压缩成短字符串，支持 Optional/Resource/Enum/Attr/列表 的递归摘要。"""
    if v is None:
        return "∅"

    # OptionalValue
    if hasattr(v, "is_none"):
        if v.is_none():
            return "∅"
        inner = getattr(v, "value", None)
        if inner is not None:
            return _summarize_value_short(inner, depth=depth, max_items=max_items)

    # ResourceValue
    if hasattr(v, "resource_type") and hasattr(v, "value"):
        return f"{getattr(v, 'value')}<{getattr(v, 'resource_type')}>"

    # Enum/Flag
    sf = _string_of_enum_or_flag(v)
    if sf is not None:
        return sf

    # Constant/Int/Bool 等统一看 .value
    if hasattr(v, "value"):
        return _summarize_value_short(getattr(v, "value"), depth=depth, max_items=max_items)

    # Attr 对象
    if _is_attr_obj(v):
        return _summarize_attr(v, depth=depth, max_items=max_items)

    # 列表/元组
    if isinstance(v, (list, tuple)):
        n = len(v)
        if n == 0:
            return "[]"
        head = v[0]
        if _is_attr_obj(head):
            # 列表里放的是结构体：展示第一个 + 计数
            return f"[{head.__class__.__name__} x{n}: {_summarize_attr(head, depth=depth + 1, max_items=max_items)}]"
        else:
            # 普通标量：展示前几个
            items = ", ".join(
                _short_scalar(_summarize_value_short(it, depth=depth + 1, max_items=max_items)) for it in v[:max_items]
            )
            suffix = "" if n <= max_items else f", …+{n - max_items}"
            return f"[{items}{suffix}]"

    # 字典
    if isinstance(v, dict):
        keys = list(v.keys())
        items = ", ".join(
            f"{k}={_summarize_value_short(v[k], depth=depth + 1, max_items=max_items)}" for k in keys[:max_items]
        )
        suffix = "" if len(keys) <= max_items else f", …+{len(keys) - max_items}"
        return "{" + items + suffix + "}"

    # 标量
    return _short_scalar(v)


def _summarize_attr(obj: Any, *, depth: int = 0, max_items: int = 4) -> str:
    """Attr 对象摘要：按优先字段选取若干 key=val；子结构再递归一层。"""
    cls = obj.__class__.__name__
    fields = getattr(obj.__class__, "FIELD_LIST", None) or getattr(obj.__class__, "MUTABLE_FIELDS", None) or []
    # 组装优先顺序
    prefer = _PREFERRED_FIELDS.get(cls, [])
    ordered = [f for f in prefer if f in fields] + [f for f in fields if f not in prefer]

    shown = []
    for f in ordered:
        if len(shown) >= max_items:
            break
        if not hasattr(obj, f):
            continue
        val = getattr(obj, f)
        # Optional(None) 跳过
        if hasattr(val, "is_none") and val.is_none():
            continue
        shown.append(f"{f}={_summarize_value_short(val, depth=depth + 1, max_items=max_items)}")

    inside = ", ".join(shown)
    return f"{cls}{{{inside}}}"


# ========== 单行摘要（适合日志） ==========


def _fmt_scalar(x: Any) -> str:
    if x is None:
        return "∅"
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, (int, float)):
        return str(x)
    s = str(x)
    if len(s) > 48:
        s = s[:45] + "..."
    return s


# def summarize_verb(v: Any, max_fields: int = 6) -> str:
#     """
#     单行摘要：VerbName(k1=v1, k2=v2, ...)
#     - ResourceValue 显示 name<type>
#     - OptionalValue(None) 显示 k=∅
#     - 过长的值做截断
#     """
#     name = v.__class__.__name__
#     parts = []

#     def show_pair(k, val):
#         # ResourceValue
#         if hasattr(val, "resource_type") and hasattr(val, "value"):
#             parts.append(f"{k}={val.value}<{val.resource_type}>")
#             return
#         # OptionalValue
#         if hasattr(val, "is_none"):
#             if val.is_none():
#                 parts.append(f"{k}=∅")
#                 return
#             inner = getattr(val, "inner", None)
#             if inner is not None:
#                 return show_pair(k, inner)
#         # Enum/Flag
#         if hasattr(val, "enum_type") and hasattr(val, "value"):
#             parts.append(f"{k}={str(val.value)}")
#             return
#         if hasattr(val, "flag_type") and hasattr(val, "value"):
#             parts.append(f"{k}={str(val.value)}")
#             return
#         # 普通
#         parts.append(f"{k}={_fmt_scalar(val)}")

#     fields = getattr(v.__class__, "MUTABLE_FIELDS", None) or getattr(v.__class__, "FIELD_LIST", None)
#     if not fields:
#         fields = [k for k in getattr(v, "__dict__", {}).keys()
#                   if not k.startswith("_") and not k.startswith("tracker")]

#     for f in fields[:max_fields]:
#         if hasattr(v, f):
#             show_pair(f, getattr(v, f))

#     extra = ""
#     if len(fields) > max_fields:
#         extra = f", …+{len(fields)-max_fields} fields"

#     return f"{name}(" + ", ".join(parts) + extra + ")"

# def summarize_verb_list(verbs: List[Any]) -> str:
#     lines = []
#     for i, v in enumerate(verbs):
#         lines.append(f"[{i:02d}] {summarize_verb(v)}")
#     return "\n".join(lines)


def summarize_verb(v: Any, max_fields: int = 6, *, deep: bool = False, max_items: int = 4) -> str:
    if not v:
        return "∅"
    name = v.__class__.__name__
    parts = []

    def show_pair(k, val):
        if deep:
            parts.append(f"{k}={_summarize_value_short(val, max_items=max_items)}")
            return
        # ------- 浅层旧逻辑（保留） -------
        # ResourceValue
        if hasattr(val, "resource_type") and hasattr(val, "name"):
            parts.append(f"{k}={val.name}<{val.resource_type}>")
            return
        # OptionalValue
        if hasattr(val, "is_none"):
            if val.is_none():
                parts.append(f"{k}=∅")
                return
            inner = getattr(val, "inner", None)
            if inner is not None:
                return show_pair(k, inner)
        # Enum/Flag
        if hasattr(val, "enum_type") and hasattr(val, "value"):
            parts.append(f"{k}={str(val.value)}")
            return
        if hasattr(val, "flag_type") and hasattr(val, "value"):
            parts.append(f"{k}={str(val.value)}")
            return
        # 普通
        parts.append(f"{k}={_fmt_scalar(val)}")

    fields = getattr(v.__class__, "MUTABLE_FIELDS", None) or getattr(v.__class__, "FIELD_LIST", None)
    if not fields:
        fields = [k for k in getattr(v, "__dict__", {}).keys() if not k.startswith("_") and not k.startswith("tracker")]

    for f in fields[:max_fields]:
        if hasattr(v, f):
            show_pair(f, getattr(v, f))

    extra = ""
    if len(fields) > max_fields:
        extra = f", …+{len(fields) - max_fields} fields"

    return f"{name}(" + ", ".join(parts) + extra + ")"


def summarize_verb_list(verbs: list[Any], *, deep: bool = False, highlight: int = None, color: str = "red") -> str:
    lines = []
    for i, v in enumerate(verbs):
        if i == highlight:
            # lines.append(f"\033[93m>[{i:02d}] {summarize_verb(v, deep=deep)}\033[0m")
            lines.append(colored(f">[{i:02d}] {summarize_verb(v, deep=deep)}", color))
        else:
            lines.append(f"[{i:02d}] {summarize_verb(v, deep=deep)}")
    return "\n".join(lines)
