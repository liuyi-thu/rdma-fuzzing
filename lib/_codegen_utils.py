# lib/_codegen_utils.py

from collections.abc import Iterable
from typing import Any


def unwrap(value: Any) -> Any:
    """取包装器 .value，否则原样返回；递归不在这里做。"""
    return getattr(value, "value", value)


def unwrap_all(seq: Iterable[Any]) -> list:
    """对序列做递归 unwrap（仅一层），非序列原样返回。"""
    if seq is None:
        return []
    try:
        return [unwrap(x) for x in seq]
    except TypeError:
        return [unwrap(seq)]


def coerce_int(value: Any) -> int:
    """把各种 wrapper/枚举/字符串数字转为 int；失败时抛出带类型信息的异常。"""
    v = unwrap(value)
    try:
        return int(v)
    except Exception as e:
        raise TypeError(f"coerce_int: cannot convert {type(value)}({value}) to int") from e


def coerce_str(value: Any) -> str:
    """把各种 wrapper/枚举转为 str（标识符/变量名务必用它）。"""
    v = unwrap(value)
    try:
        return str(v)
    except Exception as e:
        raise TypeError(f"coerce_str: cannot convert {type(value)}({value}) to str") from e


def coerce_bool(value: Any) -> bool:
    v = unwrap(value)
    return bool(v)


def coerce_list(value: Any) -> list:
    """把 wrapper list 或单值变成 list；None -> []。"""
    if value is None:
        return []
    if hasattr(value, "value"):
        inner = value.value
        return list(inner) if inner is not None else []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def coerce_seq_of(seq: Iterable[Any], to=str) -> list:
    """把序列里每个元素先 unwrap 再转型（默认转 str）。"""
    out = []
    for x in coerce_list(seq):
        x = unwrap(x)
        out.append(to(x) if to is not None else x)
    return out


def ensure_identifier(name: Any, *, default: str = "var") -> str:
    """用于 C 变量名/标识符：unwrap -> str -> 简单清洗。"""
    s = coerce_str(name).strip()
    if not s:
        s = default
    # 简单清洗：非字母数字和下划线替换成 '_'
    clean = []
    first_ok = False
    for i, ch in enumerate(s):
        ok = ch.isalnum() or ch == "_"
        if i == 0 and not (ch.isalpha() or ch == "_"):
            clean.append("_")
        clean.append(ch if ok else "_")
    return "".join(clean)
