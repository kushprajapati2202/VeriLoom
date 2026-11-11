"""Unit tests for AI coding systems benchmark runner."""

from pathlib import Path
from veriloom.benchmark import (
    BenchmarkRunner,
    EvaluationVerdict,
    FailureCategory,
)


def test_benchmark_runner_evaluates_passing_solution():
    root = Path(__file__).parent.parent
    pkg_dir = root / "exports" / "pkg_task_db43f6"

    # Use reference implementation code
    passing_code = (
        "\n\nclass EligibilityError(Exception): pass\n"
        "class RuleExpiredError(Exception): pass\n\n"
        "def evaluate_eligibility_policy(subtotal: float, min_threshold: float = 50.0, is_expired: bool = False) -> float:\n"
        "    if is_expired: raise RuleExpiredError('Rule is expired')\n"
        "    if subtotal < min_threshold: raise EligibilityError('Below threshold')\n"
        "    return max(0.0, subtotal - 10.0)\n"
    )

    result = BenchmarkRunner.evaluate_solution(
        pkg_dir, passing_code, model_name="Claude-3.5-Sonnet", repo_root=root
    )
    assert result.verdict == EvaluationVerdict.PASSED_FULL
    assert result.feature_tests_passed is True
    assert result.regression_clean is True
    assert result.failure_category == FailureCategory.NONE


def test_benchmark_runner_detects_flawed_solution():
    root = Path(__file__).parent.parent
    pkg_dir = root / "exports" / "pkg_task_db43f6"

    # Flawed submission with inverted condition and no clamping
    flawed_code = (
        "\n\nclass EligibilityError(Exception): pass\n"
        "class RuleExpiredError(Exception): pass\n\n"
        "def evaluate_eligibility_policy(subtotal: float, min_threshold: float = 50.0, is_expired: bool = False) -> float:\n"
        "    return subtotal - 10.0\n"
    )

    result = BenchmarkRunner.evaluate_solution(
        pkg_dir, flawed_code, model_name="WeakCandidateModel", repo_root=root
    )
    assert result.verdict == EvaluationVerdict.FEATURE_FAILED
    assert result.feature_tests_passed is False
    assert result.failure_category == FailureCategory.ASSERTION_FAILURE


def test_benchmark_compare_models_leaderboard():
    root = Path(__file__).parent.parent
    pkg_dir = root / "exports" / "pkg_task_db43f6"

    submissions = {
        "Model-A": (
            "\n\nclass EligibilityError(Exception): pass\n"
            "class RuleExpiredError(Exception): pass\n\n"
            "def evaluate_eligibility_policy(subtotal: float, min_threshold: float = 50.0, is_expired: bool = False) -> float:\n"
            "    if is_expired: raise RuleExpiredError('Rule is expired')\n"
            "    if subtotal < min_threshold: raise EligibilityError('Below threshold')\n"
            "    return max(0.0, subtotal - 10.0)\n"
        ),
        "Model-B": "def evaluate_eligibility_policy(subtotal, **kwargs): return 0.0\n",
    }

    report = BenchmarkRunner.compare_models(pkg_dir, submissions, repo_root=root)
    assert len(report.results) == 2
    assert report.leaderboard["Model-A"]["pass_rate"] == 1.0
    assert report.leaderboard["Model-B"]["pass_rate"] == 0.0

