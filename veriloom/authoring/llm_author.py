"""LLM-authored reference implementation, feature tests and mutants with a validate-and-repair loop.

The model sees the real target file and the task specification and returns:
  - the complete new content of the target file (reference implementation)
  - a hidden pytest file and which tests cover which requirement
  - the exact behaviour rules the tests rely on (added to the task so it is solvable)
  - faulty variants of its own implementation (mutants) as find/replace edits

Every attempt is checked by SandboxValidator (gates G1-G5). Failures are sent
back with the test output and the model repairs its previous attempt.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from veriloom.contracts.task_spec import TaskSpecification, as_str_list
from veriloom.contracts.validation import (
    AcceptanceCoverage,
    CheckOutcome,
    CheckStatus,
    MutantStatus,
    MutationCheck,
    RegressionSummary,
    ValidationReport,
)
from veriloom.llm.provider import LLMProvider
from veriloom.reference_solution.agent import ReferenceSolutionResult
from veriloom.reference_solution.patch_manager import PatchManager
from veriloom.test_generation.feature_tests import GeneratedTestSuite
from veriloom.validation.sandbox import (
    GateReport,
    GateResult,
    Mutant,
    Sandbox,
    SandboxValidator,
    discover_test_targets,
)

log = logging.getLogger("veriloom")

MAX_TARGET_CHARS = 60_000

SYSTEM_PROMPT = """You are an expert software engineer building benchmark tasks for evaluating AI coding agents.
For a feature specification and the real source of a file in an existing repository, you produce:
a reference implementation, hidden tests that verify it, the exact behaviour rules those tests rely on,
and deliberately faulty variants of your implementation that the tests must catch.
Your output is executed and validated automatically, so follow the output format exactly."""

AUTHOR_PROMPT = """# Feature specification
{spec_text}

# Repository
Language: {language}. Framework: {framework}.
The repository root is the working directory and the Python import root.
Target file: `{target_file}` (import it as `{module}`).

## Current content of `{target_file}`
```python
{source}
```

## Existing tests that use this module and MUST keep passing ({example_test_path})
Do not change the signature, defaults or behaviour of anything these tests call.
```python
{example_test}
```

# What to produce
1. NEW_FILE: the COMPLETE new content of `{target_file}` implementing every requirement.
   Keep all existing code and behaviour intact; add to it. Standard library only, no network.
2. TEST_FILE: a pytest module, run from the repository root but stored OUTSIDE the repository.
   - Import the feature from `{module}` inside each test function (so a missing name fails that test, not collection).
   - Test observable behaviour only (return values, raised exception types, state), never private details.
   - Every requirement needs at least one test that fails on the CURRENT code and passes on yours.
   - Cover the edge cases. Deterministic, fast, no network, no files outside a tmp_path fixture.
3. META (JSON):
   - "test_file_name": "test_<short_feature_name>.py"
   - "requirement_tests": {{"REQ-001": ["test_name", ...], ...}} covering every requirement id
   - "behaviour_details": precise rules a solver needs to make your tests pass that the specification
     leaves open: exact function/class names and signatures, defaults, constants, rounding, error types,
     ordering. Every literal value your tests assert must appear in these sentences, so include worked
     examples with exact numbers (e.g. "a 50.0 order with SAVE10 costs 45.0"). Do not paste code.
   - "explanation": one paragraph on the implementation.
   - "mutants": at least 4 faulty variants of YOUR new file, each
     {{"id": "MUT-001", "description": "...", "fault_type": "boundary_shift|operator_inversion|condition_omission|value_corruption|missing_check",
       "find": "exact snippet copied from NEW_FILE that occurs exactly once", "replace": "faulty version"}}.
     Make them realistic mistakes an agent could make; your tests must fail on each.

# Output format (exactly these four markers, each on its own line, nothing before the first)
=== META ===
{{...json...}}
=== NEW_FILE ===
...complete file...
=== TEST_FILE ===
...complete pytest module...
=== END ===
"""

REPAIR_PROMPT = """Your previous attempt failed automatic validation. Fix it and return a complete new answer
in the same four-section format (META, NEW_FILE, TEST_FILE, END).

## Failed checks
{failures}

## Your previous attempt
=== META ===
{meta}
=== NEW_FILE ===
{new_file}
=== TEST_FILE ===
{test_file}
=== END ===

