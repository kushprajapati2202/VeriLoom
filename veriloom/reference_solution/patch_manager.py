"""Reference patch manager and isolated worktree execution."""

import difflib
import subprocess
from pathlib import Path
from typing import Dict, Tuple, Optional


class PatchManager:
    """Creates, verifies, and applies unified diffs against a codebase."""

    @classmethod
    def generate_diff(cls, original_files: Dict[str, str], modified_files: Dict[str, str]) -> str:
        diff_lines = []
        all_paths = sorted(set(original_files.keys()).union(modified_files.keys()))

        for path in all_paths:
            orig = original_files.get(path, "").splitlines(keepends=True)
            mod = modified_files.get(path, "").splitlines(keepends=True)
            patch = difflib.unified_diff(
                orig,
                mod,
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
            diff_lines.extend(patch)

        return "".join(diff_lines)

    @classmethod
    def apply_patch(cls, repo_path: Path, patch_content: str) -> Tuple[bool, str]:
        """Apply a git unified diff patch to a target repository."""
        proc = subprocess.run(
            ["git", "apply", "--check"],
            input=patch_content,
            cwd=str(repo_path),
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            return False, f"Git apply check failed: {proc.stderr}"

        apply_proc = subprocess.run(
            ["git", "apply"],
            input=patch_content,
            cwd=str(repo_path),
            text=True,
            capture_output=True,
        )
        if apply_proc.returncode != 0:
            return False, f"Git apply failed: {apply_proc.stderr}"

        return True, "Patch applied successfully."

    @classmethod
    def revert_changes(cls, repo_path: Path) -> None:
        """Discard uncommitted modifications in repository."""
        subprocess.run(["git", "checkout", "."], cwd=str(repo_path), check=False)
        subprocess.run(["git", "clean", "-fd"], cwd=str(repo_path), check=False)

