"""Meaningful variation engine comparing new tasks against task catalogue."""

from typing import List, Dict

from veriloom.contracts.task_spec import TaskSpecification, FeatureFamily
from veriloom.contracts.variation import (
    CatalogueComparison,
    NoveltyAssessment,
    VariationReport,
)
from veriloom.variation.metrics import VariationMetrics


class VariationEngine:
    """Evaluates task behavioural diversity and prevents superficial clones."""

    @classmethod
    def extract_behavioural_tags(cls, spec: TaskSpecification) -> List[str]:
        tags = [spec.feature_family.value]

        full_text = (
            spec.title + " " + spec.summary + " " + " ".join(r.statement for r in spec.requirements)
        ).lower()

        keywords = {
            "threshold": "spending_threshold",
            "boundary": "boundary_limit",
            "expire": "temporal_expiration",
            "state": "state_transition_machine",
            "clamp": "value_clamping",
            "error": "structured_error_codes",
            "batch": "batch_validation",
            "transition": "lifecycle_guardrail",
        }

        for kw, tag in keywords.items():
            if kw in full_text:
                tags.append(tag)

        return sorted(set(tags))

    @classmethod
    def evaluate_variation(
        cls, spec: TaskSpecification, catalogue: List[TaskSpecification]
    ) -> VariationReport:
        current_tags = cls.extract_behavioural_tags(spec)
        current_files = [e.path for e in spec.repository_evidence]
        current_text = spec.title + " " + spec.summary

        comparisons: List[CatalogueComparison] = []
        min_distance = 1.0

        for past_task in catalogue:
            if past_task.task_id == spec.task_id:
                continue

            past_tags = cls.extract_behavioural_tags(past_task)
            past_files = [e.path for e in past_task.repository_evidence]
            past_text = past_task.title + " " + past_task.summary

            dist = VariationMetrics.calculate_behavioural_distance(
                current_tags,
                past_tags,
                current_files,
                past_files,
                current_text,
                past_text,
            )
            sim = VariationMetrics.text_cosine_similarity(current_text, past_text)

            is_superficial = dist < 0.35

            shared = sorted(set(current_tags).intersection(set(past_tags)))
            unique = sorted(set(current_tags).difference(set(past_tags)))

            comparisons.append(
                CatalogueComparison(
                    compared_task_id=past_task.task_id,
                    feature_family=past_task.feature_family,
                    text_cosine_similarity=round(sim, 3),
                    ast_token_overlap_jaccard=round(1.0 - VariationMetrics.jaccard_distance(set(current_files), set(past_files)), 3),
                    shared_behaviour_tags=shared,
                    unique_behaviour_tags=unique,
                    behavioural_distance_score=dist,
                    is_superficial_variant=is_superficial,
                )
            )
            if dist < min_distance:
                min_distance = dist

        is_novel = min_distance >= 0.35
        novelty_score = min_distance if comparisons else 1.0

        if not comparisons:
            justification = "First task in catalogue; sets baseline behavioural profile."
        elif is_novel:
            justification = f"Task exhibits meaningful behavioural distance ({novelty_score}) from existing catalogue entries."
        else:
            justification = f"Task distance ({novelty_score}) is below diversity threshold (0.35). Superficial paraphrase detected."

        return VariationReport(
            task_id=spec.task_id,
            feature_family=spec.feature_family,
            difficulty=spec.difficulty,
            behavioural_tags=current_tags,
            comparison_catalogue=comparisons,
            novelty_assessment=NoveltyAssessment(
                overall_novelty_score=novelty_score,
                is_meaningfully_novel=is_novel,
                justification=justification,
            ),
        )

