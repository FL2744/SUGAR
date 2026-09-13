from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from .models import PostRecord, merge_record
from .weibo import _status_to_record


Runner = Callable[..., subprocess.CompletedProcess[str]]
_SECRET_RE = re.compile(r"(?i)(access[_-]?token|refresh[_-]?token|authorization|cookie|secret)\s*[:=]\s*[^\s,;]+")


class WeiboOfficialCLIError(RuntimeError):
    """Raised when the official Weibo Open Platform CLI cannot satisfy a search request."""


@dataclass(frozen=True)
class OfficialCLIConfig:
    executable: str = ""
    sort: str = "time"
    search_command: str = "statuses/limited"
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.sort not in {"time", "hot"}:
            raise ValueError("Official Weibo CLI sort must be 'time' or 'hot'.")
        if not self.search_command.strip():
            raise ValueError("Official Weibo CLI search command cannot be blank.")
        if float(self.timeout_seconds) <= 0:
            raise ValueError("Official Weibo CLI timeout must be positive.")


def _sanitize_error(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return _SECRET_RE.sub(lambda match: match.group(1) + "=<redacted>", text)[:2000]


def resolve_official_cli(explicit: str = "") -> str:
    candidates = [explicit, os.environ.get("SUGAR_WEIBO_CLI", ""), "weibo-cli", "weibo"]
    for candidate in candidates:
        candidate = str(candidate or "").strip()
        if not candidate:
            continue
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return os.path.abspath(candidate)
    raise WeiboOfficialCLIError(
        "Official Weibo CLI is not installed or not on PATH. Install/authorize it through the Weibo Open Platform, "
        "or set SUGAR_WEIBO_CLI to the executable path. SUGAR does not install or authenticate it automatically."
    )


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("statuses", "items", "results", "list", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    data = payload.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        nested = _extract_rows(data)
        if nested:
            return nested
    return []


def _run_json(command: list[str], *, runner: Runner, timeout: float) -> Any:
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise WeiboOfficialCLIError(f"Official Weibo CLI failed to start: {_sanitize_error(exc)}") from exc
    if completed.returncode != 0:
        message = _sanitize_error(completed.stderr or completed.stdout or f"exit code {completed.returncode}")
        raise WeiboOfficialCLIError(f"Official Weibo CLI search failed: {message}")
    stdout = str(completed.stdout or "").strip()
    if not stdout:
        return []
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise WeiboOfficialCLIError("Official Weibo CLI did not return valid JSON. Use --output json and verify the CLI with its doctor command.") from exc


def _source_uri(command_family: str, query: str, page: int) -> str:
    safe_query = query.replace(" ", "%20")
    return f"weibo-open-platform://search/{command_family}?q={safe_query}&page={page}"


def _normalize_row(row: dict[str, Any], *, query: str, command_family: str, page: int) -> PostRecord | None:
    # The official CLI may return the legacy status shape directly or wrap it one level down.
    status = row.get("status") if isinstance(row.get("status"), dict) else row
    if not any(status.get(key) for key in ("id", "mid", "idstr", "bid", "mblogid")):
        return None
    record = _status_to_record(
        status,
        query=query,
        source_url=_source_uri(command_family, query, page),
        source_mode="weibo_official_open_platform_search",
    )
    if not record.native_id:
        return None
    record.source_host = "open.weibo.com"
    record.raw_stats = dict(record.raw_stats)
    record.raw_stats.update(
        {
            "access_mode": "official_open_platform",
            "official_cli_command": command_family,
            "official_cli_page": page,
        }
    )
    return record


def collect_weibo_official(
    *,
    search_terms: list[str],
    max_posts_per_query: int = 20,
    max_pages_per_query: int = 1,
    page_start: int = 1,
    page_count: int | None = None,
    executable: str = "",
    sort: str = "time",
    search_command: str = "statuses/limited",
    timeout_seconds: float = 60.0,
    runner: Runner = subprocess.run,
) -> list[PostRecord]:
    """Collect keyword results through Weibo's official authenticated CLI.

    Authentication is owned entirely by the official CLI. SUGAR does not inspect, copy, refresh, or persist
    its credentials. This function only invokes an already installed/authorized command and parses JSON.
    """
    cfg = OfficialCLIConfig(executable=executable, sort=sort, search_command=search_command, timeout_seconds=timeout_seconds)
    binary = resolve_official_cli(cfg.executable)
    per_page = max(1, min(20, int(max_posts_per_query or 20)))
    start = max(1, int(page_start or 1))
    count = max(1, int(page_count if page_count is not None else max_pages_per_query or 1))
    end = start + count - 1
    merged: dict[str, PostRecord] = {}

    for query in [str(value).strip() for value in search_terms if str(value).strip()]:
        query_total = 0
        for page in range(start, end + 1):
            command = [
                binary,
                "search",
                cfg.search_command,
                "--q",
                query,
                "--type",
                "1",
                "--sort",
                cfg.sort,
                "--count",
                str(per_page),
                "--page",
                str(page),
                "--output",
                "json",
            ]
            payload = _run_json(command, runner=runner, timeout=cfg.timeout_seconds)
            rows = _extract_rows(payload)
            if not rows:
                break
            for row in rows:
                record = _normalize_row(row, query=query, command_family=cfg.search_command, page=page)
                if record is None:
                    continue
                key = record.record_key
                if key in merged:
                    merge_record(merged[key], record)
                else:
                    merged[key] = record
                query_total += 1
                if query_total >= max(1, int(max_posts_per_query)):
                    break
            if query_total >= max(1, int(max_posts_per_query)):
                break
    return list(merged.values())
