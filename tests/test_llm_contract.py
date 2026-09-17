from types import SimpleNamespace

import pytest

from sugar_core.llm import LLMConfig, cached_chat, create_client, parse_json_object, translate_text


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
