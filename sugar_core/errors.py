"""Stable, redacted error contracts for CLI and desktop integrations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

ERROR_CODES = {
    "config_invalid",
    "input_missing",
    "input_invalid",
    "access_denied",
    "rate_limited",
    "network_failure",
    "output_failure",
    "dependency_failure",
    "internal_error",
}

_SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)((?:token|cookie|password|api[_ -]?key|secret)\s*[:=]\s*)[^\s,;]+"),
)


def redact_text(value: Any, secrets: Mapping[str, str] | None = None) -> str:
    """Return an error string that does not disclose known credentials or session values."""

    text = str(value or "")
    for secret in (secrets or {}).values():
        if secret:
            text = text.replace(str(secret), "[REDACTED]")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(r"\1[REDACTED]", text)
    return text[:2000]


def _status_code(error: BaseException) -> int | None:
    response = getattr(error, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def classify_error(error: BaseException) -> tuple[str, bool, str]:
    """Map arbitrary implementation exceptions to a small stable product contract."""

    status = _status_code(error)
    name = type(error).__name__.casefold()
    text = str(error).casefold()
    if status == 429 or "rate limit" in text or "rate-limited" in text:
        return "rate_limited", True, "Wait and retry later; preserve the checkpoint if this is a harvest."
    if status in {401, 403} or "access" in name or "credential" in text or "login" in text:
        return "access_denied", False, "Check the documented access mode and credentials; do not bypass the gate."
    if isinstance(error, (FileNotFoundError, NotADirectoryError)):
        return "input_missing", False, "Check the input path and workspace registration."
    if isinstance(error, (PermissionError, IsADirectoryError)):
        return "output_failure", False, "Check output permissions and whether the path is a file or directory."
    if isinstance(error, (json_error_types())):
        return "config_invalid", False, "Provide a valid JSON object with supported operation fields."
    if isinstance(error, (ValueError, TypeError)):
        return "input_invalid", False, "Check the operation arguments and input schema."
    if "timeout" in name or "connection" in name or "request" in name or "dns" in text:
        return (
            "network_failure",
            True,
            "Retry when the public endpoint is available; record partial coverage explicitly.",
        )
    if "import" in name or "module" in text:
        return "dependency_failure", False, "Recreate the supported environment and verify the installed package set."
    return "internal_error", False, "Capture the redacted diagnostics and report the affected operation."


def json_error_types() -> tuple[type[BaseException], ...]:
    """Import JSON errors lazily so the error module stays dependency-free."""

    import json

    return (json.JSONDecodeError,)


def error_payload(error: BaseException, *, secrets: Mapping[str, str] | None = None) -> dict[str, Any]:
    code, retryable, remediation = classify_error(error)
    return {
        "code": code,
        "message": redact_text(error, secrets),
        "exception": type(error).__name__,
        "retryable": retryable,
        "remediation": remediation,
    }


def redacted_path(path: str | Path) -> str:
    """Represent a path without exposing a user's home directory in diagnostics."""

    value = str(path)
    try:
        return str(Path(value).resolve().relative_to(Path.home().resolve()))
    except (ValueError, OSError):
        return value
