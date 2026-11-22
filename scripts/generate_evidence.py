"""Generate a batch of LLM-authored task packages and an evidence summary.

Runs the full pipeline for several candidates (one per feature family by default),
keeps going when a candidate fails, and writes:

  <out>/<package dirs>             validated task packages
  <out>/evidence-summary.json      machine-readable results, failures included
  <out>/EVIDENCE.md                human-readable table for judges

    python scripts/setup_demo_repo.py shopcart
    python scripts/generate_evidence.py test_repos/shopcart --candidates 0-6 \
        --out examples/sample_packages/shopcart
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from veriloom.llm import LLMFactory, OfflineFallbackProvider  # noqa: E402
from veriloom.orchestrator import VeriLoomPipeline  # noqa: E402


def parse_range(text: str):
    out = []
    for part in text.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--candidates", default="0-6")
    ap.add_argument("--out", required=True)
    ap.add_argument("--harbor", action="store_true")
    ap.add_argument("--backfill-harbor-check", action="store_true",
                    help="only replay oracle/no-op for already exported tasks and refresh EVIDENCE.md")
    args = ap.parse_args()

    if args.backfill_harbor_check:
        out = Path(args.out).resolve()
        summary_path = out / "evidence-summary.json"
        results = json.loads(summary_path.read_text(encoding="utf-8"))
        for row in results:
            row.update(planned(Path(args.repo), row["candidate_index"]))
            task_dir = out / "harbor_tasks" / str(row.get("task_id"))
            if row.get("status") == "validated" and task_dir.is_dir():
                row.update(harbor_check(task_dir))
                print(row["task_id"], row.get("harbor_oracle_reward"), row.get("harbor_noop_reward"), flush=True)
        summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        write_markdown(out, results)
        return 0

    logging.basicConfig(level=logging.INFO, format="    %(message)s")
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    provider = LLMFactory.get_provider()
    if isinstance(provider, OfflineFallbackProvider):
        print("No LLM key configured; evidence must come from the LLM path.", file=sys.stderr)
        return 2

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "evidence-summary.json"
    results = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else []

    pipeline = VeriLoomPipeline(Path(args.repo), out, llm_provider=provider)
    for idx in parse_range(args.candidates):
        print(f"\n=== candidate {idx} ===", flush=True)
        t0 = time.time()
        row = {"candidate_index": idx, "repo": Path(args.repo).name, **planned(Path(args.repo), idx)}
        try:
            r = pipeline.run_end_to_end(candidate_index=idx, export_harbor=args.harbor)
            log = json.loads((Path(r.package_dir) / "validation" / "authoring-log.json").read_text(encoding="utf-8"))
            gates = {g["name"]: g for g in log["final_gates"]["gates"]}
            row.update(
                status="validated",
                task_id=r.task_id,
                package=Path(r.package_dir).name,
                title=r.specification.title,
                family=r.specification.feature_family.value,
                target=r.specification.repository_evidence[0].path,
                commit=r.repository_record.starting_commit,
                requirements=len(r.specification.requirements),
                feature_tests=sum(len(c.test_names) for c in r.test_suite.coverage_mapping),
                attempts=r.authoring_attempts,
                mutation=gates.get("mutation", {}).get("detail"),
                regression=gates.get("regression", {}).get("detail"),
                novelty=r.variation_report.novelty_assessment.overall_novelty_score,
                model=log.get("model"),
                package_verified=r.package_verified,
            )
            if r.harbor_task_dir:
                row.update(harbor_check(Path(r.harbor_task_dir)))
        except Exception as e:
            attempts = getattr(e, "attempts", None) or getattr(getattr(e, "__cause__", None), "attempts", None)
            row.update(status="rejected", error=f"{type(e).__name__}: {str(e)[:400]}",
                       attempts=len(attempts) if attempts else None)
        row["seconds"] = round(time.time() - t0, 1)
        print(json.dumps(row, indent=2), flush=True)
        results = [x for x in results if not (x.get("candidate_index") == idx and x.get("repo") == row["repo"])]
        results.append(row)
        summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        write_markdown(out, results)
    return 0


def planned(repo: Path, idx: int) -> dict:
    """Family and target the candidate was meant to cover (recorded for rejected ones too)."""
    from veriloom.repository_intelligence import RepositoryIntelligenceEngine as R
    from veriloom.task_generation import CandidateOpportunityEngine as C
    repo = repo.resolve()
    rec = R.ingest(repo)
    opps = C.discover_opportunities(R.build_capability_map(repo, rec.repository_id, rec.starting_commit),
                                    extended_families=True)
    o = opps[min(idx, len(opps) - 1)]
    return {"planned_family": o.feature_family.value,
            "planned_target": o.target_evidence[0].path if o.target_evidence else None}


def harbor_check(task_dir: Path) -> dict:
    """Independent replay: oracle must score 1, an untouched repo must score 0."""
    from veriloom.packaging.harbor_local import HarborLocalRunner
    from veriloom.packaging.scrub import scrub_text
    try:
        rep = HarborLocalRunner.check(task_dir)
        (task_dir.parent / f"{task_dir.name}.local-check.json").write_text(scrub_text(rep.model_dump_json(indent=2)), encoding="utf-8")
        return {"harbor_oracle_reward": rep.oracle.reward, "harbor_noop_reward": rep.nop.reward}
    except Exception as e:
        return {"harbor_check_error": f"{type(e).__name__}: {e}"[:200]}


def write_markdown(out: Path, results) -> None:
    ok = [r for r in results if r["status"] == "validated"]
    lines = [
        "# Evidence: LLM-authored, sandbox-validated tasks",
        "",
        f"{len(ok)} of {len(results)} candidates passed all gates "
        "(fail-before, pass-after, regression, mutation, clarity). "
        "Rejected candidates are listed too: the gates are what make the accepted ones trustworthy.",
        "",
        "| # | Status | Family | Target | Title | Attempts | Mutants killed | Oracle / no-op | Novelty | Package |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(results, key=lambda x: (x["repo"], x["candidate_index"])):
        if r["status"] == "validated":
            lines.append(
                f"| {r['candidate_index']} | ✅ validated | {r['family']} | `{r['target']}` | {r['title']} | "
                f"{r['attempts']} | {r['mutation']} | {r.get('harbor_oracle_reward', '?')} / {r.get('harbor_noop_reward', '?')} | "
                f"{r['novelty']:.2f} | [{r['package']}]({r['package']}/) |"
            )
        else:
            reason = r.get("error", "").split("attempt(s): ", 1)[-1]
            lines.append(f"| {r['candidate_index']} | ❌ rejected | {r.get('planned_family', '')} | "
                         f"`{r.get('planned_target', '')}` | {reason[:150]} | "
                         f"{r.get('attempts') or ''} | | | | |")
    models = sorted({r.get("model") for r in ok if r.get("model")})
    lines += [
        "",
        "**How to read this.** *Attempts* counts validate-and-repair rounds (max 3). *Mutants killed* "
        "is the mutation gate on the model's own faulty variants. *Oracle / no-op* is an independent "
        "Harbor-format replay: applying the reference must score 1, the untouched repo must score 0.",
        "",
        f"Model used: {', '.join(models) or 'n/a'}. Each package's `validation/authoring-log.json` "
        "holds every attempt and gate result.",
        "",
        "Reproduce: `python scripts/setup_demo_repo.py shopcart` then "
        "`python scripts/generate_evidence.py test_repos/shopcart --candidates 0-6 --out <dir> --harbor`.",
    ]
    (out / "EVIDENCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
