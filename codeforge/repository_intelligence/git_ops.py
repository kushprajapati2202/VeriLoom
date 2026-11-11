"""Git repository operations and commit pinning."""

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
        code, stdout, stderr = cls.run_git(["rev-parse", "HEAD"], repo_path)
        if code != 0:
            raise GitOpsError(f"Failed to get commit SHA: {stderr}")
        return stdout

    @classmethod
    def get_active_branch(cls, repo_path: Path) -> Optional[str]:
        code, stdout, _ = cls.run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_path)
        if code == 0 and stdout and stdout != "HEAD":
            return stdout
        return None

    @classmethod
    def is_working_tree_clean(cls, repo_path: Path) -> bool:
        code, stdout, _ = cls.run_git(["status", "--porcelain"], repo_path)
        if code != 0:
            raise GitOpsError("Failed to check git working tree status.")
        return len(stdout) == 0

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
