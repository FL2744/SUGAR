from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Iterable

from .harvest import run_harvest
from .models import PostRecord
from .utils import utc_iso
from .weibo_investigation import WeiboInvestigation, investigate_weibo_seed, save_weibo_investigation


ProgressCallback = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class QualificationThresholds:
    """Project acceptance profile for State-facing research use.

    These are SUGAR project thresholds, not an official Department of State certification or ATO.
    They are intentionally explicit so the team can revise them without recollecting data.
    """

    minimum_unique_records: int = 1000
    minimum_task_completion_rate: float = 0.90
    maximum_failed_task_rate: float = 0.10
    maximum_access_limited_task_rate: float = 0.20
    minimum_query_coverage: float = 0.75
    minimum_identity_coverage: float = 0.995
    minimum_provenance_coverage: float = 0.98
    minimum_timestamp_coverage: float = 0.90
    minimum_text_coverage: float = 0.95
    maximum_duplicate_fraction: float = 0.85
    minimum_seed_success_rate: float = 0.80
    minimum_comment_surface_success_rate: float = 0.50
    minimum_replicate_jaccard: float = 0.40
    minimum_human_audit_labels: int = 50
    minimum_human_relevance_rate: float = 0.50

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "QualificationThresholds":
        data = data or {}
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        values = {key: value for key, value in data.items() if key in allowed}
        return cls(**values)


@dataclass
class QualificationCheck:
    name: str
    value: float | int | str | None
    threshold: float | int | str
    passed: bool
    severity: str = "required"
    note: str = ""


@dataclass
class QualificationResult:
    status: str
    generated_at: str
    thresholds: dict[str, Any]
    aggregate_metrics: dict[str, Any]
    replicate_metrics: list[dict[str, Any]] = field(default_factory=list)
    investigations: list[dict[str, Any]] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)


def _notify(progress: ProgressCallback | None, event: str, **values: Any) -> None:
    if progress is not None:
        progress(event, values)


def _safe_ratio(numerator: int | float, denominator: int | float) -> float | None:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 4)


def _looks_access_limited(error: str) -> bool:
    text = (error or "").casefold()
    markers = (
        "login",
        "logged-in",
        "authorized session",
        "authorization",
        "verification",
        "access limited",
        "access_limited",
        "cookie",
        "risk control",
        "risk-control",
        "需要登录",
        "访问频次过高",
    )
    return any(marker in text for marker in markers)


def _load_checkpoint(checkpoint: str | Path) -> tuple[list[PostRecord], list[dict[str, Any]], dict[str, int], int]:
    path = Path(checkpoint)
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(path)
    try:
        records = [
            PostRecord(**json.loads(row[0]))
            for row in connection.execute("SELECT payload_json FROM records").fetchall()
        ]
        tasks = [
            {
                "task_id": row[0],
                "source": row[1],
                "query": row[2],
                "page_start": int(row[3]),
                "page_count": int(row[4]),
                "status": row[5],
                "attempts": int(row[6]),
                "records_seen": int(row[7]),
                "last_error": row[8] or "",
            }
            for row in connection.execute(
                "SELECT task_id,source,query_text,page_start,page_count,status,attempts,records_seen,last_error FROM tasks"
            ).fetchall()
        ]
        event_counts = {
            str(name): int(count)
            for name, count in connection.execute(
                "SELECT event_type,COUNT(*) FROM events GROUP BY event_type"
            ).fetchall()
        }
        raw_returned = int(
            connection.execute(
                "SELECT COALESCE(SUM(records_seen),0) FROM tasks WHERE status='completed'"
            ).fetchone()[0]
        )
        return records, tasks, event_counts, raw_returned
    finally:
        connection.close()


def _record_queries(record: PostRecord) -> set[str]:
    return {str(value).strip() for value in (record.query_matches or [record.query]) if str(value).strip()}


