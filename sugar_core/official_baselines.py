from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

from .reference_registry import import_reference_dataset
from .workspace import SugarWorkspace


AMERICAN_SPACES_ENDPOINT = "https://americanspaces.info/locator/map/spaces-with-ids.json"
LANGUAGE_CENTER_DIRECTORY_PAGE = "https://www.ci.cn/en/qqwl"
LANGUAGE_CENTER_ENDPOINT = "https://www.ci.cn/open/site-tab/sitesBySiteName"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36"
)

_CANONICAL_COLUMNS = [
    "entity_id", "name", "entity_type", "network", "status", "country", "region", "city",
    "address", "latitude", "longitude", "location_precision", "opened_date", "host_entities",
    "partner_entities", "coverage_scope", "public_links", "source_url", "description",
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _unique(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean(value)
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            result.append(text)
    return result


def _session(session: requests.Session | None = None) -> requests.Session:
    target = session or requests.Session()
    target.headers.update({"User-Agent": _USER_AGENT, "Accept": "application/json,text/plain,*/*"})
    return target


def fetch_american_spaces(*, session: requests.Session | None = None, timeout: float = 30.0) -> list[dict[str, Any]]:
    response = _session(session).get(AMERICAN_SPACES_ENDPOINT, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("American Spaces locator returned an unexpected payload shape.")
    return [dict(row) for row in payload if isinstance(row, dict)]


def fetch_language_centers(*, session: requests.Session | None = None, timeout: float = 30.0) -> list[dict[str, Any]]:
    target = _session(session)
    # The directory API rejects some non-browser clients unless the public directory has first been visited.
    target.headers["Referer"] = LANGUAGE_CENTER_DIRECTORY_PAGE
    landing = target.get(LANGUAGE_CENTER_DIRECTORY_PAGE, timeout=timeout)
    landing.raise_for_status()
    response = target.get(
        LANGUAGE_CENTER_ENDPOINT,
        params={"labelId": "", "siteName": "", "pageSize": 10000, "language": "EN"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Language-center directory returned an unexpected payload shape.")
    return [dict(row) for row in rows if isinstance(row, dict)]


def _american_status(source_status: Any) -> str:
    value = _clean(source_status).casefold()
    if value in {"in operation", "in reduced operation", "virtual programming only"}:
        return "active"
    # Temporary closure is intentionally not converted to the registry's permanent `closed` state.
    return "unknown"


def normalize_american_spaces(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    type_names = {"AC": "American Corner", "BNC": "Binational Center", "CTR": "American Center", "AFF": "Affiliate"}
    output: list[dict[str, Any]] = []
    for source in rows:
        name = _clean(source.get("name"))
        source_id = _clean(source.get("id"))
        if not name or not source_id:
            continue
        uri = _clean(source.get("uri"))
        detail_url = f"https://americanspaces.info/locator/{uri}" if uri else AMERICAN_SPACES_ENDPOINT
        source_status = _clean(source.get("status"))
        space_type = _clean(source.get("type_of_space"))
        region = _clean(source.get("region"))
        generic_coordinates = bool(source.get("locator_use_generic_coordinates"))
        description_bits = [
            f"Official locator status: {source_status or 'unspecified'}",
            f"Space model: {type_names.get(space_type, space_type or 'unspecified')}",
            f"State regional code: {region or 'unspecified'}",
            f"Locator record ID: {source_id}",
        ]
        if generic_coordinates:
            description_bits.append("Locator marks coordinates as generic rather than site-exact")
        email = _clean(source.get("main_email") or source.get("email"))
        if email:
            description_bits.append(f"Public contact: {email}")
        output.append({
            "entity_id": f"american-space:{source_id}",
            "name": name,
            "entity_type": "site",
            "network": "American Spaces",
            "status": _american_status(source_status),
            "country": _clean(source.get("country_name")),
            "region": region,
            "city": _clean(source.get("city")),
            "address": _clean(source.get("address")),
            "latitude": _clean(source.get("latitude")),
            "longitude": _clean(source.get("longitude")),
            "location_precision": "generic_locator_coordinate" if generic_coordinates else "source_coordinate",
            "opened_date": "",
            "host_entities": "",
            "partner_entities": "",
            "coverage_scope": _clean(source.get("country_name")),
            "public_links": detail_url,
            "source_url": detail_url,
            "description": "; ".join(description_bits),
            "source_native_status": source_status,
            "source_native_type": space_type,
            "source_record_id": source_id,
        })
    return output


def _directory_json_data(source: dict[str, Any]) -> dict[str, Any]:
    value = source.get("jsonData")
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def normalize_language_centers(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source in rows:
        name = _clean(source.get("name"))
        site_key = _clean(source.get("siteKey"))
        country = _clean(source.get("countryName"))
        # The endpoint currently contains one CMS/root record (`www`, name `1`) that is not an institute.
        if not name or not country or not site_key or site_key == "www":
            continue
        data = _directory_json_data(source)
        hosts = _unique(data.get(f"local_cooperative_{index}") for index in range(1, 4))
        partners = _unique([
            source.get("cooperationName"),
            *(data.get(f"cooperative_{index}") for index in range(1, 4)),
        ])
        opened = _clean(data.get("establish"))
        if opened and not (len(opened) == 10 and opened[4:5] == "-" and opened[7:8] == "-"):
            opened = ""
        detail_url = f"https://www.ci.cn/en/site/{site_key}/"
        description_bits = [
            "Listed in the official public global language-center directory",
            f"Portal site key: {site_key}",
            f"Portal enable flag: {_clean(source.get('enable')) or 'unspecified'}",
            f"Portal visible flag: {_clean(source.get('visible')) or 'unspecified'}",
            f"Portal deleted flag: {_clean(source.get('deleted')) or 'unspecified'}",
        ]
        updated = _clean(source.get("updateTime"))
        if updated:
            description_bits.append(f"Directory record updated: {updated}")
        output.append({
            "entity_id": f"language-center:{site_key}",
            "name": name,
            "entity_type": "institution",
            "network": "Language Education Centers",
            # Directory presence is evidence of listing, not sufficient evidence of current operating status.
            "status": "unknown",
            "country": country,
            "region": _clean(source.get("continentName")),
            "city": "",
            "address": "",
            "latitude": "",
            "longitude": "",
            "location_precision": "",
            "opened_date": opened,
            "host_entities": "; ".join(hosts),
            "partner_entities": "; ".join(partners),
            "coverage_scope": country,
            "public_links": detail_url,
            "source_url": detail_url,
            "description": "; ".join(description_bits),
            "source_native_status": "listed",
            "source_native_type": "official_language_center_directory_entry",
            "source_record_id": _clean(source.get("siteId")) or site_key,
        })
    return output


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = sorted({key for row in rows for key in row if key not in _CANONICAL_COLUMNS})
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[*_CANONICAL_COLUMNS, *extra], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _mapping() -> dict[str, str]:
    return {field: field for field in _CANONICAL_COLUMNS if field not in {"source_native_status", "source_native_type", "source_record_id"}}


def sync_official_baselines(
    workspace: SugarWorkspace,
    *,
    sources: Iterable[str] = ("american_spaces", "language_centers"),
    session: requests.Session | None = None,
    timeout: float = 30.0,
    actor: str = "official-baseline-sync",
) -> dict[str, Any]:
    selected = {str(value).strip().casefold().replace("-", "_") for value in sources if str(value).strip()}
    supported = {"american_spaces", "language_centers"}
    unknown = sorted(selected - supported)
    if unknown:
        raise ValueError("Unsupported official baseline source(s): " + ", ".join(unknown))
    captured_at = _now()
    stamp = captured_at.replace(":", "").replace("-", "")
    root = workspace.path_for("references") / "official_baselines" / "snapshots" / stamp
    root.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"captured_at": captured_at, "snapshot_dir": str(root), "sources": {}}
    target_session = _session(session)

    jobs: list[tuple[str, str, str, list[dict[str, Any]], list[dict[str, Any]], str]] = []
    if "american_spaces" in selected:
        raw = fetch_american_spaces(session=target_session, timeout=timeout)
        normalized = normalize_american_spaces(raw)
        jobs.append((
            "american_spaces", "American Spaces", AMERICAN_SPACES_ENDPOINT, raw, normalized,
            "Public ECA American Spaces locator. Public locator coverage may differ from internal Department inventories; source-native operational wording is preserved in each row and temporary closure is not treated as permanent closure.",
        ))
    if "language_centers" in selected:
        raw = fetch_language_centers(session=target_session, timeout=timeout)
        normalized = normalize_language_centers(raw)
        jobs.append((
            "language_centers", "Language Education Centers", LANGUAGE_CENTER_ENDPOINT, raw, normalized,
            "Public CIEF global-network directory. Directory presence establishes listing, not current operating status; the non-institute CMS root record is excluded and city/coordinates are not inferred.",
        ))

    for key, network, endpoint, raw, normalized, coverage_limits in jobs:
        raw_path = root / f"{key}.raw.json"
        csv_path = root / f"{key}.normalized.csv"
        _write_json(raw_path, {"captured_at": captured_at, "endpoint": endpoint, "row_count": len(raw), "rows": raw})
        _write_csv(csv_path, normalized)
        import_result = import_reference_dataset(
            workspace,
            csv_path,
            mapping=_mapping(),
            dataset_name=f"Official {network} baseline {captured_at[:10]}",
            network=network,
            geographic_scope="Global public directory",
            known_coverage_limits=coverage_limits,
            license_notes="Public official-source data. Preserve attribution/provenance and re-check provider terms before redistribution outside the research project.",
            actor=actor,
            review_state="unreviewed",
            accept_partial=False,
        )
        workspace.register_artifact("official_baseline_raw", raw_path, label=f"Raw {network} official baseline",
                                    metadata={"captured_at": captured_at, "endpoint": endpoint, "row_count": len(raw)})
        workspace.register_artifact("official_baseline_normalized", csv_path, label=f"Normalized {network} official baseline",
                                    metadata={"captured_at": captured_at, "endpoint": endpoint, "row_count": len(normalized)})
        result["sources"][key] = {
            "endpoint": endpoint,
            "raw_rows": len(raw),
            "normalized_rows": len(normalized),
            "raw_file": str(raw_path),
            "normalized_file": str(csv_path),
            "registry_import": import_result,
        }

    manifest = root / "manifest.json"
    _write_json(manifest, result)
    workspace.register_artifact("official_baseline_manifest", manifest, label="Official baseline sync manifest",
                                metadata={"captured_at": captured_at, "sources": sorted(selected)})
    result["manifest"] = str(manifest)
    return result
