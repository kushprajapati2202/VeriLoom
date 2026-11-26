"""Clone pallets/click at the pinned release and create its isolated test environment.

    python scripts/setup_click.py            # -> target_repos/click at 8.5.1 (cf19179e...)

Idempotent. Verifies that the checkout is the exact base commit and that the repository's own
test suite passes there (Track 1 rule: every task starts from a commit where all tests pass).
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from veriloom.validation.target_env import setup_target_env  # noqa: E402

URL = "https://github.com/pallets/click.git"
TAG = "8.5.1"
COMMIT = "cf19179e8e2fd54c601378cec9e0d21bb12b6fb1"


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=str(ROOT / "target_repos" / "click"))
    ap.add_argument("--skip-tests", action="store_true")
    args = ap.parse_args()
    dest = Path(args.dest)

    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"[*] cloning {URL} -> {dest}")
        git("clone", "--quiet", URL, str(dest))
    else:
        git("fetch", "--quiet", "--tags", "origin", cwd=dest)
    git("-c", "advice.detachedHead=false", "checkout", "--quiet", TAG, cwd=dest)
    head = git("rev-parse", "HEAD", cwd=dest)
    if head != COMMIT:
        print(f"[!] {TAG} resolved to {head}, expected {COMMIT}", file=sys.stderr)
        return 1
    print(f"[+] {dest} at {TAG} = {head}")

    print("[*] creating isolated test environment (pytest + click in editable mode)")
    python = setup_target_env(dest)
    print(f"[+] {python}")

    if not args.skip_tests:
        print("[*] running click's own test suite at the base commit")
        proc = subprocess.run([python, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=dest,
                              capture_output=True, text=True)
        print(proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-500:])
        if proc.returncode != 0:
            print("[!] baseline test suite is not green", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
