from pathlib import Path
from types import SimpleNamespace

import pytest

from sugar_core.errors import classify_error, error_payload, redacted_path, sensitive_values
from sugar_core.utils import atomic_path


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (FileNotFoundError("missing"), "input_missing", False),
        (PermissionError("denied"), "output_failure", False),
        (ValueError("bad input"), "input_invalid", False),
        (TypeError("bad type"), "input_invalid", False),
        (ConnectionError("connection failed"), "network_failure", True),
        (RuntimeError("dependency module unavailable"), "dependency_failure", False),
        (RuntimeError("unexpected"), "internal_error", False),
    ],
)
def test_error_classification_is_stable(error, code, retryable):
    actual_code, actual_retryable, remediation = classify_error(error)
    assert actual_code == code
    assert actual_retryable is retryable
    assert remediation


def test_error_classification_uses_http_status_and_access_name():
    rate_limited = RuntimeError("server response")
    rate_limited.response = SimpleNamespace(status_code=429)
    assert classify_error(rate_limited)[:2] == ("rate_limited", True)
    assert classify_error(RuntimeError("credential rejected"))[0] == "access_denied"


def test_error_payload_truncates_untrusted_messages():
    payload = error_payload(RuntimeError("x" * 3000))
    assert len(payload["message"]) == 2000


def test_sensitive_config_values_are_found_without_retaining_config_shape():
    values = sensitive_values({"llm": {"api_key": "config-secret"}, "terms": ["token is a topic"]})
    assert values == {"config.llm.api_key": "config-secret"}


def test_keyboard_interrupt_has_a_stable_cancellation_contract():
    payload = error_payload(KeyboardInterrupt())
    assert payload["code"] == "cancelled"
    assert payload["retryable"] is False
    assert payload["message"] == "Operation cancelled by user."


def test_redacted_path_hides_home_prefix():
    home_path = Path.home() / "private" / "notes.txt"
    assert "private" in redacted_path(home_path)
    assert str(Path.home()) not in redacted_path(home_path)
    assert redacted_path(Path("C:/Windows/System32")) == "C:\\Windows\\System32"


def test_atomic_path_publishes_on_success_and_cleans_up_on_failure(tmp_path: Path):
    target = tmp_path / "result.txt"
    with atomic_path(target) as temporary:
        temporary.write_text("complete", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "complete"
    assert list(tmp_path.glob(".*.tmp")) == []

    with pytest.raises(RuntimeError):
        with atomic_path(target) as temporary:
            temporary.write_text("discarded", encoding="utf-8")
            raise RuntimeError("abort")
    assert target.read_text(encoding="utf-8") == "complete"
    assert list(tmp_path.glob(".*.tmp")) == []
