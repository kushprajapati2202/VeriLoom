"""VeriLoom AI CLI Entrypoint."""

import json
from pathlib import Path
import click
from dotenv import load_dotenv

load_dotenv()

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
@click.option("--harbor", is_flag=True, default=False, help="Also export the package as a Harbor task.")
@click.option("--record", "record_path", default=None, type=click.Path(),
              help="Save every model response to this JSONL file (for offline replay).")
@click.option("--replay", "replay_path", default=None, type=click.Path(exists=True),
              help="Use recorded model responses instead of calling an API. Gates still run live.")
def run_pipeline(repo_path, candidate_index, output_dir, harbor, record_path, replay_path):
    """Execute complete 11-stage pipeline from repository ingestion to verified package."""
    path = Path(repo_path).resolve()
    out_path = Path(output_dir).resolve() if output_dir else None

    import logging
    logging.basicConfig(level=logging.INFO, format="    %(message)s")
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    click.echo(f"[*] Launching VeriLoom AI pipeline against: {path}")
    from veriloom.llm import LLMFactory, RecordingProvider, ReplayProvider
    provider = None
    if replay_path:
        provider = ReplayProvider(Path(replay_path))
        click.echo(f"[*] Replaying recorded model responses from {replay_path} (all gates run live)")
    elif record_path:
        provider = RecordingProvider(LLMFactory.get_provider(), Path(record_path))
        click.echo(f"[*] Recording model responses to {record_path}")
    pipeline = VeriLoomPipeline(path, out_path, llm_provider=provider)

    try:
        result = pipeline.run_end_to_end(candidate_index=candidate_index, export_harbor=harbor)
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
        click.echo(f"  - Authoring Mode:    {result.authoring_mode}"
                   + (f" ({result.authoring_attempts} attempt(s))" if result.authoring_mode == "llm" else
                      "  [offline templates: set an LLM API key for repo-specific tasks]"))
        if result.harbor_task_dir:
            click.echo(f"  - Harbor Task:       {result.harbor_task_dir}")
    except Exception as e:
        click.echo(f"[ERROR] Pipeline execution failed: {e}", err=True)
        raise click.Abort()


@cli.command(name="verify-package")
@click.argument("package_path", required=False, type=click.Path())
@click.option("--package-dir", "-p", "option_package_dir", default=None, type=click.Path(), help="Path to exported task package.")
def verify_package(package_path, option_package_dir):
    """Verify package SHA-256 checksums and manifest integrity."""
    target = package_path or option_package_dir
    if not target:
        click.echo("[ERROR] Please provide a package directory as an argument or via --package-dir", err=True)
        raise click.Abort()
    path = Path(target).resolve()
    if not path.exists():
        click.echo(f"[ERROR] Package directory does not exist: {path}", err=True)
        raise click.Abort()
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
@click.option("--repo-path", default=None, help="Path to target repository root if different from cwd.")
def benchmark(package, solution, model, repo_path):
    """Evaluate an AI coding model's solution against a verified task package."""
    from veriloom.benchmark import BenchmarkRunner
    pkg_path = Path(package).resolve()
    target_repo = Path(repo_path).resolve() if repo_path else None

    # Check if solution is a file path
    sol_content = solution
    if Path(solution).exists():
        sol_content = Path(solution).read_text(encoding="utf-8")

    click.echo(f"[*] Benchmarking '{model}' against package {pkg_path.name}...")
    result = BenchmarkRunner.evaluate_solution(pkg_path, sol_content, model_name=model, repo_root=target_repo)

    click.echo(f"\n[BENCHMARK RESULT]")
    click.echo(f"  - Model:            {result.model_name}")
    click.echo(f"  - Verdict:          {result.verdict.value}")
    click.echo(f"  - Feature Tests:    {'PASSED' if result.feature_tests_passed else 'FAILED'}")
    click.echo(f"  - Regression Suite: {'CLEAN' if result.regression_clean else 'BROKEN'}")
    click.echo(f"  - Failure Category: {result.failure_category.value}")
    click.echo(f"  - Latency:          {result.execution_time_ms} ms")


@cli.command(name="export-harbor")
@click.argument("package_path", type=click.Path(exists=True))
@click.option("--repo", "repo_path", default=".", type=click.Path(exists=True), help="Repository the package was generated from.")
@click.option("--output-dir", default=None, type=click.Path(), help="Where to write the Harbor task (default: <package parent>/harbor_tasks).")
@click.option("--check/--no-check", default=True, help="Replay oracle (expect reward 1) and no-op (expect reward 0) trials locally.")
def export_harbor(package_path, repo_path, output_dir, check):
    """Export a VeriLoom package as a Harbor task (instruction.md, task.toml, environment/, solution/, tests/)."""
    from veriloom.packaging import HarborExporter, HarborLocalRunner

    result = HarborExporter.export(
        Path(package_path), Path(repo_path), Path(output_dir) if output_dir else None
    )
    click.echo(f"[+] Harbor task written: {result.task_dir}")
    click.echo(f"  - Starting commit:    {result.starting_commit}")
    click.echo(f"  - Regression targets: {', '.join(result.regression_targets) or 'none'}")
    click.echo(f"  - Reference patch:    {'applies cleanly' if result.patch_applies else 'DOES NOT APPLY'}")
    for w in result.warnings:
        click.echo(f"  [WARN] {w}")

    if check:
        click.echo("[*] Replaying Harbor trials locally (oracle + no-op)...")
        report = HarborLocalRunner.check(Path(result.task_dir))
        report_path = Path(result.task_dir).parent / f"{result.task_id}.local-check.json"
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        click.echo(f"  - Oracle reward: {report.oracle.reward}  (expected 1)")
        click.echo(f"  - No-op reward:  {report.nop.reward}  (expected 0)")
        click.echo(f"  - Report:        {report_path}")
        if not report.passed:
            for n in report.notes:
                click.echo(f"  [FAIL] {n}", err=True)
            raise click.Abort()
        click.echo("[PASS] Task is solvable and its tests detect the missing feature.")
    click.echo(f"\nRun under Harbor (requires Docker):\n  harbor run -p {result.task_dir} -a oracle")


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

