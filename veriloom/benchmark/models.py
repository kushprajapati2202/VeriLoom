"""Benchmark data models for evaluating AI coding systems."""

from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class EvaluationVerdict(str, Enum):
    PASSED_FULL = "PASSED_FULL"
    FEATURE_FAILED = "FEATURE_FAILED"
    REGRESSION_INTRODUCED = "REGRESSION_INTRODUCED"
    BUILD_ERROR = "BUILD_ERROR"
    TIMEOUT = "TIMEOUT"


class FailureCategory(str, Enum):
    NONE = "none"
    ASSERTION_FAILURE = "assertion_failure"
    SYNTAX_ERROR = "syntax_error"
    REGRESSION_BREAK = "regression_break"
    TIMEOUT_EXCEEDED = "timeout_exceeded"
    EXECUTION_CRASH = "execution_crash"


class BenchmarkResult(BaseModel):
    task_id: str
    model_name: str
    verdict: EvaluationVerdict
    feature_tests_passed: bool
    feature_tests_count: int
    feature_tests_passed_count: int
    regression_clean: bool
    failure_category: FailureCategory
    execution_time_ms: int
    log_output: Optional[str] = None


class ModelComparisonReport(BaseModel):
    task_id: str
    models_evaluated: List[str]
    results: List[BenchmarkResult]
    leaderboard: Dict[str, Dict[str, float]] = Field(
        description="Model name mapped to pass rate, regression rate, and speed"
    )

