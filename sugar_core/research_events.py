"""Structured activity events and timing instrumentation for research runs.

The UI consumes these events (polling or Server-Sent Events); it never scrapes log text.
Every event is redacted at emission, appended to the run's ``events.jsonl``, and given a
monotonically increasing ``seq`` so clients can resume with ``after=<seq>``.
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from . import redaction
from .research_plan import utc_now

STAGES = ("plan", "search", "collect", "translate", "process", "results")

# event type -> pipeline stage (section 16)
EVENT_STAGE: dict[str, str] = {
    "research.plan.created": "plan", "research.plan.updated": "plan", "query.generated": "plan", "query.disabled": "plan", "query.adapted": "search", "query.skipped": "search",
    "source.skipped": "plan",
    "source.search.started": "search", "source.search.completed": "search", "provider.rate_limited": "search",
    "source.retry.scheduled": "search", "source.failed": "search",
    "item.discovered": "collect", "item.changed": "collect", "item.download.started": "collect", "item.download.completed": "collect",
    "duplicate.detected": "collect", "item.rejected": "collect", "item.excluded": "collect",
    "language.detected": "translate", "translation.started": "translate", "translation.completed": "translate",
    "translation.failed": "translate", "translation.skipped": "translate",
    "extraction.started": "process", "extraction.completed": "process",
    "pipeline.completed": "results",
}
SEVERITY_OF = {"provider.rate_limited": "warning", "source.failed": "error", "item.rejected": "info", "translation.failed": "warning",
               "translation.skipped": "warning", "source.skipped": "warning", "source.retry.scheduled": "warning",
               "run.failed": "error", "warning": "warning"}

# timing categories (section 29)
TIMING_CATEGORIES = ("interpretation", "search", "download", "parsing", "extraction", "translation", "llm_call",
                     "deduplication", "serialization", "ui_delivery")


@dataclass
class ActivityEvent:
    seq: int
    run_id: str
    type: str
    stage: str
    ts: str
    severity: str = "info"
    source: str = ""
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    t_mono: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "run_id": self.run_id, "type": self.type, "stage": self.stage, "ts": self.ts,
                "severity": self.severity, "source": self.source, "message": self.message, "data": self.data}


class TimingRecorder:
    """Thread-safe aggregate timings per category (and per source for search/download)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: dict[str, dict[str, float]] = {}
        self._by_source: dict[str, dict[str, dict[str, float]]] = {}

    def record(self, category: str, seconds: float, *, source: str = "") -> None:
        ms = max(0.0, seconds) * 1000
        with self._lock:
            for table, key in ((self._rows, category),):
                row = table.setdefault(key, {"count": 0, "total_ms": 0.0, "max_ms": 0.0})
                row["count"] += 1
                row["total_ms"] += ms
                row["max_ms"] = max(row["max_ms"], ms)
            if source:
                row = self._by_source.setdefault(source, {}).setdefault(category, {"count": 0, "total_ms": 0.0, "max_ms": 0.0})
                row["count"] += 1
                row["total_ms"] += ms
                row["max_ms"] = max(row["max_ms"], ms)

    @contextmanager
    def measure(self, category: str, *, source: str = "") -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self.record(category, time.perf_counter() - start, source=source)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            def rounded(rows: dict[str, dict[str, float]]) -> dict[str, Any]:
                return {k: {"count": int(v["count"]), "total_ms": round(v["total_ms"], 1), "max_ms": round(v["max_ms"], 1),
                            "avg_ms": round(v["total_ms"] / v["count"], 1) if v["count"] else 0.0} for k, v in sorted(rows.items())}
            return {"categories": rounded(self._rows), "by_source": {s: rounded(r) for s, r in sorted(self._by_source.items())}}


class EventLog:
    """Append-only, thread-safe event stream for one run."""

    def __init__(self, run_id: str, path: Path | None = None, *, capture_debug: bool = False,
                 on_event: Callable[[ActivityEvent], None] | None = None, start_seq: int = 0) -> None:
        self.run_id = run_id
        self.path = path
        self.capture_debug = capture_debug
        self.on_event = on_event
        self._events: list[ActivityEvent] = []
        self._seq = start_seq
        self._cond = threading.Condition()
        self._closed = False
        self._file = None
        self.timings = TimingRecorder()
        self._delivery_lag_ms: list[float] = []
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_file():
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        row = json.loads(line)
                        self._events.append(ActivityEvent(**{k: row[k] for k in ("seq", "run_id", "type", "stage", "ts", "severity", "source", "message", "data")}))
                        self._seq = max(self._seq, int(row["seq"]))
                    except (ValueError, KeyError, TypeError):
                        continue
            self._file = path.open("a", encoding="utf-8", newline="\n")

    # -- emission -----------------------------------------------------------------------
    def emit(self, type: str, *, source: str = "", message: str = "", stage: str = "", severity: str = "",
             debug: bool = False, **data: Any) -> ActivityEvent | None:
        """Emit an event. ``debug=True`` events are recorded only when Debug Mode is on."""
        if debug and not self.capture_debug:
            return None
        clean = redaction.redact(data)
        clean_message = redaction.redact_text(message)
        with self._cond:
            self._seq += 1
            event = ActivityEvent(
                seq=self._seq, run_id=self.run_id, type=type, stage=stage or EVENT_STAGE.get(type, "plan"), ts=utc_now(),
                severity=severity or SEVERITY_OF.get(type, "info"), source=source, message=clean_message, data=clean,
                t_mono=time.monotonic())
            self._events.append(event)
            if self._file is not None and not self._closed:
                with self.timings.measure("serialization"):
                    self._file.write(json.dumps(event.as_dict(), ensure_ascii=False) + "\n")
                    self._file.flush()
            self._cond.notify_all()
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:
                pass
        return event

    def close(self) -> None:
        with self._cond:
            self._closed = True
            if self._file is not None:
                self._file.close()
                self._file = None
            self._cond.notify_all()

    # -- consumption --------------------------------------------------------------------
    @property
    def last_seq(self) -> int:
        with self._cond:
            return self._seq

    def since(self, after: int = 0, *, stage: str = "", source: str = "", severity: str = "",
              types: set[str] | None = None, limit: int = 1000) -> list[ActivityEvent]:
        with self._cond:
            rows = [e for e in self._events if e.seq > after]
        if stage:
            rows = [e for e in rows if e.stage == stage]
        if source:
            rows = [e for e in rows if e.source == source]
        if severity:
            rows = [e for e in rows if e.severity == severity]
        if types:
            rows = [e for e in rows if e.type in types]
        return rows[:limit]

    def wait_for(self, after: int, timeout: float = 15.0) -> bool:
        """Block until an event newer than ``after`` exists (or the log closes). True if there is one."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._seq <= after and not self._closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return self._seq > after

    @property
    def closed(self) -> bool:
        return self._closed

    def note_delivery(self, event: ActivityEvent) -> float:
        """Record emit->delivery lag for the UI event channel (section 29). Returns lag in ms."""
        lag = max(0.0, (time.monotonic() - event.t_mono) * 1000)
        self.timings.record("ui_delivery", lag / 1000)
        with self._cond:
            self._delivery_lag_ms.append(lag)
            del self._delivery_lag_ms[:-500]
        return lag

    def snapshot(self) -> list[dict[str, Any]]:
        with self._cond:
            return [e.as_dict() for e in self._events]
