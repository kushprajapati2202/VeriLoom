"""Benchmark evaluation runner scoring coding model submissions against task packages."""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

from veriloom.benchmark.models import (
    BenchmarkResult,
    EvaluationVerdict,
    FailureCategory,
    ModelComparisonReport,
)


class BenchmarkRunner:
    """Evaluates candidate coding model implementations against validated task packages."""

    @classmethod
    def evaluate_solution(
        cls,
        task_package_dir: Path,
        solution_code_or_patch: str,
        model_name: str = "CandidateModel",
        repo_root: Optional[Path] = None,
    ) -> BenchmarkResult:
        task_package_dir = task_package_dir.resolve()
        spec_file = task_package_dir / "task" / "specification.json"
        if not spec_file.exists():
            raise FileNotFoundError(f"Invalid package directory, missing: {spec_file}")

        spec = json.loads(spec_file.read_text(encoding="utf-8"))
        task_id = spec.get("task_id", "unknown")
        evidence = spec.get("repository_evidence", [])
        target_rel = evidence[0]["path"] if evidence else "veriloom/contracts/repository.py"

        repo_root = (repo_root or Path.cwd()).resolve()
        target_file = repo_root / target_rel
        orig_content = target_file.read_text(encoding="utf-8", errors="ignore") if target_file.exists() else ""

        # Locate feature test file in package
        feature_test_dir = task_package_dir / "tests" / "feature"
        test_files = list(feature_test_dir.glob("*.py"))
        if not test_files:
            raise FileNotFoundError(f"No feature test found in package: {feature_test_dir}")
        test_file_path = test_files[0]
        test_file_rel = f"tests/feature/{test_file_path.name}"
        active_test_file = repo_root / test_file_rel
        active_test_file.parent.mkdir(parents=True, exist_ok=True)
        active_test_file.write_text(test_file_path.read_text(encoding="utf-8"), encoding="utf-8")

        # Determine if submission is a patch or raw code
        applied_code = orig_content
        if "diff --git" in solution_code_or_patch or solution_code_or_patch.startswith("---"):
            lines = [l[1:] for l in solution_code_or_patch.splitlines() if l.startswith("+") and not l.startswith("+++")]
            applied_code = orig_content + "\n" + "\n".join(lines)
        else:
            applied_code = orig_content + "\n" + solution_code_or_patch

        t0 = time.time()
        env = {**os.environ, "PYTHONPATH": str(repo_root)}
        verdict = EvaluationVerdict.PASSED_FULL
        category = FailureCategory.NONE
        feature_passed = False
        reg_clean = True
        log_out = ""

        try:
            target_file.write_text(applied_code, encoding="utf-8")

            # 1. Run Feature Tests
            feat_proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(active_test_file), "-q"],
                capture_output=True,
                text=True,
                cwd=str(repo_root),
                env=env,
            )
            log_out += f"--- FEATURE TESTS ---\n{feat_proc.stdout}\n{feat_proc.stderr}\n"

            if feat_proc.returncode != 0:
                verdict = EvaluationVerdict.FEATURE_FAILED
                category = FailureCategory.ASSERTION_FAILURE
                feature_passed = False
            else:
                feature_passed = True

            # 2. Run Regression Suite
            reg_proc = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/test_contracts.py", "-q"],
                capture_output=True,
                text=True,
                cwd=str(repo_root),
                env=env,
            )
            log_out += f"--- REGRESSION TESTS ---\n{reg_proc.stdout}\n{reg_proc.stderr}\n"

            if reg_proc.returncode != 0:
                verdict = EvaluationVerdict.REGRESSION_INTRODUCED
                category = FailureCategory.REGRESSION_BREAK
                reg_clean = False

        except SyntaxError as e:
            verdict = EvaluationVerdict.BUILD_ERROR
            category = FailureCategory.SYNTAX_ERROR
            log_out += f"Syntax error: {e}\n"
        finally:
            # Restore files
            if active_test_file.exists():
                active_test_file.unlink()
            target_file.write_text(orig_content, encoding="utf-8")

        duration_ms = int((time.time() - t0) * 1000)

        return BenchmarkResult(
            task_id=task_id,
            model_name=model_name,
            verdict=verdict,
            feature_tests_passed=feature_passed,
            feature_tests_count=3,
            feature_tests_passed_count=3 if feature_passed else 0,
            regression_clean=reg_clean,
            failure_category=category,
            execution_time_ms=duration_ms,
            log_output=log_out,
        )

    @classmethod
    def compare_models(
        cls,
        task_package_dir: Path,
        submissions: Dict[str, str],
        repo_root: Optional[Path] = None,
    ) -> ModelComparisonReport:
        results: List[BenchmarkResult] = []
        leaderboard: Dict[str, Dict[str, float]] = {}

        for model_name, code in submissions.items():
            res = cls.evaluate_solution(task_package_dir, code, model_name=model_name, repo_root=repo_root)
            results.append(res)

            pass_score = 1.0 if res.verdict == EvaluationVerdict.PASSED_FULL else 0.0
            leaderboard[model_name] = {
                "pass_rate": pass_score,
                "regression_free": 1.0 if res.regression_clean else 0.0,
                "latency_ms": float(res.execution_time_ms),
            }

        task_id = results[0].task_id if results else "unknown"
        return ModelComparisonReport(
            task_id=task_id,
            models_evaluated=list(submissions.keys()),
            results=results,
            leaderboard=leaderboard,
        )

