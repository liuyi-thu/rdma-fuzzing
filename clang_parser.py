import clang.cindex

clang.cindex.Config.set_library_file("/usr/lib/x86_64-linux-gnu/libclang-14.so.14.0.6")
def visit(node, depth=0):
    # 递归遍历AST，找到函数声明和结构体定义
    if node.kind == clang.cindex.CursorKind.FUNCTION_DECL:
        print("函数:", node.spelling)
        for arg in node.get_arguments():
            print("    参数: %s 类型: %s" % (arg.spelling, arg.type.spelling))
    elif node.kind == clang.cindex.CursorKind.STRUCT_DECL:
        print("结构体:", node.spelling)
        for field in node.get_children():
            print("    字段: %s 类型: %s" % (field.spelling, field.type.spelling))
    for child in node.get_children():
        visit(child, depth + 1)

index = clang.cindex.Index.create()
tu = index.parse('verbs.h', args=['-I/usr/include/infiniband'])
visit(tu.cursor)
