"""Task generation package."""

from codeforge.task_generation.candidate_engine import (
    CandidateOpportunity,
    CandidateOpportunityEngine,
)
from codeforge.task_generation.spec_generator import TaskSpecGenerator

__all__ = [
    "CandidateOpportunity",
    "CandidateOpportunityEngine",
    "TaskSpecGenerator",
]
