"""Technology stack, framework, and command detection."""

import json
from pathlib import Path
from typing import Dict, Any, Optional


class StackDetector:
    """Infers programming language, framework, package manager, and test commands."""

    @classmethod
    def detect(cls, repo_path: Path) -> Dict[str, Optional[str]]:
        info: Dict[str, Optional[str]] = {
            "language": "unknown",
            "framework": None,
            "package_manager": None,
            "build_command": None,
            "test_command": None,
        }

        # Check Python
        if (repo_path / "pyproject.toml").exists() or (repo_path / "requirements.txt").exists() or (repo_path / "setup.py").exists():
            info["language"] = "python"
            if (repo_path / "poetry.lock").exists():
                info["package_manager"] = "poetry"
                info["test_command"] = "poetry run pytest"
            elif (repo_path / "Pipfile").exists():
                info["package_manager"] = "pipenv"
                info["test_command"] = "pipenv run pytest"
            else:
                info["package_manager"] = "pip"
                info["test_command"] = "pytest"

            # Detect Python framework
            reqs_text = ""
            if (repo_path / "requirements.txt").exists():
                try:
                    reqs_text = (repo_path / "requirements.txt").read_text(encoding="utf-8", errors="ignore").lower()
                except Exception:
                    pass

            if "fastapi" in reqs_text:
                info["framework"] = "fastapi"
            elif "flask" in reqs_text:
                info["framework"] = "flask"
            elif "django" in reqs_text:
                info["framework"] = "django"

            return info

        # Check Node / TypeScript / JavaScript
        package_json = repo_path / "package.json"
        if package_json.exists():
            try:
                data: Dict[str, Any] = json.loads(package_json.read_text(encoding="utf-8"))
            except Exception:
                data = {}

            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            scripts = data.get("scripts", {})

            if "typescript" in deps or (repo_path / "tsconfig.json").exists():
                info["language"] = "typescript"
                info["build_command"] = "npm run build" if "build" in scripts else "npx tsc --noEmit"
            else:
                info["language"] = "javascript"

            if (repo_path / "pnpm-lock.yaml").exists():
                info["package_manager"] = "pnpm"
            elif (repo_path / "yarn.lock").exists():
                info["package_manager"] = "yarn"
            else:
                info["package_manager"] = "npm"

            # Framework
            if "next" in deps:
                info["framework"] = "nextjs"
            elif "express" in deps:
                info["framework"] = "express"
            elif "react" in deps:
                info["framework"] = "react"
            elif "@nestjs/core" in deps:
                info["framework"] = "nestjs"

            # Test command
            if "test" in scripts:
                pm = info["package_manager"] or "npm"
                info["test_command"] = f"{pm} test"
            elif "jest" in deps:
                info["test_command"] = "npx jest"
            elif "vitest" in deps:
                info["test_command"] = "npx vitest run"

            return info

        # Check Go
        if (repo_path / "go.mod").exists():
            info["language"] = "go"
            info["package_manager"] = "go mod"
            info["test_command"] = "go test ./..."
            info["build_command"] = "go build ./..."
            return info

        # Check Rust
        if (repo_path / "Cargo.toml").exists():
            info["language"] = "rust"
            info["package_manager"] = "cargo"
            info["test_command"] = "cargo test"
            info["build_command"] = "cargo build"
            return info

        return info
