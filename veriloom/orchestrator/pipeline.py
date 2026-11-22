"""End-to-end pipeline orchestrator for VeriLoom AI."""

import os
import tempfile
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

from veriloom.contracts.repository import RepositoryRecord, CapabilityMap
from veriloom.contracts.task_spec import TaskSpecification
from veriloom.contracts.validation import ValidationReport
from veriloom.contracts.variation import VariationReport
from veriloom.repository_intelligence import RepositoryIntelligenceEngine
from veriloom.task_generation import (
    CandidateOpportunity,
    CandidateOpportunityEngine,
    TaskSpecGenerator,
)
from veriloom.feasibility import FeasibilityGate, FeasibilityReport
from veriloom.reference_solution import (
    ReferenceSolutionAgent,
    ReferenceSolutionResult,
)
from veriloom.test_generation import FeatureTestGenerator, GeneratedTestSuite
from veriloom.validation import ValidationRunner
from veriloom.variation import VariationEngine
from veriloom.packaging import HarborExporter, PackageBuilder, PackageVerifier
from veriloom.llm import LLMFactory, LLMProvider, OfflineFallbackProvider
from veriloom.authoring import LLMTaskAuthor


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
    harbor_task_dir: Optional[str] = None
    authoring_mode: str = "template"  # "llm" when authored + sandbox-validated by a model
    authoring_attempts: int = 0


class VeriLoomPipeline:
    """Orchestrates the complete 11-stage generation, validation, and packaging pipeline."""

    def __init__(
        self,
        repo_path: Path,
        output_base_dir: Optional[Path] = None,
        llm_provider: Optional[LLMProvider] = None,
    ):
        self.llm_provider = llm_provider
        self.repo_path = repo_path.resolve()
        
        is_read_only = bool(os.environ.get("VERCEL"))
        if not is_read_only:
            try:
                probe = self.repo_path / ".write_probe"
                probe.touch()
                probe.unlink()
            except (OSError, PermissionError):
                is_read_only = True

        if output_base_dir:
            self.output_base_dir = output_base_dir.resolve()
        elif is_read_only:
            self.output_base_dir = (Path(tempfile.gettempdir()) / "veriloom_exports").resolve()
        else:
            self.output_base_dir = (self.repo_path / "exports").resolve()
            
        self.task_catalogue: List[TaskSpecification] = []

    def run_end_to_end(
        self,
        candidate_index: int = 0,
        custom_task_id: Optional[str] = None,
        export_harbor: bool = False,
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
        provider = self.llm_provider or LLMFactory.get_provider()
        use_llm = not isinstance(provider, OfflineFallbackProvider)
        spec = TaskSpecGenerator.generate_from_opportunity(
            selected_opp,
            repo_rec.repository_id,
            repo_rec.starting_commit,
            task_id=custom_task_id,
            llm_provider=provider,
            repo_root=self.repo_path,
        )

        # Stage 4: Feasibility and Grounding Gate
        feas_report = FeasibilityGate.evaluate(spec, self.repo_path)
        if not feas_report.is_feasible:
            raise ValueError(
                f"Task failed feasibility gate: {feas_report.actionable_feedback}"
            )

        authoring_log = None
        if use_llm:
            # Stages 5-8 (LLM mode): model authors implementation, tests and mutants;
            # every attempt is validated in an isolated sandbox and repaired on failure.
            authored = LLMTaskAuthor(provider).author(
                spec,
                self.repo_path,
                repo_rec.starting_commit,
                language=repo_rec.language,
                framework=repo_rec.framework,
            )
            spec = authored.spec
            ref_solution = authored.reference_solution
            test_suite = authored.test_suite
            val_report = authored.validation_report
            authoring_log = {
                "mode": "llm",
                "provider": type(provider).__name__,
                "attempts": [a.model_dump() for a in authored.attempts],
                "final_gates": authored.gate_report.model_dump(),
            }
        else:
            # Stages 5-8 (offline template mode)
            ref_solution = ReferenceSolutionAgent.create_reference_solution(spec, self.repo_path)
            test_suite = FeatureTestGenerator.generate_tests(spec)
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
            authoring_log=authoring_log,
        )

        # Stage 11: Verification Replay Check
        is_valid, _ = PackageVerifier.verify_checksums(pkg_dir)

        # Stage 12 (optional): Harbor task export
        harbor_task_dir = None
        if export_harbor:
            harbor_task_dir = HarborExporter.export(pkg_dir, self.repo_path).task_dir

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
            harbor_task_dir=harbor_task_dir,
            authoring_mode="llm" if use_llm else "template",
            authoring_attempts=len(authoring_log["attempts"]) if authoring_log else 0,
        )

