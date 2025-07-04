import ast
import sys

def extract_classes_from_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=file_path)

    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append((node.name, node.lineno))

    return classes

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法：python find_classes.py <目标.py文件>")
        sys.exit(1)

    filename = sys.argv[1]
    # try:
    #     class_list = extract_classes_from_file(filename)
    #     print(f"{filename} 中的类定义如下：")
    #     for class_name, lineno in class_list:
    #         print(f"  第 {lineno} 行：class {class_name}")
    try:
        class_list = extract_classes_from_file(filename)
        print(f"{filename} 中的类定义如下：")
        for class_name, lineno in class_list:
            print(f"class {class_name}")
    except Exception as e:
        print(f"处理文件时出错：{e}")
