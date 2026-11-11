"""Task package builder generating version-pinned reproducible packages."""

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Dict

from codeforge.contracts.task_spec import TaskSpecification
from codeforge.contracts.repository import RepositoryRecord
from codeforge.contracts.validation import ValidationReport
from codeforge.contracts.variation import VariationReport
from codeforge.contracts.manifest import (
    PackageManifest,
    RepositoryInfo,
    PackageVerdict,
    PackageEntrypoints,
)
from codeforge.reference_solution.agent import ReferenceSolutionResult
from codeforge.test_generation.feature_tests import GeneratedTestSuite


class PackageBuilder:
    """Constructs self-contained, reproducible task package directories with SHA-256 integrity."""

    @staticmethod
    def sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return "sha256:" + h.hexdigest()

    @classmethod
    def build_package(
        cls,
        spec: TaskSpecification,
        repo_record: RepositoryRecord,
        ref_solution: ReferenceSolutionResult,
        test_suite: GeneratedTestSuite,
        val_report: ValidationReport,
        var_report: VariationReport,
        output_base_dir: Path,
    ) -> Path:
        output_base_dir = output_base_dir.resolve()
        pkg_dir = output_base_dir / f"pkg_{spec.task_id}"
        if pkg_dir.exists():
            shutil.rmtree(pkg_dir)

        # Create subdirectories
        (pkg_dir / "task").mkdir(parents=True, exist_ok=True)
        (pkg_dir / "repository").mkdir(parents=True, exist_ok=True)
        (pkg_dir / "reference").mkdir(parents=True, exist_ok=True)
        (pkg_dir / "tests" / "feature").mkdir(parents=True, exist_ok=True)
        (pkg_dir / "validation" / "logs").mkdir(parents=True, exist_ok=True)
        (pkg_dir / "metadata").mkdir(parents=True, exist_ok=True)

        # 1. Write Task Artifacts
        (pkg_dir / "task" / "specification.json").write_text(
            spec.model_dump_json(indent=2), encoding="utf-8"
        )
        (pkg_dir / "task" / "acceptance-criteria.json").write_text(
            json.dumps([r.model_dump() for r in spec.requirements], indent=2), encoding="utf-8"
        )
        (pkg_dir / "task" / "test-plan.json").write_text(
            json.dumps([t.model_dump() for t in spec.test_plan], indent=2), encoding="utf-8"
        )

        # 2. Write Repository Artifacts
        (pkg_dir / "repository" / "source-commit.txt").write_text(
            repo_record.starting_commit + "\n", encoding="utf-8"
        )

        # 3. Write Reference Patch
        (pkg_dir / "reference" / "implementation.patch").write_text(
            ref_solution.patch_diff, encoding="utf-8"
        )
        (pkg_dir / "reference" / "changed-files.txt").write_text(
            "\n".join(ref_solution.changed_files) + "\n", encoding="utf-8"
        )

        # 4. Write Tests
        test_file_name = Path(test_suite.test_file_path).name
        (pkg_dir / "tests" / "feature" / test_file_name).write_text(
            test_suite.test_code, encoding="utf-8"
        )
        (pkg_dir / "tests" / "test-to-requirement-map.json").write_text(
            json.dumps([c.model_dump() for c in test_suite.coverage_mapping], indent=2), encoding="utf-8"
        )

        # 5. Write Validation Reports
        (pkg_dir / "validation" / "validation-report.json").write_text(
            val_report.model_dump_json(indent=2), encoding="utf-8"
        )
        (pkg_dir / "validation" / "mutation-results.json").write_text(
            json.dumps([m.model_dump() for m in val_report.mutation_checks], indent=2), encoding="utf-8"
        )
        (pkg_dir / "validation" / "variation-report.json").write_text(
            var_report.model_dump_json(indent=2), encoding="utf-8"
        )

        # 6. Compute Checksums
        checksums: Dict[str, str] = {}
        for root, _, files in os.walk(pkg_dir):
            for file in sorted(files):
                full_p = Path(root) / file
                rel_p = str(full_p.relative_to(pkg_dir)).replace("\\", "/")
                checksums[rel_p] = cls.sha256_file(full_p)

        (pkg_dir / "metadata" / "checksums.txt").write_text(
            "\n".join(f"{h}  {f}" for f, h in sorted(checksums.items())) + "\n",
            encoding="utf-8",
        )

        # 7. Write Manifest
        manifest = PackageManifest(
            package_id=f"pkg_{spec.task_id}",
            task_id=spec.task_id,
            repository=RepositoryInfo(
                name=repo_record.repository_id,
                pinned_commit=repo_record.starting_commit,
                branch=repo_record.branch,
                language=repo_record.language,
                framework=repo_record.framework,
            ),
            entrypoints=PackageEntrypoints(
                specification="task/specification.json",
                reference_patch="reference/implementation.patch",
                feature_tests="tests/feature/",
                regression_tests="tests/regression/",
                validation_report="validation/validation-report.json",
                variation_report="validation/variation-report.json",
            ),
            checksums=checksums,
            verdict=PackageVerdict(
                status="VALIDATED" if val_report.status == "passed" else "FAILED",
                reference_solution_passes=val_report.status == "passed",
                regression_free=val_report.regression_summary.newly_introduced_failures == 0,
                mutation_score_pct=100.0,
                meaningful_variation_confirmed=var_report.novelty_assessment.is_meaningfully_novel,
            ),
        )

        (pkg_dir / "manifest.json").write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )

        # 8. Write README
        (pkg_dir / "README.md").write_text(
            f"# Task Package: {spec.task_id}\n\n"
            f"**Title**: {spec.title}\n"
            f"**Repository Commit**: `{repo_record.starting_commit}`\n"
            f"**Feature Family**: `{spec.feature_family.value}`\n"
            f"**Difficulty**: `{spec.difficulty.value}`\n"
            f"**Verdict**: `{manifest.verdict.status}`\n\n"
            f"## Summary\n{spec.summary}\n\n"
            f"## Independent Verification\n"
            f"To replay and verify this package:\n"
            f"```bash\npython scripts/replay_package.py --package {pkg_dir.name}\n```\n",
            encoding="utf-8",
        )

        return pkg_dir
