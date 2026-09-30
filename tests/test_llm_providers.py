import json
import os

import pytest

from _fake_llm import FakeLLMServer
from sugar_core import redaction
from sugar_core.credential_store import CredentialStore, load_env_file, parse_env_file
from sugar_core.llm_providers import (
    PROVIDER_TYPES, ProviderError, ProviderProfile, ProviderRegistry, call_with_retries, create_provider,
    validate_endpoint,
)

KEY = "sk-test-valid-key-1234567890"


def profile(server, **kw):
    base = dict(id="p1", name="Test", type="openai_compatible", endpoint=server.url, model="gpt-test")
    base.update(kw)
    return ProviderProfile(**base)


# ---- profiles and endpoint validation ------------------------------------------------------
def test_profile_hierarchy_and_credential_reference():
    p = ProviderProfile(type="openai", model="m", organization="org-1", project="proj-1")
    assert p.credential_ref == f"provider:{p.id}"
    assert p.effective_endpoint() == "https://api.openai.com/v1"
    local = ProviderProfile(type="local", endpoint="http://localhost:11434/v1", model="llama")
    assert local.credential_ref == ""                     # no credential class for local endpoints
    assert set(PROVIDER_TYPES) == {"openai", "openai_compatible", "anthropic", "arc", "local"}


@pytest.mark.parametrize("url,ok", [
    ("https://api.example.com/v1", True), ("http://localhost:1234/v1", True), ("http://192.168.1.5:8000", True),
    ("http://api.example.com/v1", False), ("ftp://x", False), ("https://user:pw@example.com", False), ("api.example.com", False),
])
def test_endpoint_validation(url, ok):
    if ok:
        validate_endpoint(url)
    else:
        with pytest.raises(ValueError):
            validate_endpoint(url)


def test_compatible_endpoint_requires_a_base_url():
    with pytest.raises(ValueError):
        ProviderProfile(type="openai_compatible", model="m")


def test_registry_never_persists_secrets_in_profile_file(tmp_path):
    store = CredentialStore(tmp_path, backend="file")
    registry = ProviderRegistry(tmp_path, store)
    p = registry.upsert(ProviderProfile(id="main", type="openai", model="gpt-x"), secret=KEY, make_default=True)
    text = (tmp_path / "providers.json").read_text()
    assert KEY not in text and "provider:main" in text
    assert registry.secret_for(p) == KEY
    public = p.public_dict(store)
    assert public["has_credential"] is True and KEY not in json.dumps(public)
    registry.upsert(p, secret=None)                          # None keeps the credential
    assert store.has("provider:main")
    registry.upsert(p, secret="")                            # '' removes it
    assert not store.has("provider:main")
    assert registry.delete("main") and registry.list() == []


# ---- connection test: every stage has a provider-specific error ---------------------------
def test_connection_success_runs_all_four_checks():
    with FakeLLMServer() as server:
        report = create_provider(profile(server), KEY).test_connection()
    assert report.ok
    assert [c.name for c in report.checks] == ["reachable", "credential", "model", "inference"]
    assert all(c.status == "ok" for c in report.checks)
    assert "gpt-test" in report.available_models


def test_rejected_credential_gives_actionable_provider_specific_error():
    with FakeLLMServer() as server:
        report = create_provider(profile(server), "sk-wrong-key-000000000000").test_connection()
    assert not report.ok and report.error_stage == "credential"
    assert "credential was rejected" in report.message
    assert "Settings → LLM Providers" in report.message


def test_missing_credential_is_reported_before_any_network_call():
    with FakeLLMServer() as server:
        report = create_provider(profile(server), "").test_connection()
        assert report.error_stage == "credential" and server.requests == []


def test_unknown_model_lists_available_models():
    with FakeLLMServer() as server:
        report = create_provider(profile(server, model="gpt-imaginary"), KEY).test_connection()
    assert report.error_stage == "model"
    assert "gpt-test" in report.message


def test_unreachable_endpoint():
    p = ProviderProfile(id="x", type="openai_compatible", endpoint="http://127.0.0.1:9/v1", model="m")
    p.advanced["timeout_seconds"] = 2
    report = create_provider(p, KEY).test_connection()
    assert report.error_stage == "reachable" and "Could not reach" in report.message


