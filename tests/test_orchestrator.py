"""End-to-end integration test for CodeForgePipeline."""

import tempfile
from pathlib import Path
from codeforge.orchestrator import CodeForgePipeline


def test_pipeline_end_to_end_run():
    root = Path(__file__).parent.parent
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_base = Path(tmp_dir)
        pipeline = CodeForgePipeline(root, tmp_base)

        result = pipeline.run_end_to_end(candidate_index=0, custom_task_id="task_e2e_001")

        assert result.task_id == "task_e2e_001"
        assert result.feasibility_report.is_feasible is True
        assert result.validation_report.status.value == "passed"
        assert result.validation_report.regression_summary.status == "NO_REGRESSION"
        assert len(result.validation_report.mutation_checks) > 0
        assert result.variation_report.novelty_assessment.is_meaningfully_novel is True
        assert result.package_verified is True
        assert Path(result.package_dir).exists()
