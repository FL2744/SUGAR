from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.1"
COLLECTOR_VERSION = "sugar-core-1.1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class PostRecord:
    platform: str
    native_id: str
    canonical_url: str
    query: str
    query_matches: list[str] = field(default_factory=list)
    content_type: str = "post"
    source_mode: str = "api"
    source_host: str = ""
    source_url: str = ""
    collected_at: str = field(default_factory=utc_now_iso)
    collector_version: str = COLLECTOR_VERSION
    schema_version: str = SCHEMA_VERSION
    published_at: str = ""
    author_handle: str = ""
    author_name: str = ""
    author_location: str = ""
    platform_language: str = ""
    detected_language: str = ""
    original_text: str = ""
    translated_text: str = ""
    engagement: dict[str, int] = field(default_factory=dict)
    raw_stats: dict[str, Any] = field(default_factory=dict)
    is_repost: bool = False
    inferred_location: str = ""
    location_confidence: float = 0.0
    location_source: str = ""
    location_reason: str = ""
    latitude: float | None = None
    longitude: float | None = None
    geocode_display_name: str = ""

    @property
    def tweet_id(self) -> str:
        return self.native_id

    @property
    def post_url(self) -> str:
        return self.canonical_url

    @property
    def x_url(self) -> str:
        return self.canonical_url if self.platform == "x" else ""

    @property
    def username(self) -> str:
        return self.author_handle

    @property
    def display_name(self) -> str:
        return self.author_name

    @property
    def date_iso(self) -> str:
        return self.published_at

    @property
    def date_raw(self) -> str:
        return self.published_at

    @property
    def translated_en(self) -> str:
        return self.translated_text

    @property
    def is_retweet(self) -> bool:
        return self.is_repost

    def add_query_match(self, query: str) -> None:
        query = (query or "").strip()
        if query and query not in self.query_matches:
            self.query_matches.append(query)
        if not self.query and query:
            self.query = query

    def export_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["query_matches"] = json.dumps(self.query_matches, ensure_ascii=False)
        data["engagement"] = json.dumps(self.engagement, sort_keys=True)
        data["raw_stats"] = json.dumps(self.raw_stats, ensure_ascii=False, sort_keys=True)
        data.update({
            "tweet_id": self.tweet_id,
            "post_url": self.post_url,
            "x_url": self.x_url,
            "username": self.username,
            "display_name": self.display_name,
            "date_iso": self.date_iso,
            "date_raw": self.date_raw,
            "translated_en": self.translated_en,
            "is_retweet": self.is_retweet,
        })
        return data


def merge_record(existing: PostRecord, incoming: PostRecord) -> PostRecord:
    for query in incoming.query_matches or [incoming.query]:
        existing.add_query_match(query)
    for attr in ("author_name", "author_location", "platform_language", "original_text", "published_at"):
        if not getattr(existing, attr) and getattr(incoming, attr):
            setattr(existing, attr, getattr(incoming, attr))
    if sum(incoming.engagement.values()) > sum(existing.engagement.values()):
        existing.engagement = dict(incoming.engagement)
        existing.raw_stats = dict(incoming.raw_stats)
    return existing
