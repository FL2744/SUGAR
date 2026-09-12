from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Iterable

import requests

from .collector_registry import CollectorRequest, collect_registered_source, get_collector
from .models import PostRecord, merge_record
from .storage import save_records
from .utils import utc_iso

# Time-window sharding is only enabled by default where the existing collector sends the
# bounds to the remote search service. For client-side-only date filters, repeated shards
# would waste requests by rescanning the same leading result pages.
DEFAULT_TIME_SHARD_SOURCES = frozenset({"x", "bluesky"})

# Conservative fallback waits are used only when a collector has already converted a 429
# into a generic exception and the server headers are no longer available. These are not a
# mechanism for getting around limits: SUGAR waits or defers the task.
RATE_LIMIT_FALLBACK_SECONDS = {
    "x": 900.0,
    "mastodon": 300.0,
    "bluesky": 60.0,
    "bilibili": 120.0,
    "weibo": 120.0,
}

ProgressCallback = Callable[[str, dict[str, Any]], None]
CollectorCallable = Callable[[str, CollectorRequest], list[PostRecord]]
Sleeper = Callable[[float], None]


def _notify(progress: ProgressCallback | None, event: str, **values: Any) -> None:
    if progress is not None:
        progress(event, values)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_date_only(value: str | None) -> date | None:
    text = _clean(value)
    if not text or len(text) != 10:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _task_id(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "task_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class HarvestTask:
    source: str
    query: str
    since: str | None = None
    until: str | None = None

    @property
    def task_id(self) -> str:
        return _task_id(asdict(self))


@dataclass(frozen=True)
class HarvestConfig:
    sources: tuple[str, ...]
    terms: tuple[str, ...]
    since: str | None = None
    until: str | None = None
    target_records: int | None = None
    shard_days: int = 7
    posts_per_task: int = 1000
    pages_per_task: int = 50
    max_retries: int = 4
    base_backoff_seconds: float = 5.0
    max_inline_wait_seconds: float = 900.0
    inter_task_delay_seconds: float = 1.0
    time_shard_sources: tuple[str, ...] = tuple(sorted(DEFAULT_TIME_SHARD_SOURCES))
    continue_on_error: bool = True

    def __post_init__(self) -> None:
        sources = tuple(dict.fromkeys(_clean(value).casefold() for value in self.sources if _clean(value)))
        terms = tuple(dict.fromkeys(_clean(value) for value in self.terms if _clean(value)))
        if not sources:
            raise ValueError("Harvest requires at least one source.")
        if not terms:
            raise ValueError("Harvest requires at least one search term.")
        for source in sources:
            get_collector(source).validate_search(CollectorRequest()) if False else get_collector(source)
        if self.target_records is not None and int(self.target_records) < 1:
            raise ValueError("target_records must be positive when provided.")
        if int(self.shard_days) < 1:
            raise ValueError("shard_days must be at least 1.")
        if int(self.posts_per_task) < 1:
            raise ValueError("posts_per_task must be at least 1.")
        if int(self.pages_per_task) < 1:
            raise ValueError("pages_per_task must be at least 1.")
        if int(self.max_retries) < 0:
            raise ValueError("max_retries cannot be negative.")
        if float(self.base_backoff_seconds) < 0 or float(self.inter_task_delay_seconds) < 0:
            raise ValueError("Harvest delays cannot be negative.")
        if float(self.max_inline_wait_seconds) < 0:
            raise ValueError("max_inline_wait_seconds cannot be negative.")
        object.__setattr__(self, "sources", sources)
        object.__setattr__(self, "terms", terms)
        object.__setattr__(self, "target_records", int(self.target_records) if self.target_records is not None else None)
        object.__setattr__(self, "shard_days", int(self.shard_days))
        object.__setattr__(self, "posts_per_task", int(self.posts_per_task))
        object.__setattr__(self, "pages_per_task", int(self.pages_per_task))
        object.__setattr__(self, "max_retries", int(self.max_retries))
        object.__setattr__(self, "base_backoff_seconds", float(self.base_backoff_seconds))
        object.__setattr__(self, "max_inline_wait_seconds", float(self.max_inline_wait_seconds))
        object.__setattr__(self, "inter_task_delay_seconds", float(self.inter_task_delay_seconds))
        object.__setattr__(self, "time_shard_sources", tuple(_clean(x).casefold() for x in self.time_shard_sources if _clean(x)))


def _date_shards(since: str | None, until: str | None, days: int) -> list[tuple[str | None, str | None]]:
    start = _parse_date_only(since)
    end = _parse_date_only(until)
    if start is None or end is None or end < start:
        return [(since, until)]
    shards: list[tuple[str, str]] = []
    cursor = start
    while cursor <= end:
        shard_end = min(end, cursor + timedelta(days=days - 1))
        shards.append((cursor.isoformat(), shard_end.isoformat()))
        cursor = shard_end + timedelta(days=1)
    return shards


def build_harvest_tasks(config: HarvestConfig) -> list[HarvestTask]:
    tasks: list[HarvestTask] = []
    shard_sources = set(config.time_shard_sources)
    for source in config.sources:
        windows = (
            _date_shards(config.since, config.until, config.shard_days)
            if source in shard_sources
            else [(config.since, config.until)]
        )
        for query in config.terms:
            for since, until in windows:
                tasks.append(HarvestTask(source=source, query=query, since=since, until=until))
    return tasks


class HarvestStore:
    """SQLite-backed checkpoint store for long-running collection.

    Records are committed after every successful task. Reopening the same store automatically
    skips completed tasks and deduplicates normalized records by stable `record_key`.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (
                record_key TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                native_id TEXT,
                payload_json TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                query_text TEXT NOT NULL,
                since_value TEXT,
                until_value TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                records_seen INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                not_before TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '',
                task_id TEXT NOT NULL DEFAULT '',
                detail_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "HarvestStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def register_tasks(self, tasks: Iterable[HarvestTask]) -> None:
        now = utc_iso()
        with self.connection:
            for task in tasks:
                self.connection.execute(
                    """
                    INSERT OR IGNORE INTO tasks
                    (task_id, source, query_text, since_value, until_value, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (task.task_id, task.source, task.query, task.since, task.until, now),
                )

    def task_status(self, task_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT status, attempts, records_seen, last_error, not_before FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "status": row[0],
            "attempts": int(row[1]),
            "records_seen": int(row[2]),
            "last_error": row[3],
            "not_before": row[4],
        }

    def runnable(self, task: HarvestTask, now: datetime | None = None) -> bool:
        status = self.task_status(task.task_id)
        if status is None or status["status"] in {"pending", "running", "failed"}:
            return True
        if status["status"] == "completed":
            return False
        if status["status"] == "deferred":
            not_before = _clean(status["not_before"])
            if not not_before:
                return True
            try:
                ready_at = datetime.fromisoformat(not_before.replace("Z", "+00:00"))
            except ValueError:
                return True
            return (now or _utc_now()) >= ready_at
        return False

    def start_task(self, task: HarvestTask) -> int:
        with self.connection:
            self.connection.execute(
                """
                UPDATE tasks SET status='running', attempts=attempts+1, last_error='', not_before='', updated_at=?
                WHERE task_id=?
                """,
                (utc_iso(), task.task_id),
            )
        status = self.task_status(task.task_id)
        return int(status["attempts"]) if status else 1

    def complete_task(self, task: HarvestTask, records_seen: int) -> None:
        with self.connection:
            self.connection.execute(
                """
                UPDATE tasks SET status='completed', records_seen=?, last_error='', not_before='', updated_at=?
                WHERE task_id=?
                """,
                (int(records_seen), utc_iso(), task.task_id),
            )

    def fail_task(self, task: HarvestTask, error: str) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE tasks SET status='failed', last_error=?, updated_at=? WHERE task_id=?",
                (_clean(error)[:2000], utc_iso(), task.task_id),
            )

    def defer_task(self, task: HarvestTask, error: str, wait_seconds: float) -> None:
        ready_at = _utc_now() + timedelta(seconds=max(0.0, float(wait_seconds)))
        with self.connection:
            self.connection.execute(
                """
                UPDATE tasks SET status='deferred', last_error=?, not_before=?, updated_at=? WHERE task_id=?
                """,
                (_clean(error)[:2000], _iso(ready_at), utc_iso(), task.task_id),
            )

    def add_event(self, event_type: str, *, source: str = "", task_id: str = "", **detail: Any) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO events(created_at,event_type,source,task_id,detail_json) VALUES(?,?,?,?,?)",
                (utc_iso(), event_type, source, task_id, json.dumps(detail, ensure_ascii=False, sort_keys=True)),
            )

    def upsert_records(self, records: Iterable[PostRecord]) -> tuple[int, int]:
        inserted = 0
        updated = 0
        now = utc_iso()
        with self.connection:
            for incoming in records:
                key = incoming.record_key
                if not key:
                    continue
                row = self.connection.execute(
                    "SELECT payload_json FROM records WHERE record_key=?", (key,)
                ).fetchone()
                if row is None:
                    payload = asdict(incoming)
                    self.connection.execute(
                        """
                        INSERT INTO records(record_key,platform,native_id,payload_json,first_seen_at,last_seen_at)
                        VALUES(?,?,?,?,?,?)
                        """,
                        (
                            key,
                            incoming.platform,
                            incoming.native_id,
                            json.dumps(payload, ensure_ascii=False, sort_keys=True),
                            now,
                            now,
                        ),
                    )
                    inserted += 1
                    continue
                existing = PostRecord(**json.loads(row[0]))
                merge_record(existing, incoming)
                self.connection.execute(
                    "UPDATE records SET payload_json=?, last_seen_at=? WHERE record_key=?",
                    (json.dumps(asdict(existing), ensure_ascii=False, sort_keys=True), now, key),
                )
                updated += 1
        return inserted, updated

    def count_records(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM records").fetchone()[0])

    def records(self) -> list[PostRecord]:
        rows = self.connection.execute("SELECT payload_json FROM records ORDER BY platform, native_id").fetchall()
        return [PostRecord(**json.loads(row[0])) for row in rows]

    def task_counts(self) -> dict[str, int]:
        rows = self.connection.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall()
        return {str(status): int(count) for status, count in rows}

    def event_count(self, event_type: str) -> int:
        return int(
            self.connection.execute("SELECT COUNT(*) FROM events WHERE event_type=?", (event_type,)).fetchone()[0]
        )


def _header_wait_seconds(headers: Any) -> float | None:
    if not headers:
        return None
    retry_after = _clean(headers.get("Retry-After", ""))
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(retry_after)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return max(0.0, (parsed.astimezone(timezone.utc) - _utc_now()).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
    reset = _clean(headers.get("x-rate-limit-reset", headers.get("X-RateLimit-Reset", "")))
    if reset:
        try:
            number = float(reset)
            # X-style reset is Unix time. Some servers instead return a small seconds value.
            if number > 10_000_000:
                return max(0.0, number - _utc_now().timestamp())
            return max(0.0, number)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(reset.replace("Z", "+00:00"))
                return max(0.0, (parsed.astimezone(timezone.utc) - _utc_now()).total_seconds())
            except ValueError:
                pass
    return None


def rate_limit_wait_seconds(error: BaseException, source: str) -> float | None:
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    text = str(error).casefold()
    limited = status_code == 429 or "429" in text or "rate limit" in text or "rate-limited" in text
    if not limited:
        return None
    header_wait = _header_wait_seconds(getattr(response, "headers", None))
    if header_wait is not None:
        return header_wait
    return RATE_LIMIT_FALLBACK_SECONDS.get(source.casefold(), 120.0)


def _is_transient(error: BaseException) -> bool:
    if isinstance(error, (requests.Timeout, requests.ConnectionError)):
        return True
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    return isinstance(status_code, int) and 500 <= status_code <= 599


def _backoff(config: HarvestConfig, attempt: int) -> float:
    return config.base_backoff_seconds * (2 ** max(0, attempt - 1))


def _jsonl_path(output_csv: Path) -> Path:
    return output_csv.with_suffix(".jsonl")


def write_jsonl(records: Iterable[PostRecord], path: str | Path) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")
    return str(path.resolve())


def run_harvest(
    config: dict[str, Any],
    secrets: dict[str, str] | None = None,
    progress: ProgressCallback | None = None,
    *,
    collector: CollectorCallable = collect_registered_source,
    sleeper: Sleeper = time.sleep,
) -> list[str]:
    """Run a resumable, rate-limit-aware high-volume public-data collection.

    This removes SUGAR's small-run orchestration ceiling; it does not remove or evade platform
    limits. On HTTP 429/rate-limit signals, SUGAR waits according to server headers when available
    or uses a conservative fallback. Long waits are checkpointed as deferred tasks.
    """
    secrets = secrets or {}
    raw = config.get("harvest") or {}
    sources = tuple(config.get("sources") or raw.get("sources") or ["x"])
    terms = tuple(config.get("terms") or raw.get("terms") or [])
    harvest_config = HarvestConfig(
        sources=sources,
        terms=terms,
        since=config.get("since") or raw.get("since") or None,
        until=config.get("until") or raw.get("until") or None,
        target_records=raw.get("target_records"),
        shard_days=int(raw.get("shard_days", 7)),
        posts_per_task=int(raw.get("posts_per_task", 1000)),
        pages_per_task=int(raw.get("pages_per_task", 50)),
        max_retries=int(raw.get("max_retries", 4)),
        base_backoff_seconds=float(raw.get("base_backoff_seconds", 5.0)),
        max_inline_wait_seconds=float(raw.get("max_inline_wait_seconds", 900.0)),
        inter_task_delay_seconds=float(raw.get("inter_task_delay_seconds", 1.0)),
        time_shard_sources=tuple(raw.get("time_shard_sources") or sorted(DEFAULT_TIME_SHARD_SOURCES)),
        continue_on_error=bool(raw.get("continue_on_error", True)),
    )

    out_dir = Path(config.get("output_directory") or raw.get("output_directory") or Path.cwd()).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    name = _clean(raw.get("name") or config.get("name") or "sugar_harvest").replace(" ", "_")
    output_csv = out_dir / f"{name}.csv"
    checkpoint = out_dir / f"{name}.harvest.sqlite3"
    manifest_path = out_dir / f"{name}.harvest.json"

    tasks = build_harvest_tasks(harvest_config)
    _notify(progress, "harvest_plan", tasks=len(tasks), sources=list(harvest_config.sources), terms=len(harvest_config.terms))

    with HarvestStore(checkpoint) as store:
        store.register_tasks(tasks)
        for index, task in enumerate(tasks, 1):
            if harvest_config.target_records is not None and store.count_records() >= harvest_config.target_records:
                _notify(progress, "harvest_target_reached", records=store.count_records(), target=harvest_config.target_records)
                break
            if not store.runnable(task):
                _notify(progress, "harvest_task_skipped", task_id=task.task_id, source=task.source, index=index, total=len(tasks))
                continue

            attempt = 0
            while True:
                attempt += 1
                store.start_task(task)
                _notify(
                    progress,
                    "harvest_task_start",
                    task_id=task.task_id,
                    source=task.source,
                    query=task.query,
                    since=task.since,
                    until=task.until,
                    attempt=attempt,
                    index=index,
                    total=len(tasks),
                )
                request = CollectorRequest(
                    search_terms=[task.query],
                    since=task.since,
                    until=task.until,
                    max_posts_per_query=harvest_config.posts_per_task,
                    max_pages_per_query=harvest_config.pages_per_task,
                    config=config,
                    secrets=secrets,
                )
                try:
                    rows = collector(task.source, request)
                    inserted, updated = store.upsert_records(rows)
                    store.complete_task(task, len(rows))
                    store.add_event(
                        "task_completed",
                        source=task.source,
                        task_id=task.task_id,
                        returned=len(rows),
                        inserted=inserted,
                        updated=updated,
                    )
                    _notify(
                        progress,
                        "harvest_task_complete",
                        task_id=task.task_id,
                        source=task.source,
                        returned=len(rows),
                        inserted=inserted,
                        updated=updated,
                        unique_records=store.count_records(),
                    )
                    break
                except Exception as exc:
                    wait = rate_limit_wait_seconds(exc, task.source)
                    if wait is not None:
                        wait = max(wait, _backoff(harvest_config, attempt))
                        store.add_event(
                            "rate_limit",
                            source=task.source,
                            task_id=task.task_id,
                            wait_seconds=round(wait, 3),
                            error=type(exc).__name__,
                        )
                        _notify(
                            progress,
                            "harvest_rate_limited",
                            task_id=task.task_id,
                            source=task.source,
                            wait_seconds=wait,
                            attempt=attempt,
                        )
                        if wait > harvest_config.max_inline_wait_seconds:
                            store.defer_task(task, str(exc), wait)
                            _notify(progress, "harvest_task_deferred", task_id=task.task_id, source=task.source, not_before_seconds=wait)
                            break
                        if attempt > harvest_config.max_retries:
                            store.defer_task(task, str(exc), wait)
                            break
                        sleeper(wait)
                        continue

                    if _is_transient(exc) and attempt <= harvest_config.max_retries:
                        wait = min(harvest_config.max_inline_wait_seconds, _backoff(harvest_config, attempt))
                        store.add_event("transient_retry", source=task.source, task_id=task.task_id, wait_seconds=wait)
                        _notify(progress, "harvest_retry", task_id=task.task_id, source=task.source, wait_seconds=wait, attempt=attempt)
                        sleeper(wait)
                        continue

                    store.fail_task(task, str(exc))
                    store.add_event("task_failed", source=task.source, task_id=task.task_id, error=type(exc).__name__, message=str(exc)[:500])
                    _notify(progress, "harvest_task_failed", task_id=task.task_id, source=task.source, message=str(exc))
                    if not harvest_config.continue_on_error:
                        raise
                    break

            if harvest_config.inter_task_delay_seconds > 0 and index < len(tasks):
                sleeper(harvest_config.inter_task_delay_seconds)

        records = store.records()
        task_counts = store.task_counts()
        manifest = {
            "generated_at": utc_iso(),
            "operation": "harvest",
            "sources": list(harvest_config.sources),
            "terms": list(harvest_config.terms),
            "since": harvest_config.since,
            "until": harvest_config.until,
            "target_records": harvest_config.target_records,
            "unique_records": len(records),
            "planned_tasks": len(tasks),
            "task_counts": task_counts,
            "rate_limit_events": store.event_count("rate_limit"),
            "checkpoint": checkpoint.name,
            "shard_days": harvest_config.shard_days,
            "posts_per_task": harvest_config.posts_per_task,
            "pages_per_task": harvest_config.pages_per_task,
            "time_shard_sources": list(harvest_config.time_shard_sources),
            "rate_limit_policy": "Honor server Retry-After/reset headers when available; otherwise wait conservatively or defer. No bypass/rotation logic.",
            "enrichment": "Raw normalized collection only. Run enrichment/triage separately after harvest.",
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

        outputs = [str(checkpoint.resolve()), str(manifest_path.resolve())]
        if records:
            save_records(records, output_csv, metadata=manifest)
            outputs.extend(
                [
                    str(output_csv.resolve()),
                    str(output_csv.with_suffix(".xlsx").resolve()),
                    str(output_csv.with_suffix(".metadata.json").resolve()),
                    write_jsonl(records, _jsonl_path(output_csv)),
                ]
            )
        _notify(progress, "harvest_complete", unique_records=len(records), task_counts=task_counts, outputs=outputs)
        return outputs