def inspect_weibo_checkpoint(
    checkpoint: str | Path,
    *,
    expected_terms: Iterable[str] = (),
) -> dict[str, Any]:
    records, tasks, events, raw_returned = _load_checkpoint(checkpoint)
    task_total = len(tasks)
    completed = sum(task["status"] == "completed" for task in tasks)
    failed = sum(task["status"] == "failed" for task in tasks)
    deferred = sum(task["status"] == "deferred" for task in tasks)
    access_limited = sum(
        task["status"] in {"failed", "deferred"} and _looks_access_limited(task["last_error"])
        for task in tasks
    )
    terms = [str(term).strip() for term in expected_terms if str(term).strip()]
    observed_terms: set[str] = set()
    for record in records:
        observed_terms.update(_record_queries(record))

    unique = len(records)
    duplicate_fraction = 0.0
    if raw_returned > 0:
        duplicate_fraction = round(max(0.0, min(1.0, 1.0 - (unique / raw_returned))), 4)

    def coverage(predicate) -> float:
        if not records:
            return 0.0
        return round(sum(1 for record in records if predicate(record)) / len(records), 4)

    query_yield: dict[str, int] = {}
    for term in terms or sorted(observed_terms):
        query_yield[term] = sum(term in _record_queries(record) for record in records)

    pages_completed = [
        task["page_start"] + max(0, task["page_count"] - 1)
        for task in tasks
        if task["status"] == "completed" and task["page_start"] > 0
    ]

    return {
        "checkpoint": str(Path(checkpoint).resolve()),
        "unique_records": unique,
        "raw_records_returned": raw_returned,
        "estimated_duplicate_fraction": duplicate_fraction,
        "planned_tasks": task_total,
        "completed_tasks": completed,
        "failed_tasks": failed,
        "deferred_tasks": deferred,
        "access_limited_tasks": access_limited,
        "task_completion_rate": _safe_ratio(completed, task_total) or 0.0,
        "failed_task_rate": _safe_ratio(failed, task_total) or 0.0,
        "access_limited_task_rate": _safe_ratio(access_limited, task_total) or 0.0,
        "rate_limit_events": int(events.get("rate_limit", 0)),
        "transient_retry_events": int(events.get("transient_retry", 0)),
        "query_coverage": _safe_ratio(sum(1 for term in terms if term in observed_terms), len(terms)) if terms else None,
        "queries_expected": len(terms),
        "queries_observed": sum(1 for term in terms if term in observed_terms) if terms else len(observed_terms),
        "query_yield": query_yield,
        "identity_coverage": coverage(lambda row: bool(row.native_id and row.canonical_url)),
        "provenance_coverage": coverage(
            lambda row: bool(row.source_mode and row.source_url and row.collected_at and _record_queries(row))
        ),
        "timestamp_coverage": coverage(lambda row: bool(row.published_at)),
        "text_coverage": coverage(lambda row: bool((row.original_text or "").strip())),
        "author_coverage": coverage(lambda row: bool(row.author_handle or row.author_name)),
        "maximum_completed_page": max(pages_completed, default=0),
        "record_keys": sorted(row.record_key for row in records if row.record_key),
    }


