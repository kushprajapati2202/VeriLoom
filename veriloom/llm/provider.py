"""Pluggable LLM providers (Gemini, Claude, OpenAI, Ollama, and Offline Fallback)."""

import json
import os
import re
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

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self.endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": system_prompt}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will strictly follow all instructions."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        with httpx.Client(timeout=45.0) as client:
            resp = client.post(
                self.endpoint,
                headers={"Content-Type": "application/json"},
                json={"contents": contents, "generationConfig": {"temperature": 0.2}},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]


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

        with httpx.Client(timeout=45.0) as client:
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

        with httpx.Client(timeout=45.0) as client:
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

        with httpx.Client(timeout=60.0) as client:
            resp = client.post(self.endpoint, json=body)
            resp.raise_for_status()
            data = resp.json()
            return data["response"]

