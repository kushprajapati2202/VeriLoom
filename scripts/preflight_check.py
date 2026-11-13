"""Pre-flight check script to verify all systems, tests, and CLI entry points before live presentation."""

import subprocess
import sys
from pathlib import Path


def run_step(step_name: str, cmd: list) -> bool:
    print(f"[*] Checking: {step_name}...", end=" ", flush=True)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(Path(__file__).parent.parent))
        if res.returncode == 0:
            print("[PASS]")
            return True
        else:
            print("[FAIL]")
            print(res.stdout)
            print(res.stderr)
            return False
    except Exception as e:
        print(f"[ERROR: {e}]")
        return False


def main():
    print("==================================================")
    print("      VeriLoom Hackathon Pre-Flight Auditor       ")
    print("==================================================")

    steps = [
        ("Python Module Imports", [sys.executable, "-c", "import veriloom; import fastapi; import pydantic; import click"]),
        ("CLI Top-Level Entrypoint", [sys.executable, "-m", "veriloom", "--help"]),
        ("Repository Inspection", [sys.executable, "-m", "veriloom", "inspect", "."]),
        ("Opportunity Discovery", [sys.executable, "-m", "veriloom", "opportunities", "."]),
        ("Sample Package Replay & SHA-256 Checksums", [sys.executable, "scripts/replay_package.py", "--package", "examples/sample_packages/pkg_task_48e3bf"]),
        ("AI Benchmark Evaluation Harness (Valid Solution)", [
            sys.executable, "-m", "veriloom", "benchmark",
            "--package", "examples/sample_packages/pkg_task_48e3bf",
            "--solution", "examples/sample_packages/pkg_task_48e3bf/reference/implementation.patch",
            "--model", "preflight-agent"
        ]),
        ("Automated Core Test Suite", [sys.executable, "-m", "pytest", "tests/test_contracts.py", "tests/test_packaging.py", "-q"]),
    ]

    all_passed = True
    for name, cmd in steps:
        if not run_step(name, cmd):
            all_passed = False

    print("==================================================")
    if all_passed:
        print("  ALL 7 AUDIT CHECKS PASSED — 100% READY TO WIN!  ")
    else:
        print("  SOME CHECKS FAILED — REVIEW LOGS ABOVE.         ")
    print("==================================================")
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
