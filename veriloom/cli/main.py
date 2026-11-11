"""VeriLoom AI CLI Entrypoint."""

import json
from pathlib import Path
import click

from veriloom.repository_intelligence import RepositoryIntelligenceEngine
from veriloom.task_generation import CandidateOpportunityEngine, TaskSpecGenerator
from veriloom.orchestrator import VeriLoomPipeline
from veriloom.packaging import PackageVerifier


@click.group()
def cli():
    """VeriLoom AI - Repository-Aware Coding Task Factory."""
    pass


@cli.command()
@click.argument("repo_path", type=click.Path(exists=True), default=".")
def inspect(repo_path):
    """Inspect repository, pin commit SHA, detect stack, and build capability map."""
    path = Path(repo_path).resolve()
    click.echo(f"[*] Inspecting repository at: {path}")

    record = RepositoryIntelligenceEngine.ingest(path)
    click.echo(f"[+] Pinned Commit SHA: {record.starting_commit}")
    click.echo(f"[+] Detected Language: {record.language}")
    click.echo(f"[+] Package Manager:   {record.package_manager or 'N/A'}")
    click.echo(f"[+] Test Command:      {record.test_command or 'N/A'}")
    click.echo(f"[+] Working Tree:      {'Clean' if record.working_tree_clean else 'DIRTY'}")

    cap_map = RepositoryIntelligenceEngine.build_capability_map(
        path, record.repository_id, record.starting_commit
    )
    click.echo(f"[+] Files Tracked:     {len(cap_map.file_tree)}")
    click.echo(f"[+] Extension Points:  {len(cap_map.candidate_extension_points)}")
    click.echo(f"[+] Existing Tests:    {len(cap_map.existing_tests)}")


@cli.command()
@click.argument("repo_path", type=click.Path(exists=True), default=".")
def opportunities(repo_path):
    """List ranked candidate feature opportunities for the repository."""
    path = Path(repo_path).resolve()
    record = RepositoryIntelligenceEngine.ingest(path)
    cap_map = RepositoryIntelligenceEngine.build_capability_map(
        path, record.repository_id, record.starting_commit
    )
    opps = CandidateOpportunityEngine.discover_opportunities(cap_map)

    click.echo(f"\nDiscovered {len(opps)} candidate opportunities:")
    for i, opp in enumerate(opps):
        click.echo(f"  [{i}] ({opp.feature_family.value}) {opp.title} [Score: {opp.score}]")


@cli.command(name="run-pipeline")
@click.argument("repo_path", type=click.Path(exists=True), default=".")
@click.option("--candidate-index", default=0, help="Index of opportunity to generate.")
@click.option("--output-dir", default=None, help="Output directory for task packages.")
def run_pipeline(repo_path, candidate_index, output_dir):
    """Execute complete 11-stage pipeline from repository ingestion to verified package."""
    path = Path(repo_path).resolve()
    out_path = Path(output_dir).resolve() if output_dir else None

    click.echo(f"[*] Launching VeriLoom AI pipeline against: {path}")
    pipeline = VeriLoomPipeline(path, out_path)

    try:
        result = pipeline.run_end_to_end(candidate_index=candidate_index)
        click.echo(f"\n[SUCCESS] Pipeline completed successfully!")
        click.echo(f"  - Task ID:           {result.task_id}")
        click.echo(f"  - Title:             {result.specification.title}")
        click.echo(f"  - Feature Family:    {result.specification.feature_family.value}")
        click.echo(f"  - Validation Status: {result.validation_report.status.value.upper()}")
        click.echo(f"  - Regression Status: {result.validation_report.regression_summary.status}")
        click.echo(f"  - Mutants Tested:    {len(result.validation_report.mutation_checks)}")
        click.echo(f"  - Novelty Score:     {result.variation_report.novelty_assessment.overall_novelty_score}")
        click.echo(f"  - Package Directory: {result.package_dir}")
        click.echo(f"  - Replay Verified:   {result.package_verified}")
    except Exception as e:
        click.echo(f"[ERROR] Pipeline execution failed: {e}", err=True)
        raise click.Abort()


@cli.command(name="verify-package")
@click.argument("package_dir", type=click.Path(exists=True))
def verify_package(package_dir):
    """Verify package SHA-256 checksums and manifest integrity."""
    path = Path(package_dir).resolve()
    is_valid, errors = PackageVerifier.verify_checksums(path)
    if is_valid:
        click.echo(f"[PASS] Package at {path} is verified and tamper-free.")
    else:
        click.echo(f"[FAIL] Package verification failed:", err=True)
        for err in errors:
            click.echo(f"  - {err}", err=True)
        raise click.Abort()


@cli.command()
@click.option("--package", required=True, type=click.Path(exists=True), help="Path to exported task package.")
@click.option("--solution", required=True, help="Python code string or patch file path.")
@click.option("--model", default="EvaluatedModel", help="Model or candidate identifier.")
def benchmark(package, solution, model):
    """Evaluate an AI coding model's solution against a verified task package."""
    from veriloom.benchmark import BenchmarkRunner
    pkg_path = Path(package).resolve()

    # Check if solution is a file path
    sol_content = solution
    if Path(solution).exists():
        sol_content = Path(solution).read_text(encoding="utf-8")

    click.echo(f"[*] Benchmarking '{model}' against package {pkg_path.name}...")
    result = BenchmarkRunner.evaluate_solution(pkg_path, sol_content, model_name=model)

    click.echo(f"\n[BENCHMARK RESULT]")
    click.echo(f"  - Model:            {result.model_name}")
    click.echo(f"  - Verdict:          {result.verdict.value}")
    click.echo(f"  - Feature Tests:    {'PASSED' if result.feature_tests_passed else 'FAILED'}")
    click.echo(f"  - Regression Suite: {'CLEAN' if result.regression_clean else 'BROKEN'}")
    click.echo(f"  - Failure Category: {result.failure_category.value}")
    click.echo(f"  - Latency:          {result.execution_time_ms} ms")


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host interface to bind.")
@click.option("--port", default=8000, help="Port to listen on.")
def serve(host, port):
    """Launch the VeriLoom interactive web dashboard and API server."""
    import uvicorn
    click.echo(f"[*] Starting VeriLoom Web Dashboard at http://{host}:{port}")
    uvicorn.run("veriloom.api.server:app", host=host, port=port, reload=False)


def main():
    cli()


if __name__ == "__main__":
    main()

