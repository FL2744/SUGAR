from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .models import PostRecord, merge_record
from .storage import save_records
from .utils import utc_iso
from .weibo_investigation import WeiboInvestigation, investigate_weibo_seed, parse_weibo_seed


ProgressCallback = Callable[[str, dict[str, Any]], None]
Investigator = Callable[..., WeiboInvestigation]
Sleeper = Callable[[float], None]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _hash(payload: Any, prefix: str = "") -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _notify(progress: ProgressCallback | None, event: str, **values: Any) -> None:
    if progress is not None:
        progress(event, values)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SeedHarvestConfig:
    seeds: tuple[str, ...]
    name: str = "weibo_seed_harvest"
    max_comments: int = 20
    comment_pages: int = 1
    max_reposts: int = 0
    repost_pages: int = 1
    author_posts: int = 0
    author_pages: int = 1
    max_retries: int = 2
    base_backoff_seconds: float = 5.0
    max_inline_wait_seconds: float = 120.0
    inter_seed_delay_seconds: float = 1.0
    continue_on_error: bool = True

    def __post_init__(self) -> None:
        seeds = tuple(dict.fromkeys(_clean(seed) for seed in self.seeds if _clean(seed)))
        if not seeds:
            raise ValueError("Seed harvest requires at least one Weibo post URL or ID.")
        for key in ("max_comments", "comment_pages", "max_reposts", "repost_pages", "author_posts", "author_pages", "max_retries"):
            if int(getattr(self, key)) < 0:
                raise ValueError(f"{key} cannot be negative.")
        if self.comment_pages < 1 or self.repost_pages < 1 or self.author_pages < 1:
            raise ValueError("page limits must be at least 1.")
        if self.base_backoff_seconds < 0 or self.max_inline_wait_seconds < 0 or self.inter_seed_delay_seconds < 0:
            raise ValueError("seed-harvest delays cannot be negative.")
        object.__setattr__(self, "seeds", seeds)
        object.__setattr__(self, "name", _clean(self.name).replace(" ", "_") or "weibo_seed_harvest")

    @property
    def plan_signature(self) -> str:
        return _hash(
            {
                "seeds": list(self.seeds),
                "max_comments": self.max_comments,
                "comment_pages": self.comment_pages,
                "max_reposts": self.max_reposts,
                "repost_pages": self.repost_pages,
                "author_posts": self.author_posts,
                "author_pages": self.author_pages,
            },
            "seedplan_",
        )


class SeedHarvestStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS seeds (
                seed_key TEXT PRIMARY KEY,
                seed_input TEXT NOT NULL,
                identity TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                not_before TEXT NOT NULL DEFAULT '',
                seed_record_key TEXT NOT NULL DEFAULT '',
                comments_retrieved INTEGER NOT NULL DEFAULT 0,
                reposts_retrieved INTEGER NOT NULL DEFAULT 0,
                author_posts_retrieved INTEGER NOT NULL DEFAULT 0,
                surface_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS records (
                record_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                first_seed_key TEXT NOT NULL,
                seed_matches_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                seed_key TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "SeedHarvestStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def get_meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.db.commit()

    def register(self, seeds: Iterable[str]) -> None:
        now = utc_iso()
        for seed in seeds:
            identity = parse_weibo_seed(seed)
            seed_key = _hash({"identity": identity}, "seed_")
            self.db.execute(
                "INSERT OR IGNORE INTO seeds(seed_key,seed_input,identity,updated_at) VALUES(?,?,?,?)",
                (seed_key, seed, identity, now),
            )
        self.db.commit()

    def eligible(self) -> list[dict[str, Any]]:
        now = utc_iso()
        rows = self.db.execute(
            """
            SELECT seed_key,seed_input,identity,status,attempts,last_error,not_before
            FROM seeds
            WHERE status IN ('pending','failed','deferred')
              AND (not_before='' OR not_before<=?)
            ORDER BY rowid
            """,
            (now,),
        ).fetchall()
        return [
            {"seed_key": row[0], "seed_input": row[1], "identity": row[2], "status": row[3], "attempts": int(row[4]), "last_error": row[5], "not_before": row[6]}
            for row in rows
        ]

    def start(self, seed_key: str) -> int:
        self.db.execute(
            "UPDATE seeds SET status='running',attempts=attempts+1,last_error='',updated_at=? WHERE seed_key=?",
            (utc_iso(), seed_key),
        )
        self.db.commit()
        return int(self.db.execute("SELECT attempts FROM seeds WHERE seed_key=?", (seed_key,)).fetchone()[0])

    def complete(self, seed_key: str, result: WeiboInvestigation) -> None:
        self.db.execute(
            """
            UPDATE seeds
            SET status='completed',last_error='',not_before='',seed_record_key=?,comments_retrieved=?,reposts_retrieved=?,
                author_posts_retrieved=?,surface_json=?,updated_at=?
            WHERE seed_key=?
            """,
            (
                result.seed.record_key,
                len(result.comments),
                len(result.reposts),
                len(result.author_posts),
                json.dumps(result.surface_status or {}, ensure_ascii=False, sort_keys=True),
                utc_iso(),
                seed_key,
            ),
        )
        self.db.commit()

    def fail(self, seed_key: str, error: str) -> None:
        self.db.execute(
            "UPDATE seeds SET status='failed',last_error=?,not_before='',updated_at=? WHERE seed_key=?",
            (error[:2000], utc_iso(), seed_key),
        )
        self.db.commit()

    def defer(self, seed_key: str, error: str, seconds: float) -> None:
        not_before = _iso(_utc_now() + timedelta(seconds=max(0.0, seconds)))
        self.db.execute(
            "UPDATE seeds SET status='deferred',last_error=?,not_before=?,updated_at=? WHERE seed_key=?",
            (error[:2000], not_before, utc_iso(), seed_key),
        )
        self.db.commit()

    def upsert_records(self, seed_key: str, records: Iterable[PostRecord]) -> tuple[int, int]:
        inserted = 0
        updated = 0
        for incoming in records:
            key = incoming.record_key
            if not key:
                continue
            row = self.db.execute("SELECT payload_json,seed_matches_json FROM records WHERE record_key=?", (key,)).fetchone()
            if row:
                existing = PostRecord(**json.loads(row[0]))
                merge_record(existing, incoming)
                matches = set(json.loads(row[1]) or [])
                matches.add(seed_key)
                self.db.execute(
                    "UPDATE records SET payload_json=?,seed_matches_json=?,updated_at=? WHERE record_key=?",
                    (json.dumps(asdict(existing), ensure_ascii=False, sort_keys=True), json.dumps(sorted(matches)), utc_iso(), key),
                )
                updated += 1
            else:
                self.db.execute(
                    "INSERT INTO records(record_key,payload_json,first_seed_key,seed_matches_json,updated_at) VALUES(?,?,?,?,?)",
                    (key, json.dumps(asdict(incoming), ensure_ascii=False, sort_keys=True), seed_key, json.dumps([seed_key]), utc_iso()),
                )
                inserted += 1
        self.db.commit()
        return inserted, updated

    def add_event(self, event_type: str, seed_key: str = "", **payload: Any) -> None:
        self.db.execute(
            "INSERT INTO events(created_at,event_type,seed_key,payload_json) VALUES(?,?,?,?)",
            (utc_iso(), event_type, seed_key, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
        )
        self.db.commit()

    def records(self) -> list[PostRecord]:
        return [PostRecord(**json.loads(row[0])) for row in self.db.execute("SELECT payload_json FROM records ORDER BY rowid").fetchall()]

    def seed_rows(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT seed_key,seed_input,identity,status,attempts,last_error,not_before,seed_record_key,comments_retrieved,reposts_retrieved,author_posts_retrieved,surface_json FROM seeds ORDER BY rowid"
        ).fetchall()
        return [
            {
                "seed_key": row[0], "seed_input": row[1], "identity": row[2], "status": row[3], "attempts": int(row[4]),
                "last_error": row[5], "not_before": row[6], "seed_record_key": row[7], "comments_retrieved": int(row[8]),
                "reposts_retrieved": int(row[9]), "author_posts_retrieved": int(row[10]), "surface_status": json.loads(row[11] or "{}"),
            }
            for row in rows
        ]

    def counts(self) -> dict[str, int]:
        return {str(status): int(count) for status, count in self.db.execute("SELECT status,COUNT(*) FROM seeds GROUP BY status").fetchall()}


def _rate_limit_error(exc: Exception) -> bool:
    text = str(exc).casefold()
    return "429" in text or "rate-limit" in text or "rate limit" in text or "访问频次过高" in text


def _retryable(exc: Exception) -> bool:
    text = str(exc).casefold()
    return _rate_limit_error(exc) or any(token in text for token in ("timeout", "temporar", "connection", "502", "503", "504"))


def _write_jsonl(records: Iterable[PostRecord], path: Path) -> str:
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record.export_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return str(path.resolve())


def _write_seed_status(rows: list[dict[str, Any]], path: Path) -> str:
    fields = [
        "seed_key", "seed_input", "identity", "status", "attempts", "last_error", "not_before", "seed_record_key",
        "comments_retrieved", "reposts_retrieved", "author_posts_retrieved", "surface_status",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            payload = dict(row)
            payload["surface_status"] = json.dumps(payload.get("surface_status") or {}, ensure_ascii=False, sort_keys=True)
            writer.writerow(payload)
    return str(path.resolve())


def run_weibo_seed_harvest(
    config: SeedHarvestConfig,
    output_directory: str | Path,
    *,
    cookie: str = "",
    progress: ProgressCallback | None = None,
    investigator: Investigator = investigate_weibo_seed,
    sleeper: Sleeper = time.sleep,
) -> list[str]:
    out_dir = Path(output_directory).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = out_dir / f"{config.name}.seedharvest.sqlite3"
    manifest_path = out_dir / f"{config.name}.seedharvest.json"
    status_path = out_dir / f"{config.name}.seeds.csv"
    records_path = out_dir / f"{config.name}.csv"
    jsonl_path = out_dir / f"{config.name}.jsonl"

    with SeedHarvestStore(checkpoint) as store:
        existing_signature = store.get_meta("plan_signature")
        if existing_signature and existing_signature != config.plan_signature:
            raise ValueError("Seed-harvest checkpoint belongs to a different seed/depth plan. Use a new --name.")
        store.set_meta("plan_signature", config.plan_signature)
        store.set_meta("access_mode", "session" if cookie else "anonymous")
        store.register(config.seeds)
        _notify(progress, "seed_harvest_start", seeds=len(config.seeds), checkpoint=str(checkpoint))

        eligible = store.eligible()
        for index, task in enumerate(eligible, 1):
            seed_key = task["seed_key"]
            attempt = store.start(seed_key)
            _notify(progress, "seed_harvest_item_start", index=index, total=len(eligible), seed=task["seed_input"], attempt=attempt)
            try:
                result = investigator(
                    task["seed_input"],
                    max_comments=config.max_comments,
                    comment_pages=config.comment_pages,
                    max_reposts=config.max_reposts,
                    repost_pages=config.repost_pages,
                    author_posts=config.author_posts,
                    author_pages=config.author_pages,
                    cookie=cookie,
                )
                inserted, updated = store.upsert_records(seed_key, result.records)
                store.complete(seed_key, result)
                store.add_event(
                    "seed_completed",
                    seed_key,
                    inserted=inserted,
                    updated=updated,
                    records=len(result.records),
                    comments=len(result.comments),
                    reposts=len(result.reposts),
                    author_posts=len(result.author_posts),
                    surface_status=result.surface_status,
                )
                _notify(progress, "seed_harvest_item_complete", seed=task["seed_input"], inserted=inserted, updated=updated, comments=len(result.comments))
            except Exception as exc:
                wait = config.base_backoff_seconds * (2 ** max(0, attempt - 1))
                if _rate_limit_error(exc) and wait > config.max_inline_wait_seconds:
                    store.defer(seed_key, str(exc), wait)
                    store.add_event("seed_deferred", seed_key, wait_seconds=wait, error=type(exc).__name__)
                    _notify(progress, "seed_harvest_item_deferred", seed=task["seed_input"], wait_seconds=wait)
                elif _retryable(exc) and attempt <= config.max_retries:
                    wait = min(wait, config.max_inline_wait_seconds)
                    store.defer(seed_key, str(exc), wait)
                    store.add_event("seed_retry_deferred", seed_key, wait_seconds=wait, error=type(exc).__name__)
                    _notify(progress, "seed_harvest_item_deferred", seed=task["seed_input"], wait_seconds=wait)
                else:
                    store.fail(seed_key, str(exc))
                    store.add_event("seed_failed", seed_key, error=type(exc).__name__, message=str(exc)[:500])
                    _notify(progress, "seed_harvest_item_failed", seed=task["seed_input"], message=str(exc))
                    if not config.continue_on_error:
                        raise
            if config.inter_seed_delay_seconds > 0 and index < len(eligible):
                sleeper(config.inter_seed_delay_seconds)

        records = store.records()
        seeds = store.seed_rows()
        counts = store.counts()
        manifest = {
            "generated_at": utc_iso(),
            "operation": "weibo_seed_harvest",
            "plan_signature": config.plan_signature,
            "access_mode": "session" if cookie else "anonymous",
            "planned_seeds": len(config.seeds),
            "seed_counts": counts,
            "unique_records": len(records),
            "configuration": {
                "max_comments": config.max_comments,
                "comment_pages": config.comment_pages,
                "max_reposts": config.max_reposts,
                "repost_pages": config.repost_pages,
                "author_posts": config.author_posts,
                "author_pages": config.author_pages,
                "inter_seed_delay_seconds": config.inter_seed_delay_seconds,
            },
            "methodology": "Known public seed expansion with durable per-seed checkpoints. Gated optional surfaces are recorded independently; no login automation or access-control bypass.",
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        _write_seed_status(seeds, status_path)
        outputs = [str(checkpoint.resolve()), str(manifest_path.resolve()), str(status_path.resolve())]
        if records:
            save_records(records, records_path, metadata=manifest)
            outputs.extend([
                str(records_path.resolve()),
                str(records_path.with_suffix(".xlsx").resolve()),
                str(records_path.with_suffix(".metadata.json").resolve()),
                _write_jsonl(records, jsonl_path),
            ])
        _notify(progress, "seed_harvest_complete", seed_counts=counts, unique_records=len(records), outputs=outputs)
        return outputs
