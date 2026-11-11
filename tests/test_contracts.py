"""Unit tests for CodeForge AI contracts."""

import pytest
from pydantic import ValidationError

from codeforge.contracts import (
    RepositoryRecord,
    SourceEvidence,
    TaskSpecification,
    Requirement,
    PriorityLevel,
    FeatureFamily,
    TaskDifficulty,
    ValidationReport,
    CheckStatus,
    PackageManifest,
    RepositoryInfo,
    PackageVerdict,
    VariationReport,
    NoveltyAssessment,
)


def test_repository_record_valid():
    record = RepositoryRecord(
        repository_id="repo_001",
        source_path="/path/to/repo",
        starting_commit="9f82d1c6e4b83f0a719234857b28d0987162534a",
        working_tree_clean=True,
        language="python",
        build_command="pytest",
        test_command="pytest",
    )
    assert record.repository_id == "repo_001"
    assert record.working_tree_clean is True
    assert record.language == "python"


def test_task_spec_validation():
    req = Requirement(
        id="REQ-001",
        statement="A discount is applicable only above $50.",
        acceptance_criteria=["Cart below $50 fails with ELIGIBILITY_FAILED."],
        priority=PriorityLevel.MUST,
    )
    spec = TaskSpecification(
        task_id="task_001",
        title="Configurable Discount",
        summary="Add discount rule",
        repository_id="repo_001",
        starting_commit="9f82d1c6e4b83f0a719234857b28d0987162534a",
        feature_family=FeatureFamily.BUSINESS_RULES,
        difficulty=TaskDifficulty.INTERMEDIATE,
        requirements=[req],
        repository_evidence=[
            SourceEvidence(
                path="src/calculator.py",
                symbol="calculate_total",
                reason="Calculates cart order total",
            )
        ],
    )
    assert spec.task_id == "task_001"
    assert len(spec.requirements) == 1
    assert spec.requirements[0].id == "REQ-001"


def test_package_manifest_checksums():
    manifest = PackageManifest(
        package_id="pkg_001",
        task_id="task_001",
        repository=RepositoryInfo(
            name="cart-repo",
            pinned_commit="9f82d1c6e4b83f0a719234857b28d0987162534a",
            language="python",
        ),
        checksums={"task/specification.json": "sha256:abc123"},
        verdict=PackageVerdict(
            status="VALIDATED",
            reference_solution_passes=True,
            regression_free=True,
            mutation_score_pct=100.0,
            meaningful_variation_confirmed=True,
        ),
    )
    assert manifest.package_id == "pkg_001"
    assert manifest.verdict.reference_solution_passes is True
