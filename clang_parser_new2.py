import clang.cindex
from clang.cindex import CursorKind, TypeKind
import os

clang.cindex.Config.set_library_file("/usr/lib/x86_64-linux-gnu/libclang-14.so.14.0.6")

def get_func_prototype(func):
    args = []
    for arg in func.get_arguments():
        args.append("%s %s" % (arg.type.spelling, arg.spelling))
    return "%s %s(%s);" % (func.result_type.spelling, func.spelling, ", ".join(args))

def print_enum(cursor, indent=0, printed_types=None):
    if not cursor.spelling or (cursor.spelling in printed_types):
        return
    printed_types.add(cursor.spelling)
    print(" " * indent + "enum %s {" % cursor.spelling)
    for field in cursor.get_children():
        if field.kind == CursorKind.ENUM_CONSTANT_DECL:
            print(" " * (indent + 4) + "%s = %s," % (field.spelling, field.enum_value))
    print(" " * indent + "};")

def print_union(cursor, indent=0, printed_types=None):
    if not cursor.is_definition() or not cursor.spelling or (cursor.spelling in printed_types):
        return
    printed_types.add(cursor.spelling)
    print(" " * indent + "union %s {" % cursor.spelling)
    for field in cursor.get_children():
        if field.kind == CursorKind.FIELD_DECL:
            t = field.type
            type_str = t.spelling
            print(" " * (indent + 4) + "%s %s;" % (type_str, field.spelling))
            print_type(t, indent + 4, printed_types)
    print(" " * indent + "};")

def print_struct(cursor, indent=0, printed_types=None):
    if not cursor.is_definition() or not cursor.spelling or (cursor.spelling in printed_types):
        return
    printed_types.add(cursor.spelling)
    print(" " * indent + "struct %s {" % cursor.spelling)
    for field in cursor.get_children():
        if field.kind == CursorKind.FIELD_DECL:
            t = field.type
            type_str = t.spelling
            print(" " * (indent + 4) + "%s %s;" % (type_str, field.spelling))
            print_type(t, indent + 4, printed_types)
    print(" " * indent + "};")

def print_type(type, indent=0, printed_types=None):
    # 解引用所有指针
    while type.kind == TypeKind.POINTER:
        type = type.get_pointee()
    t = type.get_canonical()
    decl = t.get_declaration()
    kind = decl.kind
    if kind == CursorKind.STRUCT_DECL and decl.spelling:
        print_struct(decl, indent, printed_types)
    elif kind == CursorKind.UNION_DECL and decl.spelling:
        print_union(decl, indent, printed_types)
    elif kind == CursorKind.ENUM_DECL and decl.spelling:
        print_enum(decl, indent, printed_types)

def process_function(node):
    printed_types = set()
    print(f"Function Name: {node.spelling}\nOutput:")
    print(get_func_prototype(node))
    # 返回值
    print_type(node.result_type, 0, printed_types)
    # 参数
    for arg in node.get_arguments():
        print_type(arg.type, 0, printed_types)
    print() # 分隔

def visit(node):
    if node.kind == CursorKind.FUNCTION_DECL and node.location.file and os.path.basename(str(node.location.file)) == 'verbs.h':
        process_function(node)
    for child in node.get_children():
        visit(child)

if __name__ == '__main__':
    index = clang.cindex.Index.create()
    tu = index.parse('verbs.h', args=['-I/usr/include/infiniband', '-I/usr/include', '-I/usr/include/linux', '-D_GNU_SOURCE', '-D__USE_GNU', '-D__linux__'])
    visit(tu.cursor)
