import clang.cindex
from clang.cindex import CursorKind, TypeKind
import os

clang.cindex.Config.set_library_file("/usr/lib/x86_64-linux-gnu/libclang-14.so.14.0.6")

visited_structs = set()
visited_unions = set()
visited_enums = set()

def print_enum(cursor, indent=0):
    if not cursor.spelling or cursor.spelling in visited_enums:
        return
    visited_enums.add(cursor.spelling)
    print("\n" + " " * indent + "enum %s {" % cursor.spelling)
    for field in cursor.get_children():
        if field.kind == CursorKind.ENUM_CONSTANT_DECL:
            print(" " * (indent + 4) + "%s = %s," % (field.spelling, field.enum_value))
    print(" " * indent + "};")

def print_union(cursor, indent=0):
    if not cursor.spelling or cursor.spelling in visited_unions:
        return
    visited_unions.add(cursor.spelling)
    print("\n" + " " * indent + "union %s {" % cursor.spelling)
    for field in cursor.get_children():
        if field.kind == CursorKind.FIELD_DECL:
            t = field.type
            type_str = t.spelling
            print(" " * (indent + 4) + "%s %s;" % (type_str, field.spelling))
            if t.get_declaration().kind == CursorKind.STRUCT_DECL:
                print_struct(t.get_declaration(), indent + 4)
            elif t.get_declaration().kind == CursorKind.UNION_DECL:
                print_union(t.get_declaration(), indent + 4)
            elif t.get_declaration().kind == CursorKind.ENUM_DECL:
                print_enum(t.get_declaration(), indent + 4)
    print(" " * indent + "};")

def print_struct(cursor, indent=0):
    if not cursor.spelling or cursor.spelling in visited_structs:
        return
    visited_structs.add(cursor.spelling)
    print("\n" + " " * indent + "struct %s {" % cursor.spelling)
    for field in cursor.get_children():
        if field.kind == CursorKind.FIELD_DECL:
            t = field.type
            type_str = t.spelling
            print(" " * (indent + 4) + "%s %s;" % (type_str, field.spelling))
            if t.get_declaration().kind == CursorKind.STRUCT_DECL:
                print_struct(t.get_declaration(), indent + 4)
            elif t.get_declaration().kind == CursorKind.UNION_DECL:
                print_union(t.get_declaration(), indent + 4)
            elif t.get_declaration().kind == CursorKind.ENUM_DECL:
                print_enum(t.get_declaration(), indent + 4)
    print(" " * indent + "};")

def get_underlying_type(type):
    # 递归消解typedef和pointer等
    t = type.get_canonical()
    while t.kind == TypeKind.POINTER:
        t = t.get_pointee().get_canonical()
    return t

def print_type(type, indent=0):
    t = get_underlying_type(type)
    decl = t.get_declaration()
    kind = decl.kind
    if kind == CursorKind.STRUCT_DECL and decl.spelling:
        print_struct(decl, indent)
    elif kind == CursorKind.UNION_DECL and decl.spelling:
        print_union(decl, indent)
    elif kind == CursorKind.ENUM_DECL and decl.spelling:
        print_enum(decl, indent)


def get_func_prototype(func):
    args = []
    for arg in func.get_arguments():
        args.append("%s %s" % (arg.type.spelling, arg.spelling))
    return "%s %s(%s);" % (func.result_type.spelling, func.spelling, ", ".join(args))

def visit(node):
    if node.kind == CursorKind.FUNCTION_DECL and node.location.file and os.path.basename(str(node.location.file)) == 'verbs.h':
        print(get_func_prototype(node))
        # 递归打印返回值的类型（如果是复合类型）
        print_type(node.result_type)
        # 递归打印参数类型
        for arg in node.get_arguments():
            print_type(arg.type)
    for child in node.get_children():
        visit(child)

def print_all_struct_names(node):
    if node.kind == CursorKind.STRUCT_DECL and node.is_definition():
        print("struct", node.spelling)
    for child in node.get_children():
        print_all_struct_names(child)

if __name__ == '__main__':
    index = clang.cindex.Index.create()
    tu = index.parse('verbs.h', args=['-I/usr/include/infiniband', '-I/usr/include', '-I/usr/include/linux'])
    visit(tu.cursor)

    # print_all_struct_names(tu.cursor)
