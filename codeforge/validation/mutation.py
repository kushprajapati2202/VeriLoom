"""Controlled fault injection and mutation test runner."""

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple
from pydantic import BaseModel, Field

from codeforge.contracts.task_spec import TaskSpecification, FeatureFamily
from codeforge.contracts.validation import MutationCheck, MutantStatus


class MutantVariant(BaseModel):
    mutant_id: str
    description: str
    fault_type: str
    target_file: str
    mutated_code: str
    expected_failing_test: str


class MutationEngine:
    """Generates and executes controlled faulty variants to verify test strength."""

    @classmethod
    def synthesize_mutants(cls, spec: TaskSpecification, target_rel: str) -> List[MutantVariant]:
        mutants: List[MutantVariant] = []

        if spec.feature_family == FeatureFamily.DATA_VALIDATION:
            # Mutant 1: Boundary Operator Inversion
            mutants.append(
                MutantVariant(
                    mutant_id="MUT-001",
                    description="Inverted boundary operator (allow negative boundary values)",
                    fault_type="operator_inversion",
                    target_file=target_rel,
                    mutated_code=(
                        "\n\nclass ValidationError(Exception):\n"
                        "    def __init__(self, message, code='INVALID_FIELD_VALUE', field=None):\n"
                        "        super().__init__(message); self.code = code; self.field = field\n\n"
                        "def validate_boundary_constraints(value, min_limit=0, max_limit=1000000, field_name='value'):\n"
                        "    if value is not None and value < -100:\n"  # BUG: relaxed lower bound
                        "        raise ValidationError('Below min')\n"
                        "    return True\n"
                    ),
                    expected_failing_test="test_req_001_negative_boundary_rejected",
                )
            )

            # Mutant 2: Missing Error Field
            mutants.append(
                MutantVariant(
                    mutant_id="MUT-002",
                    description="Omitted field identifier in ValidationError",
                    fault_type="value_corruption",
                    target_file=target_rel,
                    mutated_code=(
                        "\n\nclass ValidationError(Exception):\n"
                        "    def __init__(self, message, code='INVALID_FIELD_VALUE', field=None):\n"
                        "        super().__init__(message); self.code = code; self.field = None\n\n"  # BUG: field dropped
                        "def validate_boundary_constraints(value, min_limit=0, max_limit=1000000, field_name='value'):\n"
                        "    if value is None or value < min_limit:\n"
                        "        raise ValidationError('Below min', field=None)\n"
                        "    return True\n"
                    ),
                    expected_failing_test="test_req_002_error_fields_present",
                )
            )

            # Mutant 3: Missing Feature Variant (Bypass all checks)
            mutants.append(
                MutantVariant(
                    mutant_id="MUT-003",
                    description="Missing feature: validation logic completely omitted",
                    fault_type="missing_feature",
                    target_file=target_rel,
                    mutated_code=(
                        "\n\nclass ValidationError(Exception):\n    pass\n\n"
                        "def validate_boundary_constraints(value, min_limit=0, max_limit=1000000, field_name='value'):\n"
                        "    return True\n"  # BUG: always returns True
                    ),
                    expected_failing_test="test_req_001_negative_boundary_rejected",
                )
            )

        elif spec.feature_family == FeatureFamily.BUSINESS_RULES:
            # Mutant 1: Inverted Threshold Check
            mutants.append(
                MutantVariant(
                    mutant_id="MUT-001",
                    description="Inverted threshold operator (strictly greater required)",
                    fault_type="operator_inversion",
                    target_file=target_rel,
                    mutated_code=(
                        "\n\nclass EligibilityError(Exception): pass\n"
                        "class RuleExpiredError(Exception): pass\n\n"
                        "def evaluate_eligibility_policy(subtotal: float, min_threshold: float = 50.0, is_expired: bool = False) -> float:\n"
                        "    if is_expired: raise RuleExpiredError('Expired')\n"
                        "    if subtotal <= min_threshold:\n"  # BUG: <= instead of <
                        "        raise EligibilityError('Below threshold')\n"
                        "    return subtotal - 10.0\n"
                    ),
                    expected_failing_test="test_req_001_threshold_acceptance",
                )
            )

            # Mutant 2: Omitted Expiration Check
            mutants.append(
                MutantVariant(
                    mutant_id="MUT-002",
                    description="Condition omission: ignored rule expiration timestamp",
                    fault_type="condition_omission",
                    target_file=target_rel,
                    mutated_code=(
                        "\n\nclass EligibilityError(Exception): pass\n"
                        "class RuleExpiredError(Exception): pass\n\n"
                        "def evaluate_eligibility_policy(subtotal: float, min_threshold: float = 50.0, is_expired: bool = False) -> float:\n"
                        "    # BUG: expiration check bypassed\n"
                        "    if subtotal < min_threshold: raise EligibilityError('Below threshold')\n"
                        "    return max(0.0, subtotal - 10.0)\n"
                    ),
                    expected_failing_test="test_req_002_expired_rule_rejected",
                )
            )

            # Mutant 3: Omitted Clamping (Allow Negative Totals)
            mutants.append(
                MutantVariant(
                    mutant_id="MUT-003",
                    description="Removed clamping: negative totals allowed",
                    fault_type="boundary_shift",
                    target_file=target_rel,
                    mutated_code=(
                        "\n\nclass EligibilityError(Exception): pass\n"
                        "class RuleExpiredError(Exception): pass\n\n"
                        "def evaluate_eligibility_policy(subtotal: float, min_threshold: float = 50.0, is_expired: bool = False) -> float:\n"
                        "    if is_expired: raise RuleExpiredError('Expired')\n"
                        "    if subtotal < min_threshold: raise EligibilityError('Below threshold')\n"
                        "    return subtotal - 10.0\n"  # BUG: missing max(0.0, ...)
                    ),
                    expected_failing_test="test_req_001_deduction_clamping",
                )
            )

        else:
            # State transitions mutant
            mutants.append(
                MutantVariant(
                    mutant_id="MUT-001",
                    description="Omitted guardrail: invalid backwards transition permitted",
                    fault_type="condition_omission",
                    target_file=target_rel,
                    mutated_code=(
                        "\n\nclass StateTransitionError(Exception): pass\n\n"
                        "def transition_entity_state(current_state: str, new_state: str) -> str:\n"
                        "    return new_state\n"  # BUG: allows all transitions
                    ),
                    expected_failing_test="test_req_001_invalid_transition",
                )
            )

        return mutants

    @classmethod
    def evaluate_mutants(
        cls, spec: TaskSpecification, repo_path: Path, test_file_rel: str
    ) -> Tuple[List[MutationCheck], float]:
        repo_path = repo_path.resolve()
        target_rel = spec.repository_evidence[0].path if spec.repository_evidence else "codeforge/contracts/repository.py"
        target_file = repo_path / target_rel
        orig_content = target_file.read_text(encoding="utf-8", errors="ignore") if target_file.exists() else ""

        mutants = cls.synthesize_mutants(spec, target_rel)
        results: List[MutationCheck] = []

        try:
            for m in mutants:
                # Apply mutant code
                target_file.write_text(orig_content + m.mutated_code, encoding="utf-8")

                # Run feature tests against mutant
                env = {**os.environ, "PYTHONPATH": str(repo_path)}
                res = subprocess.run(
                    [sys.executable, "-m", "pytest", str(repo_path / test_file_rel), "-q"],
                    capture_output=True,
                    text=True,
                    cwd=str(repo_path),
                    env=env,
                )

                # If test FAILED (exit code != 0), the mutant was KILLED!
                if res.returncode != 0:
                    status = MutantStatus.KILLED
                    killing_test = m.expected_failing_test
                else:
                    status = MutantStatus.SURVIVED
                    killing_test = None

                results.append(
                    MutationCheck(
                        mutant_id=m.mutant_id,
                        description=m.description,
                        fault_type=m.fault_type,
                        target_file=m.target_file,
                        expected_killing_test=m.expected_failing_test,
                        actual_killing_test=killing_test,
                        status=status,
                    )
                )
        finally:
            # Restore original file state unconditionally
            target_file.write_text(orig_content, encoding="utf-8")

        killed_count = sum(1 for r in results if r.status == MutantStatus.KILLED)
        score_pct = (killed_count / len(results) * 100.0) if results else 0.0
        return results, round(score_pct, 1)
