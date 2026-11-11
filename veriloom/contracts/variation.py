"""Variation and novelty data contracts."""

from typing import List
from pydantic import BaseModel, Field

from veriloom.contracts.task_spec import FeatureFamily, TaskDifficulty


class CatalogueComparison(BaseModel):
    compared_task_id: str
    feature_family: FeatureFamily
    text_cosine_similarity: float
    ast_token_overlap_jaccard: float
    shared_behaviour_tags: List[str] = Field(default_factory=list)
    unique_behaviour_tags: List[str] = Field(default_factory=list)
    behavioural_distance_score: float
    is_superficial_variant: bool


class NoveltyAssessment(BaseModel):
    overall_novelty_score: float = Field(description="Normalized distance 0.0 to 1.0")
    is_meaningfully_novel: bool
    justification: str


class VariationReport(BaseModel):
    task_id: str
    feature_family: FeatureFamily
    difficulty: TaskDifficulty
    behavioural_tags: List[str] = Field(default_factory=list)
    comparison_catalogue: List[CatalogueComparison] = Field(default_factory=list)
    novelty_assessment: NoveltyAssessment

