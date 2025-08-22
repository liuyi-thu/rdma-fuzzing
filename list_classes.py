#!/usr/bin/env python3
import argparse
import ast
from typing import List, Tuple


class ClassCollector(ast.NodeVisitor):
    def __init__(self):
        self.results: List[dict] = []
        self._stack: List[str] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        # 组合限定名（支持嵌套类）
        self._stack.append(node.name)
        qualname = ".".join(self._stack)

        # 提取基类名（尽力还原成可读字符串）
        bases = []
        for b in node.bases:
            bases.append(self._expr_to_str(b))

        # 收集方法名（实例/类/静态方法、property）
        methods, classmethods, staticmethods, properties = self._collect_methods(node)

        self.results.append(
            {
                "name": node.name,
                "qualname": qualname,
                "lineno": node.lineno,
                "bases": bases,
                "methods": methods,
                "classmethods": classmethods,
                "staticmethods": staticmethods,
                "properties": properties,
            }
        )

        # 继续递归（以捕获嵌套类）
        self.generic_visit(node)
        self._stack.pop()

    def _collect_methods(self, node: ast.ClassDef) -> Tuple[List[str], List[str], List[str], List[str]]:
        methods, classmethods, staticmethods, properties = [], [], [], []
        for n in node.body:
            if isinstance(n, ast.FunctionDef) or isinstance(n, ast.AsyncFunctionDef):
                name = n.name
                kinds = self._method_kinds(n.decorator_list)
                if "classmethod" in kinds:
                    classmethods.append(name)
                elif "staticmethod" in kinds:
                    staticmethods.append(name)
                elif "property" in kinds:
                    properties.append(name)
                else:
                    methods.append(name)
        return methods, classmethods, staticmethods, properties

    @staticmethod
    def _method_kinds(decos: List[ast.expr]) -> List[str]:
        kinds = []
        for d in decos:
            s = ClassCollector._expr_to_str(d)
            # 常见写法：@classmethod / @staticmethod / @property / @prop.setter
            if s == "classmethod":
                kinds.append("classmethod")
            elif s == "staticmethod":
                kinds.append("staticmethod")
            elif s == "property" or s.endswith(".setter") or s.endswith(".getter") or s.endswith(".deleter"):
                kinds.append("property")
        return kinds

    @staticmethod
    def _expr_to_str(e: ast.AST) -> str:
        # 将表达式（如 ast.Attribute/Name/Subscript/Call 等）大致转为可读字符串
        if isinstance(e, ast.Name):
            return e.id
        elif isinstance(e, ast.Attribute):
            return f"{ClassCollector._expr_to_str(e.value)}.{e.attr}"
        elif isinstance(e, ast.Subscript):
            return f"{ClassCollector._expr_to_str(e.value)}[{ClassCollector._expr_to_str(e.slice)}]"
        elif isinstance(e, ast.Index):  # py<3.9
            return ClassCollector._expr_to_str(e.value)
        elif isinstance(e, ast.Constant):
            return repr(e.value)
        elif isinstance(e, ast.Tuple):
            return "(" + ", ".join(ClassCollector._expr_to_str(elt) for elt in e.elts) + ")"
        elif isinstance(e, ast.Call):
            # 对于基类写成 Base[T] 或 Base(arg) 的情况，去掉括号以便更可读
            return ClassCollector._expr_to_str(e.func)
        else:
            try:
                # Python 3.9+ 有 ast.unparse
                return ast.unparse(e)  # type: ignore[attr-defined]
            except Exception:
                return e.__class__.__name__


def list_classes(py_path: str) -> List[dict]:
    with open(py_path, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src, filename=py_path, mode="exec")
    collector = ClassCollector()
    collector.visit(tree)
    # 按出现顺序（行号）排序
    return sorted(collector.results, key=lambda d: d["lineno"])


def main():
    ap = argparse.ArgumentParser(description="List classes defined in a Python file (safe, no execution).")
    ap.add_argument("path", help="Path to the .py file")
    ap.add_argument("--show-methods", action="store_true", help="Also print methods per class")
    args = ap.parse_args()

    classes = list_classes(args.path)
    if not classes:
        print("No classes found.")
        return

    for c in classes:
        header = f"{c['qualname']} (line {c['lineno']})"
        bases = f" : {', '.join(c['bases'])}" if c["bases"] else ""
        print(header + bases)
        if args.show_methods:

            def fmt(label, items):
                if items:
                    print(f"  {label}: " + ", ".join(items))

            fmt("methods", c["methods"])
            fmt("classmethods", c["classmethods"])
            fmt("staticmethods", c["staticmethods"])
            fmt("properties", c["properties"])


if __name__ == "__main__":
    main()
