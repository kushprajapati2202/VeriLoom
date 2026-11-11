"""Data contracts for CodeForge AI."""

from codeforge.contracts.repository import (
    RepositoryRecord,
    SourceEvidence,
    CapabilityMap,
)
from codeforge.contracts.task_spec import (
    FeatureFamily,
    TaskDifficulty,
    PriorityLevel,
    Requirement,
    TestPlanItem,
    TaskSpecification,
)
from codeforge.contracts.validation import (
    CheckStatus,
    MutantStatus,
    CheckOutcome,
    AcceptanceCoverage,
    MutationCheck,
    RegressionSummary,
    ValidationReport,
)
from codeforge.contracts.manifest import (
    RepositoryInfo,
    PackageEntrypoints,
    PackageVerdict,
    PackageManifest,
)
from codeforge.contracts.variation import (
    CatalogueComparison,
    NoveltyAssessment,
    VariationReport,
)

__all__ = [
    "RepositoryRecord",
    "SourceEvidence",
    "CapabilityMap",
    "FeatureFamily",
    "TaskDifficulty",
    "PriorityLevel",
    "Requirement",
    "TestPlanItem",
    "TaskSpecification",
    "CheckStatus",
    "MutantStatus",
    "CheckOutcome",
    "AcceptanceCoverage",
    "MutationCheck",
    "RegressionSummary",
    "ValidationReport",
    "RepositoryInfo",
    "PackageEntrypoints",
    "PackageVerdict",
    "PackageManifest",
    "CatalogueComparison",
    "NoveltyAssessment",
    "VariationReport",
]

