"""Posts on a map: where each one was posted from, and where it is about.

Two different places can belong to one post, and the map keeps them apart:

* **origin**: where the post came from. Precise when the platform supplied coordinates, or the post is linked to a recorded
  institution with a location; otherwise unknown. A place named in the text is *not* treated as the origin.
* **targets**: countries the text names, i.e. where the message is about. Placed at the country's centre, which says only
  "somewhere in that country", and labeled approximate.

Nothing here judges influence or intent; it shows where things were posted from and what places they mention.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from .city_centroids import CITIES
from .country_centroids import centroid
from .institutions import LinkStore
from .reference_registry import list_entities
from .research_items import ResearchItem
from .temporal import iso_utc, publication_key, timestamp

LIVE = {"collected", "processed"}


_CITY_PATTERNS = [(name, re.compile(rf"(?<![\w]){re.escape(name)}(?![\w])", re.I)) for name in CITIES]


def _coordinate_pair(lat: Any, lon: Any) -> tuple[float, float] | None:
    try:
        if isinstance(lat, bool) or isinstance(lon, bool):
            return None
        latitude, longitude = float(lat), float(lon)
        return (latitude, longitude) if math.isfinite(latitude) and math.isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180 else None
    except (ValueError, TypeError):
        return None


def _targets(item: ResearchItem) -> list[dict[str, Any]]:
    """Countries the text names (placed at the country centre) and, when a known city is named, the city's own point."""
    rows: dict[str, dict[str, Any]] = {}
    for tag in item.geography:
        name = tag.get("name", "")
        if tag.get("method") != "text_match" or not centroid(name):
            continue
        lat, lon = centroid(name) or (0.0, 0.0)
        rows[name] = {"name": name, "latitude": lat, "longitude": lon, "confidence": tag.get("confidence", 0.0), "method": "named in the text", "precision": "country", "city": ""}
    for city, pattern in _CITY_PATTERNS:
        if not pattern.search(item.original_text):
            continue
        country, lat, lon = CITIES[city]
        base = rows.setdefault(country, {"name": country, "latitude": (centroid(country) or (lat, lon))[0], "longitude": (centroid(country) or (lat, lon))[1], "confidence": 0.6,
                                         "method": "named city", "precision": "country", "city": ""})
        if not base["city"]:
            base.update({"city": city, "city_latitude": lat, "city_longitude": lon, "precision": "city", "confidence": max(base["confidence"], 0.8)})
    return list(rows.values())


