"""Python environment the target repository's tests run in.

VeriLoom itself depends on `click`, so running a click checkout's tests with
VeriLoom's own interpreter would import the installed click instead of the
sandbox copy (and pick up unrelated pytest plugins). A target repository
therefore gets its own virtual environment, created once by
`python -m veriloom setup-target <repo>`:

    .veriloom/venvs/<repo-dir-name>/      pytest + the repo's build backend + its runtime deps

Every sandbox copy of the repository is then installed into that venv in
editable mode (`pip install -e <copy> --no-deps --no-build-isolation`), so the
tests always exercise the copy under validation.

Resolution order for the interpreter: $VERILOOM_TARGET_PYTHON, then the venv
above if it exists, otherwise the current interpreter (fine for the small
in-repo fixtures, which import their package from the working directory).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import List, Optional

VENV_ROOT = Path(os.environ.get("VERILOOM_HOME", Path(__file__).resolve().parents[2] / ".veriloom")) / "venvs"
PYTEST_PIN = "pytest==8.4.2"


def venv_dir(repo_path: Path) -> Path:
    return VENV_ROOT / Path(repo_path).resolve().name


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def target_python(repo_path: Optional[Path]) -> Optional[str]:
    """Interpreter for the repo's tests, or None to use the current interpreter as-is."""
    explicit = os.environ.get("VERILOOM_TARGET_PYTHON")
    if explicit:
        return explicit
    if repo_path is None:
        return None
    py = _venv_python(venv_dir(repo_path))
    return str(py) if py.exists() else None


def build_requires(repo_dir: Path) -> List[str]:
    pyproject = Path(repo_dir) / "pyproject.toml"
    if not pyproject.exists():
        return ["setuptools", "wheel"]
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return list(data.get("build-system", {}).get("requires", ["setuptools", "wheel"]))


def is_installable(repo_dir: Path) -> bool:
    return (Path(repo_dir) / "pyproject.toml").exists() or (Path(repo_dir) / "setup.py").exists()


def _run(cmd: List[str], cwd: Optional[Path] = None) -> None:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{proc.stdout[-2000:]}{proc.stderr[-2000:]}")


def setup_target_env(repo_path: Path) -> str:
    """Create the venv for a target repository (needs network once). Returns its interpreter."""
    repo_path = Path(repo_path).resolve()
    venv = venv_dir(repo_path)
    py = _venv_python(venv)
    if not py.exists():
        venv.parent.mkdir(parents=True, exist_ok=True)
        _run([sys.executable, "-m", "venv", str(venv)])
    _run([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"])
    _run([str(py), "-m", "pip", "install", "-q", PYTEST_PIN, *build_requires(repo_path)])
    if is_installable(repo_path):
        # Installs runtime dependencies once; sandboxes later re-point the editable install.
        _run([str(py), "-m", "pip", "install", "-q", "-e", str(repo_path)])
    return str(py)


def install_copy(python: str, repo_dir: Path) -> None:
    """Point the target venv at a sandbox copy of the repository (fast, offline)."""
    if is_installable(repo_dir):
        _run([python, "-m", "pip", "install", "-q", "--no-deps", "--no-build-isolation", "-e", str(repo_dir)])
