"""Pluggable LLM providers (Gemini, Claude, OpenAI, Ollama, and Offline Fallback)."""

import json
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import httpx


class LLMProvider(ABC):
    """Abstract interface for pluggable AI model backends."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text completion from model."""
        pass

    def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Generate structured JSON from model with fallback parsing."""
        raw = self.generate(prompt, system_prompt)
        # Clean markdown codeblocks
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback: regex search for outer JSON object
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise ValueError(f"Failed to parse model output as JSON: {raw[:200]}...")


class OfflineFallbackProvider(LLMProvider):
    """Deterministic offline fallback provider when no external API credentials are set."""

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if "TASK SPECIFICATION" in prompt or "RESPOND IN VALID JSON" in prompt:
            return json.dumps({
                "title": "Configurable Domain Policy & Boundary Checks",
                "summary": "Introduce strict boundary validation and structured error handling.",
                "requirements": [
                    {
                        "id": "REQ-001",
                        "statement": "State-mutating operations must validate inputs against defined boundary limits.",
                        "acceptance_criteria": [
                            "Rejects negative boundary values with structured error code INVALID_FIELD_VALUE.",
                            "Accepts valid inputs within acceptable range and executes normally."
                        ],
                        "priority": "must"
                    },
                    {
                        "id": "REQ-002",
                        "statement": "Structured error responses must include offending parameter name.",
                        "acceptance_criteria": [
                            "Error object includes offending field name and reason."
                        ],
                        "priority": "must"
                    }
                ],
                "constraints": ["Must execute entirely in-process without remote network calls."],
                "out_of_scope": ["External database migrations."],
                "edge_cases": ["Zero boundary condition (0).", "Extremely large integer overflow."],
                "assumptions": ["Execution environment is thread-safe."]
            })
        elif "REFERENCE_SOLUTION_PROMPT" in prompt or "reference solution" in prompt.lower():
            return (
                "class ValidationError(Exception):\n"
                "    def __init__(self, message, code='INVALID_FIELD_VALUE', field=None):\n"
                "        super().__init__(message); self.code = code; self.field = field\n\n"
                "def validate_boundary_constraints(value, min_limit=0, max_limit=1000000, field_name='value'):\n"
                "    if value is None or value < min_limit:\n"
                "        raise ValidationError(f'Value {value} below minimum {min_limit}', code='INVALID_FIELD_VALUE', field=field_name)\n"
                "    return True\n"
            )
        else:
            return "# Offline fallback test code\nimport pytest\n"


class GeminiProvider(LLMProvider):
    """Google Gemini API Provider."""

    BASE = "https://generativelanguage.googleapis.com/v1beta/models"
    RETRYABLE = {429, 500, 502, 503, 504}

    def __init__(self, api_key: str, model: str = "gemini-3.5-flash", fallback_models: Optional[list] = None):
        self.api_key = api_key
        self.model = model
        # Models tried in order when the primary is overloaded or out of quota.
        self.models = [model] + [m for m in (fallback_models or []) if m and m != model]
        self.last_model_used: Optional[str] = None

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        body: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            # Authoring replies carry a whole file, a test module and mutants.
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 65536},
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        # The key travels in a header, never in the URL, so it cannot leak into
        # exception messages or the authoring logs saved inside task packages.
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
        last_error = "no attempt made"
        with httpx.Client(timeout=300.0) as client:
            for attempt in range(4):
                for model in self.models:
                    try:
                        resp = client.post(f"{self.BASE}/{model}:generateContent", headers=headers, json=body)
                    except httpx.TransportError as e:
                        last_error = f"{model}: {type(e).__name__}"
                        continue
                    if resp.status_code == 200:
                        data = resp.json()
                        cand = (data.get("candidates") or [{}])[0]
                        if cand.get("finishReason") == "MAX_TOKENS":
                            last_error = f"{model}: response truncated (MAX_TOKENS)"
                            continue
                        parts = cand.get("content", {}).get("parts", [])
                        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                        if text.strip():
                            self.last_model_used = model
                            return text
                        last_error = f"{model}: empty response"
                        continue
                    last_error = f"{model}: HTTP {resp.status_code}"
                    if resp.status_code not in self.RETRYABLE and resp.status_code != 404:
                        raise RuntimeError(f"Gemini request failed ({last_error}): {resp.text[:300]}")
                time.sleep(min(60, 8 * (2 ** attempt)))
        raise RuntimeError(f"Gemini unavailable after retries ({last_error})")


class ClaudeProvider(LLMProvider):
    """Anthropic Claude API Provider."""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key
        self.model = model
        self.endpoint = "https://api.anthropic.com/v1/messages"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            body["system"] = system_prompt

        with httpx.Client(timeout=300.0) as client:
            resp = client.post(self.endpoint, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]


class OpenAIProvider(LLMProvider):
    """OpenAI / Compatible Provider (GPT-4o, DeepSeek, Local VLLM)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
    ):
        self.api_key = api_key
        self.model = model
        self.endpoint = f"{base_url.rstrip('/')}/chat/completions"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        with httpx.Client(timeout=300.0) as client:
            resp = client.post(
                self.endpoint,
                headers=headers,
                json={"model": self.model, "messages": messages, "temperature": 0.2},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


class OllamaProvider(LLMProvider):
    """Local Ollama Provider (100% free local models like Llama 3, Qwen, DeepSeek)."""

    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3:latest"):
        self.endpoint = f"{host.rstrip('/')}/api/generate"
        self.model = model

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        body = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        if system_prompt:
            body["system"] = system_prompt

        with httpx.Client(timeout=600.0) as client:
            resp = client.post(self.endpoint, json=body)
            resp.raise_for_status()
            data = resp.json()
            return data["response"]

