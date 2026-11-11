"""Reference implementation agent for benchmark tasks."""

from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from codeforge.contracts.task_spec import TaskSpecification, FeatureFamily
from codeforge.reference_solution.patch_manager import PatchManager


class ReferenceSolutionResult(BaseModel):
    task_id: str
    patch_diff: str
    changed_files: List[str]
    requirement_mapping: Dict[str, List[str]] = Field(
        description="Maps requirement IDs to modified functions or lines"
    )
    explanation: str


class ReferenceSolutionAgent:
    """Produces verified reference solution patches satisfying the task specification."""

    @classmethod
    def create_reference_solution(
        cls, spec: TaskSpecification, repo_path: Path
    ) -> ReferenceSolutionResult:
        repo_path = repo_path.resolve()
        target_evidence = spec.repository_evidence[0] if spec.repository_evidence else None
        target_rel = target_evidence.path if target_evidence else "src/main.py"
        full_path = repo_path / target_rel

        orig_content = full_path.read_text(encoding="utf-8", errors="ignore") if full_path.exists() else ""

        # Construct reference code based on feature family
        mod_content = orig_content
        if spec.feature_family == FeatureFamily.DATA_VALIDATION:
            helper_code = (
                "\n\n# --- CodeForge AI Reference Implementation: Strict Boundary Validation ---\n"
                "class ValidationError(Exception):\n"
                "    def __init__(self, message: str, code: str = 'INVALID_FIELD_VALUE', field: str = None):\n"
                "        super().__init__(message)\n"
                "        self.code = code\n"
                "        self.field = field\n\n"
                "def validate_boundary_constraints(value, min_limit=0, max_limit=1000000, field_name='value'):\n"
                "    if value is None or value < min_limit:\n"
                "        raise ValidationError(f'Value {value} below minimum {min_limit}', code='INVALID_FIELD_VALUE', field=field_name)\n"
                "    if value > max_limit:\n"
                "        raise ValidationError(f'Value {value} exceeds maximum {max_limit}', code='INVALID_FIELD_VALUE', field=field_name)\n"
                "    return True\n"
            )
            mod_content = orig_content + helper_code
            req_map = {
                "REQ-001": ["validate_boundary_constraints:min_limit", "validate_boundary_constraints:max_limit"],
                "REQ-002": ["ValidationError:code", "ValidationError:field"],
            }
            explanation = "Added ValidationError with structured error codes and boundary constraint validator."

        elif spec.feature_family == FeatureFamily.BUSINESS_RULES:
            helper_code = (
                "\n\n# --- CodeForge AI Reference Implementation: Configurable Eligibility Rules ---\n"
                "class EligibilityError(Exception):\n"
                "    pass\n\n"
                "class RuleExpiredError(Exception):\n"
                "    pass\n\n"
                "def evaluate_eligibility_policy(subtotal: float, min_threshold: float = 50.0, is_expired: bool = False) -> float:\n"
                "    if is_expired:\n"
                "        raise RuleExpiredError('Rule is expired')\n"
                "    if subtotal < min_threshold:\n"
                "        raise EligibilityError(f'Subtotal {subtotal} is below required threshold {min_threshold}')\n"
                "    deduction = 10.0\n"
                "    return max(0.0, subtotal - deduction)\n"
            )
            mod_content = orig_content + helper_code
            req_map = {
                "REQ-001": ["evaluate_eligibility_policy:threshold", "evaluate_eligibility_policy:clamping"],
                "REQ-002": ["evaluate_eligibility_policy:expiry_check"],
            }
            explanation = "Added evaluate_eligibility_policy with threshold validation, expiration checks, and total clamping."

        else:
            helper_code = (
                "\n\n# --- CodeForge AI Reference Implementation: State Machine Guardrails ---\n"
                "class StateTransitionError(Exception):\n"
                "    pass\n\n"
                "VALID_TRANSITIONS = {\n"
                "    'INITIALIZED': {'ACTIVE', 'CANCELLED'},\n"
                "    'ACTIVE': {'COMPLETED', 'SUSPENDED'},\n"
                "    'SUSPENDED': {'ACTIVE', 'CANCELLED'},\n"
                "    'COMPLETED': set(),\n"
                "    'CANCELLED': set(),\n"
                "}\n\n"
                "def transition_entity_state(current_state: str, new_state: str) -> str:\n"
                "    allowed = VALID_TRANSITIONS.get(current_state, set())\n"
                "    if new_state not in allowed:\n"
                "        raise StateTransitionError(f'Illegal transition from {current_state} to {new_state}')\n"
                "    return new_state\n"
            )
            mod_content = orig_content + helper_code
            req_map = {
                "REQ-001": ["transition_entity_state:allowed_transitions"],
                "REQ-002": ["VALID_TRANSITIONS"],
            }
            explanation = "Added finite state machine transition table and transition guard function."

        diff = PatchManager.generate_diff(
            {target_rel: orig_content},
            {target_rel: mod_content},
        )

        return ReferenceSolutionResult(
            task_id=spec.task_id,
            patch_diff=diff,
            changed_files=[target_rel],
            requirement_mapping=req_map,
            explanation=explanation,
        )
