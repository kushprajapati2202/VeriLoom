# VeriLoom live demo (about 7 minutes)

Audience: judges and Innodata leadership. Goal: show one task being generated and proven live, then show
that the system rejects bad tasks.

## Before you go on stage

```bash
python scripts/setup_demo_repo.py shopcart            # prints commit b6ba8b0...
python -m veriloom serve --port 8000                    # optional dashboard, second window
```
- Have `examples/sample_packages/shopcart/EVIDENCE.md` open in a browser tab.
- Clear the demo output folder: `rm -rf demo_out`.
- **Pick the run mode.** Live (API key, 1–4 minutes, can hit quota or Wi-Fi problems) or replay (no network, about 20 seconds).
  Replay still runs every gate live; say so on stage. If in doubt, use replay.

## 1. The problem (45 s)

> "Generating a coding task is easy. Knowing it is solvable, that its tests catch a wrong solution, and that it
> doesn't break the codebase is the hard part. VeriLoom doesn't trust the model: it runs everything."

## 2. The repository (30 s)

Show `test_repos/shopcart`: a catalogue with stock, cart pricing with tax, orders with a lifecycle, 16 tests.

```bash
python -m veriloom inspect test_repos/shopcart
python -m veriloom opportunities test_repos/shopcart
```
Point out: pinned commit, and candidates spread across 7 behaviour families and different files.

## 3. Generate and prove a task, live (2–3 min)

Replay (safe):
```bash
python -m veriloom run-pipeline test_repos/shopcart --candidate-index 1 \
    --replay examples/recordings/shopcart_lifecycle.jsonl --output-dir demo_out --harbor
```
Live (needs a working key):
```bash
python -m veriloom run-pipeline test_repos/shopcart --candidate-index 1 --output-dir demo_out --harbor
```

Narrate the gate lines as they appear:
- `fail_before PASS`: the tests fail on today's code, so they really test the new feature.
- `pass_after PASS`: the reference implementation makes them pass, so the task is solvable.
- `regression`: the 16 existing tests still pass. **If an attempt shows `regression FAIL`, stop and point at
  it:** "the model broke existing code, VeriLoom caught it and sent the failure back; watch the next attempt."
- `mutation PASS 4/4`: we broke the reference on purpose four ways, and the tests caught every one.
- `clarity PASS`: every value the hidden tests check is written in the task, so it is fair to the solver.

## 4. Show the package (1 min)

```bash
python scripts/replay_package.py --package demo_out/pkg_<task_id>
```
Open `task/specification.json` (requirements with worked examples), `tests/feature/`, and
`validation/authoring-log.json` (every attempt and gate result).

## 5. Independent check in Harbor format (45 s)

```bash
python -m veriloom export-harbor demo_out/pkg_<task_id> --repo test_repos/shopcart
```
> "Oracle reward 1: the reference solves it. No-op reward 0: doing nothing fails. That is the property a
> benchmark task must have."

## 6. Honesty slide (45 s)

Open `EVIDENCE.md`:
> "7 candidates, 3 shipped, 4 rejected. We show the rejections because they prove the gates work. These numbers
> come from the smallest free-tier model; a stronger model raises the pass rate, the gates stay the same."

Mention the limitations: Python only, one file per task.

## If something goes wrong

| Problem | Do this |
|---|---|
| API error, 429 or slow model | Switch to the `--replay` command. |
| A live candidate gets rejected | Say "this is the system working", show the failed gate, then run replay. |
| Laptop or terminal fails | Play the backup screen recording; walk through `EVIDENCE.md`. |
