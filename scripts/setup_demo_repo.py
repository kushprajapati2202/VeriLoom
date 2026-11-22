"""Materialise a demo target repository as a git repo with a reproducible commit SHA.

VeriLoom pins every task to a commit, and the sandbox extracts that commit with
`git archive`. The demo sources live in examples/target_repos/<name> as plain files;
this script copies them out and commits them with fixed author/date so the SHA is
identical on every machine.

    python scripts/setup_demo_repo.py shopcart            # -> test_repos/shopcart
    python scripts/setup_demo_repo.py shopcart --dest /tmp/shopcart
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXED_ENV = {
    "GIT_AUTHOR_NAME": "VeriLoom Demo",
    "GIT_AUTHOR_EMAIL": "demo@veriloom.invalid",
    "GIT_COMMITTER_NAME": "VeriLoom Demo",
    "GIT_COMMITTER_EMAIL": "demo@veriloom.invalid",
    "GIT_AUTHOR_DATE": "2026-11-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-11-01T00:00:00+00:00",
}


def git(dest: Path, *args: str) -> str:
    env = {**os.environ, **FIXED_ENV}
    out = subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", *args],
                         cwd=dest, env=env, check=True, capture_output=True, text=True)
    return out.stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="directory under examples/target_repos")
    ap.add_argument("--dest", default=None, help="output path (default: test_repos/<name>)")
    args = ap.parse_args()

    src = ROOT / "examples" / "target_repos" / args.name
    if not src.is_dir():
        print(f"no such demo repo: {src}", file=sys.stderr)
        return 1
    dest = Path(args.dest).resolve() if args.dest else ROOT / "test_repos" / args.name
    if dest.exists():
        # git marks object files read-only, which Windows refuses to delete.
        def _force(func, path, _exc):
            os.chmod(path, 0o700)
            func(path)
        # Empty the folder rather than deleting it: on Windows a terminal whose current
        # directory is `dest` locks the folder itself, but not its contents.
        for child in list(dest.iterdir()):
            if child.is_dir():
                shutil.rmtree(child, onerror=_force)
            else:
                os.chmod(child, 0o700)
                child.unlink()
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "exports"),
                    dirs_exist_ok=True)
    # Normalise line endings so the tree (and therefore the SHA) is platform independent.
    for f in dest.rglob("*"):
        if f.is_file():
            data = f.read_bytes().replace(b"\r\n", b"\n")
            f.write_bytes(data)
    (dest / ".gitignore").write_text("__pycache__/\n.pytest_cache/\nexports/\n", encoding="utf-8")

    git(dest, "init", "-q", "-b", "main")
    git(dest, "add", "-A")
    git(dest, "commit", "-q", "-m", f"{args.name}: initial import")
    sha = git(dest, "rev-parse", "HEAD")
    print(f"{dest}\ncommit {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
