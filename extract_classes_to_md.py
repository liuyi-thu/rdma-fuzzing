#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import ast
import argparse
from datetime import datetime
from typing import List, Optional, Tuple


# -------- Helpers to safely "unparse" AST nodes (py>=3.9 has ast.unparse) --------
def _node_to_src(src_text: str, node: Optional[ast.AST]) -> Optional[str]:
    if node is None:
        return None
    # Prefer exact source slice to keep comments/format where possible
    seg = ast.get_source_segment(src_text, node)
    if seg is not None:
        return seg.strip()
    # Fallback to ast.unparse if available (py>=3.9)
    if hasattr(ast, "unparse"):
        try:
            return ast.unparse(node)
        except Exception:
            pass
    # Last resort: crude literals / names
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_node_to_src(src_text, node.value)}.{node.attr}"
    return None


def _is_overload(func: ast.FunctionDef) -> bool:
    # Detect @overload decorator from typing
    for d in func.decorator_list:
        if isinstance(d, ast.Name) and d.id == "overload":
            return True
        if isinstance(d, ast.Attribute) and d.attr == "overload":
            return True
    return False


def _format_parameters(src_text: str, args: ast.arguments) -> str:
    """
    Build a Python signature parameter list string from ast.arguments.
    Handles: pos-only (PEP570), regular, vararg, kw-only, kwarg, defaults, annotations.
    """
    parts: List[str] = []

    def fmt_one(arg: ast.arg, default: Optional[ast.AST], is_kwonly: bool = False) -> str:
        name = arg.arg
        ann = _node_to_src(src_text, arg.annotation)
        default_str = _node_to_src(src_text, default) if default is not None else None
        s = name
        if ann:
            s += f": {ann}"
        if default_str is not None:
            s += f" = {default_str}"
        return s

    # 1) Positional-only (py3.8+)
    posonly = getattr(args, "posonlyargs", []) or []
    # 2) Regular positional
    pos = args.args or []
    # Defaults align to the LAST N of (posonly + pos)
    all_pos = posonly + pos
    defaults = args.defaults or []
    n_no_default = len(all_pos) - len(defaults)

    # Emit positional-only
    for i, a in enumerate(posonly):
        default = None
        if i >= n_no_default:
            default = defaults[i - n_no_default]
        parts.append(fmt_one(a, default))
    if posonly:
        parts.append("/")  # PEP570 separator

    # Emit regular positional
    for j, a in enumerate(pos):
        idx = len(posonly) + j
        default = None
        if idx >= n_no_default:
            default = defaults[idx - n_no_default]
        parts.append(fmt_one(a, default))

    # *vararg
    if args.vararg:
        var = "*" + args.vararg.arg
        ann = _node_to_src(src_text, args.vararg.annotation)
        if ann:
            var += f": {ann}"
        parts.append(var)
    else:
        # If there are kwonlyargs but no *vararg, need a bare * separator
        if args.kwonlyargs:
            parts.append("*")

    # kw-only
    for kwarg, kwdef in zip(args.kwonlyargs or [], args.kw_defaults or []):
        parts.append(fmt_one(kwarg, kwdef, is_kwonly=True))

    # **kwarg
    if args.kwarg:
        kw = "**" + args.kwarg.arg
        ann = _node_to_src(src_text, args.kwarg.annotation)
        if ann:
            kw += f": {ann}"
        parts.append(kw)

    return ", ".join(parts)


def _pick_init(cbody: List[ast.stmt]) -> List[ast.FunctionDef]:
    """Return all __init__ defs; prefer non-@overload ones for display."""
    inits = [n for n in cbody if isinstance(n, ast.FunctionDef) and n.name == "__init__"]
    return inits


def _short_doc(doc: Optional[str]) -> Optional[str]:
    if not doc:
        return None
    line = doc.strip().splitlines()[0].strip()
    return line if line else None


# -------- Core extraction --------
def extract(base_dir: str) -> List[Tuple[str, str, Optional[str], Optional[str]]]:
    """
    Returns a list of tuples:
      (rel_filepath, class_qualified_name, init_signature, init_firstline_doc)
    If class has no __init__, init_signature is "(no __init__ defined)".
    """
    out: List[Tuple[str, str, Optional[str], Optional[str]]] = []

    base_dir = os.path.normpath(base_dir)
    for root, _, files in os.walk(base_dir):
        # skip typical noise
        skip_dirs = {"__pycache__", ".mypy_cache", ".pytest_cache", ".venv", "venv", ".tox", ".git"}
        if any(part in skip_dirs for part in os.path.relpath(root, base_dir).split(os.sep)):
            continue

        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    src = f.read()
                tree = ast.parse(src, filename=path, type_comments=True)
            except Exception as e:
                print(f"[WARN] 跳过 {path}: {e}")
                continue

            rel = os.path.relpath(path, base_dir)

            # Support nested classes: keep a stack while visiting
            class StackVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.stack: List[str] = []

                def visit_ClassDef(self, node: ast.ClassDef):
                    self.stack.append(node.name)
                    # collect __init__(...) in this class body
                    inits = _pick_init(node.body)
                    if not inits:
                        qual = ".".join(self.stack)
                        out.append((rel, qual, "(no __init__ defined)", None))
                    else:
                        # If there are @overload and non-@overload, prefer non-overload list
                        non_overloads = [f for f in inits if not _is_overload(f)]
                        targets = non_overloads or inits  # if all are overloads, list them anyway
                        for f in targets:
                            sig = f"__init__({_format_parameters(src, f.args)})"
                            # try to show the first line of init docstring if exists
                            doc = ast.get_docstring(f)
                            short = _short_doc(doc)
                            qual = ".".join(self.stack)
                            out.append((rel, qual, sig, short))
                    # descend to nested classes
                    self.generic_visit(node)
                    self.stack.pop()

            StackVisitor().visit(tree)

    return out


# -------- Markdown writer --------
def write_markdown(base_dir: str, rows: List[Tuple[str, str, Optional[str], Optional[str]]], out_path: str):
    # Group by file
    from collections import defaultdict

    by_file = defaultdict(list)
    for rel, qual, sig, doc in rows:
        by_file[rel].append((qual, sig, doc))

    lines: List[str] = []
    lines.append(f"# Class & `__init__` 索引（扫描目录：`{base_dir}`）")
    lines.append("")
    lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(
        f"- 说明：如果类未定义 `__init__`，则使用父类默认构造函数。带 `@overload` 的构造将尽量显示对应实现；若只有 overload 也会列出。"
    )
    lines.append("")
    for rel in sorted(by_file):
        lines.append(f"## 📄 `{rel}`")
        lines.append("")
        lines.append("| Class | `__init__` | Doc (first line) |")
        lines.append("|---|---|---|")
        for qual, sig, doc in sorted(by_file[rel], key=lambda x: x[0]):
            sig_disp = sig if sig else ""
            doc_disp = (doc or "").replace("|", r"\|")
            lines.append(f"| `{qual}` | `{sig_disp}` | {doc_disp} |")
        lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ 已生成 Markdown：{out_path}")


# -------- CLI --------
def main():
    p = argparse.ArgumentParser(description="提取 lib/ 下所有类及其 __init__ 函数签名并导出为 Markdown。")
    p.add_argument("--base", default="lib", help="要扫描的根目录（默认：lib）")
    p.add_argument("--out", default="CLASSES_IN_LIB.md", help="输出 Markdown 文件路径")
    args = p.parse_args()

    rows = extract(args.base)
    write_markdown(args.base, rows, args.out)


if __name__ == "__main__":
    main()
