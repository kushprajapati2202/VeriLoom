"""Benchmark evaluation runner scoring coding model submissions against task packages.

A submission is evaluated in a throwaway copy of the repository at the package's
pinned commit (the same sandbox the authoring gates use), so the user's working
tree is never modified and results are reproducible.

Submissions may be:
  * a unified diff (what coding agents usually produce) - applied with `git apply`;
  * a complete replacement for the task's target file (Python source that already
    contains the target's existing definitions);
  * a code snippet - appended to the target file (convenient for quick experiments).
"""

import json
import py_compile
import shutil
import subprocess
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
from veriloom.validation.sandbox import Sandbox

_COPY_IGNORE = shutil.ignore_patterns(".git", ".venv", "venv", "__pycache__", ".pytest_cache",
                                      "exports", "node_modules", "*.egg-info", ".env")


def _is_diff(text: str) -> bool:
    head = text.lstrip()
    return head.startswith(("diff --git", "--- ")) or ("\n+++ " in text and "\n@@ " in text)


def _top_level_names(code: str) -> set:
    import ast
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    return {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


class _CopySandbox(Sandbox):
    """Fallback when the repository is not a git checkout containing the pinned commit."""

    def __init__(self, repo_path: Path):  # noqa: D401 - deliberately skips Sandbox.__init__
        self._tmp = tempfile.TemporaryDirectory(prefix="veriloom_bench_")
        self.root = Path(self._tmp.name)
        self.app = self.root / "app"
        self.hidden = self.root / "hidden_tests"
        self.hidden.mkdir()
        shutil.copytree(repo_path, self.app, ignore=_COPY_IGNORE)
        self._baseline = None


class BenchmarkRunner:
    """Evaluates candidate coding model implementations against validated task packages."""

    @staticmethod
    def _infer_repo_root(task_package_dir: Path, target_rel: str) -> Path:
        for cand in (Path.cwd(), task_package_dir.parent.parent, task_package_dir.parent):
            if (cand / target_rel).exists():
                return cand
        return Path.cwd()

    @classmethod
    def _open_sandbox(cls, repo_root: Path, commit: Optional[str]) -> Sandbox:
        if commit:
            try:
                return Sandbox(repo_root, commit)
            except Exception:
                pass
        return _CopySandbox(repo_root)

    @classmethod
    def _apply(cls, sb: Sandbox, target_rel: str, submission: str) -> Optional[str]:
        """Apply the submission inside the sandbox. Returns an error message or None."""
        if _is_diff(submission):
            patch = sb.root / "submission.patch"
            patch.write_text(submission if submission.endswith("\n") else submission + "\n",
                             encoding="utf-8", newline="\n")
            proc = subprocess.run(["git", "apply", "--whitespace=nowarn", str(patch)],
                                  cwd=sb.app, capture_output=True, text=True)
            return None if proc.returncode == 0 else f"patch does not apply: {proc.stderr.strip()[:300]}"
        original = sb.read(target_rel)
        existing = _top_level_names(original)
        if existing and existing <= _top_level_names(submission):
            sb.write(target_rel, submission)  # full replacement of the target file
        else:
            sb.write(target_rel, original.rstrip("\n") + "\n\n" + submission + "\n")
        return None

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
        target_rel = evidence[0]["path"] if evidence else "src/main.py"
        commit_file = task_package_dir / "repository" / "source-commit.txt"
        commit = commit_file.read_text(encoding="utf-8").strip() if commit_file.exists() else None

        test_files = sorted((task_package_dir / "tests" / "feature").glob("*.py"))
        if not test_files:
            raise FileNotFoundError(f"No feature test found in package: {task_package_dir / 'tests' / 'feature'}")
        test_file = test_files[0]

        repo_root = (repo_root or cls._infer_repo_root(task_package_dir, target_rel)).resolve()
        t0 = time.time()
        log: List[str] = []
        feature_total = feature_passed_n = 0
        feature_ok = False
        reg_clean = True
        verdict, category = EvaluationVerdict.PASSED_FULL, FailureCategory.NONE

        with cls._open_sandbox(repo_root, commit) as sb:
            baseline = sb.baseline()
            protected = sorted(f for f, ok in baseline.file_ok.items() if ok)
            hidden = str(sb.put_hidden_test(test_file.name, test_file.read_text(encoding="utf-8")))

            error = cls._apply(sb, target_rel, solution_code_or_patch)
            if error is None:
                try:
                    py_compile.compile(str(sb.app / target_rel), doraise=True)
                except py_compile.PyCompileError as e:
                    error = f"syntax error: {e.msg.strip()[:300]}"
                    category = FailureCategory.SYNTAX_ERROR
            if error is not None:
                log.append(error)
                verdict = EvaluationVerdict.BUILD_ERROR
                if category == FailureCategory.NONE:
                    category = FailureCategory.EXECUTION_CRASH
                reg_clean = False
            else:
                feat = sb.pytest([hidden])
                log.append("--- FEATURE TESTS ---\n" + feat.tail(40))
                feature_total = len(feat.results)
                feature_passed_n = sum(1 for v in feat.results.values() if v == "passed")
                feature_ok = feat.exit_code == 0 and feature_total > 0
                if feat.exit_code == 124:
                    verdict, category = EvaluationVerdict.TIMEOUT, FailureCategory.TIMEOUT_EXCEEDED
                elif not feature_ok:
                    verdict, category = EvaluationVerdict.FEATURE_FAILED, FailureCategory.ASSERTION_FAILURE

                if protected:
                    reg = sb.pytest(protected)
                    log.append("--- REGRESSION TESTS ---\n" + reg.tail(40))
                    reg_clean = reg.exit_code == 0
                    if not reg_clean and verdict == EvaluationVerdict.PASSED_FULL:
                        verdict, category = EvaluationVerdict.REGRESSION_INTRODUCED, FailureCategory.REGRESSION_BREAK

        return BenchmarkResult(
            task_id=task_id,
            model_name=model_name,
            verdict=verdict,
            feature_tests_passed=feature_ok,
            feature_tests_count=feature_total,
            feature_tests_passed_count=feature_passed_n,
            regression_clean=reg_clean,
            failure_category=category,
            execution_time_ms=int((time.time() - t0) * 1000),
            log_output="\n".join(log),
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
            leaderboard[model_name] = {
                "pass_rate": 1.0 if res.verdict == EvaluationVerdict.PASSED_FULL else 0.0,
                "feature_tests_passed": float(res.feature_tests_passed_count),
                "feature_tests_total": float(res.feature_tests_count),
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
