"""Unit tests for variation and novelty engine."""

from pathlib import Path
from veriloom.repository_intelligence import RepositoryIntelligenceEngine
from veriloom.task_generation import (
    CandidateOpportunityEngine,
    TaskSpecGenerator,
)
from veriloom.variation import VariationEngine, VariationMetrics


def test_variation_metrics_jaccard_and_cosine():
    set_a = {"tag_a", "tag_b"}
    set_b = {"tag_b", "tag_c"}
    dist = VariationMetrics.jaccard_distance(set_a, set_b)
    assert 0.0 < dist < 1.0

    sim = VariationMetrics.text_cosine_similarity(
        "Calculate discount eligibility threshold",
        "Calculate discount eligibility threshold",
    )
    assert sim > 0.95


def test_variation_engine_distinct_tasks():
    root = Path(__file__).parent.parent
    record = RepositoryIntelligenceEngine.ingest(root)
    cap_map = RepositoryIntelligenceEngine.build_capability_map(root, record.repository_id, record.starting_commit)

    opps = CandidateOpportunityEngine.discover_opportunities(cap_map)
    opp1 = opps[0]  # business_rules
    opp_diff = next(o for o in opps if o.feature_family != opp1.feature_family)  # data_validation / state_transitions

    spec1 = TaskSpecGenerator.generate_from_opportunity(opp1, record.repository_id, record.starting_commit, "task_001")
    spec2 = TaskSpecGenerator.generate_from_opportunity(opp_diff, record.repository_id, record.starting_commit, "task_002")

    report1 = VariationEngine.evaluate_variation(spec1, [])
    assert report1.novelty_assessment.is_meaningfully_novel is True

    report2 = VariationEngine.evaluate_variation(spec2, [spec1])
    assert len(report2.comparison_catalogue) == 1
    assert report2.novelty_assessment.overall_novelty_score >= 0.35
    assert report2.novelty_assessment.is_meaningfully_novel is True

