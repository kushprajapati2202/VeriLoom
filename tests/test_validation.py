"""Unit tests for validation runner and mutation engine."""

from pathlib import Path
from codeforge.repository_intelligence import RepositoryIntelligenceEngine
from codeforge.task_generation import (
    CandidateOpportunityEngine,
    TaskSpecGenerator,
)
from codeforge.reference_solution import ReferenceSolutionAgent
from codeforge.test_generation import FeatureTestGenerator
from codeforge.validation import ValidationRunner, MutationEngine
from codeforge.contracts.validation import MutantStatus


def test_mutation_engine_kills_faulty_mutants():
    root = Path(__file__).parent.parent
    record = RepositoryIntelligenceEngine.ingest(root)
    cap_map = RepositoryIntelligenceEngine.build_capability_map(root, record.repository_id, record.starting_commit)

    opp = CandidateOpportunityEngine.discover_opportunities(cap_map)[0]
    spec = TaskSpecGenerator.generate_from_opportunity(opp, record.repository_id, record.starting_commit)

    test_suite = FeatureTestGenerator.generate_tests(spec)

    # Write test file temporarily
    test_path = root / test_suite.test_file_path
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(test_suite.test_code, encoding="utf-8")

    try:
        results, score = MutationEngine.evaluate_mutants(spec, root, test_suite.test_file_path)
        assert len(results) > 0
        assert score >= 66.0
        assert any(r.status == MutantStatus.KILLED for r in results)
    finally:
        if test_path.exists():
            test_path.unlink()
