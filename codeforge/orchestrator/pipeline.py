"""End-to-end pipeline orchestrator for CodeForge AI."""

from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

from codeforge.contracts.repository import RepositoryRecord, CapabilityMap
from codeforge.contracts.task_spec import TaskSpecification
from codeforge.contracts.validation import ValidationReport
from codeforge.contracts.variation import VariationReport
from codeforge.repository_intelligence import RepositoryIntelligenceEngine
from codeforge.task_generation import (
    CandidateOpportunity,
    CandidateOpportunityEngine,
    TaskSpecGenerator,
)
from codeforge.feasibility import FeasibilityGate, FeasibilityReport
from codeforge.reference_solution import (
    ReferenceSolutionAgent,
    ReferenceSolutionResult,
)
from codeforge.test_generation import FeatureTestGenerator, GeneratedTestSuite
from codeforge.validation import ValidationRunner
from codeforge.variation import VariationEngine
from codeforge.packaging import PackageBuilder, PackageVerifier


class PipelineRunResult(BaseModel):
    task_id: str
    repository_record: RepositoryRecord
    specification: TaskSpecification
    feasibility_report: FeasibilityReport
    reference_solution: ReferenceSolutionResult
    test_suite: GeneratedTestSuite
    validation_report: ValidationReport
    variation_report: VariationReport
    package_dir: str
    package_verified: bool


class CodeForgePipeline:
    """Orchestrates the complete 11-stage generation, validation, and packaging pipeline."""

    def __init__(self, repo_path: Path, output_base_dir: Optional[Path] = None):
        self.repo_path = repo_path.resolve()
        self.output_base_dir = (output_base_dir or (self.repo_path / "exports")).resolve()
        self.task_catalogue: List[TaskSpecification] = []

    def run_end_to_end(
        self, candidate_index: int = 0, custom_task_id: Optional[str] = None
    ) -> PipelineRunResult:
        # Stage 1: Ingestion and Capability Mapping
        repo_rec = RepositoryIntelligenceEngine.ingest(self.repo_path)
        cap_map = RepositoryIntelligenceEngine.build_capability_map(
            self.repo_path, repo_rec.repository_id, repo_rec.starting_commit
        )

        # Stage 2: Candidate Opportunity Discovery
        opportunities = CandidateOpportunityEngine.discover_opportunities(cap_map)
        if not opportunities:
            raise RuntimeError("No candidate feature opportunities could be discovered.")

        selected_opp = opportunities[min(candidate_index, len(opportunities) - 1)]

        # Stage 3: Task Specification Generation
        spec = TaskSpecGenerator.generate_from_opportunity(
            selected_opp, repo_rec.repository_id, repo_rec.starting_commit, task_id=custom_task_id
        )

        # Stage 4: Feasibility and Grounding Gate
        feas_report = FeasibilityGate.evaluate(spec, self.repo_path)
        if not feas_report.is_feasible:
            raise ValueError(
                f"Task failed feasibility gate: {feas_report.actionable_feedback}"
            )

        # Stage 5: Reference Implementation
        ref_solution = ReferenceSolutionAgent.create_reference_solution(spec, self.repo_path)

        # Stage 6: Feature Test Generation
        test_suite = FeatureTestGenerator.generate_tests(spec)

        # Stages 7 & 8: Baseline, Feature, Regression, and Fault Injection Validation
        val_report = ValidationRunner.run_validation(
            spec, repo_rec, ref_solution, test_suite, self.repo_path
        )

        # Stage 9: Meaningful Variation Analysis
        var_report = VariationEngine.evaluate_variation(spec, self.task_catalogue)
        self.task_catalogue.append(spec)

        # Stage 10: Task Package Builder
        pkg_dir = PackageBuilder.build_package(
            spec,
            repo_rec,
            ref_solution,
            test_suite,
            val_report,
            var_report,
            self.output_base_dir,
        )

        # Stage 11: Verification Replay Check
        is_valid, _ = PackageVerifier.verify_checksums(pkg_dir)

        return PipelineRunResult(
            task_id=spec.task_id,
            repository_record=repo_rec,
            specification=spec,
            feasibility_report=feas_report,
            reference_solution=ref_solution,
            test_suite=test_suite,
            validation_report=val_report,
            variation_report=var_report,
            package_dir=str(pkg_dir),
            package_verified=is_valid,
        )
