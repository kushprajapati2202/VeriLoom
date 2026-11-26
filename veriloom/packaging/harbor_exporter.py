"""Export validated VeriLoom task packages to the Harbor 0.25 task format.

Layout (Innodata Track 1 / Harbor 0.25):

    <task_id>/
      instruction.md              # the only file the evaluated agent sees
      task.toml                   # metadata incl. repository, base_commit (40 hex), license
      environment/Dockerfile      # clones the repository and checks out base_commit
      solution/solve.sh           # oracle: applies the reference patch
      solution/reference.patch
      tests/test.sh               # verifier entrypoint -> /logs/verifier/reward.txt
      tests/fail_to_pass.json     # SWE-bench style: tests the feature must turn green
      tests/pass_to_pass.json     # SWE-bench style: tests that must stay green
      tests/feature/...           # hidden feature tests
      tests/regression/...        # pristine copy of the repository's test tree (restored before grading)
      tests/lib/grade.py          # computes the reward (see harbor_grade.py)
      tests/lib/veriloom_outcomes.py

fail_to_pass and pass_to_pass are not guessed: they come from running the repository's
whole suite and the feature tests before and after the reference patch in a sandbox.

Repositories without a public remote (the small in-repo fixtures) fall back to shipping a
source snapshot in environment/repo/ instead of cloning.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from veriloom.authoring.interface import interface_diff
from veriloom.validation.clarity import unexplained_literals
from veriloom.validation.sandbox import Sandbox, discover_test_targets, module_for, snapshot_repo
from veriloom.validation.target_env import PYTEST_PIN

GENERATOR = "veriloom-ai@1.1.0"
# python:3.12-slim pinned by digest so every build of the task is identical.
DEFAULT_IMAGE = "python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b"
FEATURE_PREFIX = "/tests/feature/"
_HERE = Path(__file__).resolve().parent


class HarborExportResult(BaseModel):
    task_dir: str
    task_id: str
    starting_commit: str
    repository_url: Optional[str] = None
    regression_targets: List[str] = Field(default_factory=list)
    fail_to_pass: int = 0
    pass_to_pass: int = 0
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


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def repository_info(repo_path: Path, commit: str) -> Dict[str, Optional[str]]:
    """Public URL, owner/name slug, release tag at the commit and SPDX license of the repository."""
    url = _git(repo_path, "remote", "get-url", "origin") or None
    if url and url.startswith("git@github.com:"):
        url = "https://github.com/" + url.split(":", 1)[1]
    if url and url.endswith(".git"):
        url = url[:-4]
    if url and not url.startswith("https://"):
        url = None  # local path remotes cannot be cloned inside the container
    slug = "/".join(url.rstrip("/").split("/")[-2:]) if url else Path(repo_path).name
    tag = _git(repo_path, "describe", "--tags", "--exact-match", commit) or None
    license_id = None
    pyproject = Path(repo_path) / "pyproject.toml"
    if pyproject.exists():
        try:
            lic = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {}).get("license")
            license_id = lic if isinstance(lic, str) else (lic or {}).get("text")
        except tomllib.TOMLDecodeError:
            pass
    if not license_id:
        for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "LICENSE.rst"):
            p = Path(repo_path) / name
            if p.exists():
                head = p.read_text(encoding="utf-8", errors="ignore")[:600]
                license_id = ("BSD-3-Clause" if "Redistribution and use" in head
                              else "MIT" if "Permission is hereby granted" in head
                              else "Apache-2.0" if "Apache License" in head else "see " + name)
                break
    return {"url": url, "slug": slug, "tag": tag, "license": license_id}


class HarborExporter:
    """Converts a VeriLoom package directory (pkg_*) into a runnable Harbor task."""

    @classmethod
    def export(
        cls,
        package_dir: Path,
        repo_path: Path,
        output_dir: Optional[Path] = None,
        python_image: str = DEFAULT_IMAGE,
    ) -> HarborExportResult:
        package_dir = Path(package_dir).resolve()
        repo_path = Path(repo_path).resolve()

        spec = json.loads((package_dir / "task" / "specification.json").read_text(encoding="utf-8"))
        manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
        patch = (package_dir / "reference" / "implementation.patch").read_text(encoding="utf-8")
        patch = patch.replace("\r\n", "\n")
        feature_tests = sorted((package_dir / "tests" / "feature").glob("*.py"))
        if not feature_tests:
            raise HarborExportError(f"No feature tests found in {package_dir / 'tests' / 'feature'}")

        task_id = spec["task_id"]
        commit = manifest["repository"]["pinned_commit"]
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise HarborExportError(f"base commit must be a full 40-character SHA, got {commit!r}")
        info = repository_info(repo_path, commit)
        warnings: List[str] = []

        out_root = Path(output_dir).resolve() if output_dir else package_dir.parent / "harbor_tasks"
        task_dir = out_root / task_id
        if task_dir.exists():
            shutil.rmtree(task_dir)
        task_dir.mkdir(parents=True)

        # 1. Solution: reference patch applied by the oracle
        _write(task_dir / "solution" / "reference.patch", patch)
        _write(task_dir / "solution" / "solve.sh", SOLVE_SH, executable=True)

        # 2. Run everything once more in a sandbox to derive fail_to_pass / pass_to_pass.
        with Sandbox(repo_path, commit) as sb:
            patch_ok, patch_err = cls._check_patch_applies(sb.app, patch)
            if not patch_ok:
                raise HarborExportError(f"Reference patch does not apply to {commit[:12]}: {patch_err}")
            changed = cls._changed_files(patch)
            originals = {f: sb.read(f) for f in changed}
            f2p, p2p, test_root = cls._test_lists(sb, patch, feature_tests)
            news = {f: sb.read(f) for f in changed}
            # Restore pristine copies of the repository's tests (agents cannot game the verifier by editing them).
            src_tests = sb.app / test_root if test_root else None
            if src_tests and src_tests.is_dir():
                shutil.copytree(src_tests, task_dir / "tests" / "regression" / test_root,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            if not info["url"]:
                cls._copy_snapshot(repo_path, commit, task_dir / "environment" / "repo")
        if not f2p:
            raise HarborExportError("No feature test fails before and passes after the reference patch")

        # 3. Environment
        _write(task_dir / "environment" / "Dockerfile", cls._dockerfile(info, commit, python_image, repo_path))

        # 4. Tests
        for t in feature_tests:
            _write(task_dir / "tests" / "feature" / t.name, t.read_text(encoding="utf-8"))
        _write(task_dir / "tests" / "fail_to_pass.json", json.dumps(f2p, indent=2) + "\n")
        _write(task_dir / "tests" / "pass_to_pass.json", json.dumps(p2p, indent=2) + "\n")
        _write(task_dir / "tests" / "lib" / "grade.py", (_HERE / "harbor_grade.py").read_text(encoding="utf-8"))
        _write(task_dir / "tests" / "lib" / "veriloom_outcomes.py",
               (_HERE.parent / "validation" / "veriloom_outcomes.py").read_text(encoding="utf-8"))
        _write(task_dir / "tests" / "test.sh", TEST_SH, executable=True)

        # 5. Instruction + task.toml
        interface: List[Tuple[str, List[str]]] = []
        for f in changed:
            sigs = interface_diff(originals.get(f, ""), news.get(f, "")) if f.endswith(".py") else []
            if sigs:
                interface.append((f, sigs))
        instruction = cls._instruction_md(spec, interface, info)
        _write(task_dir / "instruction.md", instruction)
        _write(task_dir / "task.toml", cls._task_toml(spec, manifest, info, commit, len(f2p), len(p2p)))

        # 6. Clarity lint: literal expectations in hidden tests the agent cannot infer
        test_code = "\n".join(t.read_text(encoding="utf-8") for t in feature_tests)
        for literal in unexplained_literals(test_code, instruction):
            warnings.append(
                f"Hidden tests assert the value {literal}, which the instruction never states; "
                "the task may be under-specified."
            )

        result = HarborExportResult(
            task_dir=str(task_dir),
            task_id=task_id,
            starting_commit=commit,
            repository_url=info["url"],
            regression_targets=sorted({t.split("::", 1)[0] for t in p2p if not t.startswith(FEATURE_PREFIX)}),
            fail_to_pass=len(f2p),
            pass_to_pass=len(p2p),
            patch_applies=patch_ok,
            warnings=warnings,
        )
        # Kept outside the task dir so it is not shipped to the agent or verifier.
        _write(out_root / f"{task_id}.export.json", result.model_dump_json(indent=2))
        return result

    # ------------------------------------------------------------------ test lists

    @staticmethod
    def _test_lists(sb: Sandbox, patch: str, feature_tests: List[Path]) -> Tuple[List[str], List[str], str]:
        """Run repo suite + feature tests before and after the patch; derive F2P and P2P node ids."""
        targets = discover_test_targets(sb.app)
        test_root = targets[0].split("/", 1)[0] if targets and "/" in targets[0] else ""
        for t in feature_tests:
            (sb.hidden / t.name).write_text(t.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")

        before_repo = sb.pytest(targets, junit=False, outcomes=True).nodes if targets else {}
        before_feat = sb.pytest([str(sb.hidden)], junit=False, outcomes=True).nodes
        HarborExporter._apply_patch(sb.app, patch)
        after_repo = sb.pytest(targets, junit=False, outcomes=True).nodes if targets else {}
        after_feat = sb.pytest([str(sb.hidden)], junit=False, outcomes=True).nodes

        def feat_id(nodeid: str) -> str:
            path, _, rest = nodeid.partition("::")
            return f"{FEATURE_PREFIX}{path.replace(chr(92), '/').rsplit('/', 1)[-1]}::{rest}"

        before_f = {feat_id(k): v for k, v in before_feat.items() if "::" in k}
        after_f = {feat_id(k): v for k, v in after_feat.items() if "::" in k}
        f2p = sorted(k for k, v in after_f.items() if v == "passed" and before_f.get(k) != "passed")
        # Feature tests that already pass on the original code guard existing behaviour: they are P2P.
        p2p_feat = sorted(k for k, v in after_f.items() if v == "passed" and before_f.get(k) == "passed")
        p2p_repo = sorted(k for k, v in after_repo.items()
                          if "::" in k and v == "passed" and before_repo.get(k) == "passed")
        return f2p, p2p_repo + p2p_feat, test_root

    @staticmethod
    def _apply_patch(app: Path, patch: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pf = Path(tmp) / "reference.patch"
            pf.write_text(patch, encoding="utf-8", newline="\n")
            proc = subprocess.run(["git", "apply", "--whitespace=nowarn", str(pf)], cwd=app,
                                  capture_output=True, text=True, env=_git_env(str(app)))
            if proc.returncode != 0:
                raise HarborExportError(f"git apply failed: {proc.stderr.strip()}")

    @staticmethod
    def _changed_files(patch: str) -> List[str]:
        files = []
        for line in patch.splitlines():
            if line.startswith("+++ "):
                path = line[4:].strip()
                if path != "/dev/null":
                    files.append(path[2:] if path.startswith("b/") else path)
        return files

    # ------------------------------------------------------------------ environment

    @staticmethod
    def _copy_snapshot(repo_path: Path, commit: str, dest: Path) -> None:
        try:
            snapshot_repo(repo_path, commit, dest)
        except RuntimeError as e:
            raise HarborExportError(str(e)) from e

    @staticmethod
    def _dockerfile(info: Dict, commit: str, image: str, repo_path: Path) -> str:
        head = (
            f"# Generated by {GENERATOR}: {info['slug']} at base commit {commit}\n"
            f"FROM {image}\n\n"
            "RUN apt-get update \\\n"
            " && apt-get install -y --no-install-recommends git ca-certificates \\\n"
            " && rm -rf /var/lib/apt/lists/*\n\n"
            "WORKDIR /app\n"
        )
        if info["url"]:
            # Fetch exactly the base commit (depth 1): no later history is visible to the agent.
            source = (
                "RUN git init -q /app \\\n"
                f" && git -C /app remote add origin {info['url']}.git \\\n"
                f" && git -C /app fetch -q --depth 1 origin {commit} \\\n"
                " && git -C /app checkout -q FETCH_HEAD \\\n"
                f" && test \"$(git -C /app rev-parse HEAD)\" = \"{commit}\"\n\n"
            )
        else:
            source = "COPY repo/ /app/\n\n"
        has_project = (repo_path / "pyproject.toml").exists() or (repo_path / "setup.py").exists()
        install = (
            f"RUN pip install --no-cache-dir {PYTEST_PIN}\n"
            + ("RUN pip install --no-cache-dir -e /app\n" if has_project else "")
            + ("RUN pip install --no-cache-dir -r /app/requirements.txt\n"
               if (repo_path / "requirements.txt").exists() else "")
        )
        return head + source + install

    @staticmethod
    def _check_patch_applies(repo_dir: Path, patch: str) -> Tuple[bool, str]:
        # Run in a temp copy outside any git work tree so `git apply` behaves like `patch`.
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "app"
            shutil.copytree(repo_dir, work, ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
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

    # ------------------------------------------------------------------ instruction

    @staticmethod
    def _interface_from_patch(patch: str) -> List[Tuple[str, List[str]]]:
        """Signatures of new top-level Python names in a patch (legacy helper; kept for tooling)."""
        import ast

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
            sigs = [f"def {n.name}({ast.unparse(n.args)})" if not isinstance(n, ast.ClassDef) else f"class {n.name}"
                    for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
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
    def _instruction_md(spec: dict, interface: List[Tuple[str, List[str]]], info: Dict) -> str:
        out: List[str] = [f"# {spec['title']}", "", spec["summary"], ""]
        out += [
            f"You are working in a checkout of `{info['slug']}` at `/app` "
            f"(commit `{spec['starting_commit']}`). Implement the feature described below. "
            "Existing behaviour must not change unless a requirement says so, and the repository's "
            "existing test suite must keep passing. Do not modify the existing tests.",
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
                "The feature is verified through these names and parameters; they must exist exactly "
                "as shown (`# new` marks additions, other comments name added parameters):",
                "",
            ]
            for file, sigs in interface:
                out.append(f"In `{file}` (importable as `{module_for(file)}`):")
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
    def _task_toml(spec: dict, manifest: dict, info: Dict, commit: str, n_f2p: int, n_p2p: int) -> str:
        repo = manifest.get("repository", {})
        family = spec.get("feature_family", "feature")
        language = repo.get("language") or "python"
        tags = [t for t in ["feature-development", family, language, info["slug"].split("/")[-1]] if t]
        short = re.sub(r"[^A-Za-z0-9_.-]", "-", info["slug"].split("/")[-1])
        lines = [
            f"# Generated by {GENERATOR}",
            'schema_version = "1.4"',
            "",
            "[task]",
            f"name = {_toml_str('veriloom/' + short + '-' + spec['task_id'])}",
            'version = "1.0.0"',
            f"description = {_toml_str(spec['title'])}",
            f"keywords = {_toml_list(tags)}",
            "",
            "[metadata]",
            f"repository = {_toml_str(info['slug'])}",
        ]
        if info["url"]:
            lines.append(f"repository_url = {_toml_str(info['url'])}")
        lines += [
            f"base_commit = {_toml_str(commit)}",
        ]
        if info["tag"]:
            lines.append(f"base_ref = {_toml_str(info['tag'])}")
        lines += [
            f"license = {_toml_str(info['license'] or 'unknown')}",
            f"language = {_toml_str(language)}",
            'test_runner = "pytest"',
            'category = "feature-development"',
            f"difficulty = {_toml_str(spec.get('difficulty', 'intermediate'))}",
            f"feature_family = {_toml_str(family)}",
            f"tags = {_toml_list(tags)}",
            'fail_to_pass = "tests/fail_to_pass.json"',
            'pass_to_pass = "tests/pass_to_pass.json"',
            f"fail_to_pass_count = {n_f2p}",
            f"pass_to_pass_count = {n_p2p}",
            f"generator = {_toml_str(GENERATOR)}",
            "",
            "[verifier]",
            "timeout_sec = 1800.0",
            # The verifier grades the agent's working tree in place (SWE-bench style), and the
            # hidden tests need no network.
            'environment_mode = "shared"',
            'network_mode = "no-network"',
            "",
            "[agent]",
            "timeout_sec = 3600.0",
            "",
            "[environment]",
            "build_timeout_sec = 1200.0",
            "cpus = 2",
            "memory_mb = 4096",
            "",
        ]
        return "\n".join(lines)


def _git_env(tmp: str) -> dict:
    # Stop git from discovering an enclosing repository above the work directory.
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
# reward = 0 if any pass_to_pass test breaks, else the share of fail_to_pass tests that pass.
set -uo pipefail
APP_DIR="${APP_DIR:-/app}"
TESTS_DIR="${TESTS_DIR:-/tests}"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
PYTHON="${PYTHON:-python}"
mkdir -p "$LOGS_DIR"
cd "$APP_DIR"

# Restore pristine copies of the repository's tests so edits to them cannot game the verifier.
if [ -d "$TESTS_DIR/regression" ]; then
  cp -r "$TESTS_DIR/regression/." "$APP_DIR/"
fi

"$PYTHON" "$TESTS_DIR/lib/grade.py" --app "$APP_DIR" --tests "$TESTS_DIR" --logs "$LOGS_DIR" --python "$PYTHON"
if [ ! -s "$LOGS_DIR/reward.txt" ]; then
  echo "grader crashed; reward 0" >&2
  echo 0 > "$LOGS_DIR/reward.txt"
fi
exit 0
"""
