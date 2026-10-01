"""Posts on a map: where each one was posted from, and where it is about.

Two different places can belong to one post, and the map keeps them apart:

* **origin**: where the post came from. Precise when the platform supplied coordinates, or the post is linked to a recorded
  institution with a location; otherwise unknown. A place named in the text is *not* treated as the origin.
* **targets**: countries the text names, i.e. where the message is about. Placed at the country's centre, which says only
  "somewhere in that country", and labeled approximate.

Nothing here judges influence or intent; it shows where things were posted from and what places they mention.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from .country_centroids import centroid
from .institutions import LinkStore
from .reference_registry import list_entities
from .research_items import ResearchItem

LIVE = {"collected", "processed"}


def _targets(item: ResearchItem) -> list[dict[str, Any]]:
    rows = []
    for tag in item.geography:
        name = tag.get("name", "")
        if tag.get("method") != "text_match" or not centroid(name):
            continue
        lat, lon = centroid(name) or (0.0, 0.0)
        rows.append({"name": name, "latitude": lat, "longitude": lon, "confidence": tag.get("confidence", 0.0), "method": "named in the text", "precision": "country"})
    return rows


def post_pins(project: Any, items: list[ResearchItem], *, platform: str = "", language: str = "", verdict: str = "") -> dict[str, Any]:
    review = project.review.state()
    links = LinkStore(project).active()
    placed_entities = {e["entity_id"]: e for e in list_entities(project.workspace) if e.get("latitude") not in ("", None) and e.get("longitude") not in ("", None)}
    link_of: dict[str, dict[str, Any]] = {}
    for link in links:
        entity = placed_entities.get(link.get("entity_id", ""))
        if entity:
            link_of.setdefault(link["item_id"], entity)
    pins: list[dict[str, Any]] = []
    for item in items:
        if item.status not in LIVE or (platform and item.platform != platform) or (language and item.language != language):
            continue
        state = review.get(item.item_id, {})
        if verdict and (state.get("verdict") or "none") != verdict:
            continue
        targets = _targets(item)
        origin: dict[str, Any] | None = None
        if item.coordinates:
            origin = {"latitude": item.coordinates["lat"], "longitude": item.coordinates["lon"], "kind": "platform coordinates", "precision": "exact", "label": "Coordinates supplied by the platform"}
        elif item.item_id in link_of:
            entity = link_of[item.item_id]
            origin = {"latitude": float(entity["latitude"]), "longitude": float(entity["longitude"]), "kind": "linked institution", "precision": "institution",
                      "label": f"{entity.get('name', '')} ({', '.join(x for x in (entity.get('city', ''), entity.get('country', '')) if x)})"}
        if origin is None and not targets:
            continue
        translation = item.translation if isinstance(item.translation, dict) else {}
        inferred = max(targets, key=lambda t: t["confidence"]) if targets else None
        pins.append({
            "item_id": item.item_id, "run_id": item.run_id, "author": item.author, "published_at": item.published_at, "platform": item.platform, "url": item.url,
            "language": item.language, "original_text": item.original_text[:1200], "translated_text": translation.get("text", "")[:1200] if translation.get("status") == "done" else "",
            "origin": origin, "targets": targets,
            "inferred_location": {"name": inferred["name"], "confidence": inferred["confidence"], "method": inferred["method"]} if inferred else None,
            "placement": "origin" if origin else "mentioned",
            "latitude": origin["latitude"] if origin else inferred["latitude"] if inferred else None,
            "longitude": origin["longitude"] if origin else inferred["longitude"] if inferred else None,
            "verified": state.get("verdict") == "relevant", "verdict": state.get("verdict", ""), "verified_by": state.get("verdict_by", "") if state.get("verdict") == "relevant" else "",
            "verified_at": state.get("verdict_at", "") if state.get("verdict") == "relevant" else "",
        })
    counts: Counter[str] = Counter()
    flows: Counter[tuple[float, float, str]] = Counter()
    for pin in pins:
        for t in pin["targets"]:
            counts[t["name"]] += 1
            if pin["origin"]:
                flows[(pin["origin"]["latitude"], pin["origin"]["longitude"], t["name"])] += 1
    target_rows = [{"name": n, "posts": c, "latitude": (centroid(n) or (0, 0))[0], "longitude": (centroid(n) or (0, 0))[1]} for n, c in counts.most_common()]
    flow_rows = [{"from": [lon, lat], "to": [(centroid(n) or (0, 0))[1], (centroid(n) or (0, 0))[0]], "target": n, "posts": c} for (lat, lon, n), c in flows.items()]
    return {"pins": pins, "targets": target_rows, "flows": flow_rows,
            "note": "Origin is shown only when the platform gave coordinates or the post is linked to a located institution. Countries named in the text are placed at the country's centre and mark what a post is about, not where it came from."}
