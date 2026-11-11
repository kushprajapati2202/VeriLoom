"""AST and symbol parsing to extract public interfaces and test suites."""

import ast
import re
from pathlib import Path
from typing import List, Tuple
from codeforge.contracts.repository import SourceEvidence

EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    "venv",
    ".venv",
    "dist",
    "build",
    ".pytest_cache",
    ".coverage",
    ".idea",
    ".vscode",
}


class ASTAnalyzer:
    """Extracts symbols, file trees, and test evidence from a codebase."""

    @classmethod
    def get_source_files(cls, repo_path: Path) -> List[Path]:
        files: List[Path] = []
        for path in repo_path.rglob("*"):
            if path.is_file():
                # Check if any parent part is excluded
                if any(part in EXCLUDE_DIRS for part in path.parts):
                    continue
                files.append(path)
        return sorted(files)

    @classmethod
    def analyze_python_file(cls, file_path: Path, repo_root: Path) -> List[SourceEvidence]:
        evidence: List[SourceEvidence] = []
        rel_path = str(file_path.relative_to(repo_root)).replace("\\", "/")
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return evidence

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                evidence.append(
                    SourceEvidence(
                        path=rel_path,
                        symbol=f"class {node.name}",
                        reason=ast.get_docstring(node) or f"Class definition for {node.name}",
                        line_start=node.lineno,
                        line_end=getattr(node, "end_lineno", node.lineno),
                    )
                )
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        evidence.append(
                            SourceEvidence(
                                path=rel_path,
                                symbol=f"{node.name}.{item.name}",
                                reason=ast.get_docstring(item) or f"Method {item.name}",
                                line_start=item.lineno,
                                line_end=getattr(item, "end_lineno", item.lineno),
                            )
                        )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                evidence.append(
                    SourceEvidence(
                        path=rel_path,
                        symbol=f"def {node.name}",
                        reason=ast.get_docstring(node) or f"Top-level function {node.name}",
                        line_start=node.lineno,
                        line_end=getattr(node, "end_lineno", node.lineno),
                    )
                )

        return evidence

    @classmethod
    def analyze_jsts_file(cls, file_path: Path, repo_root: Path) -> List[SourceEvidence]:
        evidence: List[SourceEvidence] = []
        rel_path = str(file_path.relative_to(repo_root)).replace("\\", "/")
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return evidence

        # Match classes, functions, exported constants/interfaces
        patterns = [
            (r"(?:export\s+)?class\s+([A-Za-z0-9_]+)", "class"),
            (r"(?:export\s+)?interface\s+([A-Za-z0-9_]+)", "interface"),
            (r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)", "function"),
            (r"export\s+const\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\(", "arrow_function"),
        ]

        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            for pattern, sym_type in patterns:
                match = re.search(pattern, line)
                if match:
                    name = match.group(1)
                    evidence.append(
                        SourceEvidence(
                            path=rel_path,
                            symbol=f"{sym_type} {name}",
                            reason=f"Exported {sym_type} declaration in {rel_path}",
                            line_start=i,
                            line_end=i,
                        )
                    )

        return evidence

    @classmethod
    def discover_test_files(cls, repo_path: Path) -> List[str]:
        test_files: List[str] = []
        for file in cls.get_source_files(repo_path):
            name = file.name.lower()
            rel_path = str(file.relative_to(repo_path)).replace("\\", "/")
            if (
                name.startswith("test_")
                or name.endswith("_test.py")
                or ".test." in name
                or ".spec." in name
                or "tests/" in rel_path.lower()
                or "test/" in rel_path.lower()
            ):
                test_files.append(rel_path)
        return test_files

    @classmethod
    def analyze_repository(cls, repo_path: Path) -> Tuple[List[str], List[SourceEvidence], List[str]]:
        source_files = cls.get_source_files(repo_path)
        rel_files = [str(f.relative_to(repo_path)).replace("\\", "/") for f in source_files]
        all_evidence: List[SourceEvidence] = []

        for file in source_files:
            if file.suffix == ".py":
                all_evidence.extend(cls.analyze_python_file(file, repo_path))
            elif file.suffix in {".ts", ".tsx", ".js", ".jsx"}:
                all_evidence.extend(cls.analyze_jsts_file(file, repo_path))

        test_files = cls.discover_test_files(repo_path)
        return rel_files, all_evidence, test_files
