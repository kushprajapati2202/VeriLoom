#!/usr/bin/env bash
# Run the official Track 1 validation matrix with real Harbor (Docker required):
#   harbor run -p <task> -a nop    -k 1 -o <out> --no-delete -y   -> expected reward 0.0
#   harbor run -p <task> -a oracle -k 1 -o <out> --no-delete -y   -> expected reward 1.0
#
# usage: scripts/harbor_validate.sh [tasks_dir] [out_dir]
#   defaults: evidence/click/harbor_tasks  evidence/click/harbor_runs
# Writes <out_dir>/summary.json and keeps every Harbor job directory for inspection.
set -uo pipefail
TASKS="${1:-evidence/click/harbor_tasks}"
OUT="${2:-evidence/click/harbor_runs}"
HARBOR="${HARBOR:-harbor}"
mkdir -p "$OUT"
"$HARBOR" --version

for task in "$TASKS"/*/; do
  task="${task%/}"
  name="$(basename "$task")"
  [ -f "$task/task.toml" ] || continue
  for agent in nop oracle; do
    job_dir="$OUT/$name/$agent"
    rm -rf "$job_dir"
    mkdir -p "$job_dir"
    echo "== $name / $agent"
    "$HARBOR" run -p "$task" -a "$agent" -k 1 -o "$job_dir" --no-delete -y > "$OUT/$name/$agent.log" 2>&1
    echo "   exit $?"
  done
done

python3 - "$OUT" <<'PY'
import glob, json, os, sys
out = sys.argv[1]
expected = {"nop": 0.0, "oracle": 1.0}
rows = []
for trial in sorted(glob.glob(os.path.join(out, "*", "*", "*", "*", "result.json"))):
    parts = trial.split(os.sep)
    task, agent = parts[-5], parts[-4]
    t = json.load(open(trial))
    vr = t.get("verifier_result") or {}
    reward = (vr.get("rewards") or {}).get("reward")
    exc = (t.get("exception_info") or {}).get("exception_type")
    rows.append({"task": task, "agent": agent, "reward": reward, "expected": expected.get(agent),
                 "ok": reward == expected.get(agent) and not exc, "exception": exc,
                 "trial": os.path.relpath(os.path.dirname(trial), out)})
json.dump(rows, open(os.path.join(out, "summary.json"), "w"), indent=2)
for r in rows:
    print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['task']:<14} {r['agent']:<7} reward={r['reward']} "
          f"(expected {r['expected']}){'  ' + r['exception'] if r['exception'] else ''}")
bad = [r for r in rows if not r["ok"]]
print(f"\n{len(rows) - len(bad)}/{len(rows)} trials match the validation matrix")
sys.exit(1 if bad else 0)
PY
