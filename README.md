# VeriLoom

> **Repository-Aware Coding Task Factory & Benchmark Validation Platform**

VeriLoom is an automated, repository-grounded pipeline that converts real software codebases into reproducible, independently verified feature-development challenges for evaluating frontier AI coding models.

**Evidence at a glance** ([full table](examples/sample_packages/shopcart/EVIDENCE.md)): on the `shopcart` demo repo, 7 candidates across 7 feature families were authored by an LLM and run through five sandbox gates. **3 passed and were packaged; 4 were rejected.** All 3 shipped tasks:
- fail on the original code, pass with the reference, and keep all 16 existing tests green;
- kill every valid mutant of their reference implementation;
- replay independently in Harbor format with **oracle reward 1 / no-op reward 0**;
- target different files and behaviours: cart discount rules, product lifecycle states that change existing stock operations, currency validation with fallbacks.

---

## Key Capabilities

- **Repository Intelligence**: Automatically analyzes codebases, detects stack dependencies, parses AST symbols, and discovers candidate extension points.
- **Specification Generation**: Synthesizes structured, testable functional requirements with observable acceptance criteria and boundary edge cases.
- **Feasibility & Grounding Gates**: Validates that all candidate tasks are strictly grounded in existing codebase symbols before code generation.
- **Reference Solution Workflow**: Builds and checks minimal, repository-compliant reference patches against pinned starting commits.
- **Black-Box Feature Testing**: Creates deterministic unit/integration test suites derived directly from acceptance criteria.
- **Regression Protection**: Enforces baseline test integrity to ensure zero newly introduced regressions.
- **Adversarial Test Strength (Fault Injection)**: Automatically mutates reference solutions (operator inversions, boundary shifts, condition omissions) to verify that generated tests reliably kill faulty implementations.
- **Behavioural Variation Engine**: Enforces multi-dimensional diversity (business rules, state transitions, constraints) using Jaccard tag and AST distance metrics.
- **Self-Contained Task Packages**: Exports version-pinned packages containing specifications, patches, test suites, SHA-256 checksums, and verification logs.

---

## Architecture Overview

```mermaid
flowchart TD
    Repo[Source Repository] --> Ingest[Repository Intelligence]
    Ingest --> Opportunities[Feature Opportunity Discovery]
    Opportunities --> SpecGen[Task Specification Generator]
    SpecGen --> Gate[Feasibility & Grounding Gate]
    Gate --> RefSol[Reference Implementation]
    RefSol --> TestGen[Feature & Regression Tests]
    TestGen --> ValRunner[Validation Runner]
    ValRunner --> FaultInj[Controlled Fault Injection]
    FaultInj --> Variation[Variation & Novelty Engine]
    Variation --> Packager[Task Package Builder]
```

---

## Quickstart

### Prerequisites
- Python 3.10+
- Git 2.30+

### Installation
```bash
git clone https://github.com/kushprajapati2202/VeriLoom.git
cd VeriLoom
pip install -r requirements.txt
```

### Running Tests
```bash
pytest
```

---

## CLI Usage

VeriLoom provides a comprehensive CLI for running individual stages or the entire end-to-end factory:

### 1. Inspect Repository & Pin Commit
```bash
python -m veriloom inspect .
```

### 2. Discover Grounded Feature Opportunities
```bash
python -m veriloom opportunities .
```

### 3. Run End-to-End Pipeline & Generate Validated Package
```bash
python -m veriloom run-pipeline . --candidate-index 0
```

### 4. Independent Package Replay & Cryptographic Verification
```bash
# Replay the pre-validated sample package (immediate out-of-the-box verification):
python scripts/replay_package.py --package ./examples/sample_packages/pkg_task_48e3bf

# Or verify any newly generated package:
python -m veriloom verify-package --package-dir ./exports/<pkg_dir>
```

### 5. AI Coding Model Benchmarking & Evaluation Harness
Score candidate AI coding models or agent patches against verified task packages with automated feature and regression tests:
```bash
# Evaluate a passing candidate solution patch:
python -m veriloom benchmark --package ./examples/sample_packages/pkg_task_48e3bf --solution ./examples/sample_packages/pkg_task_48e3bf/reference/implementation.patch --model "gemini-2.5-pro"

# Evaluate a faulty solution (demonstrating failure classification):
python -m veriloom benchmark --package ./examples/sample_packages/pkg_task_48e3bf --solution "def broken(): pass" --model "flawed-agent"
```

### 6. Interactive Engineering Dashboard & REST API
Launch the unified FastAPI control center and visual dashboard:
```bash
python -m veriloom serve --port 8000
```
Open [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard) in your browser for the real-time pipeline visualizer and task catalog. OpenAPI specifications are available at `http://127.0.0.1:8000/docs`.

