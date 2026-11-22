"""Export validated VeriLoom task packages to the Harbor task format.

Harbor task layout (https://docs.harborframework.com/tasks/overview):

    <task_id>/
      instruction.md            # prompt handed to the agent
      task.toml                 # task metadata, timeouts, resources
      environment/Dockerfile    # repo snapshot at the pinned commit
      environment/repo/...      # build context: source tree at the pinned commit
      solution/solve.sh         # oracle: applies the reference patch
      solution/reference.patch
      tests/test.sh             # verifier: feature + regression tests -> /logs/verifier/reward.txt
      tests/feature/...         # hidden feature tests
      tests/regression/...      # pristine copies of the repo's existing tests

All scripts read their locations from environment variables that default to
Harbor's container paths, so the same files run unchanged under Harbor and
under the local Docker-free checker in ``harbor_local.py``.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from veriloom.validation.clarity import unexplained_literals
from veriloom.validation.sandbox import snapshot_repo

GENERATOR = "veriloom-ai@1.0.0"


class HarborExportResult(BaseModel):
    task_dir: str
    task_id: str
    starting_commit: str
    regression_targets: List[str] = Field(default_factory=list)
    patch_applies: bool
    warnings: List[str] = Field(default_factory=list)


class HarborExportError(RuntimeError):
    pass


def _write(path: Path, text: str, executable: bool = False) -> None:
    """Write with LF line endings regardless of host OS (scripts run on Linux)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    if executable:
        path.chmod(0o755)


def _toml_str(value: str) -> str:
    # JSON string escaping is a valid subset of TOML basic strings.
    return json.dumps(value, ensure_ascii=False)


def _toml_list(values: List[str]) -> str:
    return "[" + ", ".join(_toml_str(v) for v in values) + "]"


