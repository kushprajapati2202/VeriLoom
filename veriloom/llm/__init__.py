"""LLM Integration Package."""

from veriloom.llm.provider import (
    LLMProvider,
    GeminiProvider,
    ClaudeProvider,
    OpenAIProvider,
    OllamaProvider,
    OfflineFallbackProvider,
)
from veriloom.llm.factory import LLMFactory
from veriloom.llm.recording import RecordingProvider, ReplayProvider
from veriloom.llm.prompts import (
    TASK_SPECIFICATION_PROMPT,
    REFERENCE_SOLUTION_PROMPT,
    FEATURE_TEST_PROMPT,
)

__all__ = [
    "LLMProvider",
    "GeminiProvider",
    "ClaudeProvider",
    "OpenAIProvider",
    "OllamaProvider",
    "OfflineFallbackProvider",
    "LLMFactory",
    "RecordingProvider",
    "ReplayProvider",
    "TASK_SPECIFICATION_PROMPT",
    "REFERENCE_SOLUTION_PROMPT",
    "FEATURE_TEST_PROMPT",
]

