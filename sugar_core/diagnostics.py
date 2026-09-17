"""Redacted diagnostics for support and reproducibility checks."""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import sys
import zipfile
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Mapping

from .collector_registry import collector_capabilities
from .errors import error_payload, redacted_path
from .utils import atomic_path, atomic_write_text, runtime_dependency_versions
from .workspace import SugarWorkspace

DIAGNOSTICS_SCHEMA_VERSION = 1
DIAGNOSTIC_HISTORY_FILENAME = "diagnostics.jsonl"
MAX_DIAGNOSTIC_HISTORY = 20
MAX_DIAGNOSTIC_HISTORY_BYTES = 128 * 1024

OPTIONAL_FEATURES = {
    "pyinstaller": "PyInstaller",
    "windows_gui": "PySide6",
    "rtl_support": "arabic_reshaper",
    "rtl_bidi_support": "bidi",
}

CREDENTIAL_ENVIRONMENT = {
    "x_bearer_token": "SUGAR_X_BEARER_TOKEN",
    "llm_api_key": "SUGAR_LLM_API_KEY",
    "bluesky_identifier": "SUGAR_BLUESKY_IDENTIFIER",
    "bluesky_app_password": "SUGAR_BLUESKY_APP_PASSWORD",
    "mastodon_token": "SUGAR_MASTODON_TOKEN",
    "weibo_cookie": "SUGAR_WEIBO_COOKIE",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _package_versions() -> dict[str, str]:
    return runtime_dependency_versions()


def _optional_features() -> dict[str, bool]:
    return {name: importlib.util.find_spec(module) is not None for name, module in OPTIONAL_FEATURES.items()}


def _workspace_summary(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {"status": "not-specified"}
    try:
        workspace = SugarWorkspace.open(path)
        status = workspace.status()
        return {
            "status": "healthy" if status["missing_artifacts"] == 0 else "degraded",
            "root": redacted_path(status["root"]),
            "schema_version": status["schema_version"],
            "database_schema_version": status["database_schema_version"],
            "artifact_count": status["artifact_count"],
            "artifact_counts": status["artifact_counts"],
            "missing_artifacts": status["missing_artifacts"],
            "external_artifacts": status["external_artifacts"],
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "error": error_payload(exc),
        }


def _diagnostic_history_path(workspace: str | Path) -> Path:
    return SugarWorkspace.open(workspace).internal_path / DIAGNOSTIC_HISTORY_FILENAME


def _load_history(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.stat().st_size > MAX_DIAGNOSTIC_HISTORY_BYTES:
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-MAX_DIAGNOSTIC_HISTORY:]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            entries.append(value)
    return entries[-MAX_DIAGNOSTIC_HISTORY:]


def record_error(
    workspace: str | Path | None,
    error: BaseException,
    *,
    secrets: Mapping[str, str] | None = None,
) -> None:
    """Persist only bounded, redacted error metadata inside an existing workspace."""
    if not workspace:
        return
    try:
        path = _diagnostic_history_path(workspace)
        entries = _load_history(path)
        payload = error_payload(error, secrets=secrets)
        entries.append({"recorded_at": _utc_now_iso(), **payload})
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            path, "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in entries) + "\n"
        )
    except Exception:
        # Diagnostics must never mask the operation's original failure.
        return


def build_report(workspace: str | Path | None = None) -> dict[str, Any]:
    """Build a support bundle without configuration contents, credentials, or research data."""
    recent_errors: list[dict[str, Any]] = []
    if workspace:
        try:
            recent_errors = _load_history(_diagnostic_history_path(workspace))
        except Exception:
            recent_errors = []
    return {
        "diagnostics_schema": DIAGNOSTICS_SCHEMA_VERSION,
        "application": "sugar-osint",
        "version": _package_version(),
        "bridge_protocol": 3,
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "architecture": platform.machine() or "unknown",
        "system": platform.platform(),
        "os": platform.system().lower(),
        "runtime": "bundled" if getattr(sys, "frozen", False) else "python",
        "dependencies": _package_versions(),
        "optional_features": _optional_features(),
        "credentials_configured": {
            key: bool(os.environ.get(environment)) for key, environment in CREDENTIAL_ENVIRONMENT.items()
        },
        "collectors": collector_capabilities(),
        "workspace": _workspace_summary(workspace),
        "recent_errors": recent_errors,
        "redaction": {
            "credential_values": "never included",
            "configuration_contents": "never included",
            "config_contents": "never included",
            "research_data": "never included",
        },
    }


def _package_version() -> str:
    try:
        return importlib_metadata.version("sugar-osint")
    except importlib_metadata.PackageNotFoundError:
        from . import __version__

        return __version__


def save_report(workspace: str | Path | None, output: str | Path) -> str:
    path = Path(output).expanduser().resolve()
    atomic_write_text(path, json.dumps(build_report(workspace), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return str(path)


def save_bundle(workspace: str | Path | None, output: str | Path) -> str:
    """Write an atomic, redacted diagnostic bundle for support handoff."""
    path = Path(output).expanduser().resolve()
    report = json.dumps(build_report(workspace), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    handling_note = (
        "SUGAR diagnostic bundle\n\n"
        "This archive contains runtime metadata, collector capabilities, workspace health summaries, "
        "and sanitized recent errors. It intentionally excludes credentials, configuration contents, "
        "and research data. Review the files before sharing them with a third party.\n"
    )
    with atomic_path(path, suffix=".zip") as temporary:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("diagnostics.json", report)
            archive.writestr("README.txt", handling_note)
    return str(path)
