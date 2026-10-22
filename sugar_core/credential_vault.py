"""Compatibility responses for removed OS credential vault operations.

No import, discovery, read, write, or deletion of an OS credential store occurs.
Existing Keychain entries are left untouched.
"""
from __future__ import annotations

from typing import Any

_REMOVED = "Keychain and OS credential vault access has been removed from this build. Enter credentials manually in Settings."


def vault_status() -> dict[str, Any]:
    return {"available": False, "message": _REMOVED}


def load_credentials() -> dict[str, str]:
    return {}


def save_credentials(credentials: dict[str, Any]) -> dict[str, Any]:
    raise RuntimeError(_REMOVED)


def delete_credentials(names: Any = None) -> dict[str, Any]:
    raise RuntimeError(_REMOVED)
