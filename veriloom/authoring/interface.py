"""Public interface a task's hidden tests rely on: what changed between the original and the
reference file (new functions/classes/methods and changed signatures).

The solver only sees instruction.md, so the exact names and parameters the tests call must be
stated there. Deriving them from the reference implementation (rather than trusting the
specification text) guarantees they match what the tests exercise.
"""

from __future__ import annotations

import ast
from typing import Dict, List, Optional, Tuple

_PUBLIC_DUNDERS = {"__init__", "__call__"}


def _public(name: str) -> bool:
    return not name.startswith("_") or name in _PUBLIC_DUNDERS


def _sig(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    ret = f" -> {ast.unparse(fn.returns)}" if fn.returns else ""
    prefix = "async def" if isinstance(fn, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {fn.name}({ast.unparse(fn.args)}){ret}"


def _params(fn) -> List[str]:
    a = fn.args
    names = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
    if a.vararg:
        names.append("*" + a.vararg.arg)
    if a.kwarg:
        names.append("**" + a.kwarg.arg)
    return names


def _index(tree: ast.Module) -> Tuple[Dict[str, ast.AST], Dict[str, Dict[str, ast.AST]]]:
    top: Dict[str, ast.AST] = {}
    methods: Dict[str, Dict[str, ast.AST]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            top[node.name] = node
        if isinstance(node, ast.ClassDef):
            methods[node.name] = {
                n.name: n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    return top, methods


def _class_header(node: ast.ClassDef) -> str:
    bases = ", ".join(ast.unparse(b) for b in node.bases)
    return f"class {node.name}({bases}):" if bases else f"class {node.name}:"


def interface_diff(old_src: str, new_src: str) -> List[str]:
    """Python-like listing of the public names added or changed by the reference implementation."""
    try:
        old_tree, new_tree = ast.parse(old_src or ""), ast.parse(new_src)
    except SyntaxError:
        return []
    old_top, old_methods = _index(old_tree)
    new_top, new_methods = _index(new_tree)
    out: List[str] = []

    for name, node in new_top.items():
        if not _public(name):
            continue
        before = old_top.get(name)
        if isinstance(node, ast.ClassDef):
            members = []
            for mname, m in new_methods.get(name, {}).items():
                if not _public(mname):
                    continue
                old_m = old_methods.get(name, {}).get(mname)
                if old_m is None:
                    members.append(f"    {_sig(m)}  # new")
                elif _params(old_m) != _params(m):
                    added = [p for p in _params(m) if p not in _params(old_m)]
                    note = f"new parameter(s): {', '.join(added)}" if added else "signature changed"
                    members.append(f"    {_sig(m)}  # {note}")
            if before is None:
                out.append(_class_header(node) + "  # new")
                out += members or ["    ..."]
            elif members:
                out.append(_class_header(node))
                out += members
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if before is None:
                out.append(f"{_sig(node)}  # new")
            elif isinstance(before, (ast.FunctionDef, ast.AsyncFunctionDef)) and _params(before) != _params(node):
                added = [p for p in _params(node) if p not in _params(before)]
                note = f"new parameter(s): {', '.join(added)}" if added else "signature changed"
                out.append(f"{_sig(node)}  # {note}")
    return out


def interface_text(old_src: str, new_src: str) -> str:
    return "\n".join(interface_diff(old_src, new_src))


def first_new_symbol(old_src: str, new_src: str) -> Optional[str]:
    lines = interface_diff(old_src, new_src)
    return lines[0] if lines else None
