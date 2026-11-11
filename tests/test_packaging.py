"""Unit tests for package builder and verifier."""

import tempfile
from pathlib import Path
from veriloom.repository_intelligence import RepositoryIntelligenceEngine
from veriloom.task_generation import (
    CandidateOpportunityEngine,
    TaskSpecGenerator,
)
from veriloom.reference_solution import ReferenceSolutionAgent
from veriloom.test_generation import FeatureTestGenerator
from veriloom.validation import ValidationRunner
from veriloom.variation import VariationEngine
from veriloom.packaging import PackageBuilder, PackageVerifier


def test_package_builder_and_verification():
    root = Path(__file__).parent.parent
    record = RepositoryIntelligenceEngine.ingest(root)
    cap_map = RepositoryIntelligenceEngine.build_capability_map(root, record.repository_id, record.starting_commit)

    opp = CandidateOpportunityEngine.discover_opportunities(cap_map)[0]
    spec = TaskSpecGenerator.generate_from_opportunity(opp, record.repository_id, record.starting_commit, "task_test_pkg")

    ref_solution = ReferenceSolutionAgent.create_reference_solution(spec, root)
    test_suite = FeatureTestGenerator.generate_tests(spec)
    val_report = ValidationRunner.run_validation(spec, record, ref_solution, test_suite, root)
    var_report = VariationEngine.evaluate_variation(spec, [])

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_base = Path(tmp_dir)
        pkg_dir = PackageBuilder.build_package(
            spec,
            record,
            ref_solution,
            test_suite,
            val_report,
            var_report,
            tmp_base,
        )

        assert pkg_dir.exists()
        assert (pkg_dir / "manifest.json").exists()
        assert (pkg_dir / "metadata" / "checksums.txt").exists()

        is_valid, errors = PackageVerifier.verify_checksums(pkg_dir)
        assert is_valid is True
        assert len(errors) == 0