def test_server_without_model_listing_falls_back_to_inference_test():
    with FakeLLMServer() as server:
        server.list_status = 404
        report = create_provider(profile(server), KEY).test_connection()
    assert report.ok
    assert {c.name: c.status for c in report.checks}["model"] == "skipped"


def test_local_provider_needs_no_credential():
    with FakeLLMServer(require_auth=False) as server:
        p = ProviderProfile(id="l", type="local", endpoint=server.url, model="gpt-test")
        report = create_provider(p, "").test_connection()
    assert report.ok
    assert {c.name: c.status for c in report.checks}["credential"] == "skipped"


def test_rate_limit_and_quota_are_distinguished():
    with FakeLLMServer() as server:
        provider = create_provider(profile(server), KEY)
        server.status_queue.append((429, {"error": {"message": "slow down", "code": "rate_limit_exceeded"}}))
        with pytest.raises(ProviderError) as info:
            provider.chat([{"role": "user", "content": "hi"}])
        assert info.value.stage == "rate_limit" and info.value.retryable
        server.status_queue.append((429, {"error": {"message": "You exceeded your current quota", "code": "insufficient_quota"}}))
        with pytest.raises(ProviderError) as info:
            provider.chat([{"role": "user", "content": "hi"}])
        assert not info.value.retryable and "quota" in str(info.value)


def test_token_parameter_and_structured_output_negotiation():
    with FakeLLMServer(token_param="max_tokens", supports_schema=False, reply='{"a": 1}') as server:
        provider = create_provider(profile(server, type="openai_compatible"), KEY)
        data, result = provider.chat_json([{"role": "user", "content": "x"}], {"type": "object"})
        assert data == {"a": 1}
        # downgraded json_schema -> json_object -> none, and kept the token limit under the accepted name
        sent = [r["body"] for r in server.requests if r["method"] == "POST"]
        assert any("response_format" in b and b["response_format"]["type"] == "json_schema" for b in sent)
        assert "max_tokens" in sent[-1] and "max_completion_tokens" not in sent[-1]


def test_openai_type_uses_max_completion_tokens_and_sends_org_headers():
    with FakeLLMServer(token_param="max_completion_tokens") as server:
        p = profile(server, type="openai", endpoint=server.url, organization="org-9", project="proj-9")
        create_provider(p, KEY).chat([{"role": "user", "content": "hi"}])
        post = [r for r in server.requests if r["method"] == "POST"][0]
        assert "max_completion_tokens" in post["body"]
        assert post["headers"]["OpenAI-Organization"] == "org-9" and post["headers"]["OpenAI-Project"] == "proj-9"


def test_invalid_json_from_model_is_a_retryable_response_error():
    with FakeLLMServer(reply="I think the answer is: not json") as server:
        with pytest.raises(ProviderError) as info:
            create_provider(profile(server), KEY).chat_json([{"role": "user", "content": "x"}], {"type": "object"})
    assert info.value.stage == "response" and info.value.retryable


def test_observer_receives_redacted_call_records_and_optional_content():
    seen = []
    with FakeLLMServer(reply="hello") as server:
        provider = create_provider(profile(server), KEY, observer=seen.append, capture_content=True)
        provider.chat([{"role": "user", "content": f"my key is {KEY}"}], purpose="unit")
    record = seen[-1]
    assert record["kind"] == "provider.call" and record["purpose"] == "unit" and record["ok"]
    assert KEY not in json.dumps(record)


def test_call_with_retries_only_retries_retryable_errors():
    calls, delays = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ProviderError("rate", stage="rate_limit", retryable=True)
        return "done"

    assert call_with_retries(flaky, attempts=3, base_delay=1, sleep=delays.append) == "done"
    assert delays == [1, 2]
    with pytest.raises(ProviderError):
        call_with_retries(lambda: (_ for _ in ()).throw(ProviderError("bad key", stage="credential")), attempts=3, sleep=delays.append)


def test_translate_uses_untrusted_content_framing():
    with FakeLLMServer(reply="hello world") as server:
        result = create_provider(profile(server), KEY).translate("مرحبا بالعالم", "English", source_language="Arabic")
        body = [r["body"] for r in server.requests if r["method"] == "POST"][0]
    assert result.text == "hello world"
    assert "untrusted" in body["messages"][0]["content"] and "<content>" in body["messages"][1]["content"]


