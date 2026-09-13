from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Iterator
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .models import PostRecord, merge_record
from .utils import in_inclusive_date_range, normalize_whitespace

WEIBO_MOBILE_BASE_URL = "https://m.weibo.cn"
WEIBO_WEB_BASE_URL = "https://weibo.com"
WEIBO_SEARCH_ENDPOINT = f"{WEIBO_MOBILE_BASE_URL}/api/container/getIndex"
WEIBO_STATUS_ENDPOINT = f"{WEIBO_MOBILE_BASE_URL}/statuses/show"
WEIBO_EXTEND_ENDPOINT = f"{WEIBO_MOBILE_BASE_URL}/statuses/extend"
WEIBO_COMMENTS_ENDPOINT = f"{WEIBO_MOBILE_BASE_URL}/api/comments/show"

_CHINA_TZ = timezone(timedelta(hours=8))
_LOGIN_MARKERS = ("登录", "登陆", "login", "请先登录", "未登录")


class WeiboAccessError(RuntimeError):
    """Raised when Weibo requires access state the configured collector does not have."""


def create_weibo_session(cookie: str = "") -> requests.Session:
    """Create an ordinary mobile-PWA session.

    ``cookie`` is optional and must be a legitimate session string supplied by the user/team.
    SUGAR does not generate visitor/login cookies or automate authentication.
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
                "Mobile/15E148 Safari/604.1 SUGAR-VT-Diplomacy-Lab/1.1"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Referer": f"{WEIBO_MOBILE_BASE_URL}/",
            "MWeibo-Pwa": "1",
            "X-Requested-With": "XMLHttpRequest",
        }
    )
    cookie = normalize_whitespace(cookie)
    if cookie:
        session.headers["Cookie"] = cookie
    return session


def _metric(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _plain_html(value: Any) -> str:
    return normalize_whitespace(BeautifulSoup(str(value or ""), "html.parser").get_text(" "))


def _handle_http(response: requests.Response, operation: str) -> None:
    if response.status_code in {401, 403, 418}:
        raise WeiboAccessError(
            f"Weibo denied the {operation} request (HTTP {response.status_code}). "
            "SUGAR will not bypass login, verification, or risk-control gates."
        )
    if response.status_code == 429:
        raise WeiboAccessError(f"Weibo rate-limited the {operation} request (HTTP 429). Retry later.")
    response.raise_for_status()


def _message(payload: dict[str, Any]) -> str:
    return normalize_whitespace(
        payload.get("msg", payload.get("message", payload.get("errmsg", "")))
    )


def _unwrap(payload: Any, operation: str) -> Any:
    if not isinstance(payload, dict):
        raise RuntimeError(f"Weibo {operation} returned an unexpected response shape.")

    # Some public status routes return a status object directly; API routes generally use ok/data.
    if "ok" not in payload:
        return payload

    raw_ok = payload.get("ok")
    try:
        ok = int(raw_ok)
    except (TypeError, ValueError):
        ok = 0
    message = _message(payload)
    lower_message = message.casefold()

    if ok == 1:
        return payload.get("data", {})
    if ok == -100 or any(marker.casefold() in lower_message for marker in _LOGIN_MARKERS):
        raise WeiboAccessError(
            f"Weibo {operation} requires a logged-in/authorized session"
            + (f" ({message})" if message else "")
            + ". SUGAR will not manufacture or harvest credentials."
        )
    if ok == 0 and not payload.get("data"):
        raise RuntimeError(f"Weibo {operation} returned no usable data" + (f": {message}" if message else "."))
    return payload.get("data", {})


def _parse_weibo_time(value: Any, *, now: datetime | None = None) -> str:
    text = normalize_whitespace(value)
    if not text:
        return ""

    for fmt in (
        "%a %b %d %H:%M:%S %z %Y",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=_CHINA_TZ)
            return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except ValueError:
            pass

    local_now = (now or datetime.now(timezone.utc)).astimezone(_CHINA_TZ)
    try:
        if text == "刚刚":
            parsed = local_now
        elif text.endswith("分钟前"):
            parsed = local_now - timedelta(minutes=int(text[:-3]))
        elif text.startswith("今天"):
            clock = text.replace("今天", "").strip()
            hour, minute = [int(part) for part in clock.split(":", 1)]
            parsed = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        elif text.startswith("昨天"):
            clock = text.replace("昨天", "").strip()
            hour, minute = [int(part) for part in clock.split(":", 1)]
            parsed = (local_now - timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        elif len(text) == 5 and text[2] == "-":
            month, day = [int(part) for part in text.split("-", 1)]
            parsed = local_now.replace(month=month, day=day, hour=0, minute=0, second=0, microsecond=0)
        else:
            return ""
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except (ValueError, TypeError):
        return ""


def normalize_weibo_engagement(status: dict[str, Any]) -> dict[str, int]:
    return {
        "likes": _metric(status.get("attitudes_count")),
        "replies": _metric(status.get("comments_count")),
        "reposts": _metric(status.get("reposts_count")),
        "quotes": 0,
        "bookmarks": 0,
        "impressions": 0,
    }


def _status_identity(status: dict[str, Any]) -> tuple[str, str]:
    native_id = normalize_whitespace(status.get("id", status.get("mid", status.get("idstr", ""))))
    bid = normalize_whitespace(status.get("bid", status.get("mblogid", "")))
    return native_id or bid, bid


def _status_url(native_id: str, bid: str = "") -> str:
    identity = bid or native_id
    return f"{WEIBO_MOBILE_BASE_URL}/detail/{quote(identity)}" if identity else ""


def _status_to_record(
    status: dict[str, Any],
    *,
    query: str = "",
    source_url: str = "",
    source_mode: str = "weibo_public_status",
    full_text: str = "",
) -> PostRecord:
    native_id, bid = _status_identity(status)
    user = status.get("user") if isinstance(status.get("user"), dict) else {}
    retweeted = status.get("retweeted_status") if isinstance(status.get("retweeted_status"), dict) else None
    text = _plain_html(full_text or status.get("text_raw", status.get("text", "")))
    raw = {
        "attitudes_count": _metric(status.get("attitudes_count")),
        "comments_count": _metric(status.get("comments_count")),
        "reposts_count": _metric(status.get("reposts_count")),
        "bid": bid,
        "mid": normalize_whitespace(status.get("mid", "")),
        "user_id": normalize_whitespace(user.get("id", user.get("idstr", ""))),
        "source": _plain_html(status.get("source", "")),
        "region_name": normalize_whitespace(status.get("region_name", "")),
        "created_at_raw": normalize_whitespace(status.get("created_at", "")),
        "is_long_text": bool(status.get("isLongText", status.get("is_long_text", False))),
    }
    if retweeted:
        original_id, original_bid = _status_identity(retweeted)
        raw["retweeted_status_id"] = original_id
        raw["retweeted_status_bid"] = original_bid

    record = PostRecord(
        platform="weibo",
        native_id=native_id,
        canonical_url=_status_url(native_id, bid),
        query=query,
        query_matches=[query] if query else [],
        content_type="post",
        source_mode=source_mode,
        source_host="m.weibo.cn",
        source_url=source_url,
        published_at=_parse_weibo_time(status.get("created_at", "")),
        author_handle=normalize_whitespace(user.get("id", user.get("idstr", ""))),
        author_name=_plain_html(user.get("screen_name", "")),
        author_location=normalize_whitespace(user.get("location", "")),
        original_text=text,
        raw_stats=raw,
        engagement=normalize_weibo_engagement(status),
        is_repost=bool(retweeted),
    )
    if native_id:
        record.conversation_id = native_id
        record.thread_root_key = record.record_key
    return record


def _long_text_from_payload(payload: Any) -> str:
    data = _unwrap(payload, "long-text retrieval")
    if not isinstance(data, dict):
        return ""
    return _plain_html(data.get("longTextContent", data.get("long_text", "")))


def fetch_weibo_status(
    status_id: str,
    *,
    query: str = "",
    cookie: str = "",
    session: requests.Session | None = None,
) -> PostRecord:
    """Fetch one publicly readable Weibo status by numeric ID or bid."""
    status_id = normalize_whitespace(status_id)
    if not status_id:
        raise ValueError("A Weibo status ID or bid is required.")
    session = session or create_weibo_session(cookie)

    response = session.get(WEIBO_STATUS_ENDPOINT, params={"id": status_id}, timeout=30)
    _handle_http(response, "status retrieval")
    data = _unwrap(response.json(), "status retrieval")
    if not isinstance(data, dict):
        raise RuntimeError("Weibo status retrieval returned an unexpected status shape.")

    full_text = ""
    if bool(data.get("isLongText", data.get("is_long_text", False))):
        try:
            extended = session.get(WEIBO_EXTEND_ENDPOINT, params={"id": status_id}, timeout=30)
            _handle_http(extended, "long-text retrieval")
            full_text = _long_text_from_payload(extended.json())
        except WeiboAccessError:
            # The short public status remains useful even if the extension route is separately gated.
            full_text = ""
        except (requests.RequestException, RuntimeError, ValueError):
            full_text = ""

    record = _status_to_record(
        data,
        query=query,
        source_url=response.url,
        source_mode="weibo_public_status",
        full_text=full_text,
    )
    if not record.native_id:
        raise RuntimeError("Weibo status response did not contain a stable status identifier.")
    return record


def _iter_mblogs(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        mblog = value.get("mblog")
        if isinstance(mblog, dict):
            yield mblog
        for key in ("cards", "card_group"):
            child = value.get(key)
            if isinstance(child, list):
                for item in child:
                    yield from _iter_mblogs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_mblogs(item)


def _merge_record(records: OrderedDict[tuple[str, str], PostRecord], record: PostRecord) -> None:
    key = (record.platform, record.native_id or record.canonical_url)
    if key in records:
        merge_record(records[key], record)
        return
    for query in record.query_matches or [record.query]:
        record.add_query_match(query)
    records[key] = record


def collect_weibo_public(
    *,
    search_terms: Iterable[str],
    since: str | None = None,
    until: str | None = None,
    max_posts_per_query: int = 20,
    max_pages_per_query: int = 1,
    cookie: str = "",
    hydrate_details: bool = True,
    session: requests.Session | None = None,
) -> list[PostRecord]:
    """Search the ordinary mobile Weibo surface and normalize public results.

    Anonymous availability is controlled by Weibo and can vary. A caller may supply an existing,
    legitimate Weibo session cookie. If Weibo returns a login/risk-control response, SUGAR stops
    explicitly rather than creating visitor cookies, automating login, or evading the gate.
    """
    if max_posts_per_query < 1:
        raise ValueError("max_posts_per_query must be at least 1.")
    if max_pages_per_query < 1:
        raise ValueError("max_pages_per_query must be at least 1.")

    session = session or create_weibo_session(cookie)
    records: OrderedDict[tuple[str, str], PostRecord] = OrderedDict()

    for raw_query in search_terms:
        query = normalize_whitespace(raw_query)
        if not query:
            continue
        collected = 0
        seen_page_ids: set[str] = set()
        for page in range(1, max_pages_per_query + 1):
            params = {
                "containerid": f"100103type=1&q={query}",
                "page_type": "searchall",
                "page": page,
            }
            response = session.get(WEIBO_SEARCH_ENDPOINT, params=params, timeout=30)
            _handle_http(response, "keyword search")
            data = _unwrap(response.json(), "keyword search")
            if not isinstance(data, dict):
                raise RuntimeError("Weibo keyword search returned an unexpected data shape.")
            cards = data.get("cards") or []
            mblogs = list(_iter_mblogs(cards))
            if not mblogs:
                break

            new_on_page = 0
            for status in mblogs:
                native_id, _ = _status_identity(status)
                if not native_id or native_id in seen_page_ids:
                    continue
                seen_page_ids.add(native_id)
                record = _status_to_record(
                    status,
                    query=query,
                    source_url=response.url,
                    source_mode="weibo_public_search",
                )
                if hydrate_details:
                    try:
                        detail = fetch_weibo_status(native_id, query=query, cookie=cookie, session=session)
                        detail.source_mode = "weibo_public_search+status"
                        detail.source_url = response.url
                        record = detail
                    except WeiboAccessError:
                        # Search itself was allowed; preserve its public result if detail is gated.
                        record = record
                    except (requests.RequestException, RuntimeError, ValueError):
                        record = record
                if not in_inclusive_date_range(record.published_at, since, until):
                    continue
                _merge_record(records, record)
                collected += 1
                new_on_page += 1
                if collected >= max_posts_per_query:
                    break

            if collected >= max_posts_per_query or new_on_page == 0:
                break

    return list(records.values())


def _comment_to_record(
    comment: dict[str, Any],
    *,
    status_id: str,
    query: str,
    source_url: str,
) -> PostRecord:
    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
    comment_id = normalize_whitespace(comment.get("id", comment.get("idstr", "")))
    reply_comment = comment.get("reply_comment") if isinstance(comment.get("reply_comment"), dict) else {}
    direct_parent = normalize_whitespace(
        reply_comment.get("id", comment.get("reply_id", comment.get("replyid", "")))
    )
    parent_key = f"weibo:{direct_parent}" if direct_parent else f"weibo:{status_id}"
    raw = {
        "like_count": _metric(comment.get("like_count", comment.get("like_counts"))),
        "reply_count": _metric(comment.get("total_number", comment.get("reply_count"))),
        "status_id": status_id,
        "rootid": normalize_whitespace(comment.get("rootid", "")),
        "reply_id": direct_parent,
        "created_at_raw": normalize_whitespace(comment.get("created_at", "")),
    }
    return PostRecord(
        platform="weibo",
        native_id=comment_id,
        canonical_url=(
            f"{WEIBO_MOBILE_BASE_URL}/detail/{quote(status_id)}#comment-{quote(comment_id)}"
            if comment_id
            else f"{WEIBO_MOBILE_BASE_URL}/detail/{quote(status_id)}"
        ),
        query=query,
        query_matches=[query] if query else [],
        content_type="comment",
        parent_record_key=parent_key,
        thread_root_key=f"weibo:{status_id}",
        conversation_id=status_id,
        source_mode="weibo_public_comment",
        source_host="m.weibo.cn",
        source_url=source_url,
        published_at=_parse_weibo_time(comment.get("created_at", "")),
        author_handle=normalize_whitespace(user.get("id", user.get("idstr", ""))),
        author_name=_plain_html(user.get("screen_name", "")),
        author_location=normalize_whitespace(user.get("location", "")),
        original_text=_plain_html(comment.get("text", comment.get("text_raw", ""))),
        raw_stats=raw,
        engagement={
            "likes": raw["like_count"],
            "replies": raw["reply_count"],
            "reposts": 0,
            "quotes": 0,
            "bookmarks": 0,
            "impressions": 0,
        },
    )


def _comment_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("data", "hot_data", "comments"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def collect_weibo_comments(
    status_id: str,
    *,
    query: str = "",
    since: str | None = None,
    until: str | None = None,
    max_comments: int = 100,
    max_pages: int = 5,
    cookie: str = "",
    session: requests.Session | None = None,
) -> list[PostRecord]:
    """Collect comments returned by Weibo's ordinary mobile comment surface."""
    status_id = normalize_whitespace(status_id)
    if not status_id:
        raise ValueError("A Weibo status ID is required for comment collection.")
    if max_comments < 1 or max_pages < 1:
        return []

    session = session or create_weibo_session(cookie)
    records: OrderedDict[tuple[str, str], PostRecord] = OrderedDict()

    for page in range(1, max_pages + 1):
        response = session.get(
            WEIBO_COMMENTS_ENDPOINT,
            params={"id": status_id, "page": page},
            timeout=30,
        )
        _handle_http(response, "comment retrieval")
        data = _unwrap(response.json(), "comment retrieval")
        comments = _comment_items(data)
        if not comments:
            break

        new_on_page = 0
        for item in comments:
            record = _comment_to_record(
                item,
                status_id=status_id,
                query=query,
                source_url=response.url,
            )
            if not record.native_id:
                continue
            if not in_inclusive_date_range(record.published_at, since, until):
                continue
            key = (record.platform, record.native_id)
            if key in records:
                continue
            records[key] = record
            new_on_page += 1
            if len(records) >= max_comments:
                return list(records.values())

        # Anonymous/basic comment routes can repeat the first page rather than expose deeper paging.
        if new_on_page == 0:
            break

    return list(records.values())
