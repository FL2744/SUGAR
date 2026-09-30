"""Export a run as a reproducible, verifiable bundle (section 39).

Machine-readable (JSON/JSONL/CSV/GeoJSON) and human-readable (Markdown report) files coexist in
one directory, described by a manifest with SHA-256 hashes so another researcher can confirm the
bundle is intact. Everything is redacted; credentials are never part of a run record.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import sugar_core
from . import redaction
from .research_events import EventLog
from .research_plan import utc_now
from .research_runs import ResearchProject
from .utils import safe_cell

EXPORT_SCHEMA = "1.0"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _csv_bytes(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([safe_cell(_flat(row.get(c, ""))) for c in columns])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def _flat(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return "".join(json.dumps(redaction.redact(r), ensure_ascii=False) + "\n" for r in rows).encode("utf-8")


def _report(project: ResearchProject, run: dict[str, Any], items: list[Any], translations: list[dict[str, Any]]) -> str:
    plan = run["plan"]
    lines = [f"# Research run report: {plan.get('topic', '')}", ""]
    lines += [f"- **Project:** {project.workspace.manifest.name}", f"- **Run:** `{run['run_id']}` ({run['kind'].replace('_', ' ')})",
              f"- **Status:** {run['status'].replace('_', ' ')}", f"- **Started:** {run.get('started_at', '')}  ·  **Finished:** {run.get('finished_at', '')}",
              f"- **Research question:** {plan.get('research_question', '')}", f"- **Original request:** {run.get('requirement', '')}",
              f"- **Plan:** `{run['plan_id']}` v{run['plan_version']} (fingerprint `{run['plan_fingerprint']}`)",
              f"- **SUGAR version:** {run.get('software_version', '')}", ""]
    completeness = run.get("completeness") or {}
    lines += ["## Completeness", "", completeness.get("summary", "Not recorded."), ""]
    if completeness.get("incomplete_sources"):
        lines += ["Incomplete sources: " + ", ".join(completeness["incomplete_sources"]), ""]
    lines += ["## Plan", "", "| | |", "|---|---|"]
    tf = plan.get("timeframe", {})
    lines += [f"| Region | {', '.join(plan.get('geography', [])) or 'Not restricted'} |",
              f"| Platforms | {'All enabled' if plan.get('source_scope') == 'all_enabled' else ', '.join(plan.get('platforms', []))} |",
              f"| Languages | {', '.join(plan.get('languages', []))} |", f"| Date range | {tf.get('label') or (tf.get('start', '') + ' – ' + tf.get('end', '')).strip(' –') or 'No restriction'} |",
              f"| Depth | {plan.get('depth', '')} |", f"| Exclusions | {', '.join(plan.get('exclusions', [])) or 'None'} |", ""]
    lines += ["### Searches", ""]
    for q in run.get("generated_searches", []):
        flag = "" if q.get("enabled", True) else " *(disabled)*"
        lines.append(f"- `{q['text']}`{flag} — {q.get('rationale', '')} _(origin: {q.get('origin', '')}{', ' + q['platform'] if q.get('platform') else ''}{', ' + q['language'] if q.get('language') else ''})_")
    counts = run.get("counts", {})
    lines += ["", "## Counts", ""] + [f"- {k.replace('_', ' ')}: {v}" for k, v in counts.items() if v]
    lines += ["", "## Sources", "", "| Platform | Status | Items | Note |", "|---|---|---|---|"]
    for name, row in (run.get("sources") or {}).items():
        lines.append(f"| {name} | {row.get('status')} | {row.get('items', 0)} | {(row.get('error') or {}).get('message', '')} |")
    if run.get("errors"):
        lines += ["", "## Errors and warnings", ""] + [f"- **{e['classification']}** · {e['stage']} · {e['subsystem']}: {e['message']}" for e in run["errors"]]
    lines += ["", "## Collected items", ""]
    accepted = [i for i in items if i.status in {"collected", "processed"}]
    for item in accepted[:500]:
        translation = item.translation.get("text") if isinstance(item.translation, dict) and item.translation.get("status") == "done" else ""
        lines += [f"### {item.platform} · {item.author or 'unknown'} · {item.published_at[:10]}", "", f"<{item.url}>  ·  language: {item.language}  ·  query: `{item.query}`", "",
                  "> " + item.original_text.replace("\n", "\n> ")]
        if translation:
            lines += ["", f"**Translation ({item.translation.get('target_language', '')}, {item.translation.get('provider', '')}/{item.translation.get('model', '')}):**", "",
                      "> " + translation.replace("\n", "\n> ")]
        lines.append("")
    if len(accepted) > 500:
        lines.append(f"_{len(accepted) - 500} more item(s) are in corpus.jsonl._")
    lines += ["", "## Reproducing this run", "",
              "Load `plan.json` into SUGAR and choose **Rerun** to execute the same plan, including any queries edited before or during the run. "
              "`run-manifest.json` lists every file in this bundle with its SHA-256 hash.", ""]
    return "\n".join(lines)


def export_run(project: ResearchProject, run_id: str, *, make_zip: bool = True) -> dict[str, Any]:
    record = project.get_run(run_id)
    if record is None:
        raise KeyError(f"Run {run_id} was not found.")
    run = record.to_dict()
    items = project.load_items(run_id)
    translations = project.load_translations(run_id)
    events_path = project.events_path(run_id)
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()] if events_path.is_file() else []
    out_dir = project.root / "exports" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    source_columns = ["item_id", "platform", "url", "native_id", "retrieved_at", "published_at", "query", "query_dispatched", "language", "status",
                      "rejection_reason", "duplicate_of", "project_id", "run_id", "known_from_run", "derived_from"]
    source_rows = [i.to_dict() for i in items]
    accepted = [i for i in items if i.status in {"collected", "processed"}]
    result_rows = [{
        "item_id": i.item_id, "platform": i.platform, "author": i.author, "published_at": i.published_at, "url": i.url, "language": i.language,
        "original_text": i.original_text, "translated_text": i.translation.get("text", "") if i.translation.get("status") == "done" else "",
        "translation_provider": i.translation.get("provider", ""), "translation_model": i.translation.get("model", ""),
        "queries": i.queries, "geography": [g["name"] for g in i.geography], "run_id": i.run_id, "is_new": not i.known_from_run,
    } for i in accepted]
    result_columns = list(result_rows[0].keys()) if result_rows else ["item_id", "platform", "url", "original_text"]
    features = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [i.coordinates["lon"], i.coordinates["lat"]]},
                 "properties": {"item_id": i.item_id, "platform": i.platform, "url": i.url, "language": i.language}}
                for i in accepted if i.coordinates]

    files: dict[str, bytes] = {
        "plan.json": json.dumps(redaction.redact(run["plan"]), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
        "sources.csv": _csv_bytes(source_rows, source_columns),
        "results.csv": _csv_bytes(result_rows, result_columns),
        "corpus.jsonl": _jsonl([i.to_dict() for i in accepted]),
        "translations.jsonl": _jsonl(translations),
        "activity-log.jsonl": _jsonl(events),
        "report.md": redaction.redact_text(_report(project, run, items, translations)).encode("utf-8"),
    }
    if features:
        files["geo.geojson"] = json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=2).encode("utf-8")
    manifest = {
        "schema_version": EXPORT_SCHEMA, "exported_at": utc_now(), "sugar_version": sugar_core.__version__,
        "project": {"project_id": project.project_id, "name": project.workspace.manifest.name},
        "run": {k: run[k] for k in ("run_id", "kind", "parent_run_id", "status", "requirement", "plan_id", "plan_version", "plan_fingerprint", "provider_ref",
                                    "created_at", "started_at", "finished_at", "counts", "sources", "errors", "warnings", "completeness", "metrics", "stage_states",
                                    "generated_searches", "software_version")},
        "files": {name: {"sha256": _sha256(data), "bytes": len(data)} for name, data in sorted(files.items())},
        "notes": "Credentials are never stored in run records or exports. Verify with sugar_core.research_export.verify_export.",
    }
    files["run-manifest.json"] = json.dumps(redaction.redact(manifest), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    for name, data in files.items():
        (out_dir / name).write_bytes(data)
    archive = ""
    if make_zip:
        zip_path = project.root / "exports" / f"{run_id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name, data in files.items():
                bundle.writestr(f"{run_id}/{name}", data)
        archive = str(zip_path)
    project.log("run_exported", {"run_id": run_id, "files": sorted(files)})
    return {"directory": str(out_dir), "archive": archive, "files": sorted(files), "manifest": manifest}


def verify_export(path: str | Path) -> dict[str, Any]:
    """Recompute hashes of an exported directory or zip against its manifest."""
    target = Path(path)
    blobs: dict[str, bytes] = {}
    if target.is_file() and target.suffix == ".zip":
        with zipfile.ZipFile(target) as bundle:
            manifest_name = next((n for n in bundle.namelist() if n.endswith("run-manifest.json")), "")
            prefix = manifest_name[: -len("run-manifest.json")] if manifest_name else ""
            for name in bundle.namelist():
                if manifest_name and name.startswith(prefix) and not name.endswith("/"):
                    blobs[name[len(prefix):]] = bundle.read(name)
    elif target.is_dir():
        for file in target.iterdir():
            if file.is_file():
                blobs[file.name] = file.read_bytes()
    if "run-manifest.json" not in blobs:
        return {"ok": False, "problems": ["run-manifest.json is missing."]}
    manifest = json.loads(blobs["run-manifest.json"])
    problems: list[str] = []
    for name, meta in manifest.get("files", {}).items():
        if name not in blobs:
            problems.append(f"{name} is missing.")
        elif _sha256(blobs[name]) != meta.get("sha256"):
            problems.append(f"{name} does not match its recorded hash.")
    return {"ok": not problems, "problems": problems, "files_checked": len(manifest.get("files", {})),
            "run_id": manifest.get("run", {}).get("run_id", "")}


def read_events_file(path: Path, after: int = 0, *, stage: str = "", source: str = "", severity: str = "", limit: int = 1000) -> list[dict[str, Any]]:
    """Read events from a finished run's log without opening it for append."""
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("seq", 0) <= after:
            continue
        if stage and row.get("stage") != stage or source and row.get("source") != source or severity and row.get("severity") != severity:
            continue
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


__all__ = ["export_run", "verify_export", "read_events_file", "EventLog"]
