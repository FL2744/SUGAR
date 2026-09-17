from types import SimpleNamespace

import pytest

from sugar_core.errors import error_payload
from sugar_core.llm import (
    LLMBudget,
    LLMBudgetExceeded,
    LLMConfig,
    cached_chat,
    create_client,
    parse_json_object,
    translate_text,
)


class _FakeClient:
    def __init__(self, content: str):
        self.content = content
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


def test_llm_client_requires_a_runtime_key():
    with pytest.raises(ValueError, match="API key"):
        create_client(LLMConfig(api_key=""))


def test_cached_chat_preserves_roles_and_returns_model_text():
    client = _FakeClient("answer")
    result = cached_chat(
        client,
        LLMConfig(model="test-model", api_key="runtime-only"),
        None,
        "unit-test",
        "system",
        "user",
        max_tokens=17,
    )
    assert result == "answer"
    assert client.calls[0]["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "user"},
    ]
    assert client.calls[0]["max_tokens"] == 17
    assert client.calls[0]["temperature"] == 0


def test_translation_skips_empty_input_and_json_parser_handles_fenced_object():
    client = _FakeClient("translated")
    config = LLMConfig(model="test-model", api_key="runtime-only")
    assert translate_text(client, config, None, "   ") == ""
    assert translate_text(client, config, None, "hello") == "translated"
    assert parse_json_object('```json\n{"ok": true}\n```') == {"ok": True}


def test_json_parser_rejects_non_object_payload():
    with pytest.raises(ValueError, match="JSON object"):
        parse_json_object("[1, 2]")


def test_run_budget_refuses_a_request_before_it_can_exceed_token_ceiling():
    client = _FakeClient("answer")
    budget = LLMBudget(max_total_tokens=21)
    config = LLMConfig(model="test-model", api_key="runtime-only")

    assert cached_chat(client, config, None, "first", "system", "user", max_tokens=10, budget=budget) == "answer"
    with pytest.raises(LLMBudgetExceeded, match="token budget exceeded"):
        cached_chat(client, config, None, "second", "system", "user", max_tokens=10, budget=budget)
    assert len(client.calls) == 1
    assert budget.as_dict()["request_count"] == 1


def test_cost_budget_requires_explicit_provider_rates_and_tracks_cache_hits():
    with pytest.raises(ValueError, match="cost_per_1k_tokens"):
        LLMBudget.from_config(LLMConfig(api_key="runtime-only", max_cost_usd=1.0))

    client = _FakeClient("answer")
    budget = LLMBudget(
        max_total_tokens=100, max_cost_usd=0.01, input_cost_per_1k_tokens=0.01, output_cost_per_1k_tokens=0.02
    )
    config = LLMConfig(model="test-model", api_key="runtime-only")
    cache = {}

    class _Cache:
        def get(self, key):
            return cache.get(key)

        def set(self, key, value):
            cache[key] = value

    assert cached_chat(client, config, _Cache(), "same", "system", "user", max_tokens=10, budget=budget) == "answer"
    assert cached_chat(client, config, _Cache(), "same", "system", "user", max_tokens=10, budget=budget) == "answer"
    usage = budget.as_dict()
    assert usage["request_count"] == 1
    assert usage["cache_hits"] == 1
    assert usage["total_tokens"] > 0


def test_budget_counts_success_once_when_cache_write_fails():
    class _BrokenCache:
        def get(self, _key):
            return None

        def set(self, _key, _value):
            raise OSError("cache unavailable")

    client = _FakeClient("answer")
    budget = LLMBudget(max_total_tokens=100)
    config = LLMConfig(model="test-model", api_key="runtime-only")

    with pytest.raises(OSError, match="cache unavailable"):
        cached_chat(client, config, _BrokenCache(), "same", "system", "user", max_tokens=10, budget=budget)

    usage = budget.as_dict()
    assert usage["request_count"] == 1
    assert usage["total_tokens"] > 0
    assert len(client.calls) == 1


def test_budget_exhaustion_has_a_stable_structured_error_code():
    payload = error_payload(LLMBudgetExceeded("LLM token budget exceeded: limit=1"))
    assert payload["code"] == "llm_budget_exceeded"
    assert payload["retryable"] is False
