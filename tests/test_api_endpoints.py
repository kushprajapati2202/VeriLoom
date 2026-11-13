"""Stress-tests for VeriLoom FastAPI REST endpoints."""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from veriloom.api.server import app

client = TestClient(app)


def test_dashboard_and_root_endpoints():
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "VeriLoom" in res_root.text

    res_dash = client.get("/dashboard")
    assert res_dash.status_code == 200
    assert "VeriLoom" in res_dash.text


def test_status_endpoint():
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert "service" in data


def test_repository_inspect_valid():
    res = client.post("/api/repository/inspect", json={"repo_path": "."})
    assert res.status_code == 200
    data = res.json()
    assert "repository" in data
    assert "capability_map" in data
    assert len(data["repository"]["starting_commit"]) == 40


def test_repository_inspect_invalid_path():
    res = client.post("/api/repository/inspect", json={"repo_path": "non_existent_dir_404_test"})
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_packages_list():
    res = client.get("/api/packages")
    assert res.status_code == 200
    data = res.json()
    assert "packages" in data
    assert isinstance(data["packages"], list)
    # If sample packages exist, verify structure
    if len(data["packages"]) > 0:
        pkg = data["packages"][0]
        assert "package_id" in pkg
        assert "is_valid" in pkg


def test_benchmark_evaluate_invalid_package():
    res = client.post(
        "/api/benchmark/evaluate",
        json={
            "package_dir": "non_existent_pkg_dir_404",
            "solution_code": "def foo(): pass",
            "model_name": "test-agent",
        },
    )
    assert res.status_code == 404


def test_benchmark_evaluate_valid_package():
    sample_pkg = Path("examples/sample_packages/pkg_task_48e3bf")
    if sample_pkg.exists():
        patch_file = sample_pkg / "reference" / "implementation.patch"
        if patch_file.exists():
            patch_content = patch_file.read_text(encoding="utf-8")
            res = client.post(
                "/api/benchmark/evaluate",
                json={
                    "package_dir": str(sample_pkg),
                    "solution_code": patch_content,
                    "model_name": "api-test-agent",
                },
            )
            assert res.status_code == 200
            data = res.json()
            assert data["verdict"].upper() == "PASSED_FULL"
            assert data["feature_tests_passed"] is True
            assert data["regression_clean"] is True
