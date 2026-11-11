"""Unit tests for reference solution agent and patch manager."""

from pathlib import Path
from veriloom.repository_intelligence import RepositoryIntelligenceEngine
from veriloom.task_generation import (
    CandidateOpportunityEngine,
    TaskSpecGenerator,
)
from veriloom.reference_solution import (
    PatchManager,
    ReferenceSolutionAgent,
)


def test_patch_manager_diff_generation():
    orig = {"file1.py": "def hello():\n    return 'world'\n"}
    mod = {"file1.py": "def hello():\n    return 'universe'\n"}
    diff = PatchManager.generate_diff(orig, mod)
    assert "-    return 'world'" in diff
    assert "+    return 'universe'" in diff


def test_reference_solution_agent():
    root = Path(__file__).parent.parent
    record = RepositoryIntelligenceEngine.ingest(root)
    cap_map = RepositoryIntelligenceEngine.build_capability_map(root, record.repository_id, record.starting_commit)

    opp = CandidateOpportunityEngine.discover_opportunities(cap_map)[0]
    spec = TaskSpecGenerator.generate_from_opportunity(opp, record.repository_id, record.starting_commit)

    res = ReferenceSolutionAgent.create_reference_solution(spec, root)
    assert res.task_id == spec.task_id
    assert len(res.patch_diff) > 0
    assert "REQ-001" in res.requirement_mapping

