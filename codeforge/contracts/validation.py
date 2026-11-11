"""Validation report data contracts."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    INCONCLUSIVE = "inconclusive"
    BASELINE_FAILED = "baseline_failed"


class MutantStatus(str, Enum):
    KILLED = "KILLED"
    SURVIVED = "SURVIVED"


class CheckOutcome(BaseModel):
    name: str = Field(description="Name of the validation gate, e.g. baseline_tests, feature_tests")
    status: CheckStatus
    command: str = Field(description="Actual command executed")
    exit_code: int = Field(description="Process exit code")
    duration_ms: int = Field(description="Execution time in milliseconds")
    log_path: str = Field(description="Relative path to captured stdout/stderr log")


class AcceptanceCoverage(BaseModel):
    requirement_id: str
    criteria_total: int
    criteria_covered: int
    test_names: List[str] = Field(default_factory=list)
    status: str = Field(description="fully_covered, partially_covered, uncovered")


class MutationCheck(BaseModel):
    mutant_id: str
    description: str
    fault_type: str = Field(description="operator_inversion, boundary_shift, condition_omission, value_corruption, missing_feature")
    target_file: str
    line_modified: Optional[int] = None
    expected_killing_test: Optional[str] = None
    actual_killing_test: Optional[str] = None
    status: MutantStatus
    explanation: Optional[str] = None


class RegressionSummary(BaseModel):
    baseline_tests_count: int = 0
    post_patch_tests_count: int = 0
    passed_count: int = 0
    pre_existing_failures: int = 0
    newly_introduced_failures: int = 0
    status: str = Field(description="NO_REGRESSION, REGRESSION_DETECTED, SKIPPED")


class ValidationReport(BaseModel):
    task_id: str
    repository_commit: str
    status: CheckStatus
    checks: List[CheckOutcome] = Field(default_factory=list)
    acceptance_coverage: List[AcceptanceCoverage] = Field(default_factory=list)
    mutation_checks: List[MutationCheck] = Field(default_factory=list)
    regression_summary: RegressionSummary = Field(default_factory=RegressionSummary)
    limitations: List[str] = Field(default_factory=list)
