"""Unit tests run offline by default so they are fast, free and deterministic.

Set VERILOOM_LIVE_TESTS=1 to let tests use the LLM provider configured in .env.
"""

import os

import pytest


@pytest.fixture(autouse=True)
def _offline_llm(monkeypatch):
    if os.getenv("VERILOOM_LIVE_TESTS") != "1":
        monkeypatch.setenv("VERILOOM_LLM_PROVIDER", "offline")
