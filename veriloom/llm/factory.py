"""Factory detecting and initializing configured LLM providers."""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from veriloom.llm.provider import (
    LLMProvider,
    GeminiProvider,
    ClaudeProvider,
    OpenAIProvider,
    OllamaProvider,
    OfflineFallbackProvider,
)


class LLMFactory:
    """Detects available model credentials and instantiates the appropriate LLM provider."""

    @classmethod
    def get_provider(
        cls,
        provider_name: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> LLMProvider:
        # 1. Explicit provider requested
        name = (provider_name or os.getenv("VERILOOM_LLM_PROVIDER", "")).lower()

        if name == "replay":
            from pathlib import Path
            from veriloom.llm.recording import ReplayProvider
            return ReplayProvider(Path(os.environ["VERILOOM_REPLAY_FILE"]))

        if name == "gemini" or (not name and os.getenv("GEMINI_API_KEY")):
            key = api_key or os.getenv("GEMINI_API_KEY")
            if key:
                model = model_name or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
                fallbacks = [m.strip() for m in os.getenv(
                    "GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.1-flash-lite"
                ).split(",")]
                return GeminiProvider(api_key=key, model=model, fallback_models=fallbacks)

        if name in {"anthropic", "claude"} or (not name and os.getenv("ANTHROPIC_API_KEY")):
            key = api_key or os.getenv("ANTHROPIC_API_KEY")
            if key:
                model = model_name or os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
                return ClaudeProvider(api_key=key, model=model)

        if name == "openai" or (not name and os.getenv("OPENAI_API_KEY")):
            key = api_key or os.getenv("OPENAI_API_KEY")
            if key:
                model = model_name or os.getenv("OPENAI_MODEL", "gpt-4o")
                base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
                return OpenAIProvider(api_key=key, model=model, base_url=base_url)

        # Ollama only when explicitly selected: OLLAMA_HOST alone (it is in .env.example)
        # must not hijack a run whose configured provider simply has no key.
        if name == "ollama":
            host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            model = model_name or os.getenv("OLLAMA_MODEL", "llama3:latest")
            return OllamaProvider(host=host, model=model)

        # 2. Default to deterministic offline fallback
        return OfflineFallbackProvider()

