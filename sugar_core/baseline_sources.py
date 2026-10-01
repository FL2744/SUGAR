"""Official baselines: pull a published institution directory into the registry, with its provenance.

A *baseline source* is described by a small JSON spec: where the directory is, which fields mean what, and how its status
wording maps to the registry's states. The program contains the *engine*; the specs (names, endpoints, field rules for a
particular directory) are data supplied at run time in a **baseline pack**, so this code stays free of study-specific detail.

Each sync keeps the complete raw response, writes a normalized CSV snapshot, imports it into the evidence-backed registry
with stable record IDs (so refreshing never duplicates institutions), records coverage limits and provenance, and stores a
dated manifest under ``references/official_baselines/snapshots/``. Directory presence establishes a *listing*; a spec's
status rules decide what, if anything, can be said about operation, and anything uncertain stays ``unknown``.

Pack locations, first found wins per key: the project's ``references/baseline_packs/``, a path in ``SUGAR_BASELINE_PACKS``,
and ``<SUGAR_HOME>/baselines/``. A pack is a JSON object ``{"sources": [spec, ...]}`` (a bare list or one spec also works).
"""
from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import requests

from .credential_store import sugar_home
from .reference_registry import import_reference_dataset
from .web_sources import UnsafeAddress, check_public_address
from .workspace import SugarWorkspace

