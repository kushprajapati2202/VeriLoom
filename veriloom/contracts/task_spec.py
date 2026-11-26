"""Task specification data contracts."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

from veriloom.contracts.repository import SourceEvidence


def as_str_list(value) -> List[str]:
    """Models sometimes return one string where a list is asked for; never split it into characters."""
    if value is None:
        return []
    if isinstance(value, str):
        return [line.strip(" -*	") for line in value.splitlines() if line.strip(" -*	")]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)]


class FeatureFamily(str, Enum):
    BUSINESS_RULES = "business_rules"
    API_BEHAVIOUR = "api_behaviour"
    DATA_VALIDATION = "data_validation"
    PERMISSIONS_AUTH = "permissions_auth"
    STATE_TRANSITIONS = "state_transitions"
    ERROR_HANDLING = "error_handling"
    DATA_LIFECYCLE = "data_lifecycle"


class TaskDifficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class PriorityLevel(str, Enum):
    MUST = "must"
    SHOULD = "should"
    COULD = "could"


class Requirement(BaseModel):
    id: str = Field(description="Unique requirement ID (e.g., REQ-001)")
    statement: str = Field(description="Clear functional requirement statement")
    acceptance_criteria: List[str] = Field(description="Observable, testable criteria")
    priority: PriorityLevel = Field(default=PriorityLevel.MUST)


class TestPlanItem(BaseModel):
    test_id: str = Field(description="Test identifier, e.g. TEST-001")
    requirement_id: str = Field(description="Target requirement ID")
    scenario: str = Field(description="Scenario description")
    test_type: str = Field(description="happy_path, boundary, invalid_input, error_handling")
    expected_outcome: str = Field(description="Expected assertion or result")


class TaskSpecification(BaseModel):
    """Complete specification of a generated feature-development task."""
    task_id: str = Field(description="Unique task identifier, e.g. task_001")
    title: str = Field(description="Short human-readable title")
    summary: str = Field(description="Contextual overview of the feature")
    repository_id: str = Field(description="Target repository identifier")
    starting_commit: str = Field(description="Pinned starting git commit SHA")
    feature_family: FeatureFamily
    difficulty: TaskDifficulty
    requirements: List[Requirement] = Field(description="List of functional requirements")
    constraints: List[str] = Field(default_factory=list, description="Performance or compatibility constraints")
    out_of_scope: List[str] = Field(default_factory=list, description="Explicit boundaries not to implement")
    edge_cases: List[str] = Field(default_factory=list, description="Boundary conditions and error scenarios")
    assumptions: List[str] = Field(default_factory=list, description="Explicit domain or technical assumptions")
    repository_evidence: List[SourceEvidence] = Field(
        default_factory=list, description="Citations to existing files/symbols grounding the task"
    )
    test_plan: List[TestPlanItem] = Field(default_factory=list, description="Planned test scenarios")
    known_limitations: List[str] = Field(default_factory=list, description="Acknowledged scope limitations")
    behaviour_details: List[str] = Field(
        default_factory=list,
        description="Exact rules the hidden tests rely on (names, defaults, constants) so the task is solvable",
    )

    public_interface: List[str] = Field(
        default_factory=list,
        description="Signatures added or changed by the reference implementation (shown to the solver)",
    )
    interface_module: Optional[str] = Field(default=None, description="Import path of the changed module")

    @field_validator("behaviour_details", mode="before")
    @classmethod
    def _coerce_details(cls, v):
        return as_str_list(v)

