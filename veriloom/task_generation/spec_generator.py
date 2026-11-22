"""Task Specification Generator synthesizing grounded benchmark tasks."""

import json
import uuid
from pathlib import Path
from typing import List, Optional

from veriloom.contracts.repository import SourceEvidence
from veriloom.contracts.task_spec import (
    TaskSpecification,
    Requirement,
    PriorityLevel,
    TestPlanItem,
    FeatureFamily,
    TaskDifficulty,
    as_str_list,
)
from veriloom.task_generation.candidate_engine import CandidateOpportunity
import logging

from veriloom.llm import LLMFactory, LLMProvider, OfflineFallbackProvider, TASK_SPECIFICATION_PROMPT


logger = logging.getLogger(__name__)

FAMILY_GUIDANCE = {
    FeatureFamily.BUSINESS_RULES: "Domain policy with several interacting rules (eligibility, precedence, caps, stacking).",
    FeatureFamily.DATA_VALIDATION: "Validate the file's real inputs; collect and report all violations with field names.",
    FeatureFamily.STATE_TRANSITIONS: "A lifecycle with allowed/forbidden transitions and history that persists across calls.",
    FeatureFamily.ERROR_HANDLING: "Recovery behaviour: retries, fallbacks, partial failure and precise error types.",
    FeatureFamily.DATA_LIFECYCLE: "Create/update/expire/archive data with timestamps or versions, querying by state.",
    FeatureFamily.API_BEHAVIOUR: "Extend the public functions' contract: new options, pagination, sorting or filtering.",
    FeatureFamily.PERMISSIONS_AUTH: "Role- or ownership-based access rules enforced on existing operations.",
}