class HarborExporter:
    """Converts a VeriLoom package directory (pkg_*) into a runnable Harbor task."""

    @classmethod
    def export(
        cls,
        package_dir: Path,
        repo_path: Path,
        output_dir: Optional[Path] = None,
        python_image: str = "python:3.12-slim",
    ) -> HarborExportResult:
        package_dir = Path(package_dir).resolve()
        repo_path = Path(repo_path).resolve()

        spec = json.loads((package_dir / "task" / "specification.json").read_text(encoding="utf-8"))
        manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
        val_report_path = package_dir / "validation" / "validation-report.json"
        val_report = (
            json.loads(val_report_path.read_text(encoding="utf-8")) if val_report_path.exists() else {}
        )
        patch = (package_dir / "reference" / "implementation.patch").read_text(encoding="utf-8")
        patch = patch.replace("\r\n", "\n")
        feature_tests = sorted((package_dir / "tests" / "feature").glob("*.py"))
        if not feature_tests:
            raise HarborExportError(f"No feature tests found in {package_dir / 'tests' / 'feature'}")

        task_id = spec["task_id"]
        commit = manifest["repository"]["pinned_commit"]
        warnings: List[str] = []

        out_root = Path(output_dir).resolve() if output_dir else package_dir.parent / "harbor_tasks"
        task_dir = out_root / task_id
        if task_dir.exists():
            shutil.rmtree(task_dir)
        task_dir.mkdir(parents=True)

        # 1. Environment: source snapshot at the pinned commit + Dockerfile
        repo_dir = task_dir / "environment" / "repo"
        cls._snapshot_repo(repo_path, commit, repo_dir)
        _write(task_dir / "environment" / "Dockerfile", cls._dockerfile(repo_dir, python_image))

        # 2. Solution: reference patch applied by the oracle
        _write(task_dir / "solution" / "reference.patch", patch)
        _write(task_dir / "solution" / "solve.sh", SOLVE_SH, executable=True)
        patch_ok, patch_err = cls._check_patch_applies(repo_dir, patch)
        if not patch_ok:
            warnings.append(f"Reference patch does not apply cleanly to commit {commit[:12]}: {patch_err}")

        # 3. Tests: hidden feature tests + pristine regression copies + verifier entrypoint
        for t in feature_tests:
            _write(task_dir / "tests" / "feature" / t.name, t.read_text(encoding="utf-8"))
        regression_targets = cls._regression_targets(val_report, repo_dir)
        for target in regression_targets:
            src = repo_dir / target
            dst = task_dir / "tests" / "regression" / target
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        if not regression_targets:
            warnings.append("No regression test target found; verifier checks feature tests only.")
        _write(
            task_dir / "tests" / "test.sh",
            TEST_SH.replace("__REGRESSION_TARGETS__", " ".join(regression_targets)),
            executable=True,
        )

        # 4. Instruction + task.toml
        interface = cls._interface_from_patch(patch)
        instruction = cls._instruction_md(spec, interface)
        _write(task_dir / "instruction.md", instruction)
        _write(task_dir / "task.toml", cls._task_toml(spec, manifest))

        # 5. Clarity lint: literal expectations in hidden tests the agent cannot infer
        test_code = "\n".join(t.read_text(encoding="utf-8") for t in feature_tests)
        for literal in cls._unexplained_literals(test_code, instruction):
            warnings.append(
                f"Hidden tests assert the value {literal}, which the instruction never states; "
                "the task may be under-specified."
            )

        result = HarborExportResult(
            task_dir=str(task_dir),
            task_id=task_id,
            starting_commit=commit,
            regression_targets=regression_targets,
            patch_applies=patch_ok,
            warnings=warnings,
        )
        # Kept outside the task dir so it is not shipped to the agent or verifier.
        _write(out_root / f"{task_id}.export.json", result.model_dump_json(indent=2))
        return result

    # ------------------------------------------------------------------ environment

    @staticmethod
    def _snapshot_repo(repo_path: Path, commit: str, dest: Path) -> None:
        try:
            snapshot_repo(repo_path, commit, dest)
        except RuntimeError as e:
            raise HarborExportError(str(e)) from e

    @staticmethod
    def _dockerfile(repo_dir: Path, python_image: str) -> str:
        if (repo_dir / "requirements.txt").exists():
            deps = "RUN pip install --no-cache-dir -r requirements.txt\n"
        elif (repo_dir / "pyproject.toml").exists() or (repo_dir / "setup.py").exists():
            deps = "RUN pip install --no-cache-dir -e .\n"
        else:
            deps = ""
        return (
            f"# Generated by {GENERATOR}: repository snapshot at the task's pinned commit\n"
            f"FROM {python_image}\n\n"
            "RUN apt-get update \\\n"
            " && apt-get install -y --no-install-recommends git \\\n"
            " && rm -rf /var/lib/apt/lists/*\n\n"
            "WORKDIR /app\n"
            "COPY repo/ /app/\n\n"
            f"{deps}"
            "RUN pip install --no-cache-dir pytest\n"
        )

    @staticmethod
    def _check_patch_applies(repo_dir: Path, patch: str) -> Tuple[bool, str]:
        # Run in a temp copy outside any git work tree so `git apply` behaves like `patch`.
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "app"
            shutil.copytree(repo_dir, work)
            patch_file = Path(tmp) / "reference.patch"
            patch_file.write_text(patch, encoding="utf-8", newline="\n")
            proc = subprocess.run(
                ["git", "apply", "--check", str(patch_file)],
                cwd=work,
                capture_output=True,
                text=True,
                env=_git_env(tmp),
            )
            return proc.returncode == 0, proc.stderr.strip()

    # ------------------------------------------------------------------ tests

    @staticmethod
    def _regression_targets(val_report: dict, repo_dir: Path) -> List[str]:
        """Reuse the regression suite the validation run used, if it exists in the snapshot."""
        targets: List[str] = []
        for check in val_report.get("checks", []):
            if check.get("name") != "regression_tests":
                continue
            command = check.get("command", "").split("(")[0]
            tokens = command.split()
            if "pytest" not in tokens:
                continue
            for tok in tokens[tokens.index("pytest") + 1:]:
                if tok.startswith("-") or tok == ".":
                    continue
                if (repo_dir / tok).exists() and tok not in targets:
                    targets.append(tok)
        return targets

    # ------------------------------------------------------------------ instruction

    @staticmethod
    def _interface_from_patch(patch: str) -> List[Tuple[str, List[str]]]:
        """Signatures of new top-level Python classes/functions the hidden tests import."""
        result: List[Tuple[str, List[str]]] = []
        current_file: Optional[str] = None
        added: List[str] = []

        def flush() -> None:
            if not current_file or not current_file.endswith(".py") or not added:
                return
            try:
                tree = ast.parse("\n".join(added))
            except SyntaxError:
                return
            sigs: List[str] = []
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                    sigs.append(f"def {node.name}({ast.unparse(node.args)}){ret}")
                elif isinstance(node, ast.ClassDef):
                    bases = ", ".join(ast.unparse(b) for b in node.bases)
                    sigs.append(f"class {node.name}({bases})" if bases else f"class {node.name}")
            if sigs:
                result.append((current_file, sigs))

        for line in patch.splitlines():
            if line.startswith("+++ "):
                flush()
                path = line[4:].strip()
                current_file = path[2:] if path.startswith("b/") else path
                added = []
            elif line.startswith("+") and not line.startswith("+++"):
                added.append(line[1:])
        flush()
        return result

    @staticmethod
    def _instruction_md(spec: dict, interface: List[Tuple[str, List[str]]]) -> str:
        out: List[str] = [f"# {spec['title']}", "", spec["summary"], ""]
        out += [
            "You are working in the repository checked out at `/app` "
            f"(commit `{spec['starting_commit'][:12]}`). Implement the feature below. "
            "Existing behaviour and the existing test suite must keep working.",
            "",
            "## Requirements",
            "",
        ]
        for req in spec.get("requirements", []):
            out.append(f"### {req['id']} ({req.get('priority', 'must')})")
            out.append("")
            out.append(req["statement"])
            out.append("")
            out.append("Acceptance criteria:")
            out += [f"- {c}" for c in req.get("acceptance_criteria", [])]
            out.append("")
        if interface:
            out += [
                "## Required public interface",
                "",
                "The feature is verified through the following names; they must exist with "
                "these signatures:",
                "",
            ]
            for file, sigs in interface:
                module = file[:-3].replace("/", ".")
                out.append(f"In `{file}` (importable as `{module}`):")
                out.append("")
                out.append("```python")
                out += sigs
                out.append("```")
                out.append("")
        for heading, key in (
            ("Behaviour details", "behaviour_details"),
            ("Edge cases to handle", "edge_cases"),
            ("Constraints", "constraints"),
            ("Assumptions", "assumptions"),
            ("Out of scope", "out_of_scope"),
        ):
            items = spec.get(key) or []
            if items:
                out += [f"## {heading}", ""] + [f"- {i}" for i in items] + [""]
        return "\n".join(out).rstrip() + "\n"

    @staticmethod
    def _task_toml(spec: dict, manifest: dict) -> str:
        repo = manifest.get("repository", {})
        family = spec.get("feature_family", "feature")
        tags = ["feature-development", family, repo.get("language", "")]
        if repo.get("framework"):
            tags.append(repo["framework"])
        tags = [t for t in tags if t]
        return "\n".join(
            [
                f"# Generated by {GENERATOR}",
                'schema_version = "1.4"',
                "",
                "[task]",
                f"name = {_toml_str('veriloom/' + spec['task_id'])}",
                f"description = {_toml_str(spec['title'])}",
                f"keywords = {_toml_list(tags)}",
                "",
                "[metadata]",
                f"difficulty = {_toml_str(spec.get('difficulty', 'intermediate'))}",
                'category = "feature-development"',
                f"tags = {_toml_list(tags)}",
                f"feature_family = {_toml_str(family)}",
                f"source_repository = {_toml_str(repo.get('name', spec.get('repository_id', '')))}",
                f"starting_commit = {_toml_str(repo.get('pinned_commit', spec['starting_commit']))}",
                f"generator = {_toml_str(GENERATOR)}",
                "",
                "[verifier]",
                "timeout_sec = 600.0",
                "",
                "[agent]",
                "timeout_sec = 1800.0",
                "",
                "[environment]",
                "build_timeout_sec = 900.0",
                "cpus = 1",
                "memory_mb = 2048",
                "",
            ]
        )

    @staticmethod
    def _unexplained_literals(test_code: str, instruction: str) -> List[str]:
        return unexplained_literals(test_code, instruction)


