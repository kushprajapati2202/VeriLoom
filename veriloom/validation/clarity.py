"""Task clarity checks: can a solver infer what the hidden tests expect?"""

import ast
import re
from typing import List


def unexplained_literals(test_code: str, task_text: str) -> List[str]:
    """Numeric literals compared with == in tests that never appear in the task text.

    A hidden test asserting `total == 40.0` is unfair unless the task states the
    rule that produces 40.0 (or the value itself). This is a heuristic: it only
    looks at numeric constants in equality comparisons.
    """
    try:
        tree = ast.parse(test_code)
    except SyntaxError:
        return []
    stated = {float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", task_text)}
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
                and repr(comp.value) not in missing
            ):
                missing.append(repr(comp.value))
    return missing
