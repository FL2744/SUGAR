from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup

from .models import PostRecord, merge_record
from .utils import in_inclusive_date_range, normalize_whitespace

BILIBILI_API_BASE_URL = "https://api.bilibili.com"
BILIBILI_WEB_BASE_URL = "https://www.bilibili.com"

# Bilibili returns HTTP 200 for several application-level access failures.
# These codes are treated as hard stops rather than invitations to bypass the gate.
_ACCESS_CONTROL_CODES = {-101, -352, -412}


class BilibiliAccessError(RuntimeError):
    """Raised when Bilibili requires access state this public collector does not provide."""


def create_bilibili_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "SUGAR/1.1 research-client (+Virginia Tech Diplomacy Lab; public Bilibili client)",
            "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
            "Referer": f"{BILIBILI_WEB_BASE_URL}/",
        }
    )
    return session


def _metric(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def normalize_bilibili_engagement(raw: dict[str, Any]) -> dict[str, int]:
    """Map only semantically compatible Bilibili metrics into SUGAR's canonical fields."""
    return {
        "likes": _metric(raw.get("like")),
        "replies": _metric(raw.get("reply")),
        # Bilibili shares are not equivalent to reposts, so preserve them only in raw_stats.
        "reposts": 0,
        "quotes": 0,
        "bookmarks": _metric(raw.get("favorite")),
        "impressions": _metric(raw.get("view")),
    }


def _clean_html(value: Any) -> str:
    return normalize_whitespace(BeautifulSoup(str(value or ""), "html.parser").get_text(" "))


def _iso_from_unix(value: Any) -> str:
    try:
        timestamp = int(float(value))
    except (TypeError, ValueError):
        return ""
    if timestamp <= 0:
        return ""
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return ""


def _handle_http(response: requests.Response, operation: str) -> None:
    if response.status_code in {401, 403}:
        raise BilibiliAccessError(
            f"Bilibili denied the public {operation} request (HTTP {response.status_code}). "
            "SUGAR will not attempt to bypass login or access controls."
        )
    if response.status_code == 429:
        raise BilibiliAccessError(
            f"Bilibili rate-limited the public {operation} request (HTTP 429). Stop and retry later."
        )
    response.raise_for_status()


def _unwrap(payload: Any, operation: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError(f"Bilibili {operation} returned an unexpected response shape.")
    try:
        code = int(payload.get("code", 0) or 0)
    except (TypeError, ValueError):
        code = -1
    if code in _ACCESS_CONTROL_CODES:
        message = normalize_whitespace(payload.get("message", "")) or "access denied"
        raise BilibiliAccessError(
            f"Bilibili public {operation} is unavailable for this anonymous session "
            f"(code {code}: {message}). SUGAR will not synthesize credentials, WBI signatures, "
            "device identifiers, or other bypass state."
        )
    if code != 0:
        message = normalize_whitespace(payload.get("message", "")) or "unknown API error"
        raise RuntimeError(f"Bilibili {operation} failed (code {code}: {message}).")
    data = payload.get("data")
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise RuntimeError(f"Bilibili {operation} returned an unexpected data shape.")
    return data


def warm_public_session(session: requests.Session) -> None:
    """Perform an ordinary public homepage request so the server may establish normal session state."""
    response = session.get(f"{BILIBILI_WEB_BASE_URL}/", timeout=30)
    _handle_http(response, "session initialization")


def _merge_record(records: OrderedDict[tuple[str, str], PostRecord], record: PostRecord) -> None:
    key = (record.platform, record.native_id or record.canonical_url)
    if key in records:
        merge_record(records[key], record)
        return
    for query in record.query_matches or [record.query]:
        record.add_query_match(query)
    records[key] = record


def _video_url(bvid: str, fallback: str = "") -> str:
    bvid = normalize_whitespace(bvid)
    return f"{BILIBILI_WEB_BASE_URL}/video/{bvid}" if bvid else normalize_whitespace(fallback)


def _search_item_to_record(item: dict[str, Any], *, query: str, source_url: str) -> PostRecord:
    bvid = normalize_whitespace(item.get("bvid", ""))
    aid = normalize_whitespace(item.get("aid", item.get("id", "")))
    native_id = bvid or (f"av{aid}" if aid else "")
    raw = {
        "view": _metric(item.get("play")),
        "reply": _metric(item.get("review", item.get("video_review"))),
        "favorite": _metric(item.get("favorites")),
        "like": _metric(item.get("like")),
        "share": _metric(item.get("share")),
        "coin": _metric(item.get("coin")),
        "danmaku": _metric(item.get("video_review")),
        "aid": aid,
        "bvid": bvid,
        "duration": normalize_whitespace(item.get("duration", "")),
        "typename": normalize_whitespace(item.get("typename", "")),
    }
    title = _clean_html(item.get("title", ""))
    description = _clean_html(item.get("description", item.get("desc", "")))
    text = normalize_whitespace(" — ".join(part for part in (title, description) if part))
    published = _iso_from_unix(item.get("pubdate", item.get("senddate")))
    return PostRecord(
        platform="bilibili",
        native_id=native_id,
        canonical_url=_video_url(bvid, str(item.get("arcurl", ""))),
        query=query,
        query_matches=[query],
        content_type="video",
        source_mode="bilibili_public_search",
        source_host="api.bilibili.com",
        source_url=source_url,
        published_at=published,
        author_handle=normalize_whitespace(item.get("mid", "")),
        author_name=_clean_html(item.get("author", item.get("up_name", ""))),
        original_text=text,
        raw_stats=raw,
        engagement=normalize_bilibili_engagement(raw),
    )


def _detail_to_record(data: dict[str, Any], *, query: str, source_url: str) -> PostRecord:
    bvid = normalize_whitespace(data.get("bvid", ""))
    aid = normalize_whitespace(data.get("aid", ""))
    owner = data.get("owner") if isinstance(data.get("owner"), dict) else {}
    stat = data.get("stat") if isinstance(data.get("stat"), dict) else {}
    raw = {
        "view": _metric(stat.get("view")),
        "reply": _metric(stat.get("reply")),
        "favorite": _metric(stat.get("favorite")),
        "like": _metric(stat.get("like")),
        "share": _metric(stat.get("share")),
        "coin": _metric(stat.get("coin")),
        "danmaku": _metric(stat.get("danmaku")),
        "aid": aid,
        "bvid": bvid,
        "cid": normalize_whitespace(data.get("cid", "")),
        "duration": _metric(data.get("duration")),
        "tname": normalize_whitespace(data.get("tname", "")),
    }
    title = _clean_html(data.get("title", ""))
    description = _clean_html(data.get("desc", data.get("dynamic", "")))
    text = normalize_whitespace(" — ".join(part for part in (title, description) if part))
    return PostRecord(
        platform="bilibili",
        native_id=bvid or (f"av{aid}" if aid else ""),
        canonical_url=_video_url(bvid),
        query=query,
        query_matches=[query] if query else [],
        content_type="video",
        source_mode="bilibili_public_video",
        source_host="api.bilibili.com",
        source_url=source_url,
        published_at=_iso_from_unix(data.get("pubdate", data.get("ctime"))),
        author_handle=normalize_whitespace(owner.get("mid", "")),
        author_name=_clean_html(owner.get("name", "")),
        original_text=text,
        raw_stats=raw,
        engagement=normalize_bilibili_engagement(raw),
    )


def fetch_bilibili_video(
    bvid: str,
    *,
    query: str = "",
    session: requests.Session | None = None,
) -> PostRecord:
    """Fetch public metadata for one known Bilibili video ID."""
    session = session or create_bilibili_session()
    bvid = normalize_whitespace(bvid)
    if not bvid:
        raise ValueError("A Bilibili BV identifier is required.")
    endpoint = f"{BILIBILI_API_BASE_URL}/x/web-interface/view"
    response = session.get(endpoint, params={"bvid": bvid}, timeout=30)
    _handle_http(response, "video metadata")
    data = _unwrap(response.json(), "video metadata")
    record = _detail_to_record(data, query=query, source_url=response.url)
    if not record.native_id:
        raise RuntimeError("Bilibili video metadata did not contain a stable video identifier.")
    return record


def collect_bilibili_public(
    *,
    search_terms: Iterable[str],
    since: str | None = None,
    until: str | None = None,
    max_posts_per_query: int = 20,
    max_pages_per_query: int = 1,
    order: str = "pubdate",
    hydrate_details: bool = True,
    initialize_session: bool = True,
    session: requests.Session | None = None,
) -> list[PostRecord]:
    """Search Bilibili's ordinary public web API without authenticated or bypass state.

    Search availability varies by Bilibili's current anonymous-session policy. If the API requests
    login, WBI/access state, or returns an anti-abuse/access-control code, this collector stops with
    ``BilibiliAccessError`` rather than attempting to defeat the gate.
    """
    if max_posts_per_query < 1:
        raise ValueError("max_posts_per_query must be at least 1.")
    if max_pages_per_query < 1:
        raise ValueError("max_pages_per_query must be at least 1.")
    if order not in {"totalrank", "click", "pubdate", "dm", "stow", "scores"}:
        raise ValueError("Unsupported Bilibili search order.")

    session = session or create_bilibili_session()
    if initialize_session:
        warm_public_session(session)

    endpoint = f"{BILIBILI_API_BASE_URL}/x/web-interface/wbi/search/type"
    records: OrderedDict[tuple[str, str], PostRecord] = OrderedDict()

    for raw_query in search_terms:
        query = normalize_whitespace(raw_query)
        if not query:
            continue
        collected = 0
        for page in range(1, max_pages_per_query + 1):
            remaining = max_posts_per_query - collected
            if remaining <= 0:
                break
            params = {
                "search_type": "video",
                "keyword": query,
                "page": page,
                "page_size": min(20, remaining),
                "order": order,
            }
            response = session.get(endpoint, params=params, timeout=30)
            _handle_http(response, "video search")
            data = _unwrap(response.json(), "video search")
            items = data.get("result") or []
            if not isinstance(items, list):
                raise RuntimeError("Bilibili video search returned an unexpected result shape.")
            if not items:
                break

            before_page = collected
            for item in items:
                if not isinstance(item, dict):
                    continue
                search_record = _search_item_to_record(item, query=query, source_url=response.url)
                record = search_record
                if hydrate_details and search_record.native_id.startswith("BV"):
                    try:
                        detail = fetch_bilibili_video(search_record.native_id, query=query, session=session)
                        # Search provenance remains valuable even when detail metadata is richer.
                        detail.source_mode = "bilibili_public_search+video"
                        detail.source_url = response.url
                        record = detail
                    except BilibiliAccessError:
                        raise
                    except (requests.RequestException, RuntimeError, ValueError):
                        # A single detail failure should not discard a valid public search result.
                        record = search_record
                if not in_inclusive_date_range(record.published_at, since, until):
                    continue
                _merge_record(records, record)
                collected += 1
                if collected >= max_posts_per_query:
                    break

            if len(items) < params["page_size"] or collected >= max_posts_per_query:
                break
            if collected == before_page and (since or until):
                # Continue because later pages may still contain in-range items under non-date sorts.
                continue

    return list(records.values())


def _comment_record(
    reply: dict[str, Any],
    *,
    bvid: str,
    query: str,
    source_url: str,
) -> PostRecord:
    member = reply.get("member") if isinstance(reply.get("member"), dict) else {}
    content = reply.get("content") if isinstance(reply.get("content"), dict) else {}
    rpid = normalize_whitespace(reply.get("rpid", ""))
    raw = {
        "like": _metric(reply.get("like")),
        "reply": _metric(reply.get("rcount")),
        "bvid": bvid,
        "rpid": rpid,
    }
    return PostRecord(
        platform="bilibili",
        native_id=rpid,
        canonical_url=f"{_video_url(bvid)}#reply{rpid}" if rpid else _video_url(bvid),
        query=query,
        query_matches=[query] if query else [],
        content_type="comment",
        source_mode="bilibili_public_comment",
        source_host="api.bilibili.com",
        source_url=source_url,
        published_at=_iso_from_unix(reply.get("ctime")),
        author_handle=normalize_whitespace(member.get("mid", "")),
        author_name=_clean_html(member.get("uname", "")),
        original_text=normalize_whitespace(content.get("message", "")),
        raw_stats=raw,
        engagement={
            "likes": raw["like"],
            "replies": raw["reply"],
            "reposts": 0,
            "quotes": 0,
            "bookmarks": 0,
            "impressions": 0,
        },
    )


def collect_bilibili_comments(
    bvid: str,
    *,
    query: str = "",
    since: str | None = None,
    until: str | None = None,
    max_comments: int = 100,
    max_pages: int = 5,
    session: requests.Session | None = None,
) -> list[PostRecord]:
    """Collect publicly returned top-level comments for one Bilibili video.

    Anonymous comment responses may be partial. SUGAR records only what the public endpoint returns
    and does not log in or attempt to recover comments hidden behind access controls.
    """
    if max_comments < 1:
        return []
    if max_pages < 1:
        return []
    session = session or create_bilibili_session()
    video = fetch_bilibili_video(bvid, query=query, session=session)
    aid = normalize_whitespace(video.raw_stats.get("aid", ""))
    if not aid:
        raise RuntimeError("Bilibili video metadata did not provide the AID required for comments.")

    endpoint = f"{BILIBILI_API_BASE_URL}/x/v2/reply/main"
    records: OrderedDict[tuple[str, str], PostRecord] = OrderedDict()
    next_cursor = 0

    for _ in range(max_pages):
        params = {"type": 1, "oid": aid, "mode": 3, "next": next_cursor, "plat": 1}
        response = session.get(endpoint, params=params, timeout=30)
        _handle_http(response, "comment retrieval")
        data = _unwrap(response.json(), "comment retrieval")
        replies = data.get("replies") or []
        if not isinstance(replies, list):
            raise RuntimeError("Bilibili comments returned an unexpected replies shape.")
        if not replies:
            break

        for reply in replies:
            if not isinstance(reply, dict):
                continue
            record = _comment_record(reply, bvid=bvid, query=query, source_url=response.url)
            if not record.native_id:
                continue
            if not in_inclusive_date_range(record.published_at, since, until):
                continue
            _merge_record(records, record)
            if len(records) >= max_comments:
                return list(records.values())

        cursor = data.get("cursor") if isinstance(data.get("cursor"), dict) else {}
        if cursor.get("is_end") is True:
            break
        candidate = cursor.get("next")
        try:
            candidate = int(candidate)
        except (TypeError, ValueError):
            break
        if candidate == next_cursor:
            break
        next_cursor = candidate

    return list(records.values())
