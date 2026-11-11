"""Package replay and independent verification."""

import json
from pathlib import Path
from typing import Tuple, List

from codeforge.contracts.manifest import PackageManifest
from codeforge.packaging.builder import PackageBuilder


class PackageVerifier:
    """Verifies SHA-256 package checksums and integrity independently."""

    @classmethod
    def verify_checksums(cls, pkg_dir: Path) -> Tuple[bool, List[str]]:
        pkg_dir = pkg_dir.resolve()
        manifest_file = pkg_dir / "manifest.json"
        if not manifest_file.exists():
            return False, ["manifest.json not found in package directory."]

        try:
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest = PackageManifest.model_validate(data)
        except Exception as e:
            return False, [f"Manifest parsing failed: {e}"]

        errors: List[str] = []
        for rel_path, expected_hash in manifest.checksums.items():
            full_path = pkg_dir / rel_path
            if not full_path.exists():
                errors.append(f"Missing packaged file: {rel_path}")
                continue
            actual_hash = PackageBuilder.sha256_file(full_path)
            if actual_hash != expected_hash:
                errors.append(
                    f"Checksum mismatch for {rel_path}: expected {expected_hash}, got {actual_hash}"
                )

        return len(errors) == 0, errors
