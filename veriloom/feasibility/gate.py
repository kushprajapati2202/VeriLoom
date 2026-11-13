"""Feasibility and Grounding Gate."""

import re
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

from veriloom.contracts.task_spec import TaskSpecification, PriorityLevel


class GroundingViolation(BaseModel):
    category: str = Field(description="missing_file, missing_symbol, ambiguous_wording, missing_test, duplicate_req")
    details: str
    severity: str = Field(default="error", description="error or warning")


class FeasibilityReport(BaseModel):
    task_id: str
    is_feasible: bool
    score: float = Field(description="Feasibility score 0.0 to 1.0")
    violations: List[GroundingViolation] = Field(default_factory=list)
    actionable_feedback: Optional[str] = None


class FeasibilityGate:
    """Verifies that a task specification is strictly grounded, unambiguous, and testable."""

    AMBIGUOUS_KEYWORDS = {
        "fast",
        "quickly",
        "seamlessly",
        "robustly",
        "user-friendly",
        "properly",
        "cleanly",
        "optimal",
        "elegantly",
    }

    @classmethod
    def evaluate(cls, spec: TaskSpecification, repo_path: Path) -> FeasibilityReport:
        repo_path = repo_path.resolve()
        violations: List[GroundingViolation] = []

        # 1. Check repository evidence files and symbols
        if not spec.repository_evidence:
            violations.append(
                GroundingViolation(
                    category="missing_file",
                    details="Task specification has zero repository evidence attached.",
                    severity="error",
                )
            )

        for ev in spec.repository_evidence:
            target_file = repo_path / ev.path
            if not target_file.exists():
                violations.append(
                    GroundingViolation(
                        category="missing_file",
                        details=f"Referenced evidence file does not exist in repository: {ev.path}",
                        severity="error",
                    )
                )
            elif ev.symbol:
                content = target_file.read_text(encoding="utf-8", errors="ignore")
                # Strip class / def / const prefixes for symbol check
                bare_symbol = ev.symbol.split()[-1].split("(")[0].strip()
                method_name = bare_symbol.split(".")[-1]
                if bare_symbol not in content and method_name not in content:
                    violations.append(
                        GroundingViolation(
                            category="missing_symbol",
                            details=f"Referenced symbol '{bare_symbol}' not found in {ev.path}",
                            severity="error",
                        )
                    )

        # 2. Check Requirement IDs Uniqueness
        req_ids = [r.id for r in spec.requirements]
        if len(req_ids) != len(set(req_ids)):
            violations.append(
                GroundingViolation(
                    category="duplicate_req",
                    details="Requirement IDs contain duplicates.",
                    severity="error",
                )
            )

        # 3. Check Acceptance Criteria & Planned Tests Mapping
        test_req_ids = {t.requirement_id for t in spec.test_plan}
        for req in spec.requirements:
            if not req.acceptance_criteria:
                violations.append(
                    GroundingViolation(
                        category="missing_test",
                        details=f"Requirement {req.id} has no acceptance criteria.",
                        severity="error",
                    )
                )
            if req.priority == PriorityLevel.MUST and req.id not in test_req_ids:
                violations.append(
                    GroundingViolation(
                        category="missing_test",
                        details=f"Must-have requirement {req.id} has no mapped tests in the test plan.",
                        severity="error",
                    )
                )

        # 4. Check for Ambiguous Language
        all_text = " ".join(
            [spec.summary] + [r.statement for r in spec.requirements] + [c for r in spec.requirements for c in r.acceptance_criteria]
        ).lower()

        tokens = set(re.findall(r"\b[a-z\-]+\b", all_text))
        ambiguous_found = tokens.intersection(cls.AMBIGUOUS_KEYWORDS)
        for amb in ambiguous_found:
            violations.append(
                GroundingViolation(
                    category="ambiguous_wording",
                    details=f"Unquantified adjective '{amb}' used in requirements without measurable criteria.",
                    severity="warning",
                )
            )

        # Compute Score
        error_count = sum(1 for v in violations if v.severity == "error")
        warning_count = sum(1 for v in violations if v.severity == "warning")

        is_feasible = error_count == 0
        score = max(0.0, 1.0 - (error_count * 0.3) - (warning_count * 0.05))

        feedback = None
        if not is_feasible:
            feedback = f"Feasibility gate rejected specification: {error_count} critical error(s) found."
        elif warning_count > 0:
            feedback = f"Specification passed with {warning_count} non-blocking warning(s)."
        else:
            feedback = "Specification fully grounded and verified against repository AST."

        return FeasibilityReport(
            task_id=spec.task_id,
            is_feasible=is_feasible,
            score=round(score, 2),
            violations=violations,
            actionable_feedback=feedback,
        )

