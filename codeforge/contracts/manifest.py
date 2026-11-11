"""Task package manifest contracts."""

from datetime import datetime, timezone
from typing import Dict, Optional
from pydantic import BaseModel, Field


class RepositoryInfo(BaseModel):
    name: str
    pinned_commit: str
    branch: Optional[str] = "main"
    language: str
    framework: Optional[str] = None


class PackageEntrypoints(BaseModel):
    specification: str = "task/specification.json"
    reference_patch: str = "reference/implementation.patch"
    feature_tests: str = "tests/feature/"
    regression_tests: str = "tests/regression/"
    validation_report: str = "validation/validation-report.json"
    variation_report: str = "validation/variation-report.json"


class PackageVerdict(BaseModel):
    status: str = Field(description="VALIDATED, FAILED, PARTIALLY_VALIDATED")
    reference_solution_passes: bool
    regression_free: bool
    mutation_score_pct: float
    meaningful_variation_confirmed: bool


class PackageManifest(BaseModel):
    manifest_version: str = "1.0.0"
    package_id: str
    task_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    generator_version: str = "codeforge-ai@1.0.0"
    repository: RepositoryInfo
    entrypoints: PackageEntrypoints = Field(default_factory=PackageEntrypoints)
    checksums: Dict[str, str] = Field(default_factory=dict, description="SHA-256 file hashes")
    verdict: PackageVerdict