def compare_replicates(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    if len(metrics) < 2:
        return {"replicates": len(metrics), "pairwise_jaccard": [], "minimum_jaccard": None, "mean_jaccard": None}
    values: list[float] = []
    pairs: list[dict[str, Any]] = []
    for left_index in range(len(metrics)):
        for right_index in range(left_index + 1, len(metrics)):
            left = set(metrics[left_index].get("record_keys") or [])
            right = set(metrics[right_index].get("record_keys") or [])
            union = left | right
            score = 1.0 if not union else round(len(left & right) / len(union), 4)
            values.append(score)
            pairs.append({"left": left_index + 1, "right": right_index + 1, "jaccard": score})
    return {
        "replicates": len(metrics),
        "pairwise_jaccard": pairs,
        "minimum_jaccard": min(values) if values else None,
        "mean_jaccard": round(mean(values), 4) if values else None,
    }


def _investigation_summary(seed: str, result: WeiboInvestigation | None, error: Exception | None = None) -> dict[str, Any]:
    if error is not None:
        return {"seed": seed, "status": "failed", "error": f"{type(error).__name__}: {error}"}
    assert result is not None
    surface = result.surface_status or {}
    return {
        "seed": seed,
        "status": "ok",
        "record_key": result.seed.record_key,
        "comments_retrieved": len(result.comments),
        "reposts_retrieved": len(result.reposts),
        "author_posts_retrieved": len(result.author_posts),
        "seed_surface": surface.get("seed", {}).get("status", "unknown"),
        "comment_surface": surface.get("comments", {}).get("status", "unknown"),
        "repost_surface": surface.get("reposts", {}).get("status", "unknown"),
        "author_timeline_surface": surface.get("author_timeline", {}).get("status", "unknown"),
        "reported_comments": int((result.seed.engagement or {}).get("replies", 0) or 0),
        "reported_reposts": int((result.seed.engagement or {}).get("reposts", 0) or 0),
        "comment_capture_ratio": (result.insights.get("retrieval") or {}).get("comment_retrieved_to_reported_ratio"),
        "top_responses": (result.insights.get("response_context") or {}).get("top_public_responses", [])[:5],
    }


def _deterministic_audit_sample(records: list[PostRecord], size: int) -> list[PostRecord]:
    size = max(0, int(size))
    ranked = sorted(
        records,
        key=lambda row: hashlib.sha256((row.record_key or row.canonical_url).encode("utf-8")).hexdigest(),
    )
    return ranked[: min(size, len(ranked))]


def write_human_audit_sample(records: list[PostRecord], path: str | Path, *, size: int = 100) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sample = _deterministic_audit_sample(records, size)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "record_key",
                "query_matches",
                "published_at",
                "author",
                "text",
                "url",
                "human_relevant",
                "human_provenance_ok",
                "human_notes",
            ],
        )
        writer.writeheader()
        for row in sample:
            writer.writerow(
                {
                    "record_key": row.record_key,
                    "query_matches": " | ".join(sorted(_record_queries(row))),
                    "published_at": row.published_at,
                    "author": row.author_name or row.author_handle,
                    "text": row.original_text,
                    "url": row.canonical_url,
                    "human_relevant": "",
                    "human_provenance_ok": "",
                    "human_notes": "",
                }
            )
    return str(path.resolve())


