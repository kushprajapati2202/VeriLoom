"""Remove machine-specific paths (home, temp, workspace) from text stored in packages.

Validation logs capture pytest output, which includes absolute paths such as
C:\\Users\\<name>\\AppData\\... Packages are shared artefacts, so those are
replaced with neutral placeholders before they are written and checksummed.
"""

import os
import re
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional


def _variants(path: str) -> List[str]:
    """A path as it may appear: native, forward slashes, and JSON-escaped backslashes."""
    p = path.rstrip("\\/")
    out = {p, p.replace("\\", "/"), p.replace("\\", "\\\\")}
    return sorted((v for v in out if len(v) > 3), key=len, reverse=True)


def _roots(extra: Iterable[Path] = ()) -> List[tuple]:
    pairs = []
    for root, label in [*((Path(e), "<workspace>") for e in extra),
                        (Path(tempfile.gettempdir()), "<tmp>"),
                        (Path.home(), "<home>")]:
        candidates = {str(root)}
        try:
            candidates.add(str(root.resolve()))
        except OSError:
            pass
        for c in candidates:
            pairs += [(v, label) for v in _variants(c)]
    # Longest first so the temp dir (inside home) wins over home.
    return sorted(pairs, key=lambda t: len(t[0]), reverse=True)


def scrub_text(text: str, extra_roots: Optional[Iterable[Path]] = None) -> str:
    for needle, label in _roots(extra_roots or [Path.cwd()]):
        text = re.sub(re.escape(needle), label, text, flags=re.IGNORECASE)
    # Windows 8.3 short names of the user profile (e.g. C:\Users\ABCDEF~1.XYZ).
    text = re.sub(r"[A-Za-z]:(\\\\|\\|/)Users(\\\\|\\|/)[^\\/\"'\s]*~\d[^\\/\"'\s]*", "<home>", text)
    # Any remaining 8.3 short-name segment (also inside relative paths like ..\..\ABCDEF~1.XYZ).
    text = re.sub(r"(?<=[\\/])[A-Za-z0-9_$-]{1,6}~\d(?:\.[A-Za-z0-9]{1,3})?(?=[\\/\"'\s]|$)", "<user>", text)
    user = os.environ.get("USERNAME") or os.environ.get("USER")
    if user and len(user) > 2:
        text = re.sub(re.escape(user), "<user>", text, flags=re.IGNORECASE)
    return text