class TaskSpecGenerator:
    """Generates structured, testable task specifications grounded in repository extension points."""

    @classmethod
    def generate_from_opportunity(
        cls,
        opportunity: CandidateOpportunity,
        repository_id: str,
        starting_commit: str,
        task_id: Optional[str] = None,
        llm_provider: Optional[LLMProvider] = None,
        repo_root: Optional[Path] = None,
        existing_tasks: Optional[List[str]] = None,
        feedback: Optional[str] = None,
    ) -> TaskSpecification:
        tid = task_id or f"task_{uuid.uuid4().hex[:6]}"
        target_file = opportunity.target_evidence[0].path if opportunity.target_evidence else "src/main.py"
        symbol_name = opportunity.target_evidence[0].symbol if opportunity.target_evidence else "core_logic"

        provider = llm_provider or LLMFactory.get_provider()

        # Dynamic LLM generation path
        if not isinstance(provider, OfflineFallbackProvider):
            try:
                root = repo_root or Path.cwd()
                src_path = root / target_file
                excerpt = src_path.read_text(encoding="utf-8", errors="ignore")[:12000] if src_path.exists() else ""

                prompt = TASK_SPECIFICATION_PROMPT.format(
                    repo_name=repository_id,
                    target_file=target_file,
                    source_excerpt=excerpt,
                    feature_family=opportunity.feature_family.value,
                    difficulty=opportunity.difficulty.value,
                    family_guidance=FAMILY_GUIDANCE.get(opportunity.feature_family, ""),
                    existing_tasks="\n".join(f"  - {t}" for t in (existing_tasks or [])) or "  (none yet)",
                )
                if feedback:
                    prompt += "\n\nFEEDBACK ON YOUR PREVIOUS SPECIFICATION:\n" + feedback
                data = provider.generate_json(prompt)

                reqs = [
                    Requirement(
                        id=r.get("id", f"REQ-{i+1:03d}"),
                        statement=r["statement"],
                        acceptance_criteria=r.get("acceptance_criteria", []),
                        priority=PriorityLevel(r.get("priority", "must").lower()),
                    )
                    for i, r in enumerate(data.get("requirements", []))
                ]
                if reqs:
                    test_items = [
                        TestPlanItem(
                            test_id=f"TEST-{i+1:03d}",
                            requirement_id=reqs[i % len(reqs)].id,
                            scenario=f"Validate {reqs[i % len(reqs)].id}",
                            test_type="happy_path" if i == 0 else "boundary",
                            expected_outcome="Observed criteria match",
                        )
                        for i in range(max(2, len(reqs)))
                    ]
                    return TaskSpecification(
                        task_id=tid,
                        title=data.get("title", opportunity.title),
                        summary=data.get("summary", opportunity.summary),
                        repository_id=repository_id,
                        starting_commit=starting_commit,
                        feature_family=opportunity.feature_family,
                        difficulty=opportunity.difficulty,
                        requirements=reqs,
                        constraints=data.get("constraints", [f"Must maintain backward compatibility with {symbol_name}."]),
                        out_of_scope=data.get("out_of_scope", ["External database migrations."]),
                        edge_cases=data.get("edge_cases", ["Null or boundary values."]),
                        assumptions=data.get("assumptions", ["Thread-safe execution environment."]),
                        repository_evidence=opportunity.target_evidence,
                        test_plan=test_items,
                        behaviour_details=as_str_list(data.get("behaviour_details")),
                        known_limitations=["Specification drafted by an LLM; validated by sandbox gates G1-G5."],
                    )
            except Exception as e:
                # Fall back to the deterministic template spec, but say so.
                logger.warning("LLM specification failed (%s: %s); using template spec", type(e).__name__, e)

        # Generate domain-specific requirements based on feature family
        if opportunity.feature_family == FeatureFamily.DATA_VALIDATION:
            req1 = Requirement(
                id="REQ-001",
                statement=f"Operations modifying state in {target_file} must validate input arguments against strict boundary limits.",
                acceptance_criteria=[
                    "validate_boundary_constraints(value, min_limit=0, max_limit=1000000, field_name='value') raises ValidationError when value is None or below min_limit (e.g. -1).",
                    "It raises ValidationError when value exceeds max_limit (e.g. 2000000).",
                    "It returns True for values inside the range (e.g. 50).",
                ],
                priority=PriorityLevel.MUST,
            )
            req2 = Requirement(
                id="REQ-002",
                statement="Validation error responses must provide actionable error codes and offending field identifiers.",
                acceptance_criteria=[
                    "ValidationError exposes .code == 'INVALID_FIELD_VALUE' and .field equal to the field_name argument.",
                ],
                priority=PriorityLevel.MUST,
            )
            test_items = [
                TestPlanItem(
                    test_id="TEST-001",
                    requirement_id="REQ-001",
                    scenario="Input parameter with negative boundary value",
                    test_type="boundary",
                    expected_outcome="ValidationError raised with INVALID_FIELD_VALUE",
                ),
                TestPlanItem(
                    test_id="TEST-002",
                    requirement_id="REQ-001",
                    scenario="Valid positive input parameter",
                    test_type="happy_path",
                    expected_outcome="Operation succeeds and returns expected result",
                ),
                TestPlanItem(
                    test_id="TEST-003",
                    requirement_id="REQ-002",
                    scenario="Invalid input with a named field",
                    test_type="invalid_input",
                    expected_outcome="ValidationError carries code and field name",
                ),
            ]
            edge_cases = [
                "Zero value (0) boundary condition.",
                "Extremely large integer or float overflow boundary.",
                "None as input value.",
            ]

        elif opportunity.feature_family == FeatureFamily.BUSINESS_RULES:
            req1 = Requirement(
                id="REQ-001",
                statement=f"Evaluation logic in {target_file} must apply configurable minimum threshold rules.",
                acceptance_criteria=[
                    "evaluate_eligibility_policy(subtotal, min_threshold=50.0, is_expired=False) raises EligibilityError when subtotal < min_threshold (e.g. 49.99 with threshold 50.0).",
                    "Otherwise it returns subtotal minus a fixed deduction of 10.0 (e.g. 50.0 returns 40.0).",
                    "The result is clamped at 0.0 and never negative (e.g. 5.0 with threshold 0.0 returns 0.0).",
                ],
                priority=PriorityLevel.MUST,
            )
            req2 = Requirement(
                id="REQ-002",
                statement="Rule application must respect temporal expiration timestamps.",
                acceptance_criteria=[
                    "When is_expired is True, RuleExpiredError is raised before any threshold check.",
                    "When is_expired is False, the threshold rule applies normally.",
                ],
                priority=PriorityLevel.MUST,
            )
            test_items = [
                TestPlanItem(
                    test_id="TEST-001",
                    requirement_id="REQ-001",
                    scenario="Total strictly below threshold",
                    test_type="boundary",
                    expected_outcome="EligibilityError raised",
                ),
                TestPlanItem(
                    test_id="TEST-002",
                    requirement_id="REQ-001",
                    scenario="Total meets threshold exactly",
                    test_type="boundary",
                    expected_outcome="Rule applied and total updated",
                ),
                TestPlanItem(
                    test_id="TEST-003",
                    requirement_id="REQ-002",
                    scenario="Rule evaluated after expiration time",
                    test_type="invalid_input",
                    expected_outcome="RuleExpiredError raised",
                ),
            ]
            edge_cases = [
                "Total exactly equal to minimum requirement threshold.",
                "Zero total ($0.00).",
                "Rule deduction amount exceeds entity subtotal.",
            ]

        else:  # STATE_TRANSITIONS / General
            req1 = Requirement(
                id="REQ-001",
                statement=f"Lifecycle transitions in {target_file} must follow strict state machine guardrails.",
                acceptance_criteria=[
                    "transition_entity_state(current_state, new_state) returns new_state for allowed moves (e.g. 'INITIALIZED' -> 'ACTIVE').",
                    "Disallowed moves raise StateTransitionError (e.g. 'COMPLETED' -> 'ACTIVE').",
                ],
                priority=PriorityLevel.MUST,
            )
            req2 = Requirement(
                id="REQ-002",
                statement="Allowed transitions are defined in a module-level VALID_TRANSITIONS mapping.",
                acceptance_criteria=[
                    "INITIALIZED -> {ACTIVE, CANCELLED}; ACTIVE -> {COMPLETED, SUSPENDED}; SUSPENDED -> {ACTIVE, CANCELLED}; COMPLETED and CANCELLED are terminal.",
                ],
                priority=PriorityLevel.SHOULD,
            )
            test_items = [
                TestPlanItem(
                    test_id="TEST-001",
                    requirement_id="REQ-001",
                    scenario="Valid state transition sequence",
                    test_type="happy_path",
                    expected_outcome="State advances and returns updated status",
                ),
                TestPlanItem(
                    test_id="TEST-002",
                    requirement_id="REQ-001",
                    scenario="Illegal backward transition attempt",
                    test_type="invalid_input",
                    expected_outcome="StateTransitionError raised",
                ),
            ]
            edge_cases = [
                "Attempted transition to current state (idempotency check).",
                "Transition out of a terminal state.",
            ]

        return TaskSpecification(
            task_id=tid,
            title=opportunity.title,
            summary=opportunity.summary,
            repository_id=repository_id,
            starting_commit=starting_commit,
            feature_family=opportunity.feature_family,
            difficulty=opportunity.difficulty,
            requirements=[req1, req2],
            constraints=[
                f"Must maintain backward compatibility with existing {symbol_name} callers.",
                "Must execute entirely in-process without remote network calls.",
                "Execution overhead per operation must remain under 15ms.",
            ],
            out_of_scope=[
                "External database schema migrations or remote persistence.",
                "Distributed lock managers or cross-process message brokers.",
            ],
            edge_cases=edge_cases,
            assumptions=[
                "Execution environment is thread-safe for local execution.",
                "Configuration objects are supplied in-memory or via standard environment variables.",
            ],
            repository_evidence=opportunity.target_evidence,
            test_plan=test_items,
            known_limitations=[
                "Local single-process validation; cluster-level synchronisation is out of scope.",
            ],
        )

