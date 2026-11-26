"""Repository-level feature ideation.

Template opportunities ("add a lifecycle to <file>") fit a toy app but not a real library:
"access-control rules for click/utils.py" is not a feature anyone would ship. Ideation asks
the model to read the repository's actual public API and changelog and propose a portfolio of
feature-development tasks that

  - a maintainer could plausibly accept (realistic, opt-in, backward compatible),
  - do not already exist (the changelog and API listing are in the prompt; the exporter also
    checks the reference's new names against the upstream default branch),
  - are each implementable in one source file and observable through the public API,
  - differ from each other in behaviour family AND in target file.

The portfolio is saved as ideas.json, so a run is reproducible and every later stage (spec,
authoring, gates) starts from the same candidate list.
"""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from veriloom.contracts.repository import SourceEvidence
from veriloom.contracts.task_spec import FeatureFamily, TaskDifficulty
from veriloom.llm.provider import LLMProvider
from veriloom.task_generation.candidate_engine import CandidateOpportunity

log = logging.getLogger("veriloom")

_SKIP_DIRS = {"tests", "test", "docs", "examples", "build", "dist", ".git", "__pycache__", "benchmarks"}
MAX_API_CHARS = 18_000
MAX_CHANGELOG_CHARS = 7_000

IDEATION_PROMPT = """You design feature-development tasks for benchmarking AI coding agents.
The tasks are built on a real open-source repository at a fixed commit. Each task asks an agent to
implement ONE new feature; hidden tests then check it.

# Repository: {repo_name}
{readme}

## Public API at the starting commit (module: classes with methods, functions)
{api}

## Most recent changelog entries (features that ALREADY exist; do not propose them again)
{changelog}

## Tasks already generated (yours must differ in behaviour from all of them)
{existing}

# Propose {count} feature ideas
Rules for every idea:
- A genuine NEW capability or a change to existing behaviour that a maintainer could plausibly accept.
  Not a bug fix, not a refactor, not documentation, not a pure rename.
- It must NOT already exist in the API above (constructor parameters are listed in parentheses) or in
  the changelog. Every identifier you introduce is checked automatically against the source at this
  commit and against the upstream default branch; ideas whose new names already exist are discarded.
- Implementable by editing exactly ONE existing source file listed above (target_file), standard library only.
- Opt-in and backward compatible: existing behaviour and the repository's existing tests stay unchanged
  unless the new option/argument/method is used.
- Observable through the public API in a plain pytest test (return values, raised exceptions, captured
  output via the library's own testing helpers). No interactive terminal, no network, no real filesystem
  outside a temporary directory, nothing that depends on the clock, time zone, randomness or terminal size.
- Never change what existing callers receive (no new positional arguments passed to user callbacks,
  no changed return types, no changed default output).
- Requires real reasoning: several interacting rules, an ordering/precedence decision, validation with
  precise error messages, or state that persists across calls. Not a one-liner.
- Ideas must differ from each other in behaviour; use each "family" at most twice and spread the ideas
  over at least {min_files} different target files.

Families (pick the closest): business_rules, data_validation, state_transitions, error_handling,
data_lifecycle, api_behaviour, permissions_auth.

RESPOND IN VALID JSON ONLY:
{{"ideas": [
  {{"title": "short imperative title",
    "family": "data_validation",
    "difficulty": "intermediate|advanced",
    "target_file": "path/of/the/one/file/to/change.py",
    "touches": ["ExistingClass.method", "existing_function"],
    "new_names": ["new_parameter_or_method_name", "NewClassName"],
    "summary": "two or three sentences: what the user can do after the change and the exact rules",
    "why_new": "why this does not exist yet (cite what the current API lacks)"}}
]}}
"""


def _first_line(node) -> str:
    doc = ast.get_docstring(node) or ""
    return doc.strip().splitlines()[0][:90] if doc.strip() else ""


def source_files(repo_root: Path) -> List[Path]:
    out = []
    for p in sorted(Path(repo_root).rglob("*.py")):
        rel = p.relative_to(repo_root)
        if any(part in _SKIP_DIRS or part.startswith(".") for part in rel.parts):
            continue
        if p.name.startswith("_") and p.name != "__init__.py":
            continue  # private modules are implementation details
        if p.name in ("setup.py", "conftest.py", "noxfile.py"):
            continue
        out.append(p)
    return out


