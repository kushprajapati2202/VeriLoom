"""FastAPI REST server for VeriLoom AI dashboard and control centre."""

from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

load_dotenv()
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from veriloom.repository_intelligence import RepositoryIntelligenceEngine
from veriloom.task_generation import CandidateOpportunityEngine
from veriloom.orchestrator import VeriLoomPipeline
from fastapi.middleware.cors import CORSMiddleware
from veriloom.packaging import PackageVerifier
from veriloom.benchmark import BenchmarkRunner

app = FastAPI(
    title="VeriLoom AI API",
    description="Repository-Aware Coding Task Factory & Benchmark Validation API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InspectRequest(BaseModel):
    repo_path: str = "."


class RunPipelineRequest(BaseModel):
    repo_path: str = "."
    candidate_index: int = 0
    custom_task_id: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/api/index.py", response_class=HTMLResponse)
@app.get("/api/index", response_class=HTMLResponse)
def get_dashboard():
    dashboard_file = Path(__file__).parent / "dashboard.html"
    if dashboard_file.exists():
        return HTMLResponse(content=dashboard_file.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>VeriLoom Dashboard</h1><p>Dashboard template not found.</p>")


@app.get("/api/status")
def get_status():
    return {
        "status": "online",
        "service": "VeriLoom AI Task Factory",
        "version": "1.0.0",
    }


@app.api_route("/api/repository/inspect", methods=["GET", "POST"])
@app.api_route("/api/index.py/api/repository/inspect", methods=["GET", "POST"])
@app.api_route("/api/index/api/repository/inspect", methods=["GET", "POST"])
def inspect_repository(req: Optional[InspectRequest] = None):
    raw_path = req.repo_path if req else "."
    path = Path(raw_path).resolve()
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
    pipeline = VeriLoomPipeline(path)
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
    candidate_dirs = [Path(export_dir).resolve(), Path("examples/sample_packages").resolve()]
    packages = []
    seen = set()

    for p in candidate_dirs:
        if p.exists() and p.is_dir():
            for d in p.iterdir():
                if d.is_dir() and (d / "manifest.json").exists() and d.name not in seen:
                    is_valid, _ = PackageVerifier.verify_checksums(d)
                    packages.append({"package_id": d.name, "path": str(d), "is_valid": is_valid})
                    seen.add(d.name)
    return {"packages": packages}


class BenchmarkEvaluateRequest(BaseModel):
    package_dir: str
    solution_code: str
    model_name: str = "EvaluatedModel"


class BenchmarkCompareRequest(BaseModel):
    package_dir: str
    submissions: Dict[str, str]


@app.post("/api/benchmark/evaluate")
def evaluate_benchmark(req: BenchmarkEvaluateRequest):
    pkg = Path(req.package_dir).resolve()
    if not pkg.exists():
        raise HTTPException(status_code=404, detail="Task package not found")
    try:
        res = BenchmarkRunner.evaluate_solution(pkg, req.solution_code, model_name=req.model_name)
        return res.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/benchmark/compare")
def compare_benchmark(req: BenchmarkCompareRequest):
    pkg = Path(req.package_dir).resolve()
    if not pkg.exists():
        raise HTTPException(status_code=404, detail="Task package not found")
    try:
        report = BenchmarkRunner.compare_models(pkg, req.submissions)
        return report.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


