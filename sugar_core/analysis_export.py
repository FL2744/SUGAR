"""Full-text analysis tables, daily aggregates and explicitly qualified GIS features."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
import zipfile
from collections import defaultdict
from typing import Any

from . import redaction
from .post_map import post_pins
from .sentiment import NOTE, score_item
from .temporal import iso_utc, publication_key

COLUMNS = ["item_id", "run_id", "project_id", "native_id", "platform", "content_type", "author", "url", "source_mode",
           "published_at", "retrieved_at", "publication_date_utc", "language", "original_text", "translated_text",
           "translation_provider", "translation_model", "translation_target_language", "query", "query_dispatched", "queries",
           "status", "verdict", "reviewer", "reviewed_at", "tags", "engagement", "origin_latitude", "origin_longitude", "origin_basis",
           "map_latitude", "map_longitude", "map_placement", "mentioned_places", "valence", "intensity", "direction",
           "sentiment_method", "sentiment_basis", "sentiment_status", "sentiment_reason", "sentiment_terms", "source_metadata",
           "activity_codes", "proposed_priority_tiers", "confirmed_priority_tiers", "proposed_audience_groups", "confirmed_audience_groups"]


def _csv(rows: list[dict], columns: list[str]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        cells = []
        for key in columns:
            value = row.get(key)
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            cells.append("" if value is None else value)
        writer.writerow(cells)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def analysis_files(project: Any, items: list[Any], *, mapped: dict | None = None) -> dict[str, bytes]:
    # Callers supply newest runs first. Keep one accepted observation per stable item ID.
    unique = {}
    for item in items:
        if item.status in {"collected", "processed"}:
            unique.setdefault(item.item_id, item)
    accepted = sorted(unique.values(), key=lambda i: publication_key(i, "oldest"))
    mapped = mapped if mapped is not None else post_pins(project, accepted)
    pins = {p["item_id"]: p for p in mapped["pins"]}
    reviews = project.review.state()
    from .activity_coding import CodingStore
    coding = CodingStore(project).state()
    rows, features = [], []
    daily: dict[tuple, list[dict]] = defaultdict(list)
    for item in accepted:
        pin = pins.get(item.item_id) or {}
        origin = pin.get("origin") or {}
        review = reviews.get(item.item_id) or {}
        tr = item.translation if isinstance(item.translation, dict) else {}
        score = pin.get("sentiment") or score_item(item)
        published = iso_utc(item.published_at)
        row = {"item_id": item.item_id, "run_id": item.run_id, "project_id": item.project_id, "native_id": item.native_id,
               "platform": item.platform, "content_type": item.content_type, "author": item.author, "url": item.url, "source_mode": item.source_mode,
               "published_at": published, "retrieved_at": iso_utc(item.retrieved_at), "publication_date_utc": published[:10], "language": item.language,
               "original_text": item.original_text, "translated_text": tr.get("text", "") if tr.get("status") == "done" else "",
               "translation_provider": tr.get("provider", ""), "translation_model": tr.get("model", ""), "translation_target_language": tr.get("target_language", ""),
               "query": item.query, "query_dispatched": item.query_dispatched, "queries": item.queries, "status": item.status,
               "verdict": review.get("verdict", ""), "reviewer": review.get("verdict_by", ""), "reviewed_at": review.get("verdict_at", ""), "tags": review.get("tags", []),
               "engagement": item.engagement, "source_metadata": item.source_metadata, "origin_latitude": origin.get("latitude"), "origin_longitude": origin.get("longitude"), "origin_basis": origin.get("kind", ""),
               "map_latitude": pin.get("latitude"), "map_longitude": pin.get("longitude"), "map_placement": pin.get("placement", "unlocated"),
               "mentioned_places": pin.get("targets", []), **{k: score[k] for k in ("valence", "intensity", "direction")},
               **{f"sentiment_{k}": score[k] for k in ("method", "basis", "status", "reason")}, "sentiment_terms": score["matched_terms"]}
        rows.append(row)
        codes = coding.get(item.item_id, {}).get("codes", [])
        row["activity_codes"] = codes
        for field, suffix in (("priority_tier", "priority_tiers"), ("audience_group", "audience_groups")):
            row["proposed_" + suffix] = [c["label"] for c in codes if c["field"] == field and c["status"] == "proposed"]
            row["confirmed_" + suffix] = [c["label"] for c in codes if c["field"] == field and c["status"] == "confirmed"]
        daily[(published[:10], item.platform, item.language)].append(row)
        if pin:
            features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [pin["longitude"], pin["latitude"]]},
                "properties": {"item_id": item.item_id, "run_id": item.run_id, "platform": item.platform, "url": item.url, "published_at": published,
                               "placement": pin["placement"], "location_basis": origin.get("kind") or (pin.get("inferred_location") or {}).get("method", "approximate location"),
                               "location_confidence": (pin.get("inferred_location") or {}).get("confidence"),
                               "location_evidence": (pin.get("inferred_location") or {}).get("evidence", ""),
                               "location_reason": (pin.get("inferred_location") or {}).get("reason", ""),
                               "origin_known": bool(origin), "verified": pin["verified"], **{k: score[k] for k in ("valence", "intensity", "direction")}}})
    timeline = []
    for (day, platform, language), group in sorted(daily.items()):
        row = {"publication_date_utc": day, "platform": platform, "language": language, "unique_posts": len(group),
               "reviewed_relevant": sum(r["verdict"] == "relevant" for r in group), "located_posts": sum(r["map_placement"] != "unlocated" for r in group)}
        for axis in ("valence", "intensity", "direction"):
            values = [r[axis] for r in group if r[axis] is not None]
            row[f"{axis}_n"] = len(values)
            row[f"{axis}_mean"] = round(sum(values) / len(values), 6) if values else None
        timeline.append(row)
    timeline_columns = ["publication_date_utc", "platform", "language", "unique_posts", "reviewed_relevant", "located_posts",
                        "valence_n", "valence_mean", "intensity_n", "intensity_mean", "direction_n", "direction_mean"]
    dictionary = {"schema_version": "1.0", "row_unit": "one unique accepted source item; stable item_id joins all files",
        "rows": len(rows), "mapped_rows": len(features), "csv": "UTF-8 BOM, RFC 4180 quoting, CRLF; JSON arrays/objects in nested columns. Text formulas are prefixed with an apostrophe; analysis.jsonl preserves original strings.",
        "timestamps": "ISO-8601 UTC; publication is never replaced by retrieval time. Empty = unknown; timeline includes an empty-date bucket.",
        "coordinates": "WGS84 decimal degrees. GeoJSON coordinate order is longitude, latitude. Origin columns are empty for places named only in text; map columns may be approximate text mentions.",
        "sentiment": NOTE, "missing": "CSV blank / JSON null for unscored axes; never silently converted to neutral or zero.",
        "sampling": "Source items can include social posts, news, encyclopedia articles and scholarship; stratify by platform/content_type. Counts do not establish statistical representativeness or influence.",
        "coding": "activity_codes retains source quotes, methods and human decisions; priority and audience columns separate proposed from confirmed. See study-rubric.json and coding-events.jsonl for rule versions.",
        "columns": COLUMNS}
    encode = lambda value: json.dumps(redaction.redact(value), ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    from .mission_rubric import load_rubric
    ids = {i.item_id for i in accepted}
    return {"analysis.csv": _csv([redaction.redact(r) for r in rows], COLUMNS),
            "study-rubric.json": encode(load_rubric(project)),
            "coding-events.jsonl": "".join(json.dumps(redaction.redact(e), ensure_ascii=False) + "\n" for e in CodingStore(project).events() if e.get("item_id") in ids).encode("utf-8"),
            "analysis.jsonl": "".join(json.dumps(redaction.redact(r), ensure_ascii=False, allow_nan=False) + "\n" for r in rows).encode("utf-8"),
            "timeline.csv": _csv(timeline, timeline_columns),
            "map.geojson": encode({"type": "FeatureCollection", "features": features}), "data-dictionary.json": encode(dictionary),
            "README-analysis.md": ("# Analysis files\n\nJoin tables on `item_id`; use `run_id` for collection provenance. `analysis.csv` and `analysis.jsonl` contain full text, publication/retrieval times, reviews, locations and exploratory axes. No UI row limit applies.\n\n"
                "For pandas: `pd.read_csv('analysis.csv', encoding='utf-8-sig')`; for R: `read.csv('analysis.csv', fileEncoding='UTF-8-BOM')`. JSONL retains exact strings and structured values. Open `map.geojson` in QGIS; check `placement` and `location_basis` before interpreting geography.\n\n"
                "`timeline.csv` groups by UTC publication day, source and language. Every axis mean has its own non-missing denominator (`*_n`). Consult `data-dictionary.json` for method and missing-value definitions.\n").encode("utf-8")}


def export_map(project: Any, items: list[Any], *, filters: dict[str, Any]) -> dict[str, Any]:
    from .research_plan import utc_now
    mapped = post_pins(project, items, **{k: filters[k] for k in ("since", "until", "platform", "language", "verdict", "days", "min_confidence") if k in filters})
    target = str(filters.get("target") or "")
    ids = {p["item_id"] for p in mapped["pins"] if not target or any(t["name"] == target for t in p["targets"])}
    selected = [i for i in items if i.item_id in ids]
    files = analysis_files(project, selected, mapped=mapped)
    name = "map_" + uuid.uuid4().hex[:12]
    root = project.root / "exports" / name
    root.mkdir(parents=True)
    manifest = {"schema_version": "1.1", "exported_at": utc_now(), "run": {"run_id": name, "kind": "map_export"},
                "scope": {"mapped_posts_only": True, "filters": filters, "unique_posts": len(ids), "source_runs": sorted({i.run_id for i in selected})},
                "files": {n: {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)} for n, b in files.items()}}
    files["run-manifest.json"] = json.dumps(redaction.redact(manifest), ensure_ascii=False, indent=2).encode("utf-8")
    archive = root.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for filename, data in files.items():
            (root / filename).write_bytes(data)
            bundle.writestr(f"{name}/{filename}", data)
    project.log("map_exported", {"filters": filters, "unique_posts": len(ids), "directory": root.relative_to(project.workspace.root).as_posix()})
    return {"directory": root.relative_to(project.workspace.root).as_posix(), "archive": archive.relative_to(project.workspace.root).as_posix(), "files": sorted(files), "manifest": manifest}
