from veriloom.llm import LLMFactory, OfflineFallbackProvider
from veriloom.llm.provider import GeminiProvider
from veriloom.validation.clarity import unexplained_literals

TEST_CODE = '''
def test_totals():
    cart.add("BOOK", 2, price=12.5)
    assert cart.subtotal() == 25.0          # 2 x 12.5: derivable from inputs
    assert tax(10.0, rate=0.08) == 0.8      # 10.0 x 0.08: derivable
    assert discount(cart, "SAVE") == 7.5    # stated in the task
    assert magic() == 42.0                  # nowhere: must be flagged
'''


def test_clarity_flags_only_underivable_values():
    assert unexplained_literals(TEST_CODE, "Coupon SAVE takes 7.5 off.") == ["42.0"]


def test_clarity_passes_when_value_is_stated():
    assert unexplained_literals(TEST_CODE, "SAVE takes 7.5 off; magic() returns 42.0.") == []


def test_ollama_host_does_not_hijack_missing_key(monkeypatch):
    monkeypatch.setenv("VERILOOM_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    assert isinstance(LLMFactory.get_provider(), OfflineFallbackProvider)


def test_gemini_key_never_in_url(monkeypatch):
    monkeypatch.setenv("VERILOOM_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "secret-test-key")
    p = LLMFactory.get_provider()
    assert isinstance(p, GeminiProvider)
    assert "secret-test-key" not in GeminiProvider.BASE
    assert not any("secret-test-key" in m for m in p.models)


def test_behaviour_details_string_is_not_split_into_characters():
    from veriloom.contracts.task_spec import as_str_list
    assert as_str_list("Tier 1 gives 5%.\nTier 2 gives 10%.") == ["Tier 1 gives 5%.", "Tier 2 gives 10%."]


def test_mutant_find_tolerates_reindented_snippet():
    from veriloom.validation.sandbox import apply_mutant
    src = "def f(x):\n    if x > 10:\n        return 1\n    return 0\n"
    mutated, n = apply_mutant(src, "if x > 10:\n    return 1", "if x >= 10:\n    return 1")
    assert n == 1 and mutated == src.replace("x > 10", "x >= 10")


def test_mutant_find_rejects_ambiguous_snippet():
    from veriloom.validation.sandbox import apply_mutant
    assert apply_mutant("return 1\nreturn 1\n", "return 1", "return 2") == (None, 2)
