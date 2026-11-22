"""Task clarity checks: can a solver infer what the hidden tests expect?"""

import ast
import itertools
import re
from typing import Iterable, List, Set

# Bound the arithmetic closure so pathological test files stay cheap.
_MAX_BASE_VALUES = 80


def _numbers_in_text(text: str) -> Set[float]:
    return {float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", text)}


def _asserted_constants(tree: ast.AST) -> Set[int]:
    """ids of Constant nodes that are the expected side of an == comparison."""
    ids: Set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and any(isinstance(op, ast.Eq) for op in node.ops):
            for comp in [node.left, *node.comparators]:
                if isinstance(comp, ast.Constant):
                    ids.add(id(comp))
    return ids


def _input_numbers(tree: ast.AST, asserted: Set[int]) -> Set[float]:
    """Numeric constants the test passes in as inputs (prices, quantities, ...)."""
    out: Set[float] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
            and id(node) not in asserted
        ):
            out.add(float(node.value))
    return out


def _one_step_closure(values: Iterable[float]) -> Set[float]:
    """Values reachable with a single +, -, *, / between two known values, rounded to cents."""
    base = sorted(set(values), key=abs)[:_MAX_BASE_VALUES]
    out = set(base)
    for a, b in itertools.product(base, repeat=2):
        for v in (a + b, a - b, a * b, a / b if b else None):
            if v is not None:
                out.add(round(v, 2))
    return out


def unexplained_literals(test_code: str, task_text: str) -> List[str]:
    """Numeric values asserted with == that a solver could not know or derive.

    A hidden test asserting `total == 40.0` is unfair unless the task states the
    rule that produces 40.0. A value counts as explained when it appears in the
    task text, or follows in one arithmetic step from numbers the task states or
    the test passes in as inputs (e.g. 2 x 12.50 -> 25.0, 10.0 x 0.08 -> 0.8).
    Anything else, such as a magic constant chosen by the implementation, is flagged.
    """
    try:
        tree = ast.parse(test_code)
    except SyntaxError:
        return []
    asserted = _asserted_constants(tree)
    stated = _numbers_in_text(task_text)
    known = _one_step_closure(stated | _input_numbers(tree, asserted) | {0.0, 1.0})

    missing: List[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Compare) and any(isinstance(op, ast.Eq) for op in node.ops)):
            continue
        for comp in [node.left, *node.comparators]:
            if (
                isinstance(comp, ast.Constant)
                and isinstance(comp.value, (int, float))
                and not isinstance(comp.value, bool)
                and float(comp.value) not in stated
                and round(float(comp.value), 2) not in known
                and repr(comp.value) not in missing
            ):
                missing.append(repr(comp.value))
    return missing
