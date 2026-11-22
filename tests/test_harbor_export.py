"""Tests for the Harbor task exporter and the local oracle / no-op replay."""

import tomllib
from pathlib import Path

import pytest

from veriloom.packaging import HarborExporter, HarborLocalRunner

ROOT = Path(__file__).parent.parent
SAMPLE_PKG = ROOT / "examples" / "sample_packages" / "pkg_task_48e3bf"


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    out = tmp_path_factory.mktemp("harbor")
    return HarborExporter.export(SAMPLE_PKG, ROOT, out)


def test_harbor_layout(exported):
    task = Path(exported.task_dir)
    for rel in (
        "instruction.md",
        "task.toml",
        "environment/Dockerfile",
        "solution/solve.sh",
        "solution/reference.patch",
        "tests/test.sh",
        "tests/feature/test_business_rules.py",
        "tests/regression/tests/test_contracts.py",
    ):
        assert (task / rel).is_file(), rel
    assert exported.patch_applies
    assert exported.regression_targets == ["tests/test_contracts.py"]


def test_task_toml_is_valid(exported):
    data = tomllib.loads((Path(exported.task_dir) / "task.toml").read_text(encoding="utf-8"))
    assert data["task"]["name"] == "veriloom/task_48e3bf"
    assert data["metadata"]["starting_commit"] == exported.starting_commit
    assert data["verifier"]["timeout_sec"] > 0


def test_scripts_use_lf_endings(exported):
    task = Path(exported.task_dir)
    for rel in ("tests/test.sh", "solution/solve.sh", "solution/reference.patch"):
        assert b"\r\n" not in (task / rel).read_bytes(), rel


def test_instruction_exposes_interface_not_solution(exported):
    text = (Path(exported.task_dir) / "instruction.md").read_text(encoding="utf-8")
    assert "REQ-001" in text and "REQ-002" in text
    assert "def evaluate_eligibility_policy(" in text
    assert "deduction = 10.0" not in text  # implementation body must not leak


def test_underspecified_literal_is_flagged(exported):
    assert any("40.0" in w for w in exported.warnings)


def test_oracle_and_nop_rewards(exported):
    report = HarborLocalRunner.check(Path(exported.task_dir))
    assert report.oracle.reward == 1, report.oracle.log
    assert report.nop.reward == 0, report.nop.log
    assert report.passed
