"""Repository data models and contracts."""

from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


class RepositoryRecord(BaseModel):
    """Pinned metadata and baseline details of an ingested repository."""
    repository_id: str = Field(description="Unique repository identifier")
    source_path: str = Field(description="Local path or remote repository URL")
    starting_commit: str = Field(description="Full 40-character Git commit SHA")
    branch: Optional[str] = Field(default="main", description="Active branch name")
    working_tree_clean: bool = Field(description="True if no untracked/unstaged changes exist")
    language: str = Field(description="Primary detected programming language")
    framework: Optional[str] = Field(default=None, description="Primary detected framework")
    package_manager: Optional[str] = Field(default=None, description="Package manager (npm, pip, poetry, etc.)")
    build_command: Optional[str] = Field(default=None, description="Command to build/typecheck the project")
    test_command: Optional[str] = Field(default=None, description="Command to run the test suite")
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp of ingestion"
    )


class SourceEvidence(BaseModel):
    """Source file and symbol evidence supporting an opportunity or requirement."""
    path: str = Field(description="Relative file path from repository root")
    symbol: Optional[str] = Field(default=None, description="Class, function, or interface name")
    reason: str = Field(description="Why this source element provides evidence")
    line_start: Optional[int] = Field(default=None, description="Starting line number")
    line_end: Optional[int] = Field(default=None, description="Ending line number")


class CapabilityMap(BaseModel):
    """Discovered capability and extension points extracted from a repository."""
    repository_id: str
    starting_commit: str
    file_tree: List[str] = Field(default_factory=list, description="Relevant source files")
    modules: List[str] = Field(default_factory=list, description="Identified modules/packages")
    public_interfaces: List[str] = Field(default_factory=list, description="Exported classes/functions/routes")
    existing_tests: List[str] = Field(default_factory=list, description="Discovered test files")
    candidate_extension_points: List[SourceEvidence] = Field(
        default_factory=list, description="Grounding locations for potential features"
    )

