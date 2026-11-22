# VeriLoom: a coding task factory that proves its tasks

**Innodata Frontier AI Hackathon 2026, Track 1: Coding Task Factory**
Repository: https://github.com/kushprajapati2202/VeriLoom (branch `main`)

## The problem we solve

Asking an LLM for "a feature task with tests" is easy. Knowing that the task is solvable, that the tests
actually detect a missing or wrong implementation, and that the change leaves existing behaviour intact is the
hard part. VeriLoom does not trust the model's claim: every task is executed against the real repository at a
pinned commit, and it is only shipped if it passes five independent checks.

## How it works

1. **Inspect the repository** at a pinned commit: stack, public symbols, existing tests.
2. **Pick a candidate**: one of 7 behaviour families (business rules, state transitions, validation, error
   handling, data lifecycle, API behaviour, permissions), rotated across files.
3. **Specify**: the LLM writes requirements for that file's real domain, with exact rules and worked examples,
   and is told which tasks already exist so it produces something different.
4. **Author**: the LLM sees the real file and every existing test that uses it, and returns the reference
   implementation, hidden feature tests, and deliberately faulty variants (mutants) of its own code.
5. **Validate in a throwaway copy of the repo** (`git archive` of the pinned commit):

   | Gate | Passes only if |
   |---|---|
   | fail_before | every requirement has a test that fails on the original code |
   | pass_after | every feature test passes with the reference implementation |
   | regression | every existing test that passed before still passes |
   | mutation | at least 3 valid mutants, at least 80% of them caught by the tests |
   | clarity | every value a test asserts is stated in the task or follows directly from its inputs |

6. **Repair**: failed gates, with test output and the exact code of any surviving mutant, go back to the model
   (up to 3 attempts). If every attempt breaks existing tests, the *specification* is at fault, so it is
   rewritten with those failures as feedback (one extra round). A candidate that never passes is
   **rejected and not shipped**.
7. **Package**: specification, patch, tests, gate logs, variation report and SHA-256 checksums, plus an export
   in the Harbor task format, replayed locally (oracle must score 1, the untouched repo must score 0).

## Evidence

Full table: [`examples/sample_packages/shopcart/EVIDENCE.md`](examples/sample_packages/shopcart/EVIDENCE.md).

Target: `shopcart`, a small e-commerce codebase (catalogue with stock, cart pricing with tax, order lifecycle,
16 existing tests), committed under `examples/target_repos/` and materialised with a reproducible commit SHA.

| Task | Family | File | Tests | Attempts | Mutants caught | Harbor oracle / no-op |
|---|---|---|---|---|---|---|
| Cart-level promotional discounting | business rules | `cart.py` | 7 | 2 | 3/3 | 1 / 0 |
| Product lifecycle status tracking | state transitions | `catalog.py` | 7 | 3 | 4/4 | 1 / 0 |
| Currency validation and fallback | error handling | `money.py` | 6 | 2 | 4/4 | 1 / 0 |

- **7 candidates generated, 3 shipped, 4 rejected** (data validation, data lifecycle, API behaviour,
  permissions). The rejections are part of the evidence: they show the gates filter, rather than rubber-stamp.
- The three shipped tasks differ in behaviour, not wording. The lifecycle task changes how the *existing*
  `take()` and `restock()` methods behave, so the 16 original tests constrain the solution.
- Each package's `validation/authoring-log.json` records every attempt and every gate result.

## What the gates caught during development

These are real failures from our runs, each blocked automatically:
- A reference that broke `tests/test_catalog.py` and `tests/test_orders.py` (regression gate).
- Tests that did not notice `clear()` forgetting to reset a discount (mutation gate).
- Tests that missed an off-by-one `>=` vs `>` expiry check (mutation gate).
- Hidden tests asserting totals the task text never stated (clarity gate).

## Reproduce it

```bash
pip install -r requirements.txt
python scripts/setup_demo_repo.py shopcart                    # same commit SHA on every machine

# Verify a shipped package (no key needed)
python scripts/replay_package.py --package examples/sample_packages/shopcart/pkg_task_eaf600

# Regenerate a task without an API key: recorded model text, every gate runs live
python -m veriloom run-pipeline test_repos/shopcart --candidate-index 1 \
    --replay examples/recordings/shopcart_lifecycle.jsonl --output-dir /tmp/veriloom_out

# Full live run (needs GEMINI_API_KEY, ANTHROPIC_API_KEY or OPENAI_API_KEY in .env)
python scripts/generate_evidence.py test_repos/shopcart --candidates 0-6 --out /tmp/evidence --harbor

pytest                                                        # 51 tests, offline
```

## Engineering decisions

- **Execution over judgement.** No LLM grades another LLM. Everything that decides whether a task ships is
  a test run.
- **Mutants from the reference author.** The model knows where its own logic is fragile; the mutation gate
  turns that knowledge into a test-strength check.
- **Clarity as a gate.** A hidden test that asserts an unstated value makes a task unfair to the solver, so it
  is rejected, not just logged.
- **Replayable runs.** Model responses can be recorded and replayed, so results are reproducible without a
  key while all validation still executes.
- **Safe by construction.** Validation never touches the working tree; API keys travel in headers and local
  paths are scrubbed from packaged logs.

## Limitations

- Python repositories only, one target file per task.
- The clarity gate checks numeric `==` assertions; string and structural expectations are not yet checked.
- Mutants come from the same model as the reference, so shared blind spots are possible; the fail-before gate
  and the 80% threshold reduce this risk but do not remove it.
- Our evidence was produced on a free-tier key with `gemini-3.1-flash-lite`, the smallest available model.
  A stronger model is expected to raise the pass rate; we report the numbers we measured.
- Shown on one target repository so far.
