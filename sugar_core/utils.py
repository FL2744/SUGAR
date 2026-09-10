from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def safe_cell(value: Any, formula_safe: bool = True) -> Any:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return value
    text = normalize_whitespace(str(value).replace("\r", " ").replace("\n", " ").replace("\t", " "))
    if formula_safe and text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except Exception:
            return None


def in_inclusive_date_range(value: str, since: str | None, until: str | None) -> bool:
    current = parse_date(value)
    if current is None:
        return True
    lower = parse_date(since)
    upper = parse_date(until)
    return (lower is None or current >= lower) and (upper is None or current <= upper)


def stable_hash(*parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class JsonCache:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        except Exception:
            self.data = {}

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)


def utc_iso(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
