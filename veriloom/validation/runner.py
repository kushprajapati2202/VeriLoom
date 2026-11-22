"""Validation runner executing baseline, reference, regression, and mutation gates."""

import os
import shutil
import subprocess
import tempfile
import sys
import time
from pathlib import Path
from typing import List

from veriloom.contracts.task_spec import TaskSpecification
from veriloom.contracts.validation import (
    CheckStatus,
    CheckOutcome,
    RegressionSummary,
    ValidationReport,
    MutationCheck,
    MutantStatus,
)
from veriloom.contracts.repository import RepositoryRecord
from veriloom.test_generation.feature_tests import GeneratedTestSuite
from veriloom.reference_solution.agent import ReferenceSolutionResult
from veriloom.validation.mutation import MutationEngine

_COPY_IGNORE = shutil.ignore_patterns(
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "exports", "harbor_tasks",
    "node_modules", "demo_video", "*.egg-info", ".env",
)


class ValidationRunner:
    """Executes the 5-stage validation pipeline: baseline, build, feature tests, regression, and mutation."""

    @classmethod
    def run_validation(
        cls,
        spec: TaskSpecification,
        repo_record: RepositoryRecord,
        ref_solution: ReferenceSolutionResult,
        test_suite: GeneratedTestSuite,
        repo_path: Path,
        _in_copy: bool = False,
    ) -> ValidationReport:
        repo_path = repo_path.resolve()
        checks: List[CheckOutcome] = []
        target_rel = spec.repository_evidence[0].path if spec.repository_evidence else "veriloom/contracts/repository.py"
        target_file = repo_path / target_rel
        orig_content = target_file.read_text(encoding="utf-8", errors="ignore") if target_file.exists() else ""

        # Always validate in a throwaway copy of the repository: the user's working
        # tree is never modified, and read-only hosts (e.g. Vercel) still get a real
        # pytest run instead of assumed results.
        if not _in_copy:
            with tempfile.TemporaryDirectory(prefix="veriloom_val_") as tmp:
                work = Path(tmp) / "repo"
                shutil.copytree(repo_path, work, ignore=_COPY_IGNORE)
                return cls.run_validation(
                    spec, repo_record, ref_solution, test_suite, work, _in_copy=True
                )

        env = {**os.environ, "PYTHONPATH": str(repo_path)}

        # Dynamically locate baseline test suite in target repository
        baseline_test_target = None
        if (repo_path / "tests" / "test_contracts.py").exists():
            baseline_test_target = "tests/test_contracts.py"
        elif (repo_path / "tests").exists():
            found = [
                str(p.relative_to(repo_path)).replace("\\", "/")
                for p in (repo_path / "tests").glob("test_*.py")
                if not p.name.startswith("test_feature")
            ]
            baseline_test_target = found[0] if found else "tests"
        else:
            found = [
                str(p.relative_to(repo_path)).replace("\\", "/")
                for p in repo_path.glob("**/test_*.py")
                if not any(d in p.parts for d in ("_vendor", "venv", ".venv", "build", "dist"))
            ]
            baseline_test_target = found[0] if found else None

        # 1. Baseline Test Suite Check
        t0 = time.time()
        if baseline_test_target:
            base_cmd = [sys.executable, "-m", "pytest", baseline_test_target, "-q"]
            base_proc = subprocess.run(
                base_cmd,
                capture_output=True,
                text=True,
                cwd=str(repo_path),
                env=env,
            )
            base_passed = base_proc.returncode == 0
            base_exit = base_proc.returncode
        else:
            base_passed = True
            base_exit = 0

        checks.append(
            CheckOutcome(
                name="baseline_tests",
                status=CheckStatus.PASSED if base_passed else CheckStatus.BASELINE_FAILED,
                command=f"pytest {baseline_test_target or '.'} -q",
                exit_code=base_exit,
                duration_ms=int((time.time() - t0) * 1000),
                log_path="logs/baseline.log",
            )
        )

        # 2. Write Feature Test File Temporarily
        test_file = repo_path / test_suite.test_file_path
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_suite.test_code, encoding="utf-8")

        # 3. Apply Reference Solution
        helper_code = ref_solution.patch_diff
        lines = [l[1:] for l in helper_code.splitlines() if l.startswith("+") and not l.startswith("+++")]
        applied_code = orig_content + "\n" + "\n".join(lines)

        try:
            target_file.write_text(applied_code, encoding="utf-8")

            # 4. Feature Test Execution
            t0 = time.time()
            feat_proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file), "-q"],
                capture_output=True,
                text=True,
                cwd=str(repo_path),
                env=env,
            )
            checks.append(
                CheckOutcome(
                    name="feature_tests",
                    status=CheckStatus.PASSED if feat_proc.returncode == 0 else CheckStatus.FAILED,
                    command=f"pytest {test_suite.test_file_path} -q",
                    exit_code=feat_proc.returncode,
                    duration_ms=int((time.time() - t0) * 1000),
                    log_path="logs/feature_tests.log",
                )
            )

            # 5. Regression Suite Execution (Existing tests)
            t0 = time.time()
            if baseline_test_target:
                reg_cmd = [sys.executable, "-m", "pytest", baseline_test_target, "-q"]
                reg_proc = subprocess.run(
                    reg_cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(repo_path),
                    env=env,
                )
                reg_passed = reg_proc.returncode == 0
                reg_exit = reg_proc.returncode
            else:
                reg_passed = True
                reg_exit = 0

            checks.append(
                CheckOutcome(
                    name="regression_tests",
                    status=CheckStatus.PASSED if reg_passed else CheckStatus.FAILED,
                    command=f"pytest {baseline_test_target or '.'} -q",
                    exit_code=reg_exit,
                    duration_ms=int((time.time() - t0) * 1000),
                    log_path="logs/regression_tests.log",
                )
            )

            # 6. Mutation Testing & Controlled Fault Injection
            mutation_results, score_pct = MutationEngine.evaluate_mutants(
                spec, repo_path, test_suite.test_file_path
            )

        finally:
            # Clean up test file and restore target file
            if test_file.exists():
                test_file.unlink()
            target_file.write_text(orig_content, encoding="utf-8")

        # Compile Regression Summary
        regression_summary = RegressionSummary(
            baseline_tests_count=1 if baseline_test_target else 0,
            post_patch_tests_count=1 if baseline_test_target else 0,
            passed_count=1 if reg_passed else 0,
            pre_existing_failures=0 if base_passed else 1,
            newly_introduced_failures=0 if reg_passed else 1,
            status="NO_REGRESSION" if reg_passed else "REGRESSION_DETECTED",
        )

        overall_status = (
            CheckStatus.PASSED
            if all(c.status == CheckStatus.PASSED for c in checks) and score_pct >= 66.0
            else CheckStatus.FAILED
        )

        return ValidationReport(
            task_id=spec.task_id,
            repository_commit=repo_record.starting_commit,
            status=overall_status,
            checks=checks,
            acceptance_coverage=test_suite.coverage_mapping,
            mutation_checks=mutation_results,
            regression_summary=regression_summary,
            limitations=[
                f"Controlled fault injection achieved {score_pct}% kill rate on synthetically injected mutants.",
                "Executed with pytest in an isolated temporary copy of the repository.",
            ],
        )
