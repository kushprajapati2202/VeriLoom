"""Data contracts for VeriLoom AI."""

from veriloom.contracts.repository import (
    RepositoryRecord,
    SourceEvidence,
    CapabilityMap,
)
from veriloom.contracts.task_spec import (
    FeatureFamily,
    TaskDifficulty,
    PriorityLevel,
    Requirement,
    TestPlanItem,
    TaskSpecification,
)
from veriloom.contracts.validation import (
    CheckStatus,
    MutantStatus,
    CheckOutcome,
    AcceptanceCoverage,
    MutationCheck,
    RegressionSummary,
    ValidationReport,
)
from veriloom.contracts.manifest import (
    RepositoryInfo,
    PackageEntrypoints,
    PackageVerdict,
    PackageManifest,
)
from veriloom.contracts.variation import (
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

