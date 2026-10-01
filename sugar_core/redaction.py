"""Secret redaction shared by logs, activity events, run records, exports, and bug reports.

Redaction is defence in depth: known secret *values* registered at runtime are replaced
exactly, secret-looking *patterns* (provider key formats, bearer tokens, authorization
headers, cookies) are replaced heuristically, and secret-named *keys* in structures are
masked wholesale.
"""
from __future__ import annotations

import re
import threading
from typing import Any

REDACTED = "[REDACTED]"

_SECRET_KEY_PARTS = (
    "api_key", "apikey", "secret", "token", "password", "passwd", "cookie", "authorization",
    "bearer", "credential", "private_key", "session_id", "app_password",
)
# Keys that look secret but are safe metadata (a *reference* to a credential, never its value).
_SAFE_KEYS = {"credential_ref", "has_credential", "credential_type", "credential_status", "token_count",
              "max_tokens", "max_completion_tokens", "tokens", "prompt_tokens", "completion_tokens",
              "total_tokens", "input_tokens", "output_tokens", "secret_ref"}

_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),                       # Anthropic
    re.compile(r"sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{16,}"),  # OpenAI style
    re.compile(r"AAAAAAAAAAAAAAAAAAAAA[A-Za-z0-9%\-_]{20,}"),        # X/Twitter app bearer tokens
    re.compile(r"(?i)(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{12,}"),
    re.compile(r"(?i)(authorization|x-api-key|api-key|apikey|api_key|access_token|token|password|passwd|secret|app_password)"
               r"(\"?\s*[:=]\s*\"?)([^\s\"',;&}]{6,})"),
    re.compile(r"(?i)(set-cookie|cookie)(\s*:\s*)([^\r\n]{6,})"),
    re.compile(r"(?i)([?&](?:key|api_key|apikey|access_token|token)=)([^&\s\"']{6,})"),
]

_lock = threading.Lock()
_registered: set[str] = set()


def register_secret(value: str | None) -> None:
    """Remember a live secret value so it is masked wherever it appears from now on."""
    text = str(value or "").strip()
    if len(text) >= 6:
        with _lock:
            _registered.add(text)


def register_secrets(values: Any) -> None:
    items = values.values() if isinstance(values, dict) else values
    for value in items or []:
        if isinstance(value, str):
            register_secret(value)


def clear_registered() -> None:
    with _lock:
        _registered.clear()


def _is_secret_key(key: str) -> bool:
    lowered = key.casefold()
    if lowered in _SAFE_KEYS:
        return False
    return any(part in lowered for part in _SECRET_KEY_PARTS)


def redact_text(text: str, extra: list[str] | None = None) -> str:
    if not text:
        return text
    result = str(text)
    with _lock:
        secrets = set(_registered)
    secrets.update(s for s in (extra or []) if s and len(s) >= 6)
    for secret in sorted(secrets, key=len, reverse=True):
        if secret in result:
            result = result.replace(secret, REDACTED)
    for pattern in _PATTERNS:
        if pattern.groups >= 3:
            result = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", result)
        elif pattern.groups == 2:
            result = pattern.sub(lambda m: f"{m.group(1)}{REDACTED}", result)
        elif pattern.groups == 1:
            result = pattern.sub(lambda m: f"{m.group(1)} {REDACTED}", result)
        else:
            result = pattern.sub(REDACTED, result)
    return result


def redact(value: Any, *, key: str = "", extra: list[str] | None = None) -> Any:
    """Recursively redact strings, and mask any value stored under a secret-looking key."""
    if key and _is_secret_key(key) and value not in (None, "", False, True):
        if isinstance(value, (str, int, float)):
            return REDACTED
        if isinstance(value, dict):
            return {k: REDACTED if not isinstance(v, (dict, list)) else redact(v, key=k, extra=extra) for k, v in value.items()}
    if isinstance(value, str):
        return redact_text(value, extra)
    if isinstance(value, dict):
        return {str(k): redact(v, key=str(k), extra=extra) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact(v, key=key, extra=extra) for v in value]
    return value


def mask_for_display(value: str) -> str:
    """Show only that a secret exists and its tail, e.g. '••••••••a1b2'."""
    text = str(value or "")
    if not text:
        return ""
    return "••••••••" + text[-4:] if len(text) >= 12 else "••••••••"
