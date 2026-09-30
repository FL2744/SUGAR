"""Query, group, filter and inspect the items of a run (section 34)."""
from __future__ import annotations

from collections import Counter
from typing import Any

from .research_items import ResearchItem

GROUPINGS = ("none", "platform", "language", "geography", "query", "status", "author")


def _groups_of(item: ResearchItem, group_by: str) -> list[str]:
    if group_by == "platform":
        return [item.platform or "unknown"]
    if group_by == "language":
        return [item.language or "und"]
    if group_by == "geography":
        names = [g["name"] for g in item.geography if g["name"] != "coordinates"]
        return names[:3] or ["Unspecified"]
    if group_by == "query":
        return item.queries[:3] or [item.query or "unknown"]
    if group_by == "status":
        return [item.status]
    if group_by == "author":
        return [item.author or "unknown"]
    return ["All results"]


def item_row(item: ResearchItem, *, detail: bool = False) -> dict[str, Any]:
    translation = item.translation if isinstance(item.translation, dict) else {}
    row = {
        "item_id": item.item_id, "platform": item.platform, "url": item.url, "author": item.author,
        "published_at": item.published_at, "retrieved_at": item.retrieved_at, "language": item.language,
        "status": item.status, "rejection_reason": item.rejection_reason, "duplicate_of": item.duplicate_of,
        "similarity": item.similarity, "query": item.query, "queries": item.queries,
        "original_text": item.original_text, "translated_text": translation.get("text", "") if translation.get("status") == "done" else "",
        "translation_status": translation.get("status", ""), "translation_provider": translation.get("provider", ""),
        "translation_model": translation.get("model", ""), "translation_at": translation.get("at", ""),
        "geography": [g["name"] for g in item.geography if g["name"] != "coordinates"], "coordinates": item.coordinates,
        "is_new": not item.known_from_run, "known_from_run": item.known_from_run, "run_id": item.run_id,
        "derived_from": item.derived_from, "engagement": item.engagement, "content_type": item.content_type,
    }
    if detail:
        row.update({"project_id": item.project_id, "native_id": item.native_id, "query_dispatched": item.query_dispatched,
                    "transformations": item.transformations, "evidence_chain": item.evidence_chain, "paragraphs": item.paragraphs,
                    "language_method": item.language_method, "warnings": item.warnings, "source_mode": item.source_mode,
                    "translation": translation})
    return row


def query_items(items: list[ResearchItem], *, group_by: str = "none", text: str = "", platform: str = "", language: str = "",
                status: str = "accepted", geography: str = "", translated: str = "", new_only: bool = False,
                limit: int = 200, offset: int = 0) -> dict[str, Any]:
    if group_by not in GROUPINGS:
        raise ValueError(f"group_by must be one of {', '.join(GROUPINGS)}.")
    accepted = {"collected", "processed"}

    def wanted(item: ResearchItem) -> bool:
        if status == "accepted" and item.status not in accepted:
            return False
        if status not in {"accepted", "all", ""} and item.status != status:
            return False
        if platform and item.platform != platform:
            return False
        if language and item.language != language:
            return False
        if geography and geography not in [g["name"] for g in item.geography]:
            return False
        if new_only and item.known_from_run:
            return False
        if translated == "yes" and item.translation.get("status") != "done":
            return False
        if translated == "no" and item.translation.get("status") == "done":
            return False
        if text:
            needle = text.casefold()
            hay = f"{item.original_text}\n{item.translation.get('text', '')}\n{item.author}\n{item.url}".casefold()
            if needle not in hay:
                return False
        return True

    filtered = [i for i in items if wanted(i)]
    facets = {
        "platforms": Counter(i.platform for i in filtered), "languages": Counter(i.language or "und" for i in filtered),
        "geographies": Counter(g for i in filtered for g in _groups_of(i, "geography")),
        "statuses": Counter(i.status for i in items),
    }
    groups: dict[str, list[ResearchItem]] = {}
    for item in filtered:
        for key in _groups_of(item, group_by):
            groups.setdefault(key, []).append(item)
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    page = filtered[offset:offset + max(1, min(limit, 1000))]
    return {
        "total": len(filtered), "all_items": len(items), "group_by": group_by,
        "groups": [{"key": k, "count": len(v), "items": [item_row(i) for i in v[: min(limit, 100)]]} for k, v in ordered] if group_by != "none" else [],
        "items": [item_row(i) for i in page] if group_by == "none" else [],
        "facets": {k: [{"key": a, "count": b} for a, b in sorted(v.items(), key=lambda kv: (-kv[1], str(kv[0])))] for k, v in facets.items()},
        "duplicates": sum(1 for i in items if i.status == "duplicate"), "rejected": sum(1 for i in items if i.status == "rejected"),
        "excluded": sum(1 for i in items if i.status == "excluded"),
    }
