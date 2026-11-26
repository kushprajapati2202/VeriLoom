"""End-to-end pipeline orchestrator for VeriLoom AI."""

import logging
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
from veriloom.authoring.llm_author import AuthoringError


log = logging.getLogger("veriloom")


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

    MAX_SPEC_ROUNDS = 2

    @staticmethod
    def _spec_conflict(attempts) -> Optional[str]:
        """Feedback for the spec writer when every attempt broke existing tests."""
        if not attempts or not all(
            any(g["name"] == "regression" and not g["passed"] for g in a.gates) for a in attempts if a.gates
        ):
            return None
        last = next((g for g in attempts[-1].gates if g["name"] == "regression"), None)
        if last is None:
            return None
        errors = sorted({l.strip() for l in (last.get("log_tail") or "").splitlines()
                         if l.strip().startswith(("E ", "FAILED"))})[:12]
        return (
            "Your previous specification could not be implemented without breaking the repository's "
            f"existing tests ({last['detail']}). Failures:\n" + "\n".join(errors) +
            "\nWrite a new specification whose defaults keep all current behaviour working; "
            "make the new restrictions opt-in."
        )

    def _load_catalogue(self, commit: str) -> List[TaskSpecification]:
        out: List[TaskSpecification] = []
        if not self.output_base_dir.exists():
            return out
        for spec_file in sorted(self.output_base_dir.glob("*/task/specification.json")):
            try:
                spec = TaskSpecification.model_validate_json(spec_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if spec.repository_id and spec not in out:
                out.append(spec)
        return out

    def run_end_to_end(
        self,
        candidate_index: int = 0,
        custom_task_id: Optional[str] = None,
        export_harbor: bool = False,
        ideas_path: Optional[Path] = None,
    ) -> PipelineRunResult:
        # Stage 1: Ingestion and Capability Mapping
        log.info("[1] Inspecting repository %s", self.repo_path)
        repo_rec = RepositoryIntelligenceEngine.ingest(self.repo_path)
        cap_map = RepositoryIntelligenceEngine.build_capability_map(
            self.repo_path, repo_rec.repository_id, repo_rec.starting_commit
        )

        provider = self.llm_provider or LLMFactory.get_provider()
        use_llm = not isinstance(provider, OfflineFallbackProvider)

        # Stage 2: Candidate Opportunity Discovery
        if ideas_path:
            from veriloom.task_generation.ideation import FeatureIdeation
            opportunities = FeatureIdeation.to_opportunities(FeatureIdeation.load(ideas_path))
        else:
            opportunities = CandidateOpportunityEngine.discover_opportunities(
                cap_map, extended_families=use_llm
            )
        if not opportunities:
            raise RuntimeError("No candidate feature opportunities could be discovered.")

        selected_opp = opportunities[min(candidate_index, len(opportunities) - 1)]
        log.info("[2] %d opportunities; selected [%d] %s in %s", len(opportunities),
                 min(candidate_index, len(opportunities) - 1), selected_opp.feature_family.value, selected_opp.target_evidence[0].path if selected_opp.target_evidence else "?")
        log.info("    provider: %s%s", type(provider).__name__, "" if use_llm else " (offline templates)")

        # Previously packaged tasks form the variation catalogue, so novelty is measured
        # across runs rather than only within this process.
        catalogue = self._load_catalogue(repo_rec.starting_commit)

        existing = [f"{t.title}: {t.summary}" for t in catalogue][-15:]
        spec_history: List[dict] = []
        spec_feedback: Optional[str] = None
        authored = None
        for spec_round in range(1, (self.MAX_SPEC_ROUNDS if use_llm else 1) + 1):
            # Stage 3: Task Specification Generation
            spec = TaskSpecGenerator.generate_from_opportunity(
                selected_opp,
                repo_rec.repository_id,
                repo_rec.starting_commit,
                task_id=custom_task_id,
                llm_provider=provider,
                repo_root=self.repo_path,
                existing_tasks=existing,
                feedback=spec_feedback,
            )

            log.info("[3] Specification (round %d): %s", spec_round, spec.title)
            # Stage 4: Feasibility and Grounding Gate
            feas_report = FeasibilityGate.evaluate(spec, self.repo_path)
            if not feas_report.is_feasible:
                raise ValueError(
                    f"Task failed feasibility gate: {feas_report.actionable_feedback}"
                )
            if not use_llm:
                break

            # Stages 5-8 (LLM mode): model authors implementation, tests and mutants;
            # every attempt is validated in an isolated sandbox and repaired on failure.
            try:
                authored = LLMTaskAuthor(provider).author(
                    spec,
                    self.repo_path,
                    repo_rec.starting_commit,
                    language=repo_rec.language,
                    framework=repo_rec.framework,
                )
                break
            except AuthoringError as e:
                attempts = getattr(e, "attempts", []) or []
                spec_history.append({"round": spec_round, "title": spec.title,
                                     "attempts": [a.model_dump() for a in attempts]})
                spec_feedback = self._spec_conflict(attempts)
                # Only a specification that forces existing tests to break is worth
                # rewriting; other failures are the author's and stay rejected.
                if spec_feedback is None or spec_round == self.MAX_SPEC_ROUNDS:
                    raise
                log.info("[3] Specification conflicts with existing tests; rewriting it")

        authoring_log = None
        if use_llm:
            spec = authored.spec
            ref_solution = authored.reference_solution
            test_suite = authored.test_suite
            val_report = authored.validation_report
            authoring_log = {
                "mode": "llm",
                "provider": type(provider).__name__,
                "model": getattr(provider, "last_model_used", None) or getattr(provider, "model", None),
                "attempts": [a.model_dump() for a in authored.attempts],
                "rejected_specifications": spec_history,
                "final_gates": authored.gate_report.model_dump(),
            }
        else:
            # Stages 5-8 (offline template mode)
            ref_solution = ReferenceSolutionAgent.create_reference_solution(spec, self.repo_path)
            test_suite = FeatureTestGenerator.generate_tests(spec)
            val_report = ValidationRunner.run_validation(
                spec, repo_rec, ref_solution, test_suite, self.repo_path
            )

        log.info("[5-8] Validation status: %s", val_report.status.value)
        # Stage 9: Meaningful Variation Analysis
        var_report = VariationEngine.evaluate_variation(spec, catalogue + self.task_catalogue)
        self.task_catalogue.append(spec)

        log.info("[9] Novelty %.2f against %d catalogued task(s)", var_report.novelty_assessment.overall_novelty_score,
                 len(var_report.comparison_catalogue))
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

