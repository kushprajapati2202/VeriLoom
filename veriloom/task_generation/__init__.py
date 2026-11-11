"""Task generation package."""

from veriloom.task_generation.candidate_engine import (
    CandidateOpportunity,
    CandidateOpportunityEngine,
)
from veriloom.task_generation.spec_generator import TaskSpecGenerator

__all__ = [
    "CandidateOpportunity",
    "CandidateOpportunityEngine",
    "TaskSpecGenerator",
]