### 7. LLM-Authored Tasks with Sandbox Validation
With an LLM key configured (see `.env.example`), `run-pipeline` has the model write the reference implementation, the hidden feature tests, the exact behaviour rules and faulty variants (mutants) for the **real target file**. Each attempt runs in a throwaway copy of the repo at the pinned commit and must pass five gates, or the failures go back to the model for repair (up to 3 attempts):

| Gate | Checks |
|---|---|
| `fail_before` | every requirement has a test that fails on the original code |
| `pass_after` | all feature tests pass with the reference implementation |
| `regression` | existing tests that passed at baseline still pass |
| `mutation` | ≥3 valid mutants and ≥80% of them killed by the tests |
| `clarity` | every value a test asserts is stated in the task or follows in one arithmetic step from stated numbers and test inputs |

The attempt history and gate results are saved to `validation/authoring-log.json` in the package. Candidates that never pass every gate are **rejected, not shipped**.

Without a key the pipeline uses **offline templates**: three fixed feature families appended to the target file. They exist so the pipeline, tests and dashboard work with no credentials; they are not repository-specific and are not the evidence for task quality.

### Reproducing the evidence
```bash
python scripts/setup_demo_repo.py shopcart        # demo target repo with a fixed, reproducible commit SHA
python scripts/generate_evidence.py test_repos/shopcart --candidates 0-6 \
    --out examples/sample_packages/shopcart --harbor
```
Results, including rejected candidates, are in [examples/sample_packages/shopcart/EVIDENCE.md](examples/sample_packages/shopcart/EVIDENCE.md).

### 8. Export to the Harbor Task Format
Convert a validated package into a [Harbor](https://www.harborframework.com/) task:
```bash
python -m veriloom export-harbor ./examples/sample_packages/pkg_task_48e3bf --repo .
# or generate + export in one go:
python -m veriloom run-pipeline <repo> --harbor
```
Produces `instruction.md`, `task.toml`, `environment/` (Dockerfile + repo snapshot at the pinned commit), `solution/solve.sh` (applies the reference patch) and `tests/test.sh` (hidden feature tests + tamper-proof regression suite, writing `/logs/verifier/reward.txt`). By default it replays the task locally without Docker and requires **oracle reward = 1** and **no-op reward = 0**. It also warns when hidden tests assert values that the instruction never states. With Docker installed, run the real thing:
```bash
harbor run -p <harbor_tasks/task_id> -a oracle
```

---

## Cloud Deployment

VeriLoom is pre-configured for 1-click cloud deployment:

### 1. Deploy on Vercel
1. Import `kushprajapati2202/VeriLoom` on [vercel.com](https://vercel.com).
2. Vercel automatically detects `vercel.json` and `api/index.py`.
3. Click **Deploy**. Your dashboard will be live at `https://<your-project>.vercel.app/dashboard`.

### 2. Deploy via Docker (Render / Railway / Hugging Face Spaces)
The repository includes a production-ready `Dockerfile` and `Procfile`:
- **Render**: Create New Web Service $\to$ Select `kushprajapati2202/VeriLoom` $\to$ Deploy.
- **Railway**: New Project $\to$ Deploy from GitHub repo $\to$ Generate Domain.
- **Hugging Face Spaces**: Create Space $\to$ Choose Docker $\to$ Connect GitHub.

---

## Quality Gates Enforced

- **Grounding Gate**: Rejects any candidate task lacking verified AST symbol evidence.
- **Feasibility Gate**: Enforces unambiguous acceptance criteria and maps every requirement to tests.
- **Regression Protection**: Ensures 0 newly introduced failures on baseline test suites.
- **Controlled Fault Injection**: Tests reference solutions against synthesized mutants (operator inversions, boundary shifts, condition omissions) to prove tests catch defects.
- **Behavioural Variation**: Computes 4-factor distance $D(T_A, T_B)$ to reject cosmetic paraphrases.
- **Package Integrity**: Pinned commit metadata, patches, tests, and validation logs with SHA-256 verification.

---

## Limitations (stated honestly)

- **Python targets only.** The authoring loop rewrites one `.py` file (up to 60k characters) and runs pytest; other stacks need a new sandbox runner.
- **One target file per task.** Features that need coordinated changes across several modules are out of reach for now.
- **Clarity is a heuristic.** It checks numeric values asserted with `==`; string or structural expectations are not yet checked.
- **Mutants come from the same model as the reference.** They are realistic, but a model can miss its own blind spots; the ≥80% kill threshold and fail-before gate reduce, not remove, this risk.
- **Variation metric is lexical/tag based.** It rejects paraphrases but does not prove semantic difference; feature families and per-file rotation provide the structural variety.
- **Model availability.** Free-tier Gemini keys hit quotas and overload; the provider retries and falls back across models, and runs can still be slow.

---

## License
MIT License.

