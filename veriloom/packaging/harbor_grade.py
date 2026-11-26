"""Harbor verifier for a VeriLoom task (shipped as tests/lib/grade.py, runs inside the container).

Reward, as defined by the Innodata Track 1 validation matrix:
  - any pass_to_pass test fails (or is missing)  -> 0.0
  - otherwise                                      -> share of fail_to_pass tests that pass
    (1.0 when the feature is fully implemented, 0.0 for the untouched repository)

Test ids are pytest node ids. Ids that start with /tests/feature/ name the hidden feature tests
(matched by file name and test name, since they run from outside the repository); all other ids
are the repository's own tests, relative to the repository root.

Standard library only (plus pytest in the environment). Writes:
  $LOGS/reward.txt     the reward as a float
  $LOGS/results.json   per-group counts and the failing ids
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

FEATURE_PREFIX = "/tests/feature/"


def feature_key(nodeid):
    path, sep, rest = nodeid.partition("::")
    return path.replace("\\", "/").rsplit("/", 1)[-1] + sep + rest


def run_pytest(python, targets, cwd, outcomes_file, lib_dir, log_file, timeout):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(lib_dir)
    env["VERILOOM_OUTCOMES_FILE"] = str(outcomes_file)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [python, "-m", "pytest", *targets, "-p", "veriloom_outcomes", "-p", "no:cacheprovider",
           "-q", "-rfE", "--rootdir", str(cwd)]
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        output, code = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        output, code = f"TIMEOUT after {timeout}s\n{e.stdout or ''}", 124
    Path(log_file).write_text(" ".join(cmd) + "\n\n" + output, encoding="utf-8")
    outcomes = {}
    if Path(outcomes_file).exists():
        outcomes = json.loads(Path(outcomes_file).read_text(encoding="utf-8"))
    return code, outcomes, output


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default=os.environ.get("APP_DIR", "/app"))
    ap.add_argument("--tests", default=os.environ.get("TESTS_DIR", "/tests"))
    ap.add_argument("--logs", default=os.environ.get("LOGS_DIR", "/logs/verifier"))
    ap.add_argument("--python", default=os.environ.get("PYTHON", sys.executable))
    ap.add_argument("--timeout", type=int, default=int(os.environ.get("VERILOOM_TEST_TIMEOUT", "1200")))
    args = ap.parse_args(argv)

    app, tests, logs = Path(args.app), Path(args.tests), Path(args.logs)
    lib = tests / "lib"
    logs.mkdir(parents=True, exist_ok=True)
    f2p = json.loads((tests / "fail_to_pass.json").read_text(encoding="utf-8"))
    p2p = json.loads((tests / "pass_to_pass.json").read_text(encoding="utf-8"))

    # 1. Hidden feature tests (run from outside the repository, as during validation).
    _, feat, feat_out = run_pytest(args.python, [str(tests / "feature")], app, logs / "feature-outcomes.json",
                                   lib, logs / "feature.log", args.timeout)
    feat_by_key = {feature_key(k): v for k, v in feat.items()}

    # 2. The repository's own tests that passed before and after the reference change.
    repo_ids = [t for t in p2p if not t.startswith(FEATURE_PREFIX)]
    targets = sorted({t.split("::", 1)[0] for t in repo_ids})
    reg = {}
    if targets:
        _, reg, _ = run_pytest(args.python, targets, app, logs / "regression-outcomes.json",
                               lib, logs / "regression.log", args.timeout)

    def outcome(test_id):
        if test_id.startswith(FEATURE_PREFIX):
            return feat_by_key.get(feature_key(test_id), "missing")
        return reg.get(test_id, "missing")

    f2p_failed = [t for t in f2p if outcome(t) != "passed"]
    # A skip is not a regression (platform-dependent skips); a failure or a vanished test is.
    p2p_failed = [t for t in p2p if outcome(t) not in ("passed", "skipped")]
    if p2p_failed:
        reward = 0.0
    else:
        reward = (len(f2p) - len(f2p_failed)) / len(f2p) if f2p else 0.0
    reward = round(reward, 4)

    (logs / "reward.txt").write_text(f"{reward}\n", encoding="utf-8")
    results = {
        "reward": reward,
        "fail_to_pass": {"total": len(f2p), "passed": len(f2p) - len(f2p_failed), "failing": f2p_failed[:50]},
        "pass_to_pass": {"total": len(p2p), "broken": len(p2p_failed), "failing": p2p_failed[:50]},
    }
    (logs / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("== feature tests ==")
    print(feat_out[-6000:])
    print(f"fail_to_pass: {results['fail_to_pass']['passed']}/{len(f2p)} passing")
    print(f"pass_to_pass: {len(p2p) - len(p2p_failed)}/{len(p2p)} still passing")
    for t in p2p_failed[:20]:
        print(f"  REGRESSION {t} -> {outcome(t)}")
    print(f"reward={reward}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
