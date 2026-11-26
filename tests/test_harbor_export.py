"""Harbor 0.25 export: layout, task.toml, fail_to_pass / pass_to_pass, reward matrix."""

import json
import shutil
import tomllib
from pathlib import Path

import pytest

from test_llm_authoring import (  # same tiny shop repository and scripted model as the authoring test
    CART,
    GOOD_IMPL,
    GOOD_META,
    GOOD_TESTS,
    ScriptedProvider,
    make_spec,
    render,
)
from veriloom.authoring import LLMTaskAuthor
from veriloom.contracts.repository import RepositoryRecord
from veriloom.packaging import HarborExporter, HarborLocalRunner, PackageBuilder
from veriloom.reference_solution.patch_manager import PatchManager
from veriloom.variation import VariationEngine


def _git_repo(root: Path):
    import subprocess

    repo = root / "cart_repo"
    (repo / "shop").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "shop" / "__init__.py").write_text("")
    (repo / "shop" / "cart.py").write_text(CART)
    (repo / "tests" / "test_cart.py").write_text(
        "from shop.cart import subtotal\n\n\ndef test_subtotal():\n    assert subtotal([1.5, 2.5]) == 4.0\n"
    )
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "core.autocrlf=false"]
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(git + ["add", "."], cwd=repo, check=True)
    subprocess.run(git + ["commit", "-qm", "init"], cwd=repo, check=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    return repo, commit


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    root = tmp_path_factory.mktemp("harbor_export")
    repo, commit = _git_repo(root)
    authored = LLMTaskAuthor(ScriptedProvider([render(GOOD_META, GOOD_IMPL, GOOD_TESTS)])).author(
        make_spec(commit), repo, commit
    )
    record = RepositoryRecord(repository_id="cart_repo", source_path=str(repo), starting_commit=commit,
                              working_tree_clean=True, language="python")
    pkg = PackageBuilder.build_package(
        authored.spec, record, authored.reference_solution, authored.test_suite,
        authored.validation_report, VariationEngine.evaluate_variation(authored.spec, []), root / "out",
    )
    result = HarborExporter.export(pkg, repo, root / "harbor")
    return result, repo, commit


def test_layout_matches_track1_spec(exported):
    result, _, _ = exported
    task = Path(result.task_dir)
    for rel in (
        "instruction.md", "task.toml", "environment/Dockerfile",
        "solution/solve.sh", "solution/reference.patch",
        "tests/test.sh", "tests/fail_to_pass.json", "tests/pass_to_pass.json",
        "tests/feature/test_discounts.py", "tests/regression/tests/test_cart.py",
        "tests/lib/grade.py", "tests/lib/veriloom_outcomes.py",
    ):
        assert (task / rel).is_file(), rel
    assert result.patch_applies


def test_task_toml_records_base_commit(exported):
    result, _, commit = exported
    data = tomllib.loads((Path(result.task_dir) / "task.toml").read_text(encoding="utf-8"))
    assert data["metadata"]["base_commit"] == commit and len(commit) == 40
    assert data["metadata"]["fail_to_pass"] == "tests/fail_to_pass.json"
    assert data["task"]["name"] == "veriloom/cart_repo-task_discounts"
    assert data["verifier"]["environment_mode"] == "shared"


def test_task_toml_parses_with_harbor_if_installed(exported):
    harbor_config = pytest.importorskip("harbor.models.task.config")
    result, _, _ = exported
    cfg = harbor_config.TaskConfig.model_validate_toml(
        (Path(result.task_dir) / "task.toml").read_text(encoding="utf-8"))
    assert cfg.metadata["base_commit"]


def test_fail_to_pass_and_pass_to_pass_are_measured(exported):
    result, _, _ = exported
    tests = Path(result.task_dir) / "tests"
    f2p = json.loads((tests / "fail_to_pass.json").read_text())
    p2p = json.loads((tests / "pass_to_pass.json").read_text())
    assert f2p == sorted(f"/tests/feature/test_discounts.py::{n}" for n in (
        "test_below_minimum_rejected", "test_save10_applies_at_threshold",
        "test_save25_rate", "test_unknown_code_rejected"))
    assert p2p == ["tests/test_cart.py::test_subtotal"]


def test_snapshot_environment_for_repo_without_remote(exported):
    result, _, _ = exported
    dockerfile = (Path(result.task_dir) / "environment" / "Dockerfile").read_text()
    assert "COPY repo/ /app/" in dockerfile and "@sha256:" in dockerfile
    assert result.repository_url is None


def test_scripts_use_lf_endings(exported):
    task = Path(exported[0].task_dir)
    for rel in ("tests/test.sh", "solution/solve.sh", "solution/reference.patch", "environment/Dockerfile"):
        assert b"\r\n" not in (task / rel).read_bytes(), rel


def test_instruction_states_interface_not_solution(exported):
    text = (Path(exported[0].task_dir) / "instruction.md").read_text(encoding="utf-8")
    assert "REQ-001" in text and "REQ-002" in text
    assert "def apply_discount(amount: float, code: str) -> float  # new" in text
    assert "round(amount * (1 - rate), 2)" not in text  # implementation body must not leak


def test_oracle_one_nop_zero(exported):
    result, repo, _ = exported
    report = HarborLocalRunner.check(Path(result.task_dir), repo_path=repo)
    assert report.oracle.reward == 1.0, report.oracle.log
    assert report.nop.reward == 0.0, report.nop.log
    assert report.passed


def _with_solution(result, tmp_path, impl):
    task = tmp_path / "task"
    shutil.copytree(result.task_dir, task)
    patch = PatchManager.generate_diff({"shop/cart.py": CART}, {"shop/cart.py": impl})
    (task / "solution" / "reference.patch").write_text(patch, encoding="utf-8", newline="\n")
    return task


def test_partial_solution_gets_share_of_feature_tests(exported, tmp_path):
    result, repo, _ = exported
    task = _with_solution(result, tmp_path, GOOD_IMPL.replace('"SAVE25": (0.25', '"SAVE25": (0.20'))
    trial = HarborLocalRunner.run_trial(task, "oracle", repo_path=repo)
    assert trial.reward == 0.75, trial.log  # 3 of 4 fail_to_pass tests pass


def test_any_regression_zeroes_the_reward(exported, tmp_path):
    result, repo, _ = exported
    broken = GOOD_IMPL.replace("return round(sum(prices), 2)", "return round(sum(prices), 2) + 1")
    trial = HarborLocalRunner.run_trial(_with_solution(result, tmp_path, broken), "oracle", repo_path=repo)
    assert trial.reward == 0.0, trial.log


# ---------------------------------------------------------------- helpers used by the exporter


def test_interface_diff_reports_new_and_changed_signatures():
    from veriloom.authoring.interface import interface_diff

    old = "class Opt:\n    def __init__(self, name):\n        pass\n\ndef f(a):\n    pass\n"
    new = ("class Opt:\n    def __init__(self, name, *, limit=None):\n        pass\n"
           "    def check(self, value):\n        pass\n\ndef f(a):\n    pass\n\ndef g(x=1):\n    pass\n")
    lines = interface_diff(old, new)
    assert "class Opt:" in lines
    assert "    def __init__(self, name, *, limit=None)  # new parameter(s): limit" in lines
    assert "    def check(self, value)  # new" in lines
    assert "def g(x=1)  # new" in lines
    assert not any(l.startswith("def f(") for l in lines)


def test_module_for_src_layout():
    from veriloom.validation.sandbox import module_for

    assert module_for("src/click/types.py") == "click.types"
    assert module_for("shop/cart.py") == "shop.cart"
    assert module_for("src/click/__init__.py") == "click"


def test_edit_blocks_apply_and_report_bad_anchor():
    from veriloom.authoring.llm_author import AuthoringError, apply_edits

    src = "def a():\n    return 1\n"
    ok = "<<<<<<< SEARCH\ndef a():\n    return 1\n=======\ndef a():\n    return 2\n>>>>>>> REPLACE\n"
    assert apply_edits(src, ok) == "def a():\n    return 2\n"
    with pytest.raises(AuthoringError, match="matches 0 times"):
        apply_edits(src, ok.replace("return 1", "return 9", 1))
