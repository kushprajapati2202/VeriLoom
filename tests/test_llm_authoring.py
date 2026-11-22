"""LLM authoring loop: generate -> sandbox gates -> repair, using a scripted provider."""

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from veriloom.authoring import AuthoringError, LLMTaskAuthor
from veriloom.contracts.repository import SourceEvidence
from veriloom.contracts.task_spec import (
    FeatureFamily,
    Requirement,
    TaskDifficulty,
    TaskSpecification,
)
from veriloom.llm.provider import LLMProvider
from veriloom.packaging import HarborExporter, HarborLocalRunner, PackageBuilder

CART = textwrap.dedent('''\
    def subtotal(prices):
        return round(sum(prices), 2)
    ''')

CART_TEST = textwrap.dedent('''\
    from shop.cart import subtotal


    def test_subtotal():
        assert subtotal([1.5, 2.5]) == 4.0
    ''')

GOOD_IMPL = CART + textwrap.dedent('''\


    class DiscountError(ValueError):
        pass


    DISCOUNTS = {"SAVE10": (0.10, 50.0), "SAVE25": (0.25, 100.0)}


    def apply_discount(amount: float, code: str) -> float:
        if code not in DISCOUNTS:
            raise DiscountError(f"unknown code {code}")
        rate, minimum = DISCOUNTS[code]
        if amount < minimum:
            raise DiscountError("below minimum spend")
        return round(amount * (1 - rate), 2)
    ''')

GOOD_TESTS = textwrap.dedent('''\
    import pytest


    def test_save10_applies_at_threshold():
        from shop.cart import apply_discount
        assert apply_discount(50.0, "SAVE10") == 45.0


    def test_save25_rate():
        from shop.cart import apply_discount
        assert apply_discount(200.0, "SAVE25") == 150.0


    def test_below_minimum_rejected():
        from shop.cart import DiscountError, apply_discount
        with pytest.raises(DiscountError):
            apply_discount(49.99, "SAVE10")


    def test_unknown_code_rejected():
        from shop.cart import DiscountError, apply_discount
        with pytest.raises(DiscountError):
            apply_discount(100.0, "BOGUS")
    ''')

GOOD_META = {
    "test_file_name": "test_discounts.py",
    "requirement_tests": {
        "REQ-001": ["test_save10_applies_at_threshold", "test_save25_rate"],
        "REQ-002": ["test_below_minimum_rejected", "test_unknown_code_rejected"],
    },
    "behaviour_details": [
        "apply_discount(amount, code) returns the discounted amount rounded to 2 decimals.",
        "SAVE10 gives 10% off and needs amount >= 50.0, e.g. 50.0 -> 45.0.",
        "SAVE25 gives 25% off and needs amount >= 100.0, e.g. 200.0 -> 150.0.",
        "Unknown codes and amounts below the minimum raise DiscountError (a ValueError subclass).",
    ],
    "explanation": "Table-driven discount codes with minimum spend.",
    "mutants": [
        {"id": "MUT-001", "description": "minimum becomes exclusive", "fault_type": "boundary_shift",
         "find": "if amount < minimum:", "replace": "if amount <= minimum:"},
        {"id": "MUT-002", "description": "wrong SAVE25 rate", "fault_type": "value_corruption",
         "find": '"SAVE25": (0.25, 100.0)', "replace": '"SAVE25": (0.20, 100.0)'},
        {"id": "MUT-003", "description": "unknown code not rejected", "fault_type": "missing_check",
         "find": '    if code not in DISCOUNTS:\n        raise DiscountError(f"unknown code {code}")\n',
         "replace": ""},
        {"id": "MUT-004", "description": "returns the discount instead of the total",
         "fault_type": "operator_inversion",
         "find": "round(amount * (1 - rate), 2)", "replace": "round(amount * rate, 2)"},
        {"id": "MUT-005", "description": "bad snippet", "fault_type": "value_corruption",
         "find": "this text is not in the file", "replace": "x"},
    ],
}

# Attempt 1 is wrong in a realistic way: its tests only check existing behaviour,
# so they pass on the original code and cannot detect a missing feature.
BAD_META = dict(GOOD_META, requirement_tests={"REQ-001": ["test_subtotal_still_works"],
                                              "REQ-002": ["test_subtotal_still_works"]})
BAD_TESTS = "def test_subtotal_still_works():\n    from shop.cart import subtotal\n    assert subtotal([1, 2]) == 3\n"


def render(meta, impl, tests):
    return f"=== META ===\n{json.dumps(meta)}\n=== NEW_FILE ===\n{impl}\n=== TEST_FILE ===\n{tests}\n=== END ===\n"


class ScriptedProvider(LLMProvider):
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def generate(self, prompt, system_prompt=None):
        self.prompts.append(prompt)
        return self.replies.pop(0)


