"""Run one bounded read from SUGAR's Bluesky and Mastodon search adapters.

The live portion is deliberately small: one public search request to Bluesky AppView and, only when
an authorized user token with ``read:search`` is configured, one request to a Mastodon instance.
Each request is limited to five records and one page; redirects and retries are disabled and no
writes are made. It stores normalized rows only in a temporary SQLite checkpoint and emits aggregate
metrics without post text, IDs, or account names.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from sugar_core import __version__
from sugar_core.collectors import collect_bluesky, collect_mastodon
from sugar_core.harvest import HarvestStore
if __package__:
    from .benchmark_utils import atomic_write_text
else:
    from benchmark_utils import atomic_write_text

DEFAULT_QUERY = "education"
MAX_RECORDS_PER_SOURCE = 5


class MeteredSession(requests.Session):
    """Requests session that records safe aggregate telemetry and never follows redirects."""

    def __init__(self) -> None:
        super().__init__()
        self.headers.update({
            "User-Agent": "SUGAR research client (+https://github.com/FL2744/SUGAR)",
            "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
        })
        self.events: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        kwargs["allow_redirects"] = False
        started = time.perf_counter()
        try:
            response = super().get(url, **kwargs)
        except requests.RequestException as exc:
            self.events.append({
                "status_code": None,
                "elapsed_seconds": round(time.perf_counter() - started, 6),
                "response_bytes": 0,
                "error_type": type(exc).__name__,
                "rate_limit_headers": {},
            })
            raise

        rate_headers = {
            name: response.headers[name]
            for name in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After")
            if name in response.headers
        }
        self.events.append({
            "status_code": int(response.status_code),
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "response_bytes": len(response.content),
            "error_type": "",
            "rate_limit_headers": rate_headers,
        })
        if 300 <= response.status_code < 400:
            response.close()
            raise requests.TooManyRedirects("The bounded benchmark stops at the first redirect.")
        return response


def _validate_instance(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Mastodon instance must be an HTTPS origin, such as https://mastodon.social.")
    return f"https://{parsed.netloc}"


def _source_result(source: str, rows: list[Any], session: MeteredSession, elapsed: float, error: Exception | None) -> dict[str, Any]:
    request_events = session.events
    statuses = [event["status_code"] for event in request_events if event.get("status_code") is not None]
    status_code = statuses[-1] if statuses else None
    if error is None:
        status = "success" if rows else "zero_results"
    elif status_code in {401, 403, 429}:
        status = "access_limited"
    elif isinstance(error, requests.Timeout):
        status = "timeout"
    elif status_code is not None:
        status = "http_error"
    else:
        status = "network_or_collector_error"

    fields = {
        "identity": lambda row: bool(row.native_id or row.canonical_url),
        "canonical_url": lambda row: bool(row.canonical_url),
        "published_at": lambda row: bool(row.published_at),
        "author_handle": lambda row: bool(row.author_handle),
        "text": lambda row: bool(row.original_text),
        "query_provenance": lambda row: bool(row.query_matches or row.query),
        "source_provenance": lambda row: bool(row.source_host and row.source_url),
    }
    completeness = {
        name: {
            "present": sum(1 for row in rows if predicate(row)),
            "records": len(rows),
            "fraction": round(sum(1 for row in rows if predicate(row)) / len(rows), 4) if rows else None,
        }
        for name, predicate in fields.items()
    }
    keys = [row.record_key for row in rows if row.record_key]
    unique_keys = set(keys)
    return {
        "source": source,
        "status": status,
        "records_returned": len(rows),
        "unique_records": len(unique_keys),
        "duplicate_fraction": round((len(keys) - len(unique_keys)) / len(keys), 4) if keys else None,
        "field_completeness": completeness,
        "elapsed_seconds": round(elapsed, 6),
        "records_per_second": round(len(rows) / elapsed, 4) if elapsed > 0 else None,
        "request_count": len(request_events),
        "requests": request_events,
        "error_type": type(error).__name__ if error is not None else "",
        "api_body_saved": False,
        "personal_identifiers_saved": False,
    }


def run_benchmark(
    query: str = DEFAULT_QUERY,
    mastodon_instance: str = "https://mastodon.social",
    *,
    mastodon_token: str | None = None,
) -> dict[str, Any]:
    """Run the bounded live sample and return a privacy-minimized report.

    Mastodon status search is skipped unless ``mastodon_token`` or
    ``SUGAR_MASTODON_TOKEN`` supplies an authorized user token with ``read:search``.
    """
    clean_query = " ".join(str(query or "").split())
    if not clean_query or len(clean_query) > 160:
        raise ValueError("Provide a non-empty search query of at most 160 characters.")
    instance = _validate_instance(mastodon_instance)
    token = (os.environ.get("SUGAR_MASTODON_TOKEN", "") if mastodon_token is None else mastodon_token).strip()
    query_hash = hashlib.sha256(clean_query.encode("utf-8")).hexdigest()

    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    outcomes: dict[str, tuple[list[Any], dict[str, Any]]] = {}
    for source in ("bluesky", "mastodon"):
        if source == "mastodon" and not token:
            outcomes[source] = ([], {
                "source": source,
                "status": "credential_required",
                "records_returned": 0,
                "unique_records": 0,
                "duplicate_fraction": None,
                "field_completeness": {},
                "elapsed_seconds": 0.0,
                "records_per_second": None,
                "request_count": 0,
                "requests": [],
                "error_type": "",
                "access_requirement": "user token with read:search",
                "api_body_saved": False,
                "personal_identifiers_saved": False,
                "instance": urlparse(instance).netloc,
            })
            continue
        session = MeteredSession()
        started = time.perf_counter()
        rows: list[Any] = []
        error: Exception | None = None
        try:
            if source == "bluesky":
                rows = collect_bluesky(
                    search_terms=[clean_query],
                    max_posts_per_query=MAX_RECORDS_PER_SOURCE,
                    max_pages_per_query=1,
                    session=session,
                )
            else:
                rows = collect_mastodon(
                    instance_url=instance,
                    search_terms=[clean_query],
                    access_token=token,
                    max_posts_per_query=MAX_RECORDS_PER_SOURCE,
                    max_pages_per_query=1,
                    session=session,
                )
        except Exception as exc:  # Keep the other platform's bounded probe independent.
            error = exc
        elapsed = time.perf_counter() - started
        source_report = _source_result(source, rows, session, elapsed, error)
        if source == "mastodon":
            source_report["instance"] = urlparse(instance).netloc
        else:
            source_report["instance"] = "public.api.bsky.app"
        outcomes[source] = (rows, source_report)
        session.close()

    all_rows = [row for rows, _ in outcomes.values() for row in rows]
    checkpoint: dict[str, Any]
    with tempfile.TemporaryDirectory(prefix="sugar-live-benchmark-") as temp_dir:
        store_path = Path(temp_dir) / "checkpoint.sqlite3"
        with HarvestStore(store_path) as store:
            upsert_started = time.perf_counter()
            inserted, updated = store.upsert_records(all_rows)
            upsert_seconds = time.perf_counter() - upsert_started
            read_started = time.perf_counter()
            restored = store.records()
            read_seconds = time.perf_counter() - read_started
            expected = sorted((row.record_key, row.original_text) for row in all_rows)
            actual = sorted((row.record_key, row.original_text) for row in restored)
            checkpoint = {
                "records_submitted": len(all_rows),
                "unique_records_stored": store.count_records(),
                "inserted": inserted,
                "updated": updated,
                "records_restored": len(restored),
                "round_trip_exact": expected == actual,
                "upsert_seconds": round(upsert_seconds, 6),
                "read_seconds": round(read_seconds, 6),
                "temporary_checkpoint_removed": True,
            }

    finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return {
        "schema_version": 1,
        "operation": "bounded_live_public_api_benchmark",
        "sugar_version": __version__,
        "python": platform.python_version(),
        "started_at": started_at,
        "finished_at": finished_at,
        "query_sha256": query_hash,
        "query_length": len(clean_query),
        "request_policy": {
            "sources": ["bluesky", "mastodon"],
            "queries_per_source": 1,
            "max_records_per_source": MAX_RECORDS_PER_SOURCE,
            "max_pages_per_source": 1,
            "max_http_requests": 2,
            "retries": 0,
            "redirects_followed": 0,
            "authentication_used": bool(token),
            "authenticated_sources": ["mastodon"] if token else [],
            "writes_performed": False,
        },
        "sources": {name: result for name, (_, result) in outcomes.items()},
        "local_checkpoint": checkpoint,
        "intelligence": {
            "status": "not_scored",
            "reason": "Live retrieval and storage are measured here; analytic accuracy needs independent human labels and model outputs.",
        },
        "limitations": [
            "One query and one page per platform are an integration sample, not a representative corpus or a live load test.",
            "Mastodon status search requires a read:search user token and an instance with search configured; without the token, the request is skipped.",
            "The benchmark does not follow redirects, retry requests, perform writes, or save post text, IDs, or account names.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default=DEFAULT_QUERY, help="One public search term (stored only as a SHA-256 hash).")
    parser.add_argument("--mastodon-instance", default="https://mastodon.social", help="HTTPS Mastodon instance origin.")
    parser.add_argument("--output", type=Path, required=True, help="Path for the aggregate JSON report.")
    args = parser.parse_args(argv)
    report = run_benchmark(args.query, args.mastodon_instance)
    output = args.output.expanduser().resolve()
    atomic_write_text(output, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
