from __future__ import annotations

from types import SimpleNamespace

from sugar_core.llm import LLMConfig, cached_chat


class _CreateSequence:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    def create(self, **_kwargs):
        self.calls += 1
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=value))])


class _Client:
    def __init__(self, values):
        self.chat = SimpleNamespace(completions=_CreateSequence(values))


class FakeRateLimitError(Exception):
    status_code = 429

    def __init__(self, retry_after_s: float):
        super().__init__("rate limited")
        self.body = {"error": {"reason": "capacity", "retry_after_s": retry_after_s}}
        self.response = SimpleNamespace(status_code=429, headers={})


def test_cached_chat_honors_arc_retry_after(monkeypatch):
    waits = []
    monkeypatch.setattr("sugar_core.llm.time.sleep", waits.append)
    client = _Client([FakeRateLimitError(7), "ok"])
    result = cached_chat(
        client,
        LLMConfig(provider="arc", model="gpt-oss-120b", api_key="test"),
        None,
        "test",
        "system",
        "user",
    )
    assert result == "ok"
    assert waits == [7.0]
    assert client.chat.completions.calls == 2


def test_cached_chat_caps_server_wait(monkeypatch):
    waits = []
    monkeypatch.setattr("sugar_core.llm.time.sleep", waits.append)
    client = _Client([FakeRateLimitError(900), "ok"])
    result = cached_chat(
        client,
        LLMConfig(provider="arc", model="gpt-oss-120b", api_key="test"),
        None,
        "test",
        "system",
        "user",
        max_retry_wait_seconds=30,
    )
    assert result == "ok"
    assert waits == [30.0]


def test_cached_chat_keeps_exponential_backoff_for_other_errors(monkeypatch):
    waits = []
    monkeypatch.setattr("sugar_core.llm.time.sleep", waits.append)
    client = _Client([RuntimeError("temporary"), RuntimeError("temporary"), "ok"])
    result = cached_chat(
        client,
        LLMConfig(api_key="test"),
        None,
        "test",
        "system",
        "user",
    )
    assert result == "ok"
    assert waits == [1.0, 2.0]