@pytest.fixture()
def cart_repo(tmp_path):
    repo = tmp_path / "cart_repo"
    (repo / "shop").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "shop" / "__init__.py").write_text("")
    (repo / "shop" / "cart.py").write_text(CART)
    (repo / "tests" / "test_cart.py").write_text(CART_TEST)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "core.autocrlf=false"]
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(git + ["add", "."], cwd=repo, check=True)
    subprocess.run(git + ["commit", "-qm", "init"], cwd=repo, check=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    return repo, commit


def make_spec(commit):
    return TaskSpecification(
        task_id="task_discounts",
        title="Add discount codes with minimum spend",
        summary="Shoppers can apply discount codes; each code has a rate and a minimum spend.",
        repository_id="cart_repo",
        starting_commit=commit,
        feature_family=FeatureFamily.BUSINESS_RULES,
        difficulty=TaskDifficulty.INTERMEDIATE,
        requirements=[
            Requirement(id="REQ-001", statement="Valid codes reduce the amount by their rate.",
                        acceptance_criteria=["SAVE10 and SAVE25 apply their rates."]),
            Requirement(id="REQ-002", statement="Invalid use of codes is rejected.",
                        acceptance_criteria=["Unknown codes and amounts under the minimum raise an error."]),
        ],
        repository_evidence=[SourceEvidence(path="shop/cart.py", reason="cart pricing")],
    )


def test_repair_loop_then_full_harbor_roundtrip(cart_repo, tmp_path):
    repo, commit = cart_repo
    provider = ScriptedProvider([render(BAD_META, GOOD_IMPL, BAD_TESTS), render(GOOD_META, GOOD_IMPL, GOOD_TESTS)])

    authored = LLMTaskAuthor(provider).author(make_spec(commit), repo, commit)

    # Attempt 1 rejected by the fail-before gate, and the failure was fed back.
    assert len(authored.attempts) == 2
    first = {g["name"]: g["passed"] for g in authored.attempts[0].gates}
    assert first["fail_before"] is False
    assert "fail_before" in provider.prompts[1]

    gates = {g.name: g.passed for g in authored.gate_report.gates}
    assert all(gates.values()), authored.gate_report
    statuses = {m.id: m.status for m in authored.gate_report.mutants}
    assert statuses == {"MUT-001": "KILLED", "MUT-002": "KILLED", "MUT-003": "KILLED",
                        "MUT-004": "KILLED", "MUT-005": "INVALID"}
    assert authored.gate_report.regression_targets == ["tests/test_cart.py"]
    assert authored.validation_report.status.value == "passed"
    assert any("45.0" in d for d in authored.spec.behaviour_details)
    # The user's repository is untouched.
    assert (repo / "shop" / "cart.py").read_text() == CART

    # Package -> Harbor -> local oracle/no-op replay.
    from veriloom.contracts.repository import RepositoryRecord
    from veriloom.variation import VariationEngine

    record = RepositoryRecord(repository_id="cart_repo", source_path=str(repo), starting_commit=commit,
                              working_tree_clean=True, language="python")
    pkg = PackageBuilder.build_package(
        authored.spec, record, authored.reference_solution, authored.test_suite,
        authored.validation_report, VariationEngine.evaluate_variation(authored.spec, []),
        tmp_path / "out", authoring_log={"attempts": [a.model_dump() for a in authored.attempts]},
    )
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["verdict"]["mutation_score_pct"] == 100.0

    exported = HarborExporter.export(pkg, repo, tmp_path / "harbor")
    assert exported.patch_applies
    assert exported.warnings == []  # every asserted value is stated in the instruction
    instruction = (Path(exported.task_dir) / "instruction.md").read_text()
    assert "## Behaviour details" in instruction and "def apply_discount(" in instruction

    check = HarborLocalRunner.check(Path(exported.task_dir))
    assert check.oracle.reward == 1, check.oracle.log
    assert check.nop.reward == 0, check.nop.log


def test_gives_up_with_evidence_after_max_attempts(cart_repo):
    repo, commit = cart_repo
    provider = ScriptedProvider([render(BAD_META, GOOD_IMPL, BAD_TESTS), "not the right format at all"])
    with pytest.raises(AuthoringError) as err:
        LLMTaskAuthor(provider, max_attempts=2).author(make_spec(commit), repo, commit)
    assert "fail_before failed" in str(err.value)
    assert "missing the === META ===" in str(err.value)


def test_surviving_mutant_fails_mutation_gate(cart_repo):
    repo, commit = cart_repo
    weak_tests = GOOD_TESTS.replace('assert apply_discount(200.0, "SAVE25") == 150.0',
                                    'assert apply_discount(200.0, "SAVE25") < 200.0')
    provider = ScriptedProvider([render(GOOD_META, GOOD_IMPL, weak_tests)])
    with pytest.raises(AuthoringError):
        LLMTaskAuthor(provider, max_attempts=1).author(make_spec(commit), repo, commit)
