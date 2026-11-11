"""Candidate Feature Opportunity Engine."""

from typing import List
from pydantic import BaseModel, Field

from veriloom.contracts.repository import CapabilityMap, SourceEvidence
from veriloom.contracts.task_spec import FeatureFamily, TaskDifficulty


class CandidateOpportunity(BaseModel):
    candidate_id: str
    title: str
    feature_family: FeatureFamily
    difficulty: TaskDifficulty
    summary: str
    target_evidence: List[SourceEvidence] = Field(default_factory=list)
    score: float = Field(description="Internal ranking score 0.0 to 1.0")
    feasibility_notes: str


class CandidateOpportunityEngine:
    """Discovers realistic feature extension opportunities grounded in the repository capability map."""

    @classmethod
    def discover_opportunities(cls, capability_map: CapabilityMap) -> List[CandidateOpportunity]:
        opportunities: List[CandidateOpportunity] = []
        extension_points = capability_map.candidate_extension_points

        if not extension_points:
            return opportunities

        # Group extension points by file
        by_file = {}
        for ep in extension_points:
            by_file.setdefault(ep.path, []).append(ep)

        cand_idx = 1
        for path, points in by_file.items():
            symbols = [p.symbol for p in points if p.symbol]
            file_name = Path_name = path.split("/")[-1].split(".")[0]

            # 1. Validation & Constraint Family
            opportunities.append(
                CandidateOpportunity(
                    candidate_id=f"cand_{cand_idx:03d}",
                    title=f"Add strict boundary validation and constraint checks to {file_name}",
                    feature_family=FeatureFamily.DATA_VALIDATION,
                    difficulty=TaskDifficulty.INTERMEDIATE,
                    summary=f"Introduce domain boundary checks, input sanitation, and structured error responses for operations in {path}.",
                    target_evidence=points[:3],
                    score=0.88,
                    feasibility_notes="Target module exists; validation logic can be added without remote dependencies.",
                )
            )
            cand_idx += 1

            # 2. Business Rules Family
            opportunities.append(
                CandidateOpportunity(
                    candidate_id=f"cand_{cand_idx:03d}",
                    title=f"Implement stateful business policy evaluation in {file_name}",
                    feature_family=FeatureFamily.BUSINESS_RULES,
                    difficulty=TaskDifficulty.INTERMEDIATE,
                    summary=f"Add configurable eligibility policies and threshold deductions around {', '.join(symbols[:2]) if symbols else path}.",
                    target_evidence=points[:3],
                    score=0.92,
                    feasibility_notes="Strong architectural fit. Observable via return values or exceptions.",
                )
            )
            cand_idx += 1

            # 3. State Transitions & Lifecycle Family
            opportunities.append(
                CandidateOpportunity(
                    candidate_id=f"cand_{cand_idx:03d}",
                    title=f"Add lifecycle status transition guardrails to {file_name}",
                    feature_family=FeatureFamily.STATE_TRANSITIONS,
                    difficulty=TaskDifficulty.ADVANCED,
                    summary=f"Enforce an explicit finite state machine preventing invalid lifecycle jumps in {path}.",
                    target_evidence=points[:3],
                    score=0.85,
                    feasibility_notes="Easily asserted by attempting valid and invalid state transitions.",
                )
            )
            cand_idx += 1

            if len(opportunities) >= 9:
                break

        # Sort by score descending
        opportunities.sort(key=lambda o: o.score, reverse=True)
        return opportunities

