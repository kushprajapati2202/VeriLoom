"""FastAPI REST server for CodeForge AI dashboard and control centre."""

from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from codeforge.repository_intelligence import RepositoryIntelligenceEngine
from codeforge.task_generation import CandidateOpportunityEngine
from codeforge.orchestrator import CodeForgePipeline
from codeforge.packaging import PackageVerifier

app = FastAPI(
    title="CodeForge AI API",
    description="Repository-Aware Coding Task Factory & Benchmark Validation API",
    version="1.0.0",
)


class InspectRequest(BaseModel):
    repo_path: str = "."


class RunPipelineRequest(BaseModel):
    repo_path: str = "."
    candidate_index: int = 0
    custom_task_id: Optional[str] = None


@app.get("/api/status")
def get_status():
    return {
        "status": "online",
        "service": "CodeForge AI Task Factory",
        "version": "1.0.0",
    }


@app.post("/api/repository/inspect")
def inspect_repository(req: InspectRequest):
    path = Path(req.repo_path).resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail="Repository path not found")
    record = RepositoryIntelligenceEngine.ingest(path)
    cap_map = RepositoryIntelligenceEngine.build_capability_map(
        path, record.repository_id, record.starting_commit
    )
    return {
        "repository": record.model_dump(),
        "capability_map": cap_map.model_dump(),
    }


@app.post("/api/pipeline/run")
def run_pipeline(req: RunPipelineRequest):
    path = Path(req.repo_path).resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail="Repository path not found")
    pipeline = CodeForgePipeline(path)
    try:
        result = pipeline.run_end_to_end(
            candidate_index=req.candidate_index, custom_task_id=req.custom_task_id
        )
        return {
            "task_id": result.task_id,
            "specification": result.specification.model_dump(),
            "validation_report": result.validation_report.model_dump(),
            "variation_report": result.variation_report.model_dump(),
            "package_dir": result.package_dir,
            "package_verified": result.package_verified,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/packages")
def list_packages(export_dir: str = "exports"):
    path = Path(export_dir).resolve()
    if not path.exists():
        return {"packages": []}

    packages = []
    for d in path.iterdir():
        if d.is_dir() and (d / "manifest.json").exists():
            is_valid, _ = PackageVerifier.verify_checksums(d)
            packages.append({"package_id": d.name, "path": str(d), "is_valid": is_valid})
    return {"packages": packages}
