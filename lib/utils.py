def emit_assign(varname, field, value, enums=None):
    # enums: dict(field->enum_map)
    if enums and field in enums:
        enum_map = enums[field]
        if value in enum_map:
            value = enum_map[value]
    return f"    {varname}.{field} = {value};\n"


# TODO: 以下代码备用


# # utils_or_codegen.py (你现在 emit_assign 所在文件)
# import itertools

# _tmp_id_counter = itertools.count()

# def emit_assign(varname: str, field: str, value, enums: dict | None = None) -> str:
#     """
#     通用赋值：
#       - 若 value 是基本字面量，直接赋值；
#       - 若 value 是 wrapper（含 DeferredValue），调用 value.to_cxx(tmp) 生成临时变量，再赋值；
#       - 若 value 是 EnumValue/FlagValue 等，按你现有逻辑处理。
#     """
#     s = ""
#     # 1) 可展开对象（支持 DeferredValue / Ibv*Attr / etc.）
#     if hasattr(value, "to_cxx") and callable(getattr(value, "to_cxx")):
#         tmp = f"tmp_{next(_tmp_id_counter)}"
#         # 推断 C 类型：如果是 DeferredValue，拿它的 c_type；否则给个通用类型或由 value 内部声明
#         cty = getattr(value, "c_type", None)
#         if cty is not None and hasattr(value, "to_cxx"):
#             # 让 value 内部做声明（ctx.alloc_variable）
#             s += value.to_cxx(tmp, ctx=None)  # 如果你需要 ctx 来 alloc，可以把 ctx 传进来
#         else:
#             s += value.to_cxx(tmp)
#         s += f"    {varname}.{field} = {tmp};\n"
#         return s

#     # 2) 字符串常量（例如 "IBV_QPS_RTS"）
#     if isinstance(value, str):
#         # 如果是枚举名，保留原样；如果是普通字符串，需要引号
#         if value.startswith("IBV_") or value.startswith("RDMA_"):
#             s += f"    {varname}.{field} = {value};\n"
#         else:
#             s += f'    {varname}.{field} = "{value}";\n'
#         return s

#     # 3) 基本数字
#     if isinstance(value, (int, float)):
#         s += f"    {varname}.{field} = {value};\n"
#         return s

#     # 4) 其它情况（例如 ConstantValue 等）按你项目原逻辑：
#     if hasattr(value, "get_c_literal"):
#         s += f"    {varname}.{field} = {value.get_c_literal()};\n"
#         return s

#     # 兜底：直接 str()
#     s += f"    {varname}.{field} = {value};\n"
#     return s