What the checks mean:
- fail_before: each requirement needs a test that FAILS on the original file.
- pass_after: all tests must pass with NEW_FILE.
- regression: NEW_FILE must not break existing tests.
- mutation: tests must fail on each mutant; strengthen tests or fix invalid `find` snippets.
- clarity: every literal value a test asserts must appear in behaviour_details (or the spec).
"""


class AuthoringError(RuntimeError):
    pass


class Attempt(BaseModel):
    number: int
    gates: List[Dict] = Field(default_factory=list)
    passed: bool = False
    error: Optional[str] = None


class AuthoredTask(BaseModel):
    spec: TaskSpecification
    reference_solution: ReferenceSolutionResult
    test_suite: GeneratedTestSuite
    validation_report: ValidationReport
    gate_report: GateReport
    attempts: List[Attempt]


class _Draft(BaseModel):
    meta: Dict
    new_file: str
    test_file: str


def _strip_fence(text: str) -> str:
    text = text.strip("\n")
    m = re.match(r"^\s*```[\w-]*\n(.*?)\n?```\s*$", text, re.DOTALL)
    return (m.group(1) if m else text).rstrip() + "\n"


def parse_draft(raw: str) -> _Draft:
    sections = re.split(r"^===\s*(META|NEW_FILE|TEST_FILE|END)\s*===\s*$", raw, flags=re.MULTILINE)
    found: Dict[str, str] = {}
    for i in range(1, len(sections) - 1, 2):
        found[sections[i]] = sections[i + 1]
    for key in ("META", "NEW_FILE", "TEST_FILE"):
        if key not in found or not found[key].strip():
            raise AuthoringError(f"Response is missing the === {key} === section")
    meta_text = _strip_fence(found["META"])
    try:
        meta = json.loads(meta_text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", meta_text, re.DOTALL)
        if not m:
            raise AuthoringError("META section is not valid JSON")
        meta = json.loads(m.group(0))
    return _Draft(meta=meta, new_file=_strip_fence(found["NEW_FILE"]), test_file=_strip_fence(found["TEST_FILE"]))


def spec_text(spec: TaskSpecification, extra_details: Optional[List[str]] = None) -> str:
    out = [f"Title: {spec.title}", f"Summary: {spec.summary}", "", "Requirements:"]
    for r in spec.requirements:
        out.append(f"- {r.id} ({r.priority.value}): {r.statement}")
        out += [f"    - {c}" for c in r.acceptance_criteria]
    for label, items in (
        ("Behaviour details", list(spec.behaviour_details) + list(extra_details or [])),
        ("Edge cases", spec.edge_cases),
        ("Constraints", spec.constraints),
        ("Assumptions", spec.assumptions),
        ("Out of scope", spec.out_of_scope),
    ):
        if items:
            out += ["", f"{label}:"] + [f"- {i}" for i in items]
    return "\n".join(out)


def _test_names(test_code: str) -> List[str]:
    try:
        tree = ast.parse(test_code)
    except SyntaxError:
        return []
    return [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test")]


MAX_TEST_CONTEXT_CHARS = 24_000


def _relevant_tests(sb: Sandbox, test_files: List[str], module: str):
    """Existing tests that exercise the target module, so the model sees what it must not break."""
    short = module.rsplit(".", 1)[-1]
    scored = []
    for f in test_files:
        src = sb.read(f)
        hits = src.count(module) * 3 + len(re.findall(rf"\b{re.escape(short)}\b", src))
        scored.append((hits, f, src))
    scored.sort(key=lambda t: (-t[0], t[1]))
    chosen = [t for t in scored if t[0] > 0] or scored[:1]
    parts, names, used = [], [], 0
    for _, f, src in chosen:
        room = MAX_TEST_CONTEXT_CHARS - used
        if room <= 0:
            break
        src = src[:room]
        parts.append(f"# ---- {f} ----\n{src}")
        names.append(f)
        used += len(src)
    if not parts:
        return "(none)", "# no tests yet"
    return ", ".join(names), "\n\n".join(parts)


class LLMTaskAuthor:
    def __init__(self, provider: LLMProvider, max_attempts: int = 3):
        self.provider = provider
        self.max_attempts = max_attempts

    def author(
        self,
        spec: TaskSpecification,
        repo_path: Path,
        commit: str,
        language: str = "python",
        framework: Optional[str] = None,
    ) -> AuthoredTask:
        if not spec.repository_evidence:
            raise AuthoringError("Specification has no target file (repository_evidence is empty)")
        target = spec.repository_evidence[0].path.replace("\\", "/")
        if not target.endswith(".py"):
            raise AuthoringError(f"Only Python targets are supported, got {target}")
        module = target[:-3].replace("/", ".")

        attempts: List[Attempt] = []
        with Sandbox(repo_path, commit) as sb:
            source = sb.read(target)
            if len(source) > MAX_TARGET_CHARS:
                raise AuthoringError(f"{target} is {len(source)} chars; too large to rewrite reliably")
            examples = discover_test_targets(sb.app)
            example_path, example_src = _relevant_tests(sb, examples, module)

            prompt = AUTHOR_PROMPT.format(
                spec_text=spec_text(spec),
                language=language,
                framework=framework or "none",
                target_file=target,
                module=module,
                source=source,
                example_test_path=example_path,
                example_test=example_src,
            )

            draft: Optional[_Draft] = None
            report: Optional[GateReport] = None
            for n in range(1, self.max_attempts + 1):
                attempt = Attempt(number=n)
                attempts.append(attempt)
                log.info("[author] attempt %d/%d: asking model for implementation, tests and mutants",
                         n, self.max_attempts)
                try:
                    raw = self.provider.generate(prompt, SYSTEM_PROMPT)
                    draft = parse_draft(raw)
                except Exception as e:  # malformed output or provider error: ask again
                    attempt.error = f"{type(e).__name__}: {e}"
                    log.info("[author] attempt %d unusable: %s", n, attempt.error[:200])
                    if "FORMAT REMINDER" not in prompt:
                        prompt += ("\n\nFORMAT REMINDER: a previous reply could not be parsed "
                                   f"({attempt.error}). Use exactly the four === markers.")
                    continue

                details = as_str_list(draft.meta.get("behaviour_details"))
                req_tests = {k: list(v) for k, v in (draft.meta.get("requirement_tests") or {}).items()}
                unmapped = [r.id for r in spec.requirements if not req_tests.get(r.id)]
                mutants = [Mutant(**m) for m in draft.meta.get("mutants", []) if m.get("find") is not None]
                test_name = Path(draft.meta.get("test_file_name") or "test_feature.py").name
                if not test_name.startswith("test_") or not test_name.endswith(".py"):
                    test_name = "test_feature.py"

                report = SandboxValidator.validate(
                    sb,
                    target_file=target,
                    new_content=draft.new_file,
                    test_file_name=test_name,
                    test_code=draft.test_file,
                    requirement_tests=req_tests,
                    mutants=mutants,
                    task_text=spec_text(spec, details) + "\n" + interface_text(target, source, draft.new_file),
                )
                if unmapped:
                    report.gates.insert(0, _gate("coverage", False,
                                                 "requirement_tests has no tests for: " + ", ".join(unmapped)))
                attempt.gates = [g.model_dump() for g in report.gates]
                attempt.passed = report.passed
                for g in report.gates:
                    log.info("[gate] %-12s %s  %s", g.name, "PASS" if g.passed else "FAIL", g.detail[:140])
                    if not g.passed and g.log_tail:
                        log.debug("[gate] %s output:\n%s", g.name, g.log_tail)
                if report.passed:
                    return self._result(spec, target, source, draft, test_name, req_tests, details, report,
                                        attempts, commit)

                failures = "\n\n".join(
                    f"### {g.name}: {g.detail}" + (f"\n```\n{g.log_tail}\n```" if g.log_tail else "")
                    for g in report.failures()
                )
                prompt = REPAIR_PROMPT.format(
                    failures=failures,
                    meta=json.dumps(draft.meta, indent=2),
                    new_file=draft.new_file,
                    test_file=draft.test_file,
                )
                # Keep the original context available to the model on repair.
                prompt = AUTHOR_PROMPT.format(
                    spec_text=spec_text(spec), language=language, framework=framework or "none",
                    target_file=target, module=module, source=source,
                    example_test_path=example_path, example_test=example_src,
                ) + "\n\n" + prompt

        summary = "; ".join(
            f"attempt {a.number}: " + (a.error or ", ".join(f"{g['name']} failed" for g in a.gates if not g["passed"]))
            for a in attempts
        )
        err = AuthoringError(f"No candidate passed validation after {len(attempts)} attempt(s): {summary}")
        err.attempts = attempts  # type: ignore[attr-defined]
        raise err

    # ------------------------------------------------------------------ result assembly

    @staticmethod
    def _result(spec, target, source, draft, test_name, req_tests, details, report, attempts, commit) -> AuthoredTask:
        spec = spec.model_copy(update={
            "behaviour_details": list(spec.behaviour_details) + details,
            "known_limitations": [l for l in spec.known_limitations]
            + ["Reference implementation, tests and mutants authored by LLM and validated in a sandbox."],
        })
        patch = PatchManager.generate_diff({target: source}, {target: draft.new_file})
        ref = ReferenceSolutionResult(
            task_id=spec.task_id,
            patch_diff=patch,
            changed_files=[target],
            requirement_mapping={k: v for k, v in req_tests.items()},
            explanation=str(draft.meta.get("explanation", "")),
        )
        coverage = [
            AcceptanceCoverage(
                requirement_id=r.id,
                criteria_total=len(r.acceptance_criteria),
                criteria_covered=len(r.acceptance_criteria) if req_tests.get(r.id) else 0,
                test_names=req_tests.get(r.id, []),
                status="fully_covered" if req_tests.get(r.id) else "uncovered",
            )
            for r in spec.requirements
        ]
        suite = GeneratedTestSuite(
            task_id=spec.task_id,
            test_file_path=f"tests/feature/{test_name}",
            test_code=draft.test_file,
            coverage_mapping=coverage,
        )
        return AuthoredTask(
            spec=spec,
            reference_solution=ref,
            test_suite=suite,
            validation_report=to_validation_report(spec.task_id, commit, report, coverage, target, test_name),
            gate_report=report,
            attempts=attempts,
        )


def _gate(name: str, passed: bool, detail: str) -> GateResult:
    return GateResult(name=name, passed=passed, detail=detail)


def interface_text(target: str, old: str, new: str) -> str:
    """Signatures of new public names, as the Harbor instruction will show them."""
    from veriloom.packaging.harbor_exporter import HarborExporter

    patch = PatchManager.generate_diff({target: old}, {target: new})
    return "\n".join(sig for _, sigs in HarborExporter._interface_from_patch(patch) for sig in sigs)


def to_validation_report(task_id, commit, report: GateReport, coverage, target, test_name) -> ValidationReport:
    by_name = {g.name: g for g in report.gates}

    def outcome(gate: str, check_name: str, command: str) -> CheckOutcome:
        g = by_name.get(gate)
        return CheckOutcome(
            name=check_name,
            status=CheckStatus.PASSED if g and g.passed else CheckStatus.FAILED,
            command=command,
            exit_code=0 if g and g.passed else 1,
            duration_ms=0,
            log_path=f"logs/{check_name}.log",
        )

    reg_cmd = "pytest " + " ".join(report.regression_targets) + " -q" if report.regression_targets else "pytest -q (no baseline tests)"
    checks = [
        outcome("fail_before", "feature_tests_fail_on_original", f"pytest {test_name} -q  # on original code"),
        outcome("pass_after", "feature_tests", f"pytest {test_name} -q  # with reference"),
        outcome("regression", "regression_tests", reg_cmd),
        outcome("clarity", "spec_clarity", "assert every tested literal is stated in the task"),
    ]
    mutation_checks = [
        MutationCheck(
            mutant_id=m.id,
            description=m.description,
            fault_type=m.fault_type,
            target_file=target,
            status=MutantStatus.KILLED if m.status == "KILLED" else MutantStatus.SURVIVED,
            explanation=m.detail or None,
        )
        for m in report.mutants
        if m.status != "INVALID"
    ]
    killed = sum(1 for m in mutation_checks if m.status == MutantStatus.KILLED)
    score = round(100.0 * killed / len(mutation_checks), 1) if mutation_checks else 0.0
    return ValidationReport(
        task_id=task_id,
        repository_commit=commit,
        status=CheckStatus.PASSED if report.passed else CheckStatus.FAILED,
        checks=checks,
        acceptance_coverage=coverage,
        mutation_checks=mutation_checks,
        regression_summary=RegressionSummary(
            baseline_tests_count=len(report.regression_targets) + len(report.baseline_failing_files),
            post_patch_tests_count=len(report.regression_targets),
            passed_count=len(report.regression_targets) if by_name.get("regression", None) and by_name["regression"].passed else 0,
            pre_existing_failures=len(report.baseline_failing_files),
            newly_introduced_failures=0 if by_name.get("regression") and by_name["regression"].passed else 1,
            status="NO_REGRESSION" if by_name.get("regression") and by_name["regression"].passed else "REGRESSION_DETECTED",
        ),
        limitations=[
            f"Mutation score {score}% over {len(mutation_checks)} LLM-authored mutants, executed in an isolated sandbox.",
            "Regression scope: existing test files that passed at the pinned commit"
            + (f"; {len(report.baseline_failing_files)} file(s) already failing at baseline were excluded."
               if report.baseline_failing_files else "."),
        ],
    )