def _git_env(tmp: str) -> dict:
    # Stop git from discovering an enclosing repository above the temp directory.
    return {**os.environ, "GIT_CEILING_DIRECTORIES": str(Path(tmp).parent)}


SOLVE_SH = """#!/usr/bin/env bash
# Oracle solution generated by VeriLoom AI: applies the validated reference patch.
set -euo pipefail
APP_DIR="${APP_DIR:-/app}"
SOLUTION_DIR="${SOLUTION_DIR:-/solution}"
cd "$APP_DIR"
git apply --whitespace=nowarn "$SOLUTION_DIR/reference.patch"
echo "Reference patch applied."
"""

TEST_SH = """#!/usr/bin/env bash
# Verifier generated by VeriLoom AI.
# Reward 1 only if the hidden feature tests pass AND the existing regression suite still passes.
set -uo pipefail
APP_DIR="${APP_DIR:-/app}"
TESTS_DIR="${TESTS_DIR:-/tests}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
PYTHON="${PYTHON:-python}"
REGRESSION_TARGETS="__REGRESSION_TARGETS__"

mkdir -p "$LOGS_DIR"
cd "$APP_DIR"

# Restore pristine copies of the regression tests so edits to them cannot game the verifier.
if [ -d "$TESTS_DIR/regression" ]; then
  cp -r "$TESTS_DIR/regression/." "$APP_DIR/"
fi

feature_status=0
"$PYTHON" -m pytest "$TESTS_DIR/feature" -q -p no:cacheprovider --rootdir "$APP_DIR" \\
  > "$LOGS_DIR/feature.log" 2>&1 || feature_status=$?
echo "== feature tests (exit $feature_status) =="
cat "$LOGS_DIR/feature.log"

regression_status=0
if [ -n "$REGRESSION_TARGETS" ]; then
  # shellcheck disable=SC2086
  "$PYTHON" -m pytest $REGRESSION_TARGETS -q -p no:cacheprovider \\
    > "$LOGS_DIR/regression.log" 2>&1 || regression_status=$?
  echo "== regression tests (exit $regression_status) =="
  cat "$LOGS_DIR/regression.log"
fi

if [ "$feature_status" -eq 0 ] && [ "$regression_status" -eq 0 ]; then
  reward=1
else
  reward=0
fi
echo "$reward" > "$LOGS_DIR/reward.txt"
printf '{"feature_exit": %d, "regression_exit": %d, "reward": %d}\\n' \\
  "$feature_status" "$regression_status" "$reward" > "$LOGS_DIR/results.json"
echo "reward=$reward"
exit 0
"""
