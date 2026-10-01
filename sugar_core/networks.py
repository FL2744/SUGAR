"""Networks: which institutions belong to which network, importing reference datasets, and overlap.

A *network* is a label on institutions ("example-net"). In a project each network has a role:

* ``subject``   - the network being studied
* ``reference`` - a network to compare against (for example a government's own centers)

Reference networks usually arrive as a published directory (CSV, JSON or GeoJSON). Importing is two steps so
nothing is guessed: ``preview_upload`` stores the file and proposes a column mapping, and ``import_upload`` imports
it with the mapping a person confirmed.

``overlap`` computes where subject and reference institutions are near each other, and which recorded audiences and
programs they share. Proximity and shared labels are computed facts about the records; they do not show influence,
competition, coordination or causation, and the output says so.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .reference_registry import import_reference_dataset, list_entities, preview_reference_import
from .research_plan import utc_now
from .spatial import distance_band, haversine_km

ROLES = ("subject", "reference")
DEFAULT_BANDS_KM = (5.0, 25.0, 100.0, 250.0)
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def network_settings(project: Any) -> dict[str, dict[str, str]]:
    raw = (project.meta().get("settings") or {}).get("networks") or {}
    return {str(k): {"role": v.get("role", "subject") if v.get("role") in ROLES else "subject", "label": str(v.get("label") or k), "color": str(v.get("color") or "")}
            for k, v in raw.items() if isinstance(v, dict)}


def set_network(project: Any, name: str, *, role: str, label: str = "", color: str = "", actor: str = "analyst") -> dict[str, dict[str, str]]:
    name = " ".join(str(name or "").split())
    if not name:
        raise ValueError("A network needs a name.")
    if role not in ROLES:
        raise ValueError("A network's role is subject or reference.")
    current = (project.meta().get("settings") or {}).get("networks") or {}
    current = {**current, name: {"role": role, "label": label or name, "color": color}}
    project.update_settings({"networks": current}, actor=actor)
    return network_settings(project)


def list_networks(project: Any) -> list[dict[str, Any]]:
    settings = network_settings(project)
    entities = list_entities(project.workspace)
    counts = Counter((e.get("network") or "") for e in entities)
    placed = Counter((e.get("network") or "") for e in entities if e.get("latitude") not in ("", None) and e.get("longitude") not in ("", None))
    names = sorted(set(settings) | {n for n in counts if n})
    rows = [{"name": n, "role": settings.get(n, {}).get("role", "subject"), "label": settings.get(n, {}).get("label", n), "color": settings.get(n, {}).get("color", ""),
             "institutions": counts.get(n, 0), "placed": placed.get(n, 0)} for n in names]
    if counts.get(""):
        rows.append({"name": "", "role": "subject", "label": "Unassigned", "color": "", "institutions": counts[""], "placed": placed.get("", 0)})
    return rows


# ---------------------------------------------------------------------------------------- imports
def _upload_dir(project: Any) -> Path:
    path = project.root / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def store_upload(project: Any, filename: str, content: bytes) -> tuple[str, Path]:
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("That file is larger than 25 MB.")
    suffix = Path(filename or "").suffix.casefold()
    if suffix not in {".csv", ".tsv", ".json", ".jsonl", ".geojson", ".xlsx"}:
        raise ValueError("Use a CSV, TSV, JSON, JSONL, GeoJSON or Excel file.")
    digest = hashlib.sha256(content).hexdigest()[:16]
    path = _upload_dir(project) / f"{digest}_{_SAFE_NAME.sub('_', Path(filename).stem)[:60]}{suffix}"
    path.write_bytes(content)
    return digest, path


def _find_upload(project: Any, file_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{16}", file_id or ""):
        raise ValueError("Unknown uploaded file.")
    matches = sorted(_upload_dir(project).glob(f"{file_id}_*"))
    if not matches:
        raise ValueError("That uploaded file is no longer available; upload it again.")
    return matches[0]


def preview_upload(project: Any, filename: str, content: bytes) -> dict[str, Any]:
    file_id, path = store_upload(project, filename, content)
    preview = preview_reference_import(path)
    preview["file_id"] = file_id
    preview["filename"] = filename
    return preview


def import_upload(project: Any, file_id: str, *, mapping: dict[str, str], network: str, role: str, dataset_name: str = "", geographic_scope: str = "",
                  known_coverage_limits: str = "", license_notes: str = "", accept_partial: bool = False, actor: str = "analyst") -> dict[str, Any]:
    if not network.strip():
        raise ValueError("Name the network these institutions belong to.")
    path = _find_upload(project, file_id)
    result = import_reference_dataset(project.workspace, path, mapping=mapping, dataset_name=dataset_name, network=network.strip(),
                                      geographic_scope=geographic_scope, known_coverage_limits=known_coverage_limits, license_notes=license_notes,
                                      actor=actor, review_state="unreviewed", accept_partial=accept_partial)
    set_network(project, network.strip(), role=role, actor=actor)
    project.log("network_imported", {"network": network.strip(), "role": role, "dataset": dataset_name or path.name}, actor=actor)
    return result


# ---------------------------------------------------------------------------------------- overlap
def _placed(entity: dict[str, Any]) -> tuple[float, float] | None:
    try:
        lat, lon = float(entity.get("latitude")), float(entity.get("longitude"))
    except (TypeError, ValueError):
        return None
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def overlap(project: Any, *, subjects: list[str], references: list[str], bands_km: tuple[float, ...] = DEFAULT_BANDS_KM, include_closed: bool = False,
            country: str = "") -> dict[str, Any]:
    """Nearest reference institution to each subject institution, and what they have in common on record."""
    entities = list_entities(project.workspace)
    usable = (lambda e: include_closed or e.get("status") not in {"closed"})
    subj = [e for e in entities if (e.get("network") or "") in subjects and usable(e) and (not country or e.get("country") == country)]
    refs = [e for e in entities if (e.get("network") or "") in references and usable(e)]
    ref_points = [(e, _placed(e)) for e in refs]
    ref_points = [(e, p) for e, p in ref_points if p]
    rows, unplaced = [], 0
    for e in subj:
        point = _placed(e)
        if not point:
            unplaced += 1
            continue
        distances = sorted(((haversine_km(point[0], point[1], p[0], p[1]), r) for r, p in ref_points), key=lambda t: t[0])
        nearest = distances[0] if distances else None
        within = {f"{b:g}": sum(1 for d, _ in distances if d <= b) for b in bands_km}
        near_refs = [r for d, r in distances if d <= max(bands_km[:2] or bands_km)]
        shared_aud = sorted(set(e.get("normalized_audiences") or []) & {a for r in near_refs for a in r.get("normalized_audiences") or []})
        shared_prog = sorted(set(e.get("normalized_program_domains") or []) & {p for r in near_refs for p in r.get("normalized_program_domains") or []})
        same_city = bool(nearest) and bool(e.get("city")) and e.get("city", "").casefold() == (nearest[1].get("city") or "").casefold()
        rows.append({
            "entity_id": e["entity_id"], "name": e.get("name", ""), "country": e.get("country", ""), "city": e.get("city", ""),
            "nearest_reference": ({"entity_id": nearest[1]["entity_id"], "name": nearest[1].get("name", ""), "city": nearest[1].get("city", ""), "country": nearest[1].get("country", ""),
                                   "distance_km": round(nearest[0], 1), "band": distance_band(nearest[0], bands_km), "same_city": same_city} if nearest else None),
            "references_within_km": within, "shared_audiences": shared_aud, "shared_programs": shared_prog,
        })
    by_country: dict[str, dict[str, Any]] = defaultdict(lambda: {"subjects": 0, "references": 0, "subjects_near_reference": 0, "shared_audience_pairs": 0})
    for e in subj:
        by_country[e.get("country") or "unknown"]["subjects"] += 1
    for e in refs:
        by_country[e.get("country") or "unknown"]["references"] += 1
    near_cut = f"{bands_km[1]:g}" if len(bands_km) > 1 else f"{bands_km[0]:g}"
    for row in rows:
        c = by_country[row["country"] or "unknown"]
        if row["references_within_km"].get(near_cut):
            c["subjects_near_reference"] += 1
        if row["shared_audiences"]:
            c["shared_audience_pairs"] += 1
    summary = [{"country": c, **v} for c, v in sorted(by_country.items(), key=lambda kv: (-kv[1]["subjects"], kv[0]))]
    return {"generated_at": utc_now(), "subjects": subjects, "references": references, "bands_km": list(bands_km), "near_km": float(near_cut),
            "rows": rows, "by_country": summary, "counts": {"subject_institutions": len(subj), "reference_institutions": len(refs), "subjects_not_placed": unplaced,
                                                            "references_not_placed": len(refs) - len(ref_points)},
            "method": "Great-circle distance between recorded coordinates; shared audiences and programs are labels both records carry. "
                      "Coordinates may be city-level. These are computed facts about the records, not findings of influence, competition, coordination or causation."}
