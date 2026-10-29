"""Built-in Team 4 network catalog and layered HTML map export."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from .mapping import MapOptions, ReferenceLayer, create_map
from .networks import set_network
from .reference_registry import import_reference_dataset, list_entities
from .spatial import haversine_km


CATALOG_PATH = Path(__file__).with_name("data") / "team4_network_catalog.json"
_CORE_IDS = ("confucius_institutes", "luban_workshops", "american_spaces")
_CORE_NAMES = {
    "confucius_institutes": "team4_confucius_institutes",
    "luban_workshops": "team4_luban_workshops",
    "american_spaces": "team4_american_spaces",
}
_FIELD_MAPPING = {
    "entity_id": "entity_id", "name": "name", "entity_type": "entity_type",
    "network": "network", "country": "country", "region": "region", "city": "city",
    "address": "address", "latitude": "latitude", "longitude": "longitude",
    "location_precision": "location_precision", "status": "status",
    "reported_status": "source_status_claim", "source_url": "source_url",
    "description": "description", "aliases": "aliases", "program_domains": "program_domains",
    "host_entities": "host_entities", "source_origin": "source_origin",
    "location_source": "location_source", "status_basis": "status_basis",
    "last_publication_search": "last_publication_search",
}


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _datasets() -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in _catalog().get("networks", [])}


def _assumed_workbook_status(source_label: Any) -> str:
    label = re.sub(r"[^a-z0-9]+", " ", str(source_label or "").casefold()).strip()
    if label == "open" or label.startswith("active") or label in {
        "in operation", "in reduced operation", "virtual programming only",
    }:
        return "active"
    if "closed" in label or label in {"wound down", "not renewed"}:
        return "closed"
    return "unknown"


def workbook_status_assumptions() -> dict[str, dict[str, str]]:
    """Map each bundled Team 4 row to its source-label-based working status."""
    return {
        str(record.get("entity_id") or ""): {
            "status": _assumed_workbook_status(record.get("source_status_claim")),
            "source_status_claim": str(record.get("source_status_claim") or ""),
            "status_basis": "source_workbook_assumption",
        }
        for dataset in _catalog().get("networks", [])
        for record in dataset.get("records", [])
        if record.get("entity_id")
    }


def map_status_for_entity(entity: dict[str, Any], assumptions: dict[str, dict[str, str]] | None = None) -> dict[str, str]:
    assumptions = assumptions if assumptions is not None else workbook_status_assumptions()
    assumption = assumptions.get(str(entity.get("entity_id") or ""))
    if not assumption:
        return {"status": str(entity.get("status") or "unknown"), "source_status_claim": "", "status_basis": "registry"}
    status_resolution = entity.get("resolved_fields", {}).get("status", {})
    if str(status_resolution.get("state") or "").startswith("human_verified"):
        return {"status": str(entity.get("status") or "unknown"),
                "source_status_claim": assumption["source_status_claim"], "status_basis": "human_verified_registry"}
    return assumption


def _publication_audit(catalog: dict[str, Any]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    by_network: dict[str, dict[str, int]] = {}
    source_scope_counts: Counter[str] = Counter()
    result_counts: Counter[str] = Counter()
    exact_count = relative_count = page_date_count = any_date_count = 0
    for dataset in catalog.get("networks", []):
        network_records = dataset.get("records", [])
        network_counts = {
            "rows": len(network_records), "matched_page": 0, "exact_date": 0,
            "relative_label": 0, "page_date_candidate": 0, "no_date_or_page": 0,
        }
        for record in network_records:
            search = record.get("last_publication_search") or {}
            result = str(search.get("result") or "not_searched")
            exact_date = str(search.get("exact_publication_date") or "")
            relative_label = str(search.get("search_age_label") or "")
            page_date = str(search.get("date_shown_in_result") or "")
            has_date_signal = bool(exact_date or relative_label or page_date)
            has_page = result in {"dated_or_relative_signal", "relevant_page_without_date"}
            scope = str(search.get("evidence_scope") or "none")
            result_counts[result] += 1
            source_scope_counts[scope] += 1
            exact_count += bool(exact_date)
            relative_count += bool(relative_label)
            page_date_count += bool(page_date)
            any_date_count += has_date_signal
            network_counts["matched_page"] += has_page
            network_counts["exact_date"] += bool(exact_date)
            network_counts["relative_label"] += bool(relative_label)
            network_counts["page_date_candidate"] += bool(page_date)
            network_counts["no_date_or_page"] += not has_page

            candidates: list[dict[str, Any]] = []
            seen_urls: set[str] = set()
            if has_page:
                for candidate in search.get("candidates", []):
                    url = str(candidate.get("url") or "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    candidates.append({
                        "title": str(candidate.get("title") or ""), "url": url,
                        "match": str(candidate.get("match") or ""),
                        "publication_date": str(candidate.get("publication_date") or ""),
                        "date_basis": str(candidate.get("publication_date_basis") or ""),
                        "page_date_candidate": str(candidate.get("page_date_candidate") or ""),
                        "search_age_label": str(candidate.get("published_label") or ""),
                        "source_scope": str(candidate.get("source_scope") or ""),
                    })
            records.append({
                "entity_id": str(record.get("entity_id") or ""),
                "name": str(record.get("name") or ""), "country": str(record.get("country") or ""),
                "city": str(record.get("city") or ""), "network": str(record.get("network") or dataset.get("network") or ""),
                "network_label": str(dataset.get("label") or ""),
                "checked_on": str(search.get("checked_on") or catalog.get("as_of") or ""),
                "result": result, "query": str(search.get("query") or ""),
                "fallback_query": str(search.get("fallback_query") or ""),
                "exact_publication_date": exact_date, "date_shown_in_result": page_date,
                "search_age_label": relative_label, "date_basis": str(search.get("date_basis") or ""),
                "evidence_scope": scope if scope != "none" else "",
                "match_strength": str(search.get("match_strength") or ""),
                "evidence_title": str(search.get("evidence_title") or ""),
                "evidence_url": str(search.get("evidence_url") or ""),
                "candidates": candidates,
            })
        by_network[str(dataset.get("network") or dataset.get("id") or "")] = network_counts

    stored = catalog.get("web_publication_audit", {})
    return {
        "checked_on": str(stored.get("checked_on") or catalog.get("as_of") or ""),
        "rows_searched": len(records),
        "matched_page": result_counts["dated_or_relative_signal"] + result_counts["relevant_page_without_date"],
        "exact_publication_date_candidate": exact_count,
        "relative_search_age_label": relative_count,
        "date_shown_in_result": page_date_count,
        "any_date_or_age_signal": any_date_count,
        "no_relevant_result": result_counts["no_relevant_dated_result"],
        "source_scope_counts": dict(sorted(source_scope_counts.items())),
        "result_counts": dict(sorted(result_counts.items())),
        "by_network": by_network,
        "method": str(stored.get("method") or ""),
        "caveat": str(stored.get("caveat") or ""),
        "records": records,
    }


def catalog_summary() -> dict[str, Any]:
    catalog = _catalog()
    datasets = []
    for row in catalog.get("networks", []):
        records = row.get("records", [])
        datasets.append({
            "id": row["id"], "network": row["network"], "label": row["label"],
            "role": row["role"], "color": row["color"], "records": len(records),
            "placed": sum(1 for item in records if item.get("latitude") is not None and item.get("longitude") is not None),
            "status_counts": {
                status: sum(1 for item in records if item.get("status") == status)
                for status in ("active", "closed", "unknown")
            },
            "source": row.get("source", ""), "summary": row.get("summary", ""),
            "default_selected": row["id"] in _CORE_IDS,
        })
    core_records = [
        record
        for dataset in catalog.get("networks", [])
        if dataset.get("id") in _CORE_IDS
        for record in dataset.get("records", [])
    ]
    supplemental_records = [
        record
        for dataset in catalog.get("networks", [])
        if dataset.get("id") not in _CORE_IDS
        for record in dataset.get("records", [])
    ]
    last_post_fields = ("last_post", "last_post_date", "latest_post_at", "last_activity_date", "last_activity_at")
    spot_checks = catalog.get("site_activity_spot_checks", [])
    status_claim_counts = {
        dataset["label"]: {
            str(claim): count
            for claim, count in sorted(
                Counter(
                    str(record.get("source_status_claim") or "Unspecified")
                    for record in dataset.get("records", [])
                ).items()
            )
        }
        for dataset in catalog.get("networks", [])
    }
    activity_audit = {
        "core_records": len(core_records),
        "supplementary_records": len(supplemental_records),
        "core_records_with_last_post_date": sum(any(record.get(field) for field in last_post_fields) for record in core_records),
        "supplementary_records_with_last_post_date": sum(any(record.get(field) for field in last_post_fields) for record in supplemental_records),
        "named_site_checks": len(spot_checks),
        "named_site_checks_with_dated_signals": sum(
            any(signal.get("date") for signal in check.get("signals", [])) for check in spot_checks
        ),
        "source_status_claim_counts": status_claim_counts,
        "interpretation": "Map and imported statuses use the supplied workbook labels as working assumptions. They are not independently verified; dated spot checks do not establish a record-wide posting cadence.",
    }
    return {
        "catalog_id": catalog.get("catalog_id", ""), "label": catalog.get("catalog_label", ""),
        "as_of": catalog.get("as_of", ""), "use_note": catalog.get("use_note", ""),
        "networks": datasets, "source_inventory": catalog.get("source_inventory", []),
        "data_quality_notes": catalog.get("data_quality_notes", []),
        "activity_audit": activity_audit,
        "workbook_status_assumptions": {
            "by_network": {item["label"]: item["status_counts"] for item in datasets},
            "basis": "Source status labels are mapped to active, closed, or unknown for map use; the original label remains visible as evidence.",
        },
        "publication_audit": _publication_audit(catalog),
        "activity_pulse": catalog.get("activity_pulse", []),
        "site_activity_spot_checks": catalog.get("site_activity_spot_checks", []),
        "overlap_claim_counts": catalog.get("overlap_claim_counts", {}),
        "program_overlap_interpretations": [
            {
                "program_type": row.get("fields", {}).get("PRC program type", ""),
                "niche_term_ids": row.get("fields", {}).get("Niche examples (term IDs on Niche Search Terms tab)", ""),
                "american_spaces_counterpart": row.get("fields", {}).get("American Spaces counterpart", ""),
                "overlap_assessment": row.get("fields", {}).get("Overlap", ""),
                "team_judgment": row.get("fields", {}).get("Does it further PRC initiatives? (judgment)", ""),
                "strongest_regions": row.get("fields", {}).get("Where it is strongest", ""),
                "source_origin": row.get("source_origin", {}),
            }
            for row in catalog.get("source_lists", {}).get("program_overlap_interpretations", [])
        ],
        "curated_search_suggestions": catalog.get("curated_search_suggestions", []),
    }


def import_catalog(workspace_project: Any, selected_ids: list[str], *, actor: str = "Researcher") -> dict[str, Any]:
    datasets = _datasets()
    selected = list(dict.fromkeys(str(item) for item in selected_ids if str(item)))
    unknown = sorted(set(selected) - set(datasets))
    if unknown:
        raise ValueError("Unknown built-in catalog selection: " + ", ".join(unknown))
    if not selected:
        raise ValueError("Choose at least one built-in team dataset to import.")

    workspace = workspace_project.workspace
    workspace_root = workspace.root
    source_catalog = CATALOG_PATH.resolve()
    catalog_copy = workspace_root / "references" / "team4_network_catalog.json"
    catalog_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_catalog, catalog_copy)
    workspace.register_artifact(
        "team4_network_catalog", catalog_copy, label="Team 4 network catalog",
        metadata={"catalog_id": _catalog().get("catalog_id"), "as_of": _catalog().get("as_of"),
                  "overlap_claim_counts": _catalog().get("overlap_claim_counts", {})},
    )

    existing_ids = {str(row.get("entity_id") or "") for row in list_entities(workspace)}
    to_import: list[dict[str, Any]] = []
    selected_networks: list[dict[str, Any]] = []
    selected_records = 0
    skipped_existing = 0
    for dataset_id in selected:
        dataset = datasets[dataset_id]
        selected_networks.append(dataset)
        records = dataset.get("records", [])
        selected_records += len(records)
        for record in records:
            if str(record.get("entity_id") or "") in existing_ids:
                skipped_existing += 1
            else:
                to_import.append(record)

    imported = {"added": 0, "updated": 0, "imported_entity_ids": []}
    if to_import:
        fingerprint = hashlib.sha256("\n".join(sorted(str(row["entity_id"]) for row in to_import)).encode("utf-8")).hexdigest()[:16]
        source_path = workspace_root / "references" / f"team4-catalog-import-{fingerprint}.geojson"
        features = []
        for record in to_import:
            properties = dict(record)
            lat, lon = record.get("latitude"), record.get("longitude")
            geometry = ({"type": "Point", "coordinates": [float(lon), float(lat)]}
                        if lat is not None and lon is not None else None)
            features.append({"type": "Feature", "id": record["entity_id"], "geometry": geometry, "properties": properties})
        source_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        available_columns = {str(key) for record in to_import for key in record}
        field_mapping = {field: column for field, column in _FIELD_MAPPING.items() if column in available_columns}
        imported = import_reference_dataset(
            workspace, source_path, mapping=field_mapping,
            dataset_name="Team 4 built-in network catalog · " + ", ".join(row["label"] for row in selected_networks),
            geographic_scope="Global; coverage and coordinates are limited to the supplied team workbooks.",
            known_coverage_limits="Statuses are working assumptions normalized from source-workbook labels; locations are unverified and publication dates are search candidates.",
            license_notes=_catalog().get("license_notes", ""), actor=actor, review_state="unreviewed", accept_partial=False,
        )

    settings = []
    for dataset in selected_networks:
        set_network(workspace_project, dataset["network"], role=dataset["role"], label=dataset["label"], color=dataset["color"], actor=actor)
        settings.append(dataset["network"])

    workspace_project.log("team_catalog_imported", {
        "catalog_id": _catalog().get("catalog_id"), "selected_datasets": selected,
        "selected_records": selected_records, "new_records": len(to_import),
        "skipped_existing": skipped_existing, "network_settings": settings,
        "catalog_file": catalog_copy.relative_to(workspace_root).as_posix(),
    }, actor=actor)
    return {
        "selected_datasets": selected, "selected_records": selected_records,
        "added": imported.get("added", 0), "updated": imported.get("updated", 0),
        "skipped_existing": skipped_existing, "catalog_file": catalog_copy.relative_to(workspace_root).as_posix(),
        "network_names": settings,
        "note": "Imported status uses the original workbook label as a working assumption; the raw label is retained as source evidence and has not been independently verified.",
    }


def _valid_point(row: dict[str, Any]) -> tuple[float, float] | None:
    try:
        lat, lon = float(row.get("latitude")), float(row.get("longitude"))
    except (TypeError, ValueError):
        return None
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon
    return None


def _country_key(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    return {"united states": "united states of america", "usa": "united states of america",
            "uk": "united kingdom", "russia": "russian federation"}.get(text, text)


def _source_text(record: dict[str, Any], field: str = "source_origin") -> str:
    origin = record.get(field)
    if not origin:
        for claim in record.get("claims", []):
            for evidence in claim.get("evidence_refs", []):
                if isinstance(evidence, dict) and evidence.get(field):
                    origin = evidence[field]
                    break
            if origin:
                break
    if isinstance(origin, dict):
        parts = [str(origin.get(key) or "") for key in ("file", "sheet")]
        row_number = origin.get("row")
        text = " · ".join(value for value in parts if value)
        return f"{text} · row {row_number}" if row_number else text
    return str(origin or "")


def _status_provenance_line(status: dict[str, str]) -> str:
    claim = str(status.get("source_status_claim") or "")
    if not claim:
        return ""
    working_status = str(status.get("status") or "unknown")
    if status.get("status_basis") == "human_verified_registry":
        return f"Original workbook status claim: {claim}; human-verified registry status {working_status} takes precedence."
    return f"Original workbook status claim: {claim}; map status {working_status} is a working assumption from the workbook."


def export_network_map(workspace_project: Any, network_names: list[str], *, near_km: float = 25.0, country: str = "") -> dict[str, Any]:
    catalog = _catalog()
    datasets = {row["network"]: row for row in catalog.get("networks", []) if row.get("id") in _CORE_IDS}
    selected = list(dict.fromkeys(str(name) for name in network_names if str(name)))
    valid_sets = [
        {_CORE_NAMES["confucius_institutes"], _CORE_NAMES["american_spaces"]},
        {_CORE_NAMES["luban_workshops"], _CORE_NAMES["american_spaces"]},
        set(_CORE_NAMES.values()),
    ]
    if set(selected) not in valid_sets or len(selected) not in (2, 3):
        raise ValueError("Choose Confucius Institutes + American Spaces, Luban Workshops + American Spaces, or all three layers.")
    try:
        near = float(near_km)
    except (TypeError, ValueError) as exc:
        raise ValueError("Choose a valid comparison distance.") from exc
    if near not in {5.0, 25.0, 100.0, 250.0}:
        raise ValueError("Comparison distance must be 5, 25, 100, or 250 km.")

    entities = [row for row in list_entities(workspace_project.workspace) if row.get("network") in selected]
    wanted_country = _country_key(country)
    if wanted_country:
        entities = [row for row in entities if _country_key(row.get("country")) == wanted_country]
    status_assumptions = workbook_status_assumptions()
    status_by_id = {str(row.get("entity_id") or ""): map_status_for_entity(row, status_assumptions) for row in entities}
    records_by_network = {name: [row for row in entities if row.get("network") == name and _valid_point(row)] for name in selected}
    if any(not records_by_network.get(name) for name in selected):
        missing = [datasets[name]["label"] for name in selected if not records_by_network.get(name)]
        raise ValueError("No mapped records are available for " + ", ".join(missing) + ". Import the selected built-in catalog layers first.")

    reference_name = _CORE_NAMES["american_spaces"]
    references = records_by_network[reference_name]
    reference_label = datasets[reference_name]["label"]
    subject_names = [name for name in selected if name != reference_name]
    observation_rows: list[dict[str, Any]] = []
    proximity_count = 0
    counts_by_network: dict[str, dict[str, int]] = {}
    for name in subject_names:
        count_with_nearby = 0
        status_counts: Counter[str] = Counter()
        for row in records_by_network[name]:
            point = _valid_point(row)
            assert point is not None
            map_status = status_by_id.get(str(row.get("entity_id") or ""), {})
            source_lines = [str(row.get("description") or "")]
            status_note = _status_provenance_line(map_status)
            if status_note:
                source_lines.append(status_note)
            source_origin = _source_text(row)
            coordinate_origin = _source_text(row, "location_source")
            if source_origin:
                source_lines.append("Original source row: " + source_origin)
            if coordinate_origin:
                source_lines.append("Coordinate source row: " + coordinate_origin)
            matches = []
            for reference in references:
                ref_point = _valid_point(reference)
                if ref_point is None:
                    continue
                distance = haversine_km(point[0], point[1], ref_point[0], ref_point[1])
                if distance <= near:
                    matches.append((distance, reference, ref_point))
            matches.sort(key=lambda value: value[0])
            spatial_matches = []
            if matches:
                distance, reference, ref_point = matches[0]
                spatial_matches.append({
                    "reference_id": reference.get("entity_id", ""),
                    "reference_name": reference.get("name", ""),
                    "reference_layer": reference_label,
                    "distance_km": distance,
                    "same_city": bool(row.get("city") and str(row.get("city")).casefold() == str(reference.get("city") or "").casefold()),
                    "same_country": bool(row.get("country") and _country_key(row.get("country")) == _country_key(reference.get("country"))),
                    "latitude": ref_point[0], "longitude": ref_point[1],
                })
                count_with_nearby += 1
            observation_rows.append({
                "observation_id": row.get("entity_id", ""), "title": row.get("name", ""),
                "observation_type": "language_institute" if name == _CORE_NAMES["confucius_institutes"] else "vocational_training",
                "summary": "; ".join(value for value in source_lines if value), "country": row.get("country", ""),
                "region": row.get("region", ""), "city": row.get("city", ""),
                "latitude": point[0], "longitude": point[1], "activity_status": map_status.get("status", "unknown"),
                "verification_state": "unreviewed", "location_basis": "team_supplied_directory_coordinate",
                "location_precision": row.get("location_precision", ""),
                "primary_source_url": row.get("source_url", ""), "registry_id": row.get("entity_id", ""),
                "spatial_matches": json.dumps(spatial_matches, ensure_ascii=False),
            })
            status_counts[str(map_status.get("status") or "unknown")] += 1
        proximity_count += count_with_nearby
        counts_by_network[name] = {"mapped": len(records_by_network[name]), "within_distance": count_with_nearby,
                                   "status_counts": dict(sorted(status_counts.items()))}

    reference_status_counts = Counter(
        status_by_id.get(str(row.get("entity_id") or ""), {}).get("status", "unknown")
        for row in references
    )
    counts_by_network[reference_name] = {
        "mapped": len(references), "within_distance": 0,
        "status_counts": dict(sorted(reference_status_counts.items())),
    }

    reference_frame = pd.DataFrame([{
        "entity_id": row.get("entity_id", ""), "name": row.get("name", ""),
        "category": row.get("entity_type", "American Space"), "city": row.get("city", ""),
        "country": row.get("country", ""), "address": row.get("address", ""),
        "latitude": _valid_point(row)[0], "longitude": _valid_point(row)[1],
        "description": "; ".join(value for value in (str(row.get("description") or ""),
                                                       _status_provenance_line(status_by_id.get(str(row.get("entity_id") or ""), {})),
                                                       ("Original source row: " + _source_text(row)) if _source_text(row) else "") if value),
        "status": status_by_id.get(str(row.get("entity_id") or ""), {}).get("status", "unknown"),
        "location_precision": row.get("location_precision", ""),
        "source_url": row.get("source_url", ""),
    } for row in references])

    selected_labels = [datasets[name]["label"] for name in selected]
    timestamp = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")
    target = workspace_project.root / "exports" / f"network-overlap-{timestamp}-{uuid.uuid4().hex[:6]}.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    output = create_map(
        pd.DataFrame(observation_rows), target,
        options=MapOptions(
            title="Network location comparison",
            subtitle=f"{' + '.join(selected_labels)} · active records use their network color; gray × marks closed, ↻ marks renamed, ↗ marks relocated, and ? marks unknown. Workbook labels are working assumptions unless a human-verified registry status takes precedence. Lines show computed coordinate proximity within {near:g} km; proximity does not establish partnership or influence.",
            show_computed_proximity=True,
        ),
        reference_layers=[ReferenceLayer(name=reference_label, frame=reference_frame,
                                         color=datasets[reference_name]["color"], show=True)],
    )
    relative = Path(output).resolve().relative_to(workspace_project.workspace.root).as_posix()
    workspace_project.workspace.register_artifact(
        "network_map_html", output, label="Team 4 network overlap map",
        metadata={"network_names": selected, "distance_km": near, "country": country,
                  "mapped_records": sum(len(records_by_network[name]) for name in selected),
                  "computed_nearby_subject_records": proximity_count},
    )
    workspace_project.log("network_map_exported", {
        "file": relative, "networks": selected, "distance_km": near, "country": country,
        "counts": counts_by_network, "computed_nearby_subject_records": proximity_count,
    })
    return {"file": relative, "filename": Path(output).name, "networks": selected_labels,
            "counts": counts_by_network, "computed_nearby_subject_records": proximity_count,
            "distance_km": near, "country": country,
            "note": "Only coordinates within the selected distance are linked. Team overlap assertions are retained separately and are not treated as computed matches."}