def post_pins(project: Any, items: list[ResearchItem], *, platform: str = "", language: str = "", verdict: str = "", days: int = 0,
              since: str = "", until: str = "", order: str = "newest", now: datetime | None = None) -> dict[str, Any]:
    if order not in {"newest", "oldest"}:
        raise ValueError("Choose newest or oldest publication order.")
    def boundary(value: str) -> datetime | None:
        if not value:
            return None
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start, end = boundary(since), boundary(until)
    if start and end and start > end:
        raise ValueError("The start date must be on or before the end date.")
    review = project.review.state()
    links = LinkStore(project).active()
    placed_entities = {e["entity_id"]: e for e in list_entities(project.workspace) if _coordinate_pair(e.get("latitude"), e.get("longitude")) is not None}
    link_of: dict[str, dict[str, Any]] = {}
    for link in links:
        entity = placed_entities.get(link.get("entity_id", ""))
        if entity:
            link_of.setdefault(link["item_id"], entity)
    pins: list[dict[str, Any]] = []
    clock = timestamp(now) if now is not None else datetime.now(timezone.utc)
    clock = clock or datetime.now(timezone.utc)
    cutoff = clock - timedelta(days=days) if days > 0 else None
    seen: set[str] = set()
    matched = unlocated = undated = 0
    for item in items:
        if item.status not in LIVE or (platform and item.platform != platform) or (language and item.language != language):
            continue
        if item.item_id in seen:
            continue
        seen.add(item.item_id)
        published = timestamp(item.published_at)
        if (cutoff or start or end) and published is None:
            continue
        if published and ((cutoff and (published < cutoff or published > clock)) or (start and published < start) or (end and published >= end + timedelta(days=1))):
            continue
        state = review.get(item.item_id, {})
        if verdict and (state.get("verdict") or "none") != verdict:
            continue
        matched += 1
        undated += int(published is None)
        targets = _targets(item)
        origin: dict[str, Any] | None = None
        pair = _coordinate_pair(item.coordinates.get("lat"), item.coordinates.get("lon")) if item.coordinates else None
        if pair is not None:
            origin = {"latitude": pair[0], "longitude": pair[1], "kind": "platform coordinates", "precision": "exact", "label": "Coordinates supplied by the platform"}
        elif item.item_id in link_of:
            entity = link_of[item.item_id]
            origin = {"latitude": float(entity["latitude"]), "longitude": float(entity["longitude"]), "kind": "linked institution", "precision": "institution",
                      "label": f"{entity.get('name', '')} ({', '.join(x for x in (entity.get('city', ''), entity.get('country', '')) if x)})"}
        if origin is None and not targets:
            unlocated += 1
            continue
        translation = item.translation if isinstance(item.translation, dict) else {}
        inferred = max(targets, key=lambda t: t["confidence"]) if targets else None
        pins.append({
            "item_id": item.item_id, "run_id": item.run_id, "author": item.author, "published_at": iso_utc(item.published_at), "platform": item.platform, "url": item.url,
            "language": item.language, "original_text": item.original_text[:1200], "translated_text": translation.get("text", "")[:1200] if translation.get("status") == "done" else "",
            "origin": origin, "targets": targets,
            "inferred_location": {"name": inferred["name"], "confidence": inferred["confidence"], "method": inferred["method"]} if inferred else None,
            "placement": "origin" if origin else "mentioned",
            "latitude": origin["latitude"] if origin else (inferred.get("city_latitude", inferred["latitude"]) if inferred else None),
            "longitude": origin["longitude"] if origin else (inferred.get("city_longitude", inferred["longitude"]) if inferred else None),
            "verified": state.get("verdict") == "relevant", "verdict": state.get("verdict", ""), "verified_by": state.get("verdict_by", "") if state.get("verdict") == "relevant" else "",
            "verified_at": state.get("verdict_at", "") if state.get("verdict") == "relevant" else "",
        })
    from .sentiment import NOTE, score_item
    by_id = {i.item_id: i for i in reversed(items) if i.status in LIVE}
    for pin in pins:
        pin["sentiment"] = score_item(by_id[pin["item_id"]])
    # Stable ordering, with unknown publication dates last in both directions.
    pins.sort(key=lambda p: publication_key(by_id[p["item_id"]], order))
    flows: Counter[tuple[float, float, str]] = Counter()
    for pin in pins:
        for t in pin["targets"]:
            if pin["origin"]:
                flows[(pin["origin"]["latitude"], pin["origin"]["longitude"], t["name"])] += 1
    fresh_cutoff = clock - timedelta(hours=24)
    summary: dict[str, dict[str, Any]] = {}
    for pin in pins:
        for t in pin["targets"]:
            row = summary.setdefault(t["name"], {"name": t["name"], "posts": 0, "last_24h": 0, "platforms": Counter(), "languages": Counter(), "cities": Counter(), "verified": 0, "item_ids": [],
                                                 "latitude": (centroid(t["name"]) or (0, 0))[0], "longitude": (centroid(t["name"]) or (0, 0))[1], "last_at": ""})
            row["posts"] += 1
            row["verified"] += 1 if pin["verified"] else 0
            published = timestamp(pin["published_at"])
            row["last_24h"] += int(published is not None and fresh_cutoff <= published <= clock)
            row["platforms"][pin["platform"] or "unknown"] += 1
            row["languages"][pin["language"] or "und"] += 1
            if t.get("city"):
                row["cities"][t["city"]] += 1
            row["last_at"] = max(row["last_at"], pin["published_at"] or "")
            row["item_ids"].append(pin["item_id"])
    target_rows = [{**{k: v for k, v in r.items() if k not in {"platforms", "languages", "cities"}}, "platforms": dict(r["platforms"].most_common(4)), "languages": dict(r["languages"].most_common(4)),
                    "cities": dict(r["cities"].most_common(4))} for r in sorted(summary.values(), key=lambda r: (-r["posts"], r["name"]))]
    flow_rows = [{"from": [lon, lat], "to": [(centroid(n) or (0, 0))[1], (centroid(n) or (0, 0))[0]], "target": n, "posts": c} for (lat, lon, n), c in flows.items()]
    return {"pins": pins, "targets": target_rows, "flows": flow_rows,
            "as_of": clock.isoformat().replace("+00:00", "Z"),
            "coverage": {"unique_posts": matched, "mapped_posts": len(pins), "unlocated_posts": unlocated, "undated_posts": undated},
            "sentiment_note": NOTE,
            "note": "Origin is shown only when the platform gave coordinates or the post is linked to a located institution. Countries named in the text are placed at the country's centre and mark what a post is about, not where it came from."}