CANONICAL_COLUMNS = [
    "entity_id", "name", "entity_type", "network", "status", "country", "region", "city",
    "address", "latitude", "longitude", "location_precision", "opened_date", "host_entities",
    "partner_entities", "coverage_scope", "public_links", "source_url", "description",
]
_EXTRA = ("source_native_status", "source_native_type", "source_record_id")
_DEFAULT_UA = "SUGAR research client (+https://github.com/FL2744/SUGAR; Virginia Tech Diplomacy Lab)"
_KEY = re.compile(r"[a-z0-9][a-z0-9_\-]{1,40}")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ENTITY_TYPES = {"network", "organization", "institution", "site", "program", "account", "event", "service"}
_STATUSES = {"active", "closed", "renamed", "relocated", "unknown"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _unique(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = _clean(value)
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append(text)
    return out


# ------------------------------------------------------------------------------------------------ specs
def validate_spec(raw: Any) -> dict[str, Any]:
    """Check a baseline spec. Raises ValueError with a plain message."""
    if not isinstance(raw, dict):
        raise ValueError("A baseline source is a JSON object.")
    spec = dict(raw)
    key = _clean(spec.get("key")).casefold()
    if not _KEY.fullmatch(key):
        raise ValueError("A baseline source needs a short key (letters, numbers, - and _).")
    spec["key"] = key
    for field in ("network", "endpoint"):
        if not _clean(spec.get(field)):
            raise ValueError(f"Baseline source “{key}” needs a {field}.")
    for field in ("endpoint", "landing_url"):
        value = _clean(spec.get(field))
        if value and urlparse(value).scheme != "https":
            raise ValueError(f"Baseline source “{key}”: {field} must be an https address.")
    if spec.get("role", "reference") not in {"subject", "reference"}:
        raise ValueError(f"Baseline source “{key}”: role is subject or reference.")
    spec.setdefault("role", "reference")
    spec.setdefault("entity_type", "institution")
    if spec["entity_type"] not in _ENTITY_TYPES:
        raise ValueError(f"Baseline source “{key}”: entity_type must be one of {', '.join(sorted(_ENTITY_TYPES))}.")
    fields = spec.get("fields")
    if not isinstance(fields, dict) or "name" not in fields:
        raise ValueError(f"Baseline source “{key}” needs a fields map that includes name.")
    if not (_clean(spec.get("id_field")) or spec.get("id_fields")):
        raise ValueError(f"Baseline source “{key}” needs id_field so records keep a stable identity.")
    status = spec.get("status") or {}
    for value in (status.get("map") or {}).values():
        if value not in _STATUSES:
            raise ValueError(f"Baseline source “{key}”: status values must be one of {', '.join(sorted(_STATUSES))}.")
    if status.get("default", "unknown") not in _STATUSES:
        raise ValueError(f"Baseline source “{key}”: the default status must be one of {', '.join(sorted(_STATUSES))}.")
    return spec


def parse_pack(raw: Any) -> list[dict[str, Any]]:
    data = raw
    if isinstance(raw, (bytes, str)):
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise ValueError("That baseline pack is not valid JSON.") from exc
    if isinstance(data, dict) and "sources" in data:
        data = data["sources"]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise ValueError("A baseline pack lists at least one source.")
    specs = [validate_spec(item) for item in data]
    if len({s["key"] for s in specs}) != len(specs):
        raise ValueError("Baseline source keys must be unique within a pack.")
    return specs


def pack_directories(workspace: SugarWorkspace | None = None) -> list[Path]:
    dirs: list[Path] = []
    if workspace is not None:
        dirs.append(workspace.path_for("references") / "baseline_packs")
    configured = os.environ.get("SUGAR_BASELINE_PACKS", "").strip()
    if configured:
        dirs.append(Path(configured).expanduser())
    dirs.append(sugar_home() / "baselines")
    return dirs


def load_specs(workspace: SugarWorkspace | None = None, extra_files: Iterable[str | Path] = ()) -> dict[str, dict[str, Any]]:
    """All available source specs by key. Earlier locations win; unreadable packs are skipped with their reason in ``_errors``."""
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    paths: list[Path] = [Path(p) for p in extra_files]
    for directory in pack_directories(workspace):
        paths.extend([directory] if directory.is_file() else sorted(directory.glob("*.json")) if directory.is_dir() else [])
    for path in paths:
        try:
            for spec in parse_pack(path.read_text(encoding="utf-8")):
                found.setdefault(spec["key"], {**spec, "_pack": str(path)})
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")
    if errors:
        found["_errors"] = {"errors": errors}                       # type: ignore[assignment]
    return found


def store_pack(workspace: SugarWorkspace, raw: Any, *, name: str = "pack") -> dict[str, Any]:
    """Save a validated pack in the project so a hosted installation can add one without file access."""
    specs = parse_pack(raw)
    directory = workspace.path_for("references") / "baseline_packs"
    directory.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-")[:40] or "pack"
    path = directory / f"{slug}.json"
    path.write_text(json.dumps({"sources": specs}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"stored": path.name, "sources": [s["key"] for s in specs]}


# ------------------------------------------------------------------------------------------------ normalizing
def _get(row: dict[str, Any], path: str) -> Any:
    """A value from a row. 'a.b' reaches into nested objects; a JSON string along the way is read as JSON."""
    current: Any = row
    for part in path.split("."):
        if isinstance(current, str) and current.strip().startswith(("{", "[")):
            try:
                current = json.loads(current)
            except ValueError:
                return None
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _value(row: dict[str, Any], rule: Any) -> str:
    if isinstance(rule, dict) and "const" in rule:
        return _clean(rule["const"])
    if isinstance(rule, list):
        return "; ".join(_unique(_get(row, p) for p in rule))
    if isinstance(rule, str):
        return _clean(_get(row, rule))
    return ""


def _excluded(row: dict[str, Any], spec: dict[str, Any]) -> bool:
    for rule in spec.get("exclude") or []:
        value = _clean(_get(row, str(rule.get("field", ""))))
        if "equals" in rule and value == _clean(rule["equals"]):
            return True
        if rule.get("empty") and not value:
            return True
    return False


def normalize(spec: dict[str, Any], rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    fields = spec["fields"]
    status_rule = spec.get("status") or {}
    id_fields = spec.get("id_fields") or [spec["id_field"]]
    for row in rows:
        if not isinstance(row, dict) or _excluded(row, spec):
            continue
        record_id = next((v for v in (_clean(_get(row, f)) for f in id_fields) if v), "")
        values = {c: _value(row, fields[c]) for c in CANONICAL_COLUMNS if c in fields}
        if not record_id or not values.get("name"):
            continue
        if any(not (values.get(f) or _clean(_get(row, f))) for f in spec.get("require") or []):
            continue
        native_status = _clean(_get(row, status_rule["field"])) if status_rule.get("field") else ""
        mapping = {str(k).casefold(): v for k, v in (status_rule.get("map") or {}).items()}
        status = mapping.get(native_status.casefold(), status_rule.get("default", "unknown"))
        for date_field in ("opened_date", "closed_date"):
            if values.get(date_field) and not _DATE.fullmatch(values[date_field]):
                values[date_field] = ""
        template = _clean(spec.get("detail_url"))
        detail = template.format_map({k: _clean(_get(row, k)) for k in re.findall(r"\{(\w+)\}", template)}) if template and all(
            _clean(_get(row, k)) for k in re.findall(r"\{(\w+)\}", template)) else _clean(spec.get("detail_url_fallback") or spec["endpoint"])
        precision = ""
        if spec.get("location_precision"):
            lp = spec["location_precision"]
            precision = lp["true"] if _get(row, lp["flag"]) else lp.get("false", "")
        bits: list[str] = []
        for item in spec.get("description") or []:
            raw = _clean(_get(row, item["field"])) if item.get("field") else ""
            if item.get("when_true"):
                if _get(row, item["field"]):
                    bits.append(item["when_true"])
                continue
            shown = (item.get("map") or {}).get(raw, raw) if raw else ""
            if not shown and item.get("skip_if_empty"):
                continue
            bits.append(f"{item.get('label', item['field'])}: {shown or item.get('default', 'unspecified')}")
        native_type = _clean(_get(row, spec["native_type_field"])) if spec.get("native_type_field") else _clean(spec.get("native_type"))
        record: dict[str, Any] = {c: values.get(c, "") for c in CANONICAL_COLUMNS}
        record.update({
            "entity_id": f"{spec.get('id_prefix', spec['key'] + ':')}{record_id}", "entity_type": spec["entity_type"], "network": spec["network"], "status": status,
            "location_precision": precision or values.get("location_precision", ""), "public_links": detail, "source_url": detail,
            "description": "; ".join(bits) or values.get("description", ""),
            "source_native_status": native_status or ("listed" if spec.get("listed_means_listed") else ""), "source_native_type": native_type,
            "source_record_id": _clean(_get(row, spec["record_id_field"])) if spec.get("record_id_field") and _get(row, spec["record_id_field"]) else record_id,
        })
        out.append(record)
    return out


# ------------------------------------------------------------------------------------------------ fetching
def fetch(spec: dict[str, Any], *, session: requests.Session | None = None, timeout: float = 30.0) -> list[dict[str, Any]]:
    """Download a source's directory. Only public https addresses are read."""
    for url in (spec["endpoint"], spec.get("landing_url")):
        if url:
            try:
                check_public_address(url)
            except UnsafeAddress as exc:
                raise ValueError(str(exc)) from exc
    target = session or requests.Session()
    target.headers.update({"User-Agent": spec.get("user_agent") or _DEFAULT_UA, "Accept": "application/json,text/plain,*/*", **{str(k): str(v) for k, v in (spec.get("headers") or {}).items()}})
    if spec.get("landing_url"):
        # Some directory APIs reject clients that have not first visited the public page.
        target.headers["Referer"] = spec["landing_url"]
        target.get(spec["landing_url"], timeout=timeout).raise_for_status()
    response = target.get(spec["endpoint"], params=spec.get("params") or {}, timeout=timeout)
    if response.status_code == 429:
        raise RuntimeError(f"{urlparse(spec['endpoint']).netloc} rate limit reached (429); retry after a short wait.")
    response.raise_for_status()
    payload = response.json()
    path = _clean(spec.get("rows_path"))
    rows = _get({"_": payload}, f"_.{path}" if path else "_")
    if not isinstance(rows, list):
        raise ValueError(f"The directory for “{spec['key']}” returned an unexpected shape; expected a list of records" + (f" at “{path}”." if path else "."))
    return [dict(r) for r in rows if isinstance(r, dict)]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = sorted({k for r in rows for k in r if k not in CANONICAL_COLUMNS})
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[*CANONICAL_COLUMNS, *extra], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sync_baselines(workspace: SugarWorkspace, specs: dict[str, dict[str, Any]], keys: Iterable[str] | None = None, *, session: requests.Session | None = None,
                   timeout: float = 30.0, actor: str = "baseline-sync", fetcher: Any = None) -> dict[str, Any]:
    """Fetch, snapshot and import the chosen sources. Stable record IDs make repeated syncs idempotent."""
    available = {k: v for k, v in specs.items() if not k.startswith("_")}
    wanted = [str(k).casefold().replace("-", "_") for k in (keys or available)]
    wanted = [k if k in available else k.replace("_", "-") for k in wanted]
    unknown = [k for k in wanted if k not in available]
    if unknown:
        raise ValueError("Unknown baseline source(s): " + ", ".join(unknown) + (". Available: " + ", ".join(sorted(available)) if available else ". No baseline pack is installed."))
    if not wanted:
        raise ValueError("No baseline pack is installed. See docs/operations-runbook.md, “Baseline packs”.")
    captured_at = _now()
    root = workspace.path_for("references") / "official_baselines" / "snapshots" / captured_at.replace(":", "").replace("-", "")
    root.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"captured_at": captured_at, "snapshot_dir": str(root), "sources": {}}
    fetch_fn = fetcher or fetch
    for key in wanted:
        spec = available[key]
        raw = fetch_fn(spec, session=session, timeout=timeout)
        rows = normalize(spec, raw)
        raw_path, csv_path = root / f"{key}.raw.json", root / f"{key}.normalized.csv"
        _write_json(raw_path, {"captured_at": captured_at, "endpoint": spec["endpoint"], "row_count": len(raw), "rows": raw})
        _write_csv(csv_path, rows)
        imported = import_reference_dataset(
            workspace, csv_path, mapping={f: f for f in CANONICAL_COLUMNS}, dataset_name=f"Official {spec['network']} baseline {captured_at[:10]}", network=spec["network"],
            geographic_scope=spec.get("geographic_scope", "Published directory"), known_coverage_limits=spec.get("coverage_limits", ""),
            license_notes=spec.get("license_notes", "Public official-source data. Preserve attribution and provenance, and re-check the provider's terms before redistributing."),
            actor=actor, review_state="unreviewed", accept_partial=False)
        workspace.register_artifact("official_baseline_raw", raw_path, label=f"Raw {spec['network']} baseline", metadata={"captured_at": captured_at, "endpoint": spec["endpoint"], "row_count": len(raw)})
        workspace.register_artifact("official_baseline_normalized", csv_path, label=f"Normalized {spec['network']} baseline", metadata={"captured_at": captured_at, "endpoint": spec["endpoint"], "row_count": len(rows)})
        result["sources"][key] = {"network": spec["network"], "role": spec["role"], "endpoint": spec["endpoint"], "raw_rows": len(raw), "normalized_rows": len(rows),
                                  "raw_file": str(raw_path), "normalized_file": str(csv_path), "registry_import": imported}
    manifest = root / "manifest.json"
    _write_json(manifest, result)
    workspace.register_artifact("official_baseline_manifest", manifest, label="Baseline sync manifest", metadata={"captured_at": captured_at, "sources": wanted})
    result["manifest"] = str(manifest)
    return result
