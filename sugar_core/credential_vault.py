"""OS-backed provider credential storage for the local desktop application.

This module deliberately has no file-based fallback. If an operating-system
credential store is unavailable, callers must leave credentials in session
memory and explain how to enable a supported vault.
"""
from __future__ import annotations

from typing import Any


SERVICE_NAME = "SUGAR Research Desktop"
SECRET_NAMES = (
    "llm_api_key",
    "x_bearer_token",
    "bluesky_identifier",
    "bluesky_app_password",
    "mastodon_token",
    "weibo_cookie",
)
_OS_BACKEND_PREFIXES = (
    "keyring.backends.windows",
    "keyring.backends.macos",
    "keyring.backends.secretservice",
    "keyring.backends.kwallet",
    "keyring.backends.libsecret",
)


def _keyring_backend():
    try:
        import keyring
    except ImportError as exc:
        raise RuntimeError(
            "Secure credential storage is unavailable because the keyring package is not installed."
        ) from exc

    backend = keyring.get_keyring()
    module = type(backend).__module__.casefold()
    try:
        priority = float(backend.priority)
    except (AttributeError, TypeError, ValueError):
        priority = 0.0
    if priority <= 0 or not module.startswith(_OS_BACKEND_PREFIXES):
        raise RuntimeError(
            "No supported operating-system credential vault is available. "
            "SUGAR will keep credentials in memory for this session only."
        )
    return keyring


def vault_status() -> dict[str, Any]:
    try:
        keyring = _keyring_backend()
    except RuntimeError as exc:
        return {"available": False, "message": str(exc)}
    backend = keyring.get_keyring()
    return {
        "available": True,
        "backend": type(backend).__name__,
        "stored": {
            name: bool(keyring.get_password(SERVICE_NAME, name))
            for name in SECRET_NAMES
        },
    }


def load_credentials() -> dict[str, str]:
    keyring = _keyring_backend()
    return {
        name: value
        for name in SECRET_NAMES
        if (value := keyring.get_password(SERVICE_NAME, name))
    }


def save_credentials(credentials: dict[str, Any]) -> dict[str, Any]:
    keyring = _keyring_backend()
    unknown = sorted(set(credentials) - set(SECRET_NAMES))
    if unknown:
        raise ValueError(f"Unsupported credential field(s): {', '.join(unknown)}")
    saved = []
    for name in SECRET_NAMES:
        value = credentials.get(name)
        if value is None or value == "":
            continue
        if not isinstance(value, str) or len(value) > 32_768:
            raise ValueError(f"{name} must be a string no longer than 32,768 characters.")
        keyring.set_password(SERVICE_NAME, name, value)
        saved.append(name)
    return {"saved": saved, "count": len(saved)}


def delete_credentials(names: Any = None) -> dict[str, Any]:
    keyring = _keyring_backend()
    selected = list(SECRET_NAMES if names is None else names)
    unknown = sorted(set(selected) - set(SECRET_NAMES))
    if unknown:
        raise ValueError(f"Unsupported credential field(s): {', '.join(unknown)}")
    deleted = []
    for name in selected:
        if keyring.get_password(SERVICE_NAME, name) is None:
            continue
        try:
            keyring.delete_password(SERVICE_NAME, name)
        except Exception as exc:
            # Keep going so the user can remove every available entry in one action.
            if type(exc).__name__ not in {"PasswordDeleteError", "PasswordNotFoundError"}:
                raise RuntimeError(f"Could not remove saved {name} from the OS credential vault.") from exc
        deleted.append(name)
    return {"deleted": deleted, "count": len(deleted)}
