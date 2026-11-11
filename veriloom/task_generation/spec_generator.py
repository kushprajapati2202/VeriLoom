"""Task Specification Generator synthesizing grounded benchmark tasks."""

import uuid
from typing import List, Optional

from veriloom.contracts.repository import SourceEvidence
from veriloom.contracts.task_spec import (
    TaskSpecification,
    Requirement,
    PriorityLevel,
    TestPlanItem,
    FeatureFamily,
    TaskDifficulty,
)
from veriloom.task_generation.candidate_engine import CandidateOpportunity


class TaskSpecGenerator:
    """Generates structured, testable task specifications grounded in repository extension points."""

    @classmethod
    def generate_from_opportunity(
        cls,
        opportunity: CandidateOpportunity,
        repository_id: str,
        starting_commit: str,
        task_id: Optional[str] = None,
    ) -> TaskSpecification:
        tid = task_id or f"task_{uuid.uuid4().hex[:6]}"
        target_file = opportunity.target_evidence[0].path if opportunity.target_evidence else "src/main.py"
        symbol_name = opportunity.target_evidence[0].symbol if opportunity.target_evidence else "core_logic"

        # Generate domain-specific requirements based on feature family
        if opportunity.feature_family == FeatureFamily.DATA_VALIDATION:
            req1 = Requirement(
                id="REQ-001",
                statement=f"Operations modifying state in {target_file} must validate input arguments against strict boundary limits.",
                acceptance_criteria=[
                    "Rejects negative or null values with a structured ValidationError.",
                    "Accepts valid inputs within acceptable range and executes normally.",
                    "Preserves existing state when validation fails.",
                ],
                priority=PriorityLevel.MUST,
            )
            req2 = Requirement(
                id="REQ-002",
                statement="Validation error responses must provide actionable error codes and offending field identifiers.",
                acceptance_criteria=[
                    "ValidationError contains code 'INVALID_FIELD_VALUE' and the name of the failing parameter.",
                    "Multiple simultaneous validation failures are accumulated and returned in batch.",
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
                    scenario="Input with multiple invalid fields",
                    test_type="invalid_input",
                    expected_outcome="Batch error returned listing all invalid field names",
                ),
            ]
            edge_cases = [
                "Zero value (0) boundary condition.",
                "Extremely large integer or float overflow boundary.",
                "Empty string or whitespace-only string input.",
            ]

        elif opportunity.feature_family == FeatureFamily.BUSINESS_RULES:
            req1 = Requirement(
                id="REQ-001",
                statement=f"Evaluation logic in {target_file} must apply configurable minimum threshold rules.",
                acceptance_criteria=[
                    "Entities strictly below the minimum threshold are rejected with an ELIGIBILITY_FAILED error.",
                    "Entities meeting or exceeding the threshold receive appropriate rule application.",
                    "Computed deductions must not result in negative final totals.",
                ],
                priority=PriorityLevel.MUST,
            )
            req2 = Requirement(
                id="REQ-002",
                statement="Rule application must respect temporal expiration timestamps.",
                acceptance_criteria=[
                    "Expired rules are rejected with RULE_EXPIRED.",
                    "Active unexpired rules execute successfully.",
                ],
                priority=PriorityLevel.MUST,
            )
            test_items = [
                TestPlanItem(
                    test_id="TEST-001",
                    requirement_id="REQ-001",
                    scenario="Total strictly below threshold",
                    test_type="boundary",
                    expected_outcome="ELIGIBILITY_FAILED error raised",
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
                    expected_outcome="RULE_EXPIRED error raised",
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
                    "Direct transition from initialized to active state is permitted.",
                    "Illegal transition from completed/terminated back to active is rejected with INVALID_TRANSITION.",
                    "State changes trigger atomic status updates without partial commits.",
                ],
                priority=PriorityLevel.MUST,
            )
            req2 = Requirement(
                id="REQ-002",
                statement="State transition events must record transition timestamp and triggering reason.",
                acceptance_criteria=[
                    "Transition record contains timestamp and previous state.",
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
                    expected_outcome="INVALID_TRANSITION error raised; state remains unchanged",
                ),
            ]
            edge_cases = [
                "Attempted transition to current state (idempotency check).",
                "Concurrent transition requests on the same entity.",
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

