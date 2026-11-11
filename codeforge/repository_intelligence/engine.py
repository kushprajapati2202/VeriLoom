"""Repository Intelligence Engine orchestrating git commit pinning, stack detection, and AST capability mapping."""

import uuid
from pathlib import Path
from typing import Optional

from codeforge.contracts.repository import RepositoryRecord, CapabilityMap, SourceEvidence
from codeforge.repository_intelligence.git_ops import GitOps
from codeforge.repository_intelligence.stack_detector import StackDetector
from codeforge.repository_intelligence.ast_analyzer import ASTAnalyzer


class RepositoryIntelligenceEngine:
    """Extracts ground truth from a repository: commit hash, stack, AST symbols, and test suites."""

    @classmethod
    def ingest(cls, repo_path: Path, repository_id: Optional[str] = None) -> RepositoryRecord:
        repo_path = repo_path.resolve()
        if not repo_path.exists():
            raise FileNotFoundError(f"Repository path does not exist: {repo_path}")

        commit_sha = GitOps.get_commit_sha(repo_path)
        branch = GitOps.get_active_branch(repo_path)
        is_clean = GitOps.is_working_tree_clean(repo_path)
        stack = StackDetector.detect(repo_path)

        repo_id = repository_id or f"repo_{repo_path.name.lower()}_{uuid.uuid4().hex[:6]}"

        return RepositoryRecord(
            repository_id=repo_id,
            source_path=str(repo_path),
            starting_commit=commit_sha,
            branch=branch,
            working_tree_clean=is_clean,
            language=stack["language"] or "unknown",
            framework=stack["framework"],
            package_manager=stack["package_manager"],
            build_command=stack["build_command"],
            test_command=stack["test_command"],
        )

    @classmethod
    def build_capability_map(cls, repo_path: Path, repository_id: str, commit_sha: str) -> CapabilityMap:
        repo_path = repo_path.resolve()
        files, symbols, test_files = ASTAnalyzer.analyze_repository(repo_path)

        # Extract unique modules
        modules = sorted({f.split("/")[0] for f in files if "/" in f})
        public_interfaces = [s.symbol for s in symbols if s.symbol]

        # Prioritize non-test symbols as candidate extension points
        extension_points = [s for s in symbols if not any(t in s.path.lower() for t in ["test", "spec"])]

        return CapabilityMap(
            repository_id=repository_id,
            starting_commit=commit_sha,
            file_tree=files,
            modules=modules,
            public_interfaces=public_interfaces,
            existing_tests=test_files,
            candidate_extension_points=extension_points,
        )