def read_human_audit(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {"provided": False, "labeled": 0, "relevance_rate": None, "provenance_ok_rate": None}
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    relevant: list[bool] = []
    provenance: list[bool] = []
    truthy = {"1", "true", "yes", "y", "relevant", "ok"}
    falsy = {"0", "false", "no", "n", "irrelevant", "bad"}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            relevance = str(row.get("human_relevant", "")).strip().casefold()
            provenance_value = str(row.get("human_provenance_ok", "")).strip().casefold()
            if relevance in truthy | falsy:
                relevant.append(relevance in truthy)
            if provenance_value in truthy | falsy:
                provenance.append(provenance_value in truthy)
    return {
        "provided": True,
        "path": str(path.resolve()),
        "labeled": len(relevant),
        "provenance_labeled": len(provenance),
        "relevance_rate": round(sum(relevant) / len(relevant), 4) if relevant else None,
        "provenance_ok_rate": round(sum(provenance) / len(provenance), 4) if provenance else None,
    }


def _aggregate_runs(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    if not metrics:
        return {}
    numeric_min = (
        "unique_records",
        "task_completion_rate",
        "query_coverage",
        "identity_coverage",
        "provenance_coverage",
        "timestamp_coverage",
        "text_coverage",
    )
    numeric_max = (
        "failed_task_rate",
        "access_limited_task_rate",
        "estimated_duplicate_fraction",
        "rate_limit_events",
    )
    result: dict[str, Any] = {"replicate_count": len(metrics), "record_counts": [row["unique_records"] for row in metrics]}
    for key in numeric_min:
        values = [row.get(key) for row in metrics if row.get(key) is not None]
        result[key] = min(values) if values else None
    for key in numeric_max:
        values = [row.get(key) for row in metrics if row.get(key) is not None]
        result[key] = max(values) if values else None
    return result


def evaluate_qualification(
    aggregate: dict[str, Any],
    investigations: list[dict[str, Any]],
    reproducibility: dict[str, Any],
    audit: dict[str, Any],
    thresholds: QualificationThresholds,
) -> tuple[str, list[QualificationCheck], list[str]]:
    checks: list[QualificationCheck] = []

    def minimum(name: str, value: Any, threshold: float | int, *, severity: str = "required", note: str = "") -> None:
        passed = value is not None and float(value) >= float(threshold)
        checks.append(QualificationCheck(name, value, threshold, passed, severity, note))

    def maximum(name: str, value: Any, threshold: float | int, *, severity: str = "required", note: str = "") -> None:
        passed = value is not None and float(value) <= float(threshold)
        checks.append(QualificationCheck(name, value, threshold, passed, severity, note))

    minimum("unique_records", aggregate.get("unique_records"), thresholds.minimum_unique_records)
    minimum("task_completion_rate", aggregate.get("task_completion_rate"), thresholds.minimum_task_completion_rate)
    maximum("failed_task_rate", aggregate.get("failed_task_rate"), thresholds.maximum_failed_task_rate)
    maximum("access_limited_task_rate", aggregate.get("access_limited_task_rate"), thresholds.maximum_access_limited_task_rate, severity="advisory")
    minimum("query_coverage", aggregate.get("query_coverage"), thresholds.minimum_query_coverage)
    minimum("identity_coverage", aggregate.get("identity_coverage"), thresholds.minimum_identity_coverage)
    minimum("provenance_coverage", aggregate.get("provenance_coverage"), thresholds.minimum_provenance_coverage)
    minimum("timestamp_coverage", aggregate.get("timestamp_coverage"), thresholds.minimum_timestamp_coverage)
    minimum("text_coverage", aggregate.get("text_coverage"), thresholds.minimum_text_coverage)
    maximum("duplicate_fraction", aggregate.get("estimated_duplicate_fraction"), thresholds.maximum_duplicate_fraction, severity="advisory")

    if investigations:
        seed_success = sum(row.get("status") == "ok" and row.get("seed_surface") == "ok" for row in investigations) / len(investigations)
        comment_candidates = [row for row in investigations if row.get("status") == "ok" and int(row.get("reported_comments", 0) or 0) > 0]
        comment_success = (
            sum(row.get("comment_surface") == "ok" and int(row.get("comments_retrieved", 0) or 0) > 0 for row in comment_candidates) / len(comment_candidates)
            if comment_candidates
            else 1.0
        )
        minimum("seed_investigation_success_rate", round(seed_success, 4), thresholds.minimum_seed_success_rate)
        minimum("comment_surface_success_rate", round(comment_success, 4), thresholds.minimum_comment_surface_success_rate)
    else:
        checks.append(QualificationCheck("seed_investigation_success_rate", None, thresholds.minimum_seed_success_rate, False, "required", "No real-post seeds were supplied."))
        checks.append(QualificationCheck("comment_surface_success_rate", None, thresholds.minimum_comment_surface_success_rate, False, "required", "No real-post seeds were supplied."))

    if reproducibility.get("replicates", 0) >= 2:
        minimum("replicate_minimum_jaccard", reproducibility.get("minimum_jaccard"), thresholds.minimum_replicate_jaccard, severity="advisory")

    audit_labels = int(audit.get("labeled", 0) or 0)
    minimum("human_audit_labels", audit_labels, thresholds.minimum_human_audit_labels, severity="human")
    if audit_labels:
        minimum("human_relevance_rate", audit.get("relevance_rate"), thresholds.minimum_human_relevance_rate, severity="human")

    required_failures = [check for check in checks if check.severity == "required" and not check.passed]
    human_failures = [check for check in checks if check.severity == "human" and not check.passed]
    advisory_failures = [check for check in checks if check.severity == "advisory" and not check.passed]
    if required_failures:
        status = "fail"
    elif human_failures or advisory_failures:
        status = "conditional"
    else:
        status = "pass"

    limitations = [
        "This is a SUGAR project qualification profile for State-facing research, not an official Department of State security authorization, ATO, records determination, procurement approval, or AI certification.",
        "Weibo public/mobile surfaces can change independently; successful seed retrieval does not imply search, repost, or account-timeline access is complete.",
        "Search-result reproducibility measures accessible ranked-result overlap, not recall against the full Weibo corpus.",
        "A human relevance audit is required before a technically successful collection campaign should be described as analytically qualified.",
    ]
    return status, checks, limitations


def _markdown_report(result: QualificationResult) -> str:
    lines = [
        "# SUGAR Weibo Industrial Qualification Report",
        "",
        f"**Status:** {result.status.upper()}",
        f"**Generated:** {result.generated_at}",
        "",
        "> This is a SUGAR project acceptance profile for State-facing research. It is not an official Department of State certification or security authorization.",
        "",
        "## Acceptance checks",
        "",
        "| Check | Value | Threshold | Result | Severity |",
        "|---|---:|---:|---|---|",
    ]
    for raw in result.checks:
        mark = "PASS" if raw["passed"] else "FAIL"
        lines.append(f"| {raw['name']} | {raw['value']} | {raw['threshold']} | {mark} | {raw['severity']} |")
    lines.extend(["", "## Aggregate collection metrics", "", "```json", json.dumps(result.aggregate_metrics, ensure_ascii=False, indent=2, sort_keys=True), "```", "", "## Real-post investigations", ""])
    if result.investigations:
        for row in result.investigations:
            lines.append(
                f"- `{row.get('seed')}` — {row.get('status')} — comments {row.get('comments_retrieved', 0)} — "
                f"seed={row.get('seed_surface', 'unknown')} comments={row.get('comment_surface', 'unknown')} "
                f"reposts={row.get('repost_surface', 'unknown')} timeline={row.get('author_timeline_surface', 'unknown')}"
            )
    else:
        lines.append("- No seed investigations supplied.")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in result.limitations)
    lines.append("")
    return "\n".join(lines)


def run_weibo_qualification(
    config: dict[str, Any],
    secrets: dict[str, str] | None = None,
    progress: ProgressCallback | None = None,
    *,
    harvest_runner: Callable[..., list[str]] = run_harvest,
    investigator: Callable[..., WeiboInvestigation] = investigate_weibo_seed,
) -> list[str]:
    secrets = secrets or {}
    raw = config.get("qualification") or {}
    out_dir = Path(config.get("output_directory") or raw.get("output_directory") or ".").expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    name = str(raw.get("name") or config.get("name") or "weibo_qualification").strip().replace(" ", "_")
    terms = [str(value).strip() for value in (config.get("terms") or raw.get("terms") or []) if str(value).strip()]
    if not terms:
        raise ValueError("Weibo qualification requires at least one keyword/query term.")
    seeds = [str(value).strip() for value in (raw.get("seeds") or []) if str(value).strip()]
    repeats = max(1, int(raw.get("replicates", 2)))
    thresholds = QualificationThresholds.from_mapping(raw.get("thresholds"))
    audit_size = max(0, int(raw.get("audit_sample_size", 100)))
    audit_file = raw.get("audit_file") or None

    _notify(progress, "qualification_start", terms=len(terms), seeds=len(seeds), replicates=repeats)
    replicate_metrics: list[dict[str, Any]] = []
    replicate_checkpoints: list[Path] = []
    for replicate in range(1, repeats + 1):
        replicate_name = f"{name}.rep{replicate}"
        harvest_config = dict(config)
        harvest_config["sources"] = ["weibo"]
        harvest_config["terms"] = terms
        harvest_config["output_directory"] = str(out_dir)
        harvest_raw = dict(config.get("harvest") or {})
        harvest_raw["name"] = replicate_name
        harvest_config["harvest"] = harvest_raw
        _notify(progress, "qualification_replicate_start", replicate=replicate, total=repeats)
        harvest_runner(harvest_config, secrets, progress=progress)
        checkpoint = out_dir / f"{replicate_name}.harvest.sqlite3"
        replicate_checkpoints.append(checkpoint)
        metrics = inspect_weibo_checkpoint(checkpoint, expected_terms=terms)
        replicate_metrics.append(metrics)
        _notify(progress, "qualification_replicate_complete", replicate=replicate, unique_records=metrics["unique_records"], completion=metrics["task_completion_rate"])

    investigations: list[dict[str, Any]] = []
    investigation_dir = out_dir / f"{name}.investigations"
    investigation_dir.mkdir(parents=True, exist_ok=True)
    cookie = secrets.get("weibo_cookie", "")
    for index, seed in enumerate(seeds, 1):
        _notify(progress, "qualification_seed_start", seed=seed, index=index, total=len(seeds))
        try:
            result = investigator(
                seed,
                max_comments=int(raw.get("max_comments", 50)),
                comment_pages=int(raw.get("comment_pages", 3)),
                max_reposts=int(raw.get("max_reposts", 25)),
                repost_pages=int(raw.get("repost_pages", 2)),
                author_posts=int(raw.get("author_posts", 20)),
                author_pages=int(raw.get("author_pages", 1)),
                cookie=cookie,
            )
            seed_name = f"seed_{index}_{result.seed.native_id or index}"
            save_weibo_investigation(result, investigation_dir, name=seed_name)
            summary = _investigation_summary(seed, result)
        except Exception as exc:
            summary = _investigation_summary(seed, None, exc)
        investigations.append(summary)
        _notify(progress, "qualification_seed_complete", seed=seed, status=summary.get("status"), comments=summary.get("comments_retrieved", 0))

    reproducibility = compare_replicates(replicate_metrics)
    aggregate = _aggregate_runs(replicate_metrics)
    aggregate["reproducibility"] = reproducibility

    first_records, _, _, _ = _load_checkpoint(replicate_checkpoints[0])
    audit_sample_path = out_dir / f"{name}.human_audit.csv"
    write_human_audit_sample(first_records, audit_sample_path, size=audit_size)
    audit = read_human_audit(audit_file)
    aggregate["human_audit"] = audit

    status, checks, limitations = evaluate_qualification(aggregate, investigations, reproducibility, audit, thresholds)
    result = QualificationResult(
        status=status,
        generated_at=utc_iso(),
        thresholds=asdict(thresholds),
        aggregate_metrics=aggregate,
        replicate_metrics=[{key: value for key, value in row.items() if key != "record_keys"} for row in replicate_metrics],
        investigations=investigations,
        checks=[asdict(check) for check in checks],
        limitations=limitations,
    )

    json_path = out_dir / f"{name}.qualification.json"
    md_path = out_dir / f"{name}.qualification.md"
    json_path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown_report(result), encoding="utf-8")
    outputs = [str(json_path.resolve()), str(md_path.resolve()), str(audit_sample_path.resolve()), *[str(path.resolve()) for path in replicate_checkpoints]]
    result.outputs = outputs
    json_path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    _notify(progress, "qualification_complete", status=status, outputs=outputs)
    return outputs
