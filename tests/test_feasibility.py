"""Unit tests for the feasibility and grounding gate."""

from pathlib import Path
from codeforge.repository_intelligence import RepositoryIntelligenceEngine
from codeforge.task_generation import (
    CandidateOpportunityEngine,
    TaskSpecGenerator,
)
from codeforge.feasibility import FeasibilityGate
from codeforge.contracts.repository import SourceEvidence


def test_feasibility_gate_passes_grounded_spec():
    root = Path(__file__).parent.parent
    record = RepositoryIntelligenceEngine.ingest(root)
    cap_map = RepositoryIntelligenceEngine.build_capability_map(root, record.repository_id, record.starting_commit)

    opp = CandidateOpportunityEngine.discover_opportunities(cap_map)[0]
    spec = TaskSpecGenerator.generate_from_opportunity(opp, record.repository_id, record.starting_commit)

    report = FeasibilityGate.evaluate(spec, root)
    assert report.is_feasible is True
    assert report.score >= 0.8


def test_feasibility_gate_rejects_hallucinated_file():
    root = Path(__file__).parent.parent
    record = RepositoryIntelligenceEngine.ingest(root)
    cap_map = RepositoryIntelligenceEngine.build_capability_map(root, record.repository_id, record.starting_commit)

    opp = CandidateOpportunityEngine.discover_opportunities(cap_map)[0]
    spec = TaskSpecGenerator.generate_from_opportunity(opp, record.repository_id, record.starting_commit)

    # Inject hallucinated file into evidence
    spec.repository_evidence = [
        SourceEvidence(
            path="non_existent_folder/imaginary_service.py",
            symbol="MagicClass",
            reason="Hallucinated evidence",
        )
    ]

    report = FeasibilityGate.evaluate(spec, root)
    assert report.is_feasible is False
    assert any(v.category == "missing_file" for v in report.violations)
