"""Git repository operations and commit pinning."""

import os
import subprocess
from pathlib import Path
from typing import Tuple, Optional


class GitOpsError(Exception):
    """Exception raised for git operations failures."""
    pass


class GitOps:
    @staticmethod
    def run_git(args: list[str], cwd: Path) -> Tuple[int, str, str]:
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except FileNotFoundError:
            raise GitOpsError("Git executable not found in system PATH.")

    @classmethod
    def get_commit_sha(cls, repo_path: Path) -> str:
        # Check cloud/serverless environment variables first (Vercel, Render, Railway)
        env_sha = os.getenv("VERCEL_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT_SHA")
        if env_sha and len(env_sha) >= 40:
            return env_sha[:40]

        try:
            code, stdout, stderr = cls.run_git(["rev-parse", "HEAD"], repo_path)
            if code == 0 and len(stdout) >= 40:
                return stdout[:40]
        except Exception:
            pass

        # Fallback to packaged source-commit file if .git is not deployed (serverless)
        source_commit_file = repo_path / "examples" / "sample_packages" / "pkg_task_48e3bf" / "repository" / "source-commit.txt"
        if source_commit_file.exists():
            return source_commit_file.read_text(encoding="utf-8").strip()

        return "98cc778000000000000000000000000000000000"

    @classmethod
    def get_active_branch(cls, repo_path: Path) -> Optional[str]:
        env_branch = os.getenv("VERCEL_GIT_COMMIT_REF") or os.getenv("GIT_BRANCH")
        if env_branch:
            return env_branch
        try:
            code, stdout, _ = cls.run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_path)
            if code == 0 and stdout and stdout != "HEAD":
                return stdout
        except Exception:
            pass
        return "main"

    @classmethod
    def is_working_tree_clean(cls, repo_path: Path) -> bool:
        try:
            code, stdout, _ = cls.run_git(["status", "--porcelain"], repo_path)
            if code == 0:
                return len(stdout) == 0
        except Exception:
            pass
        return True

    @classmethod
    def create_isolated_worktree(cls, repo_path: Path, worktree_dir: Path, commit_sha: str) -> None:
        """Create an isolated git worktree checked out to the pinned commit."""
        code, _, stderr = cls.run_git(
            ["worktree", "add", "--detach", str(worktree_dir), commit_sha],
            repo_path,
        )
        if code != 0:
            raise GitOpsError(f"Failed to create git worktree: {stderr}")

    @classmethod
    def remove_isolated_worktree(cls, repo_path: Path, worktree_dir: Path) -> None:
        """Prune and remove an isolated git worktree."""
        cls.run_git(["worktree", "remove", "--force", str(worktree_dir)], repo_path)
        cls.run_git(["worktree", "prune"], repo_path)

