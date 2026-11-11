"""Unit tests for task opportunity and specification generation."""

from pathlib import Path
from veriloom.repository_intelligence import RepositoryIntelligenceEngine
from veriloom.task_generation import (
    CandidateOpportunityEngine,
    TaskSpecGenerator,
)


def test_candidate_discovery():
    root = Path(__file__).parent.parent
    record = RepositoryIntelligenceEngine.ingest(root)
    cap_map = RepositoryIntelligenceEngine.build_capability_map(root, record.repository_id, record.starting_commit)

    opportunities = CandidateOpportunityEngine.discover_opportunities(cap_map)
    assert len(opportunities) > 0
    assert opportunities[0].score >= 0.8
    assert len(opportunities[0].target_evidence) > 0


def test_spec_generation_structure():
    root = Path(__file__).parent.parent
    record = RepositoryIntelligenceEngine.ingest(root)
    cap_map = RepositoryIntelligenceEngine.build_capability_map(root, record.repository_id, record.starting_commit)

    opp = CandidateOpportunityEngine.discover_opportunities(cap_map)[0]
    spec = TaskSpecGenerator.generate_from_opportunity(opp, record.repository_id, record.starting_commit)

    assert spec.repository_id == record.repository_id
    assert spec.starting_commit == record.starting_commit
    assert len(spec.requirements) >= 2
    assert len(spec.test_plan) >= 2
    assert len(spec.repository_evidence) > 0

