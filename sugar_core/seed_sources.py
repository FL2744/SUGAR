"""Seeds for institution lists from open, structured sources: Wikidata and OpenStreetMap.

These return *candidates* (name, place, dates, address of the source record) for an analyst to review and import;
nothing is recorded until chosen, and every imported record cites the Wikidata or OpenStreetMap page it came from.
They are a starting list, not an authority: both are community-edited and incomplete.
"""
from __future__ import annotations

import re
from typing import Any

import requests

from .open_sources import _get, _session
from .utils import normalize_whitespace

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
OVERPASS_API = "https://overpass-api.de/api/interpreter"


def _claim_value(entity: dict[str, Any], prop: str) -> Any:
    for claim in (entity.get("claims") or {}).get(prop, []):
        if claim.get("rank") == "deprecated":
            continue
        snak = claim.get("mainsnak") or {}
        if snak.get("snaktype") == "value":
            return snak.get("datavalue", {}).get("value")
    return None


def _wd_date(value: Any) -> str:
    text = str((value or {}).get("time", "") if isinstance(value, dict) else "")
    match = re.match(r"[+-]?(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{year}-{month if month != '00' else '01'}-{day if day != '00' else '01'}"


def search_wikidata(term: str, *, limit: int = 15, language: str = "en", session: requests.Session | None = None) -> list[dict[str, Any]]:
    term = normalize_whitespace(term)
    if len(term) < 3:
        raise ValueError("Type at least three characters to search.")
    session = session or _session()
    found = _get(session, WIKIDATA_API, params={"action": "wbsearchentities", "search": term, "language": language, "limit": min(30, max(1, limit)), "format": "json", "type": "item"}).json()
    ids = [row["id"] for row in found.get("search", []) if row.get("id")]
    if not ids:
        return []
    entities = _get(session, WIKIDATA_API, params={"action": "wbgetentities", "ids": "|".join(ids), "props": "labels|descriptions|aliases|claims", "languages": language, "format": "json"}).json().get("entities", {})
    country_ids = {v.get("id") for e in entities.values() for v in [_claim_value(e, "P17")] if isinstance(v, dict) and v.get("id")}
    labels: dict[str, str] = {}
    if country_ids:
        got = _get(session, WIKIDATA_API, params={"action": "wbgetentities", "ids": "|".join(sorted(country_ids)), "props": "labels", "languages": language, "format": "json"}).json().get("entities", {})
        labels = {k: (v.get("labels", {}).get(language, {}) or {}).get("value", "") for k, v in got.items()}
    rows = []
    for qid in ids:
        e = entities.get(qid)
        if not e:
            continue
        coord = _claim_value(e, "P625")
        country = _claim_value(e, "P17")
        site = _claim_value(e, "P856")
        closed = _wd_date(_claim_value(e, "P576"))
        rows.append({
            "seed_source": "wikidata", "seed_id": qid, "name": (e.get("labels", {}).get(language) or {}).get("value", ""),
            "description": (e.get("descriptions", {}).get(language) or {}).get("value", ""),
            "aliases": [a.get("value", "") for a in e.get("aliases", {}).get(language, [])][:6],
            "country": labels.get(country.get("id", ""), "") if isinstance(country, dict) else "",
            "latitude": coord.get("latitude") if isinstance(coord, dict) else None, "longitude": coord.get("longitude") if isinstance(coord, dict) else None,
            "opened_date": _wd_date(_claim_value(e, "P571")), "closed_date": closed, "status": "closed" if closed else "",
            "website": site if isinstance(site, str) else "", "source_url": f"https://www.wikidata.org/wiki/{qid}",
        })
    return [r for r in rows if r["name"]]


_SAFE_PATTERN = re.compile(r"^[\w\s'’&.\-]{3,60}$", re.UNICODE)


def search_osm(name: str, *, country_code: str = "", limit: int = 50, session: requests.Session | None = None) -> list[dict[str, Any]]:
    """OpenStreetMap features whose name matches, optionally within one country (ISO 3166-1 alpha-2)."""
    name = normalize_whitespace(name)
    if not _SAFE_PATTERN.match(name):
        raise ValueError("Search names may use letters, numbers, spaces and basic punctuation (3 to 60 characters).")
    if country_code and not re.fullmatch(r"[A-Za-z]{2}", country_code):
        raise ValueError("Use a two-letter country code, for example KE.")
    pattern = re.sub(r"([\\.^$*+?()\[\]{}|])", r"\\\1", name)
    area = f'area["ISO3166-1"="{country_code.upper()}"]->.a;' if country_code else ""
    scope = "(area.a)" if country_code else ""
    query = f'[out:json][timeout:25];{area}nwr["name"~"{pattern}",i]{scope};out center {min(100, max(1, limit))};'
    session = session or _session()
    response = session.post(OVERPASS_API, data={"data": query}, timeout=45)
    if response.status_code == 429:
        raise RuntimeError("overpass-api.de rate limit reached (429); retry after a short wait.")
    response.raise_for_status()
    rows = []
    for element in response.json().get("elements", []):
        tags = element.get("tags") or {}
        lat = element.get("lat") if element.get("lat") is not None else (element.get("center") or {}).get("lat")
        lon = element.get("lon") if element.get("lon") is not None else (element.get("center") or {}).get("lon")
        if not tags.get("name") or lat is None or lon is None:
            continue
        rows.append({
            "seed_source": "osm", "seed_id": f"{element.get('type')}/{element.get('id')}", "name": tags["name"], "description": normalize_whitespace(
                " ".join(filter(None, [tags.get("amenity", ""), tags.get("building", ""), tags.get("operator", "")]))),
            "aliases": [v for k, v in tags.items() if k.startswith("name:") or k == "alt_name"][:6], "country": tags.get("addr:country", ""),
            "city": tags.get("addr:city", ""), "latitude": lat, "longitude": lon, "website": tags.get("website", "") or tags.get("contact:website", ""),
            "status": "", "opened_date": "", "closed_date": "", "source_url": f"https://www.openstreetmap.org/{element.get('type')}/{element.get('id')}",
        })
    return rows


def import_seeds(project: Any, rows: list[dict[str, Any]], *, network: str, role: str, actor: str = "analyst") -> dict[str, Any]:
    """Record chosen seed rows as unreviewed institutions that cite the page they came from."""
    from .networks import set_network
    from .reference_registry import upsert_entity
    if not network.strip():
        raise ValueError("Name the network these institutions belong to.")
    created = []
    for row in rows[:200]:
        name = normalize_whitespace(str(row.get("name") or ""))
        source = str(row.get("source_url") or "")
        if not name or not source.startswith("https://"):
            continue
        values = {"name": name, "network": network.strip(), "country": row.get("country"), "city": row.get("city"), "latitude": row.get("latitude"), "longitude": row.get("longitude"),
                  "location_precision": "site" if row.get("latitude") is not None else "", "opened_date": row.get("opened_date"), "closed_date": row.get("closed_date"),
                  "status": row.get("status") or None, "aliases": row.get("aliases"), "description": row.get("description"),
                  "public_links": [row["website"]] if str(row.get("website") or "").startswith("http") else None}
        entity = upsert_entity(project.workspace, {k: v for k, v in values.items() if v not in (None, "", [])},
                               evidence_refs=[{"source_url": source, "method": f"seed:{row.get('seed_source', '')}", "seed_id": row.get("seed_id", ""), "kind": "open_data_seed"}],
                               actor=actor, reason="Imported from an open-data search", review_state="unreviewed")
        created.append(entity["entity_id"])
    set_network(project, network.strip(), role=role, actor=actor)
    project.log("seeds_imported", {"network": network.strip(), "count": len(created)}, actor=actor)
    return {"imported": created, "skipped": len(rows) - len(created)}
