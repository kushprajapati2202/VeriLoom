"""Isolated, evidence-producing validation of a candidate task.

Every check runs against a throwaway copy of the repository at the pinned
commit (never the user's working tree). Feature tests live outside the repo
copy, exactly as Harbor mounts them at /tests, so what passes here is what the
Harbor verifier will see.

Gates
  G1 fail_before  - each requirement has at least one test that fails on the original code
  G2 pass_after   - every feature test passes with the reference implementation
  G3 regression   - no existing test that passed at baseline fails after the change
  G4 mutation     - the feature tests kill enough faulty variants of the reference
  G5 clarity      - every literal the tests assert is stated in the task text
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from veriloom.validation.clarity import unexplained_literals

PYTEST_TIMEOUT_SEC = 600
_IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "build", "dist", "__pycache__", "exports", "_vendor"}


def snapshot_repo(repo_path: Path, commit: str, dest: Path) -> None:
    """Extract the tracked tree at `commit` with LF endings (as a Linux checkout would)."""
    proc = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", "archive", "--format=tar", commit],
        cwd=repo_path,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git archive {commit} failed in {repo_path}: {proc.stderr.decode(errors='replace').strip()}"
        )
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
        tar.extractall(dest, filter="data")


def discover_test_targets(repo_dir: Path) -> List[str]:
    """Existing test files in the repository (relative paths)."""
    if (repo_dir / "tests").is_dir():
        roots = [repo_dir / "tests"]
    elif (repo_dir / "test").is_dir():
        roots = [repo_dir / "test"]
    else:
        roots = [repo_dir]
    found = []
    for root in roots:
        for p in list(root.rglob("test_*.py")) + list(root.rglob("*_test.py")):
            if not any(part in _IGNORED_DIRS for part in p.relative_to(repo_dir).parts):
                found.append(p.relative_to(repo_dir).as_posix())
    return sorted(set(found))


class PytestRun(BaseModel):
    exit_code: int
    output: str
    # test function name (without parametrisation) -> "passed" | "failed" | "skipped"
    results: Dict[str, str] = Field(default_factory=dict)
    # test file -> True if every test in it passed or was skipped
    file_ok: Dict[str, bool] = Field(default_factory=dict)
    collection_error: bool = False

    def tail(self, n: int = 60) -> str:
        return "\n".join(self.output.splitlines()[-n:])


class Mutant(BaseModel):
    id: str
    description: str
    fault_type: str = "behaviour_change"
    find: str
    replace: str


class MutantOutcome(BaseModel):
    id: str
    description: str
    fault_type: str
    status: str  # KILLED | SURVIVED | INVALID
    detail: str = ""


class GateResult(BaseModel):
    name: str
    passed: bool
    detail: str
    log_tail: str = ""


class GateReport(BaseModel):
    gates: List[GateResult]
    mutants: List[MutantOutcome] = Field(default_factory=list)
    regression_targets: List[str] = Field(default_factory=list)
    baseline_failing_files: List[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(g.passed for g in self.gates)

    def failures(self) -> List[GateResult]:
        return [g for g in self.gates if not g.passed]


class Sandbox:
    """A disposable copy of the repository at a commit, plus a hidden test directory."""

    def __init__(self, repo_path: Path, commit: str):
        self._tmp = tempfile.TemporaryDirectory(prefix="veriloom_sandbox_")
        self.root = Path(self._tmp.name)
        self.app = self.root / "app"
        self.hidden = self.root / "hidden_tests"
        self.hidden.mkdir()
        snapshot_repo(Path(repo_path).resolve(), commit, self.app)
        self._baseline: Optional[PytestRun] = None

    def close(self) -> None:
        self._tmp.cleanup()

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -------------------------------------------------------------- files

    def read(self, rel: str) -> str:
        p = self.app / rel
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def write(self, rel: str, content: str) -> None:
        p = self.app / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")

    def put_hidden_test(self, name: str, code: str) -> Path:
        for old in self.hidden.glob("*.py"):
            old.unlink()
        p = self.hidden / name
        p.write_text(code, encoding="utf-8", newline="\n")
        return p

    # -------------------------------------------------------------- pytest

    def pytest(self, targets: List[str], junit: bool = True) -> PytestRun:
        junit_path = self.root / "junit.xml"
        if junit_path.exists():
            junit_path.unlink()
        cmd = [sys.executable, "-m", "pytest", *targets, "-q", "-p", "no:cacheprovider",
               "--rootdir", str(self.app)]
        if junit:
            cmd += [f"--junitxml={junit_path}", "-o", "junit_family=xunit1"]
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("PYTHONPATH", None)
        try:
            proc = subprocess.run(cmd, cwd=self.app, env=env, capture_output=True, text=True,
                                  timeout=PYTEST_TIMEOUT_SEC)
            exit_code, output = proc.returncode, proc.stdout + proc.stderr
        except subprocess.TimeoutExpired as e:
            exit_code = 124
            output = f"TIMEOUT after {PYTEST_TIMEOUT_SEC}s\n{e.stdout or ''}"
        run = PytestRun(exit_code=exit_code, output=output, collection_error=exit_code in (2, 3, 4))
        if junit and junit_path.exists():
            self._parse_junit(junit_path, run)
        return run

    def _parse_junit(self, path: Path, run: PytestRun) -> None:
        try:
            tree = ET.parse(path)
        except ET.ParseError:
            return
        for case in tree.iter("testcase"):
            name = case.get("name", "").split("[")[0]
            file = (case.get("file") or "").replace("\\", "/")
            if case.find("failure") is not None or case.find("error") is not None:
                status = "failed"
                if not name.startswith("test"):  # pytest reports collection errors as a pseudo-case
                    run.collection_error = True
            elif case.find("skipped") is not None:
                status = "skipped"
            else:
                status = "passed"
            if run.results.get(name) != "failed":
                run.results[name] = status
            if file:
                run.file_ok[file] = run.file_ok.get(file, True) and status != "failed"

    def baseline(self) -> PytestRun:
        """Existing test suite on the untouched snapshot (computed once)."""
        if self._baseline is None:
            targets = discover_test_targets(self.app)
            self._baseline = self.pytest(targets) if targets else PytestRun(exit_code=0, output="no tests")
        return self._baseline


class SandboxValidator:
    """Runs gates G1-G5 for one candidate (reference implementation + tests + mutants)."""

    MIN_VALID_MUTANTS = 3
    MIN_KILL_RATIO = 0.8

    @classmethod
    def validate(
        cls,
        sandbox: Sandbox,
        target_file: str,
        new_content: str,
        test_file_name: str,
        test_code: str,
        requirement_tests: Dict[str, List[str]],
        mutants: List[Mutant],
        task_text: str,
    ) -> GateReport:
        gates: List[GateResult] = []
        original = sandbox.read(target_file)
        hidden_test = str(sandbox.put_hidden_test(test_file_name, test_code))

        # Static sanity first: cheap and gives precise feedback.
        for label, code in (("reference implementation", new_content), ("feature tests", test_code)):
            try:
                compile(code, label, "exec")
            except SyntaxError as e:
                gates.append(GateResult(name="syntax", passed=False, detail=f"SyntaxError in {label}: {e}"))
                return GateReport(gates=gates)

        baseline = sandbox.baseline()
        passing_files = sorted(f for f, ok in baseline.file_ok.items() if ok)
        failing_files = sorted(f for f, ok in baseline.file_ok.items() if not ok)

        try:
            # G1: tests must detect the missing feature, per requirement.
            before = sandbox.pytest([hidden_test])
            undetected = [
                req for req, names in requirement_tests.items()
                if not before.collection_error
                and not any(before.results.get(n) == "failed" for n in names)
            ]
            g1_ok = before.exit_code != 0 and not undetected and before.exit_code != 5
            gates.append(GateResult(
                name="fail_before",
                passed=g1_ok,
                detail=("Feature tests fail on the original code"
                        + (" (import/collection error)" if before.collection_error else ""))
                if g1_ok else
                ("No test fails on the original code for: " + ", ".join(undetected)
                 if undetected else "Feature tests pass (or collect nothing) on the original code"),
                log_tail=before.tail(),
            ))

            # G2: reference passes all feature tests.
            sandbox.write(target_file, new_content)
            after = sandbox.pytest([hidden_test])
            expected = {n for names in requirement_tests.values() for n in names}
            missing = sorted(n for n in expected if n not in after.results)
            g2_ok = after.exit_code == 0 and not missing
            gates.append(GateResult(
                name="pass_after",
                passed=g2_ok,
                detail="All feature tests pass with the reference implementation" if g2_ok else
                (f"Mapped tests not found: {', '.join(missing)}" if missing and after.exit_code == 0
                 else f"Feature tests fail with the reference implementation (exit {after.exit_code})"),
                log_tail=after.tail(),
            ))

            # G3: no new failures among tests that passed at baseline.
            if passing_files:
                reg = sandbox.pytest(passing_files)
                broken = sorted(f for f in passing_files if not reg.file_ok.get(f, reg.exit_code == 0))
                g3_ok = reg.exit_code == 0 and not broken
                gates.append(GateResult(
                    name="regression",
                    passed=g3_ok,
                    detail=f"{len(passing_files)} existing test file(s) still pass" if g3_ok else
                    f"Existing tests broken by the change: {', '.join(broken) or '(see log)'}",
                    log_tail=reg.tail(),
                ))
            else:
                gates.append(GateResult(name="regression", passed=True,
                                        detail="No passing baseline tests to protect"))

            # G4: mutation analysis (only meaningful if the reference passes).
            outcomes: List[MutantOutcome] = []
            if g2_ok:
                for m in mutants:
                    count = new_content.count(m.find) if m.find else 0
                    if count != 1:
                        outcomes.append(MutantOutcome(
                            id=m.id, description=m.description, fault_type=m.fault_type, status="INVALID",
                            detail=f"`find` snippet occurs {count} times in the reference (must be exactly 1)",
                        ))
                        continue
                    mutated = new_content.replace(m.find, m.replace)
                    if mutated == new_content:
                        outcomes.append(MutantOutcome(id=m.id, description=m.description,
                                                      fault_type=m.fault_type, status="INVALID",
                                                      detail="replacement equals original"))
                        continue
                    sandbox.write(target_file, mutated)
                    res = sandbox.pytest([hidden_test], junit=False)
                    outcomes.append(MutantOutcome(
                        id=m.id, description=m.description, fault_type=m.fault_type,
                        status="KILLED" if res.exit_code != 0 else "SURVIVED",
                    ))
                sandbox.write(target_file, new_content)
                valid = [o for o in outcomes if o.status != "INVALID"]
                killed = [o for o in valid if o.status == "KILLED"]
                ratio = len(killed) / len(valid) if valid else 0.0
                g4_ok = len(valid) >= cls.MIN_VALID_MUTANTS and ratio >= cls.MIN_KILL_RATIO
                survivors = [f"{o.id} ({o.description})" for o in valid if o.status == "SURVIVED"]
                invalid = [f"{o.id}: {o.detail}" for o in outcomes if o.status == "INVALID"]
                gates.append(GateResult(
                    name="mutation",
                    passed=g4_ok,
                    detail=f"{len(killed)}/{len(valid)} valid mutants killed"
                    + (f"; survived: {'; '.join(survivors)}" if survivors else "")
                    + (f"; invalid: {'; '.join(invalid)}" if invalid else "")
                    + ("" if len(valid) >= cls.MIN_VALID_MUTANTS
                       else f"; need at least {cls.MIN_VALID_MUTANTS} valid mutants"),
                ))
            else:
                gates.append(GateResult(name="mutation", passed=False,
                                        detail="Skipped: reference does not pass its own tests"))
        finally:
            sandbox.write(target_file, original)

        # G5: clarity.
        unexplained = unexplained_literals(test_code, task_text)
        gates.append(GateResult(
            name="clarity",
            passed=not unexplained,
            detail="Every asserted literal is stated in the task" if not unexplained else
            "Tests assert values the task never states: " + ", ".join(unexplained),
        ))

        return GateReport(
            gates=gates,
            mutants=outcomes,
            regression_targets=passing_files,
            baseline_failing_files=failing_files,
        )
