import json
from typing import Any, Dict, List, Optional


def verb_to_obj(verb: Any) -> Dict:
    """
    将单个 verb 转成可 JSON 序列化的 dict。
    - 如果本身就是 dict，直接返回。
    - 如果有 to_dict() / to_json() / to_json_obj() 方法，调用之。
    - 否则抛异常，让你自己处理。
    """
    if isinstance(verb, dict):
        return verb

    for method_name in ("to_dict", "to_json", "to_json_obj"):
        if hasattr(verb, method_name) and callable(getattr(verb, method_name)):
            return getattr(verb, method_name)()

    raise TypeError(f"Unsupported verb type for JSON export: {type(verb)}")


def export_verbs_to_program_json(
    verbs_list: List[Any],
    trace_id: Optional[str] = None,
    seed: Optional[int] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
    pretty: bool = True,
) -> str:
    """
    将 verbs_list 导出为 program JSON 字符串：
    {
      "version": 1,
      "meta": { ... },
      "program": [ {verb1...}, {verb2...}, ... ]
    }

    参数:
        verbs_list: 你的 verb 对象列表（dict 或自定义类均可）
        trace_id:   可选，给这个 trace 一个 ID
        seed:       可选，记录对应的随机种子
        extra_meta: 其他元信息，dict
        pretty:     是否 pretty-print（缩进），默认 True

    返回:
        JSON 字符串（str）
    """
    meta: Dict[str, Any] = {}
    if trace_id is not None:
        meta["trace_id"] = trace_id
    if seed is not None:
        meta["seed"] = seed
    if extra_meta:
        meta.update(extra_meta)

    program = [verb_to_obj(v) for v in verbs_list]

    root = {
        "version": 1,
        "meta": meta,
        "program": program,
    }

    if pretty:
        return json.dumps(root, indent=2, sort_keys=False, ensure_ascii=False)
    else:
        return json.dumps(root, separators=(",", ":"), ensure_ascii=False)
