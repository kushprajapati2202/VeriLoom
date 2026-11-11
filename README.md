# VeriLoom

> **Repository-Aware Coding Task Factory & Benchmark Validation Platform**

VeriLoom is an automated, repository-grounded pipeline that converts real software codebases into reproducible, independently verified feature-development challenges for evaluating frontier AI coding models.

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
python -m veriloom.cli.main inspect
```

### 2. Discover Grounded Feature Opportunities
```bash
python -m veriloom.cli.main opportunities
```

### 3. Run End-to-End Pipeline & Generate Validated Package
```bash
python -m veriloom.cli.main run-pipeline --candidate-index 0
```

### 4. Independent Package Replay & Verification
```bash
python scripts/replay_package.py --package ./exports/pkg_task_18366f
```

---

## REST API Server

Launch the FastAPI control centre backend:
```bash
uvicorn veriloom.api.server:app --reload --port 8000
```
Interactive API documentation available at `http://localhost:8000/docs`.

---

## Quality Gates Enforced

- **Grounding Gate**: Rejects any candidate task lacking verified AST symbol evidence.
- **Feasibility Gate**: Enforces unambiguous acceptance criteria and maps every requirement to tests.
- **Regression Protection**: Ensures 0 newly introduced failures on baseline test suites.
- **Controlled Fault Injection**: Tests reference solutions against synthesized mutants (operator inversions, boundary shifts, condition omissions) to prove tests catch defects.
- **Behavioural Variation**: Computes 4-factor distance $D(T_A, T_B)$ to reject cosmetic paraphrases.
- **Package Integrity**: Pinned commit metadata, patches, tests, and validation logs with SHA-256 verification.

---

## License
MIT License.

