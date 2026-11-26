"""Upstream novelty: a generated feature must not already exist in the repository.

Two checks, both executed with `git grep -w` (whole-identifier match):
  1. at the task's base commit, in the source tree (the feature is not there yet), and
  2. on the upstream default branch (origin/HEAD, e.g. origin/main), so the task does not ask
     for something the maintainers have already shipped after the base commit.

Ideation runs it on the identifiers each idea says it will introduce; the exporter runs it
again on the names the validated reference implementation actually adds.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

_GENERIC = {"name", "value", "default", "callback", "ctx", "self", "args", "kwargs", "help", "type", "error"}


def upstream_ref(repo: Path) -> Optional[str]:
    for ref in ("origin/HEAD", "origin/main", "origin/master", "upstream/main"):
        proc = subprocess.run(["git", "rev-parse", "--verify", "-q", ref], cwd=repo, capture_output=True, text=True)
        if proc.returncode == 0:
            return ref
    return None


def _source_paths(repo: Path) -> List[str]:
    return ["src"] if (Path(repo) / "src").is_dir() else ["."]


def _grep(repo: Path, ref: str, name: str, paths: List[str]) -> List[str]:
    proc = subprocess.run(["git", "grep", "-l", "-w", "-F", name, ref, "--", *paths],
                          cwd=repo, capture_output=True, text=True)
    return [l.split(":", 1)[-1] for l in proc.stdout.splitlines() if l.strip()]


def check_names(repo: Path, base_commit: str, names: List[str],
                target_file: Optional[str] = None) -> Dict[str, Dict[str, List[str]]]:
    """For each identifier, the source files that already contain it at the base commit and upstream.

    When `target_file` is given, only hits in that file count at the base commit: a generic
    identifier elsewhere in the code base (e.g. `exit_code`) does not make a feature old, but the
    same name already present in the file the feature extends does.
    """
    repo = Path(repo)
    up = upstream_ref(repo)
    paths = _source_paths(repo)
    out: Dict[str, Dict[str, List[str]]] = {}
    for raw in names:
        name = re.sub(r"[^A-Za-z0-9_]", "", str(raw).split(".")[-1].split("(")[0])
        if len(name) < 4 or name in _GENERIC:
            continue
        base_hits = _grep(repo, base_commit, name, paths)
        if target_file:
            base_hits = [h for h in base_hits if h == target_file]
        up_hits = _grep(repo, up, name, paths) if up else []
        if target_file:
            up_hits = [h for h in up_hits if h == target_file]
        out[name] = {"base": base_hits, "upstream": up_hits, "upstream_ref": [up] if up else []}
    return out


def already_exists(report: Dict[str, Dict[str, List[str]]]) -> List[str]:
    return [n for n, r in report.items() if r["base"] or r["upstream"]]
