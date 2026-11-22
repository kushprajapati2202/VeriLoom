"""Record and replay model responses.

Recording wraps a real provider and saves every response to a JSONL file.
Replaying feeds those responses back so a run can be reproduced without an API
key or network. Only the model's text is cached: specification checks, the
sandbox gates (fail-before, pass-after, regression, mutation, clarity) and
packaging all execute live, so a replayed run is still independently validated.
"""

import hashlib
import json
from pathlib import Path
from typing import List, Optional

from veriloom.llm.provider import LLMProvider


def _key(prompt: str, system_prompt: Optional[str]) -> str:
    return hashlib.sha256(((system_prompt or "") + "\x00" + prompt).encode("utf-8")).hexdigest()


class RecordingProvider(LLMProvider):
    def __init__(self, inner: LLMProvider, path: Path):
        self.inner = inner
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def last_model_used(self):
        return getattr(self.inner, "last_model_used", None) or getattr(self.inner, "model", None)

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        text = self.inner.generate(prompt, system_prompt)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "key": _key(prompt, system_prompt),
                "model": self.last_model_used,
                "prompt_head": prompt[:200],
                "response": text,
            }) + "\n")
        return text


class ReplayProvider(LLMProvider):
    """Serves recorded responses: exact prompt match first, otherwise in recorded order.

    Prompts can differ slightly between runs (for example the list of tasks
    already in the output folder), so ordered fallback keeps replays robust.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"replay file not found: {self.path}")
        self.entries: List[dict] = [
            json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        self._used = [False] * len(self.entries)
        self.model = "replay"
        self.last_model_used: Optional[str] = None

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        k = _key(prompt, system_prompt)
        idx = next((i for i, e in enumerate(self.entries) if not self._used[i] and e["key"] == k), None)
        if idx is None:
            idx = next((i for i, used in enumerate(self._used) if not used), None)
        if idx is None:
            raise RuntimeError(f"replay file {self.path} has no more recorded responses")
        self._used[idx] = True
        entry = self.entries[idx]
        self.last_model_used = f"replay of {entry.get('model') or 'unknown'}"
        return entry["response"]