# ---- credential store ----------------------------------------------------------------------
def test_file_store_is_owner_only_and_atomic(tmp_path):
    store = CredentialStore(tmp_path / "home", backend="file")
    store.set("provider:a", KEY)
    path = tmp_path / "home" / "credentials.json"
    if os.name != "nt":
        assert oct(path.stat().st_mode & 0o777) == "0o600"
        assert oct((tmp_path / "home").stat().st_mode & 0o777) == "0o700"
    assert store.get("provider:a") == KEY and store.refs("provider:") == ["provider:a"]
    assert store.source_of("provider:a") == "file"
    store.delete("provider:a")
    assert store.get("provider:a") == "" and store.source_of("provider:a") == ""
    with pytest.raises(Exception):
        store.set("provider:a", "   ")


def test_environment_overrides_stored_credentials(tmp_path, monkeypatch):
    store = CredentialStore(tmp_path, backend="file")
    store.set("platform:x_bearer_token", "stored-value-123456")
    monkeypatch.setenv("SUGAR_X_BEARER_TOKEN", "env-value-123456789")
    assert store.get("platform:x_bearer_token") == "env-value-123456789"
    assert store.source_of("platform:x_bearer_token") == "environment"
    assert store.platform_secrets()["x_bearer_token"] == "env-value-123456789"
    monkeypatch.setenv("SUGAR_CRED_PROVIDER_MAIN", "per-ref-value-123456")
    assert store.get("provider:main") == "per-ref-value-123456"


def test_env_file_loading_only_accepts_sugar_variables(tmp_path, monkeypatch):
    env = tmp_path / ".env.local"
    env.write_text("# comment\nexport SUGAR_LLM_API_KEY='sk-from-env-file-123456'\nPATH=/evil\nSUGAR_X_BEARER_TOKEN=abc123456789 # trailing\n")
    monkeypatch.delenv("SUGAR_LLM_API_KEY", raising=False)
    monkeypatch.delenv("SUGAR_X_BEARER_TOKEN", raising=False)
    loaded = load_env_file(env)
    assert sorted(loaded) == ["SUGAR_LLM_API_KEY", "SUGAR_X_BEARER_TOKEN"]
    assert os.environ["SUGAR_X_BEARER_TOKEN"] == "abc123456789"
    assert os.environ["PATH"] != "/evil"
    assert redaction.redact_text("token sk-from-env-file-123456 leaked") == "token [REDACTED] leaked"
    assert parse_env_file('A="x y"\n1BAD=z\n') == {"A": "x y"}


def test_legacy_env_key_is_used_when_profile_has_no_stored_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("SUGAR_LLM_API_KEY", "sk-legacy-env-key-123456")
    registry = ProviderRegistry(tmp_path, CredentialStore(tmp_path, backend="memory"))
    p = registry.upsert(ProviderProfile(id="main", type="openai", model="m"))
    assert registry.secret_for(p) == "sk-legacy-env-key-123456"


# ---- redaction -----------------------------------------------------------------------------
def test_redaction_patterns_and_secret_named_keys():
    text = ("Authorization: Bearer abcdef1234567890abcdef and sk-proj-abcdefghijklmnop1234 and sk-ant-api03-abcdefgh12345678 "
            "url https://x.test/a?api_key=SECRETVALUE99&b=1 cookie: SUB=abcdef123456; other")
    out = redaction.redact_text(text)
    for leaked in ("abcdef1234567890abcdef", "sk-proj-abcdefghijklmnop1234", "sk-ant-api03-abcdefgh12345678", "SECRETVALUE99", "SUB=abcdef123456"):
        assert leaked not in out
    data = redaction.redact({"model": "m", "api_key": "hunter2hunter2", "nested": {"weibo_cookie": "c=1234567", "max_tokens": 10,
                                                                                    "credential_ref": "provider:a"},
                             "headers": [{"Authorization": "Bearer zzzzzzzzzzzzzzzz"}]})
    assert data["api_key"] == "[REDACTED]" and data["nested"]["weibo_cookie"] == "[REDACTED]"
    assert data["nested"]["max_tokens"] == 10 and data["nested"]["credential_ref"] == "provider:a"
    assert "zzzzzzzz" not in json.dumps(data)
    assert redaction.mask_for_display("sk-abcdefghijklmnop") == "••••••••mnop"
