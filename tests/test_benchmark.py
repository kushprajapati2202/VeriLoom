"""Benchmark runner tests against a shipped, LLM-authored task package.

Self-contained: the demo target repository is materialised into a temp dir with
scripts/setup_demo_repo.py, so these tests work on a fresh clone.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from veriloom.benchmark import BenchmarkRunner, EvaluationVerdict, FailureCategory

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "examples" / "sample_packages" / "shopcart" / "pkg_task_eaf600"  # product lifecycle task


@pytest.fixture(scope="module")
def shopcart(tmp_path_factory):
    dest = tmp_path_factory.mktemp("repos") / "shopcart"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "setup_demo_repo.py"), "shopcart",
                    "--dest", str(dest)], check=True, capture_output=True)
    return dest


def test_reference_patch_passes(shopcart):
    patch = (PKG / "reference" / "implementation.patch").read_text(encoding="utf-8")
    r = BenchmarkRunner.evaluate_solution(PKG, patch, model_name="reference", repo_root=shopcart)
    assert r.verdict == EvaluationVerdict.PASSED_FULL
    assert r.feature_tests_passed and r.regression_clean
    assert r.feature_tests_count == r.feature_tests_passed_count > 0


def test_missing_feature_fails(shopcart):
    r = BenchmarkRunner.evaluate_solution(PKG, "def unrelated():\n    return 1\n", repo_root=shopcart)
    assert r.verdict == EvaluationVerdict.FEATURE_FAILED
    assert r.failure_category == FailureCategory.ASSERTION_FAILURE
    assert r.feature_tests_passed_count < r.feature_tests_count


def test_syntax_error_is_build_error(shopcart):
    r = BenchmarkRunner.evaluate_solution(PKG, "def broken(:\n", repo_root=shopcart)
    assert r.verdict == EvaluationVerdict.BUILD_ERROR
    assert r.failure_category == FailureCategory.SYNTAX_ERROR


def test_patch_that_does_not_apply_is_build_error(shopcart):
    bad = "--- a/shopcart/catalog.py\n+++ b/shopcart/catalog.py\n@@ -1,1 +1,1 @@\n-no such line\n+x\n"
    r = BenchmarkRunner.evaluate_solution(PKG, bad, repo_root=shopcart)
    assert r.verdict == EvaluationVerdict.BUILD_ERROR


def test_breaking_existing_behaviour_is_caught(shopcart):
    # Correct feature, but `take` no longer removes stock: existing tests must catch it.
    patch = (PKG / "reference" / "implementation.patch").read_text(encoding="utf-8")
    r_ok = BenchmarkRunner.evaluate_solution(PKG, patch, repo_root=shopcart)
    assert r_ok.regression_clean
    sabotage = "\n_orig_take = Catalog.take\nCatalog.take = lambda self, sku, q: self.stock_of(sku)\n"
    r = BenchmarkRunner.evaluate_solution(PKG, sabotage, repo_root=shopcart)
    assert not r.regression_clean


def test_repository_is_never_modified(shopcart):
    BenchmarkRunner.evaluate_solution(PKG, "def broken(:\n", repo_root=shopcart)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=shopcart, capture_output=True, text=True)
    assert status.stdout.strip() == ""


def test_compare_models_leaderboard(shopcart):
    patch = (PKG / "reference" / "implementation.patch").read_text(encoding="utf-8")
    report = BenchmarkRunner.compare_models(
        PKG, {"strong": patch, "weak": "def unrelated():\n    return 1\n"}, repo_root=shopcart
    )
    assert report.leaderboard["strong"]["pass_rate"] == 1.0
    assert report.leaderboard["weak"]["pass_rate"] == 0.0
