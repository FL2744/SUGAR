from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable


COVERAGE_SCHEMA_VERSION = "1.0"
COVERAGE_STATUSES = {"success", "zero_result", "partial", "unavailable", "failed", "not_run"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


@dataclass
class SourceCoverage:
    source: str
    status: str
    records: int = 0
    attempted: bool = True
    access_mode: str = ""
    reason: str = ""
    error_type: str = ""
    started_at: str = ""
    completed_at: str = ""

    def __post_init__(self) -> None:
        self.source = _clean(self.source).casefold()
        self.status = _clean(self.status).casefold()
        self.records = int(self.records)
        self.attempted = bool(self.attempted)
        self.access_mode = _clean(self.access_mode)
        self.reason = _clean(self.reason)
        self.error_type = _clean(self.error_type)
        self.started_at = _clean(self.started_at)
        self.completed_at = _clean(self.completed_at)
        if not self.source:
            raise ValueError("Source coverage requires a source name.")
        if self.status not in COVERAGE_STATUSES:
            raise ValueError(f"Unsupported coverage status: {self.status}")
        if self.records < 0:
            raise ValueError("Coverage record count cannot be negative.")

    def export_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_collection_error(exc: Exception, *, records: int = 0) -> str:
    """Classify a source failure without pretending all exceptions mean the same thing.

    Access/authentication gates are unavailable coverage. A collector that exposes
    partial_records is partial coverage. Everything else remains an explicit failure.
    """

    partial_records = getattr(exc, "partial_records", None)
    if partial_records is not None or records > 0:
        return "partial"

    message = _clean(exc).casefold()
    unavailable_markers = (
        "requires credential",
        "requires a logged-in",
        "requires a logged in",
        "missing credential",
        "bearer token",
        "captcha",
        "access control",
        "access-control",
        "login required",
        "authentication required",
        "http 401",
        "http 403",
        "forbidden",
        "unauthorized",
    )
    if any(marker in message for marker in unavailable_markers):
        return "unavailable"
    return "failed"


def coverage_payload(
    entries: Iterable[SourceCoverage],
    *,
    terms: Iterable[str] = (),
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    rows = list(entries)
    statuses = {row.status for row in rows}
    if not rows:
        overall = "not_run"
    elif statuses <= {"success", "zero_result"}:
        overall = "success"
    elif statuses == {"unavailable"}:
        overall = "unavailable"
    elif statuses == {"failed"}:
        overall = "failed"
    else:
        overall = "partial"
    return {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "overall_status": overall,
        "terms": [_clean(term) for term in terms if _clean(term)],
        "since": _clean(since),
        "until": _clean(until),
        "sources": {row.source: row.export_dict() for row in rows},
    }


def load_collection_coverage(source_file: str | Path) -> dict[str, Any] | None:
    """Load the nearest durable coverage record associated with a dataset.

    Raw collection outputs prefer the dedicated `.coverage.json` sidecar. Derived
    datasets can carry the same payload inside their `.metadata.json` sidecar.
    """

    source = Path(source_file).expanduser().resolve()
    coverage_path = source.with_suffix(".coverage.json")
    if coverage_path.is_file():
        payload = json.loads(coverage_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    metadata_path = source.with_suffix(".metadata.json")
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        embedded = metadata.get("source_coverage") if isinstance(metadata, dict) else None
        return embedded if isinstance(embedded, dict) else None
    return None
