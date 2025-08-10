def emit_assign(varname, field, value, enums=None):
    # enums: dict(field->enum_map)
    if enums and field in enums:
        enum_map = enums[field]
        if value in enum_map:
            value = enum_map[value]
    return f"    {varname}.{field} = {value};\n"