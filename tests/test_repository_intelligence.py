"""Unit tests for repository intelligence engine."""

from pathlib import Path
from veriloom.repository_intelligence import (
    GitOps,
    StackDetector,
    ASTAnalyzer,
    RepositoryIntelligenceEngine,
)


def test_git_ops_current_repo():
    root = Path(__file__).parent.parent
    sha = GitOps.get_commit_sha(root)
    assert len(sha) == 40
    branch = GitOps.get_active_branch(root)
    assert branch == "main"
    is_clean = GitOps.is_working_tree_clean(root)
    assert isinstance(is_clean, bool)


def test_stack_detector_current_repo():
    root = Path(__file__).parent.parent
    stack = StackDetector.detect(root)
    assert stack["language"] == "python"
    assert stack["package_manager"] == "pip"
    assert "pytest" in stack["test_command"]


def test_ast_analyzer_extracts_symbols():
    root = Path(__file__).parent.parent
    files, symbols, test_files = ASTAnalyzer.analyze_repository(root)
    assert any("veriloom/contracts" in f for f in files)
    assert any("RepositoryRecord" in (s.symbol or "") for s in symbols)
    assert any("test_contracts.py" in t for t in test_files)


def test_engine_ingest_and_capability_map():
    root = Path(__file__).parent.parent
    record = RepositoryIntelligenceEngine.ingest(root)
    assert record.language == "python"
    assert record.starting_commit is not None
    assert len(record.starting_commit) == 40

    cap_map = RepositoryIntelligenceEngine.build_capability_map(root, record.repository_id, record.starting_commit)
    assert cap_map.repository_id == record.repository_id
    assert cap_map.starting_commit == record.starting_commit
    assert len(cap_map.candidate_extension_points) > 0