def api_summary(repo_root: Path, limit: int = MAX_API_CHARS) -> str:
    lines: List[str] = []
    for path in source_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        entries = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                methods = [n.name for n in node.body
                           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                           and not n.name.startswith("_")]
                init = next((n for n in node.body if getattr(n, "name", None) == "__init__"), None)
                params = ""
                if init is not None:
                    a = init.args
                    names = [x.arg for x in a.args[1:] + a.kwonlyargs]
                    params = "(" + ", ".join(names[:24]) + (", ..." if len(names) > 24 else "") + ")"
                entries.append(f"  class {node.name}{params}: {', '.join(methods[:18])}"
                               + (" ..." if len(methods) > 18 else ""))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                entries.append(f"  def {node.name}({', '.join(a.arg for a in node.args.args)})"
                               + (f"  # {_first_line(node)}" if _first_line(node) else ""))
        if entries:
            lines.append(f"{rel}  ({path.stat().st_size // 1000} KB)")
            lines += entries
    text = "\n".join(lines)
    return text[:limit] + ("\n  ... (truncated)" if len(text) > limit else "")


def _changelog(repo_root: Path) -> str:
    for name in ("CHANGES.md", "CHANGES.rst", "CHANGELOG.md", "HISTORY.md", "NEWS.md"):
        p = Path(repo_root) / name
        if p.exists():
            return p.read_text(encoding="utf-8", errors="ignore")[:MAX_CHANGELOG_CHARS]
    return "(no changelog found)"


def _readme(repo_root: Path) -> str:
    for name in ("README.md", "README.rst", "README.txt"):
        p = Path(repo_root) / name
        if p.exists():
            return p.read_text(encoding="utf-8", errors="ignore")[:1500]
    return ""


def _family(value: str) -> FeatureFamily:
    try:
        return FeatureFamily(str(value).strip().lower())
    except ValueError:
        return FeatureFamily.API_BEHAVIOUR


def _difficulty(value: str) -> TaskDifficulty:
    try:
        return TaskDifficulty(str(value).strip().lower())
    except ValueError:
        return TaskDifficulty.INTERMEDIATE


class FeatureIdeation:
    @classmethod
    def propose(
        cls,
        provider: LLMProvider,
        repo_root: Path,
        repo_name: str,
        count: int = 10,
        existing: Optional[List[str]] = None,
        base_commit: Optional[str] = None,
    ) -> List[Dict]:
        repo_root = Path(repo_root)
        prompt = IDEATION_PROMPT.format(
            repo_name=repo_name,
            readme=_readme(repo_root),
            api=api_summary(repo_root),
            changelog=_changelog(repo_root),
            existing="\n".join(f"- {t}" for t in (existing or [])) or "(none yet)",
            count=count,
            min_files=min(5, max(2, count // 2)),
        )
        data = provider.generate_json(prompt)
        ideas = data.get("ideas", data if isinstance(data, list) else [])
        valid_files = {p.relative_to(repo_root).as_posix() for p in source_files(repo_root)}
        kept: List[Dict] = []
        for idea in ideas:
            target = str(idea.get("target_file", "")).replace("\\", "/").lstrip("./")
            if target not in valid_files:
                log.info("[ideate] dropped %r: target %r is not a public source file", idea.get("title"), target)
                continue
            idea["target_file"] = target
            if base_commit:
                from veriloom.task_generation.novelty import already_exists, check_names

                report = check_names(repo_root, base_commit, idea.get("new_names", []), target)
                idea["novelty_check"] = report
                clash = already_exists(report)
                if clash:
                    idea["rejected"] = f"already exists: {', '.join(clash)}"
                    log.info("[ideate] dropped %r: %s", idea.get("title"), idea["rejected"])
                    continue
                if not report:
                    idea["rejected"] = "no checkable new identifier (new_names empty or too generic)"
                    log.info("[ideate] dropped %r: %s", idea.get("title"), idea["rejected"])
                    continue
            kept.append(idea)
        cls.last_rejected = [i for i in ideas if i.get("rejected")]
        return kept

    last_rejected: List[Dict] = []

    @staticmethod
    def to_opportunities(ideas: List[Dict]) -> List[CandidateOpportunity]:
        opps = []
        for i, idea in enumerate(ideas):
            touches = [str(t) for t in idea.get("touches", [])][:3] or [None]
            opps.append(CandidateOpportunity(
                candidate_id=f"idea_{i + 1:03d}",
                title=idea.get("title", f"Feature {i + 1}"),
                feature_family=_family(idea.get("family", "")),
                difficulty=_difficulty(idea.get("difficulty", "")),
                summary=idea.get("summary", ""),
                target_evidence=[
                    SourceEvidence(path=idea["target_file"], symbol=t,
                                   reason="Named by repository-level ideation as the code this feature extends")
                    for t in touches
                ],
                score=round(1.0 - i * 0.01, 2),
                feasibility_notes=idea.get("why_new", ""),
            ))
        return opps

    @staticmethod
    def save(ideas: List[Dict], path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({"ideas": ideas}, indent=2), encoding="utf-8")

    @staticmethod
    def load(path: Path) -> List[Dict]:
        return json.loads(Path(path).read_text(encoding="utf-8"))["ideas"]
