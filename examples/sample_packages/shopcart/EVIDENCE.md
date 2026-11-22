# Evidence: LLM-authored, sandbox-validated tasks

3 of 7 candidates passed all gates (fail-before, pass-after, regression, mutation, clarity). Rejected candidates are listed too: the gates are what make the accepted ones trustworthy.

| # | Status | Family | Target | Title | Attempts | Mutants killed | Oracle / no-op | Novelty | Package |
|---|---|---|---|---|---|---|---|---|---|
| 0 | ✅ validated | business_rules | `shopcart/cart.py` | Implement Cart-Level Promotional Discounting | 2 | 3/3 valid mutants killed; invalid: MUT-004: `find` snippet occurs 2 times in the reference (must be exactly 1) | 1 / 0 | 1.00 | [pkg_task_c398ca](pkg_task_c398ca/) |
| 1 | ✅ validated | state_transitions | `shopcart/catalog.py` | Implement Product Lifecycle Status Tracking | 3 | 4/4 valid mutants killed | 1 / 0 | 0.83 | [pkg_task_eaf600](pkg_task_eaf600/) |
| 2 | ❌ rejected | data_validation | `shopcart/orders.py` | attempt 1: pass_after failed, mutation failed; attempt 2: pass_after failed, mutation failed; attempt 3: pass_after failed, mutation failed | 3 | | | | |
| 3 | ✅ validated | error_handling | `shopcart/money.py` | Robust Currency Validation and Fallback Mechanism | 2 | 4/4 valid mutants killed | 1 / 0 | 0.95 | [pkg_task_c669b3](pkg_task_c669b3/) |
| 4 | ❌ rejected | data_lifecycle | `shopcart/cart.py` | attempt 1: mutation failed; attempt 2: mutation failed; attempt 3: mutation failed | 3 | | | | |
| 5 | ❌ rejected | api_behaviour | `shopcart/catalog.py` | attempt 1: mutation failed; attempt 2: mutation failed; attempt 3: mutation failed | 3 | | | | |
| 6 | ❌ rejected | permissions_auth | `shopcart/orders.py` | attempt 1: regression failed, mutation failed; attempt 2: regression failed, mutation failed; attempt 3: regression failed | 3 | | | | |

**How to read this.** *Attempts* counts validate-and-repair rounds (max 3). *Mutants killed* is the mutation gate on the model's own faulty variants. *Oracle / no-op* is an independent Harbor-format replay: applying the reference must score 1, the untouched repo must score 0.

Model used: gemini-3.1-flash-lite. Each package's `validation/authoring-log.json` holds every attempt and gate result.

Reproduce: `python scripts/setup_demo_repo.py shopcart` then `python scripts/generate_evidence.py test_repos/shopcart --candidates 0-6 --out <dir> --harbor`.
