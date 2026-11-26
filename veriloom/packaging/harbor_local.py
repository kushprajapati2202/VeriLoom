"""Docker-free replay of a Harbor task's oracle and no-op trials.

Mirrors `harbor run -a oracle|nop`: materialise the repository at the task's base_commit
(from the local clone, or environment/repo/ for snapshot tasks), optionally run
solution/solve.sh, then run tests/test.sh and read reward.txt. Container paths are remapped
through APP_DIR / TESTS_DIR / SOLUTION_DIR / LOGS_DIR, which the generated scripts honour.

This is a fast pre-check. The authoritative check is a real `harbor run` in Docker
(scripts/harbor_validate.sh), whose results are kept in the evidence folder.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from veriloom.validation.sandbox import snapshot_repo
from veriloom.validation.target_env import install_copy, target_python


class HarborTrialResult(BaseModel):
    mode: str  # "oracle" or "nop"
    reward: Optional[float]
    solve_exit: Optional[int] = None
    verifier_exit: int
    log: str


class HarborLocalCheck(BaseModel):
    task_dir: str
    oracle: HarborTrialResult
    nop: HarborTrialResult
    passed: bool = Field(description="oracle reward == 1.0 and nop reward == 0.0")
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


def _base_commit(task_dir: Path) -> Optional[str]:
    meta = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8")).get("metadata", {})
    return meta.get("base_commit") or meta.get("starting_commit")


class HarborLocalRunner:
    @classmethod
    def run_trial(cls, task_dir: Path, mode: str, python: Optional[str] = None,
                  repo_path: Optional[Path] = None) -> HarborTrialResult:
        if mode not in ("oracle", "nop"):
            raise ValueError("mode must be 'oracle' or 'nop'")
        task_dir = Path(task_dir).resolve()
        bash = find_bash()
        with tempfile.TemporaryDirectory(prefix="harbor_trial_") as tmp:
            root = Path(tmp)
            app, tests, solution, logs = root / "app", root / "tests", root / "solution", root / "logs" / "verifier"
            snapshot = task_dir / "environment" / "repo"
            if snapshot.is_dir():
                shutil.copytree(snapshot, app)
            elif repo_path is not None:
                snapshot_repo(Path(repo_path), _base_commit(task_dir), app)
            else:
                raise RuntimeError("task clones its repository at build time; pass repo_path for a local check")
            py = python or target_python(repo_path)
            if py:
                install_copy(py, app)
            else:
                py = sys.executable
            logs.mkdir(parents=True)
            env = {
                **os.environ,
                "APP_DIR": _posix(app),
                "TESTS_DIR": _posix(tests),
                "SOLUTION_DIR": _posix(solution),
                "LOGS_DIR": _posix(logs),
                "PYTHON": _posix(Path(py)),
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
            log_parts.append(f"$ test.sh (exit {proc.returncode})\n{proc.stdout[-8000:]}{proc.stderr[-4000:]}")

            reward_file = logs / "reward.txt"
            reward = float(reward_file.read_text().strip()) if reward_file.exists() else None
            return HarborTrialResult(
                mode=mode,
                reward=reward,
                solve_exit=solve_exit,
                verifier_exit=proc.returncode,
                log="\n".join(log_parts),
            )

    @classmethod
    def check(cls, task_dir: Path, python: Optional[str] = None,
              repo_path: Optional[Path] = None) -> HarborLocalCheck:
        oracle = cls.run_trial(task_dir, "oracle", python, repo_path)
        nop = cls.run_trial(task_dir, "nop", python, repo_path)
        notes: List[str] = []
        if oracle.reward != 1.0:
            notes.append(f"Reference solution earned reward {oracle.reward}, expected 1.0.")
        if nop.reward != 0.0:
            notes.append(f"Unmodified repository earned reward {nop.reward}, expected 0.0.")
        return HarborLocalCheck(
            task_dir=str(Path(task_dir).resolve()),
            oracle=oracle,
            nop=nop,
            passed=oracle.reward == 1.0 and nop.reward == 0.0,
            notes=notes,
        )
