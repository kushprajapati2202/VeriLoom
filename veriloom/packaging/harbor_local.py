"""Docker-free replay of a Harbor task's oracle and no-op trials.

Mirrors what `harbor run -a oracle` does inside the container: copy the
environment's repo snapshot to the working directory, optionally run
solution/solve.sh, then run tests/test.sh and read /logs/verifier/reward.txt.
Container paths are remapped through the APP_DIR / TESTS_DIR / SOLUTION_DIR /
LOGS_DIR variables the generated scripts honour.

This proves the task is internally consistent (the reference solution earns
reward 1, the untouched repo earns reward 0). It does not replace a real
`harbor run`, which also builds the Docker image.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class HarborTrialResult(BaseModel):
    mode: str  # "oracle" or "nop"
    reward: Optional[int]
    solve_exit: Optional[int] = None
    verifier_exit: int
    log: str


class HarborLocalCheck(BaseModel):
    task_dir: str
    oracle: HarborTrialResult
    nop: HarborTrialResult
    passed: bool = Field(description="oracle reward == 1 and nop reward == 0")
    notes: List[str] = Field(default_factory=list)


def find_bash() -> str:
    """Prefer Git Bash on Windows (System32\\bash.exe is WSL and cannot see Windows Python)."""
    if sys.platform == "win32":
        git = shutil.which("git")
        if git:
            git_root = Path(git).resolve().parent.parent
            for cand in (git_root / "bin" / "bash.exe", git_root / "usr" / "bin" / "bash.exe"):
                if cand.exists():
                    return str(cand)
    bash = shutil.which("bash")
    if not bash:
        raise RuntimeError("bash not found; install Git Bash (Windows) or bash.")
    return bash


def _posix(p: Path) -> str:
    return str(p).replace("\\", "/")


class HarborLocalRunner:
    @classmethod
    def run_trial(cls, task_dir: Path, mode: str, python: Optional[str] = None) -> HarborTrialResult:
        if mode not in ("oracle", "nop"):
            raise ValueError("mode must be 'oracle' or 'nop'")
        task_dir = Path(task_dir).resolve()
        bash = find_bash()
        with tempfile.TemporaryDirectory(prefix="harbor_trial_") as tmp:
            root = Path(tmp)
            app, tests, solution, logs = root / "app", root / "tests", root / "solution", root / "logs" / "verifier"
            shutil.copytree(task_dir / "environment" / "repo", app)
            logs.mkdir(parents=True)
            env = {
                **os.environ,
                "APP_DIR": _posix(app),
                "TESTS_DIR": _posix(tests),
                "SOLUTION_DIR": _posix(solution),
                "LOGS_DIR": _posix(logs),
                "PYTHON": _posix(Path(python or sys.executable)),
                # Keep git apply from treating an enclosing repo as the work tree.
                "GIT_CEILING_DIRECTORIES": str(root.parent),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            env.pop("PYTHONPATH", None)
            log_parts: List[str] = []

            solve_exit = None
            if mode == "oracle":
                shutil.copytree(task_dir / "solution", solution)
                proc = subprocess.run(
                    [bash, _posix(solution / "solve.sh")], cwd=app, env=env, capture_output=True, text=True
                )
                solve_exit = proc.returncode
                log_parts.append(f"$ solve.sh (exit {proc.returncode})\n{proc.stdout}{proc.stderr}")

            # Harbor uploads tests/ only after the agent phase.
            shutil.copytree(task_dir / "tests", tests)
            proc = subprocess.run(
                [bash, _posix(tests / "test.sh")], cwd=app, env=env, capture_output=True, text=True
            )
            log_parts.append(f"$ test.sh (exit {proc.returncode})\n{proc.stdout}{proc.stderr}")

            reward_file = logs / "reward.txt"
            reward = int(reward_file.read_text().strip()) if reward_file.exists() else None
            return HarborTrialResult(
                mode=mode,
                reward=reward,
                solve_exit=solve_exit,
                verifier_exit=proc.returncode,
                log="\n".join(log_parts),
            )

    @classmethod
    def check(cls, task_dir: Path, python: Optional[str] = None) -> HarborLocalCheck:
        oracle = cls.run_trial(task_dir, "oracle", python)
        nop = cls.run_trial(task_dir, "nop", python)
        notes: List[str] = []
        if oracle.reward != 1:
            notes.append("Reference solution did not earn reward 1: task is not solvable as packaged.")
        if nop.reward != 0:
            notes.append("Unmodified repository earned reward 1: feature tests do not detect the missing feature.")
        return HarborLocalCheck(
            task_dir=str(Path(task_dir).resolve()),
            oracle=oracle,
            nop=nop,
            passed=oracle.reward == 1 and nop.reward == 0,
            notes=notes,
        )
