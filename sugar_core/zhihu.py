from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests

from .models import PostRecord

ZHIHU_SEARCH_URL = "https://developer.zhihu.com/api/v1/content/zhihu_search"
REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "SUGAR/1.2 (+public-source research; Virginia Tech Diplomacy Lab)"


def _value(mapping: dict[str, Any], *names: str, default: Any = None) -> Any:
    if not isinstance(mapping, dict):
        return default
    direct = {str(key): value for key, value in mapping.items()}
    folded = {str(key).casefold(): value for key, value in mapping.items()}
    for name in names:
        if name in direct:
            return direct[name]
        if name.casefold() in folded:
            return folded[name.casefold()]
    return default


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = []
    data = _value(payload, "Data", "data")
    if isinstance(data, dict):
        candidates.extend([
            _value(data, "Items", "items"),
            _value(data, "List", "list"),
            _value(data, "Results", "results"),
        ])
    candidates.extend([
        _value(payload, "Items", "items"),
        _value(payload, "List", "list"),
        _value(payload, "Results", "results"),
    ])
    for candidate in candidates:
        if isinstance(candidate, list):
            return [row for row in candidate if isinstance(row, dict)]
    return []


def _strip_highlight(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"</?em\b[^>]*>", "", text, flags=re.I)


def _published(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)) or str(value).strip().isdigit():
        try:
            stamp = int(float(value))
            if stamp > 10_000_000_000:
                stamp //= 1000
            return datetime.fromtimestamp(stamp, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            return ""
    return str(value).strip()


def _native_id(url: str) -> str:
    for pattern, prefix in (
        (r"/answer/(\d+)", "answer"),
        (r"/question/(\d+)", "question"),
        (r"/p/(\d+)", "article"),
    ):
        match = re.search(pattern, url)
        if match:
            return f"{prefix}-{match.group(1)}"
    return "url-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


def _record(item: dict[str, Any], query: str) -> PostRecord | None:
    url = str(_value(item, "Url", "url", "Link", "link", default="") or "").strip()
    if not url:
        return None
    title = _strip_highlight(_value(item, "Title", "title", default=""))
    summary = _strip_highlight(
        _value(item, "ContentText", "content_text", "Summary", "summary", "Excerpt", "excerpt", default="")
    )
    text = summary or title
    author = str(_value(item, "AuthorName", "author_name", "Author", "author", default="") or "").strip()
    vote_count = _value(item, "VoteUpCount", "vote_up_count", "UpvoteCount", "upvote_count", default=0)
    comment_count = _value(item, "CommentCount", "comment_count", default=0)
    try:
        votes = int(vote_count or 0)
    except (TypeError, ValueError):
        votes = 0
    try:
        comments = int(comment_count or 0)
    except (TypeError, ValueError):
        comments = 0
    published = _published(_value(item, "EditTime", "edit_time", "PublishedAt", "published_at", default=""))
    return PostRecord(
        platform="zhihu",
        native_id=_native_id(url),
        canonical_url=url,
        query=query,
        query_matches=[query],
        content_type="search_result",
        source_mode="zhihu_official_search",
        source_host="developer.zhihu.com",
        source_url=ZHIHU_SEARCH_URL,
        published_at=published,
        author_name=author,
        original_text=text,
        engagement={"likes": votes, "replies": comments},
        raw_stats={
            "vote_up_count": votes,
            "comment_count": comments,
            "official_api": True,
            "api_result_title": title,
        },
    )


def collect_zhihu_official(
    *,
    search_terms: list[str],
    access_secret: str,
    max_posts_per_query: int = 10,
    session: requests.Session | None = None,
) -> list[PostRecord]:
    secret = str(access_secret or "").strip()
    if not secret:
        raise ValueError(
            "Zhihu keyword search requires a Zhihu Open Platform Access Secret. "
            "Public known-item URL import remains separate from authenticated search."
        )
    client = session or requests.Session()
    results: list[PostRecord] = []
    seen: set[str] = set()
    count = max(1, min(int(max_posts_per_query or 10), 10))
    for raw_term in search_terms:
        term = str(raw_term or "").strip()
        if not term:
            continue
        response = client.get(
            ZHIHU_SEARCH_URL,
            params={"Query": term, "Count": count},
            headers={
                "Authorization": f"Bearer {secret}",
                "X-Request-Timestamp": str(int(time.time())),
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        if 300 <= response.status_code < 400:
            raise RuntimeError("Zhihu Open Platform search redirected unexpectedly; refusing to forward credentials.")
        if response.status_code >= 400:
            raise RuntimeError(f"Zhihu Open Platform returned HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Zhihu Open Platform returned a non-JSON response.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Zhihu Open Platform returned an unexpected response shape.")
        code = _value(payload, "Code", "code", default=0)
        try:
            code_number = int(code or 0)
        except (TypeError, ValueError):
            code_number = -1
        if code_number != 0:
            message = str(_value(payload, "Message", "message", default="Unknown Zhihu API error") or "Unknown Zhihu API error")
            raise RuntimeError(f"Zhihu Open Platform error {code_number}: {message}")
        for item in _items(payload)[:count]:
            record = _record(item, term)
            if record is None:
                continue
            if record.record_key in seen:
                existing = next(row for row in results if row.record_key == record.record_key)
                existing.add_query_match(term)
                continue
            seen.add(record.record_key)
            results.append(record)
    return results
