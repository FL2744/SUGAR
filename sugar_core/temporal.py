"""UTC publication-time handling shared by maps, tables and analysis exports."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any


def timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (ValueError, TypeError, OverflowError):
            return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def iso_utc(value: Any) -> str:
    parsed = timestamp(value)
    return parsed.isoformat().replace("+00:00", "Z") if parsed else ""


def publication_key(item: Any, order: str = "newest") -> tuple:
    parsed = timestamp(item.published_at)
    seconds = parsed.timestamp() if parsed else 0
    return (parsed is None, -seconds if order == "newest" else seconds, item.item_id)
