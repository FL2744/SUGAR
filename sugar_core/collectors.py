from __future__ import annotations

import json
from collections import OrderedDict
from typing import Iterable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .models import PostRecord, merge_record
from .utils import in_inclusive_date_range, normalize_whitespace

X_API_BASE_URL = "https://api.x.com/2"
BLUESKY_API_BASE_URL = "https://public.api.bsky.app"
BLUESKY_PDS_URL = "https://bsky.social"
BLUESKY_SERVICE_PROXY = "did:web:api.bsky.app#bsky_appview"


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "SUGAR/1.1 research-client (+Virginia Tech Diplomacy Lab)",
        "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
    })
    return session


def _metric(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def normalize_engagement(platform: str, raw: dict) -> dict[str, int]:
    if platform == "x":
        return {
            "likes": _metric(raw.get("like_count")),
            "replies": _metric(raw.get("reply_count")),
            "reposts": _metric(raw.get("retweet_count")),
            "quotes": _metric(raw.get("quote_count")),
            "bookmarks": _metric(raw.get("bookmark_count")),
            "impressions": _metric(raw.get("impression_count")),
        }
    if platform == "bluesky":
        return {
            "likes": _metric(raw.get("like_count")),
            "replies": _metric(raw.get("reply_count")),
            "reposts": _metric(raw.get("repost_count")),
            "quotes": _metric(raw.get("quote_count")),
            "bookmarks": 0,
            "impressions": 0,
        }
    if platform == "mastodon":
        return {
            "likes": _metric(raw.get("favourite_count")),
            "replies": _metric(raw.get("reply_count")),
            "reposts": _metric(raw.get("reblog_count")),
            "quotes": 0,
            "bookmarks": 0,
            "impressions": 0,
        }
    return {"likes": 0, "replies": 0, "reposts": 0, "quotes": 0, "bookmarks": 0, "impressions": 0}


def _merge(records: OrderedDict[tuple[str, str], PostRecord], record: PostRecord) -> None:
    key = (record.platform, record.native_id or record.canonical_url)
    if key in records:
        merge_record(records[key], record)
    else:
        for query in record.query_matches or [record.query]:
            record.add_query_match(query)
        records[key] = record


def _platform_key(platform: str, native_id: str) -> str:
    native_id = normalize_whitespace(native_id)
    return f"{platform}:{native_id}" if native_id else ""


def _at_uri_rkey(uri: str) -> str:
    uri = normalize_whitespace(uri)
    return uri.rsplit("/", 1)[-1] if "/" in uri else uri


def create_bluesky_access_token(session: requests.Session, identifier: str, app_password: str) -> str:
    response = session.post(
        f"{BLUESKY_PDS_URL}/xrpc/com.atproto.server.createSession",
        json={"identifier": identifier, "password": app_password}, timeout=60,
    )
    if response.status_code in {400, 401}:
        raise RuntimeError("Bluesky rejected the handle/app password.")
    response.raise_for_status()
    token = str(response.json().get("accessJwt", "")).strip()
    if not token:
        raise RuntimeError("Bluesky login returned no access token.")
    return token


def collect_x(*, bearer_token: str, search_terms: Iterable[str], search_mode: str = "recent",
              since: str | None = None, until: str | None = None, post_languages: list[str] | None = None,
              include_reposts: bool = False, max_posts_per_query: int = 100,
              max_pages_per_query: int = 1, session: requests.Session | None = None) -> list[PostRecord]:
    if search_mode not in {"recent", "all"}:
        raise ValueError("X search_mode must be recent or all")
    if not bearer_token:
        raise ValueError("X bearer token is required.")
    session = session or create_session()
    records: OrderedDict[tuple[str, str], PostRecord] = OrderedDict()
    endpoint = f"{X_API_BASE_URL}/tweets/search/{search_mode}"

    for original_query in search_terms:
        query = normalize_whitespace(original_query)
        if post_languages and not "lang:" in query:
            query += " (" + " OR ".join(f"lang:{x}" for x in post_languages) + ")"
        if not include_reposts and "is:retweet" not in query:
            query += " -is:retweet"
        next_token = None
        collected = 0
        for _ in range(max_pages_per_query):
            remaining = max_posts_per_query - collected
            if remaining <= 0:
                break
            params = {
                "query": query,
                "max_results": max(10, min(500 if search_mode == "all" else 100, remaining)),
                "tweet.fields": "id,text,author_id,created_at,conversation_id,lang,public_metrics,referenced_tweets",
                "expansions": "author_id",
                "user.fields": "id,name,username,location",
            }
            if since:
                params["start_time"] = since + "T00:00:00Z" if len(since) == 10 else since
            if until:
                params["end_time"] = until + "T23:59:59Z" if len(until) == 10 else until
            if next_token:
                params["next_token"] = next_token
            response = session.get(endpoint, params=params, headers={"Authorization": f"Bearer {bearer_token}"}, timeout=60)
            if response.status_code == 401:
                raise RuntimeError("X rejected the bearer token (401).")
            if response.status_code == 402:
                raise RuntimeError("X API billing/credits are required (402).")
            if response.status_code == 403:
                raise RuntimeError(f"X denied {search_mode} search for this app (403).")
            if response.status_code == 429:
                raise RuntimeError("X rate limit reached (429).")
            response.raise_for_status()
            payload = response.json()
            users = {str(x.get("id", "")): x for x in payload.get("includes", {}).get("users", [])}
            page_items = payload.get("data", []) or []
            for item in page_items:
                author = users.get(str(item.get("author_id", "")), {})
                refs = item.get("referenced_tweets") or []
                repost = any(x.get("type") == "retweeted" for x in refs)
                if repost and not include_reposts:
                    continue
                native_id = str(item.get("id", ""))
                conversation_id = str(item.get("conversation_id", "") or native_id)
                replied_to = next(
                    (str(ref.get("id", "")) for ref in refs if ref.get("type") == "replied_to" and ref.get("id")),
                    "",
                )
                handle = str(author.get("username", ""))
                raw = dict(item.get("public_metrics") or {})
                raw["conversation_id"] = conversation_id
                if replied_to:
                    raw["replied_to_id"] = replied_to
                url = f"https://x.com/{handle}/status/{native_id}" if handle else f"https://x.com/i/web/status/{native_id}"
                _merge(records, PostRecord(
                    platform="x", native_id=native_id, canonical_url=url, query=original_query,
                    query_matches=[original_query],
                    parent_record_key=_platform_key("x", replied_to),
                    thread_root_key=_platform_key("x", conversation_id),
                    conversation_id=conversation_id,
                    source_mode=f"x_api_{search_mode}", source_host="api.x.com",
                    source_url=response.url, published_at=str(item.get("created_at", "")),
                    author_handle=handle, author_name=str(author.get("name", "")),
                    author_location=str(author.get("location", "")), platform_language=str(item.get("lang", "")),
                    original_text=str(item.get("text", "")), raw_stats=raw,
                    engagement=normalize_engagement("x", raw), is_repost=repost,
                ))
                collected += 1
                if collected >= max_posts_per_query:
                    break
            next_token = payload.get("meta", {}).get("next_token")
            if not next_token or collected >= max_posts_per_query:
                break
    return list(records.values())


def collect_bluesky(*, search_terms: Iterable[str], since: str | None = None, until: str | None = None,
                    max_posts_per_query: int = 100, max_pages_per_query: int = 1,
                    access_jwt: str = "", session: requests.Session | None = None) -> list[PostRecord]:
    session = session or create_session()
    records: OrderedDict[tuple[str, str], PostRecord] = OrderedDict()
    if access_jwt:
        endpoint = f"{BLUESKY_PDS_URL}/xrpc/app.bsky.feed.searchPosts"
        headers = {"Authorization": f"Bearer {access_jwt}", "atproto-proxy": BLUESKY_SERVICE_PROXY}
    else:
        endpoint = f"{BLUESKY_API_BASE_URL}/xrpc/app.bsky.feed.searchPosts"
        headers = {}
    for query in search_terms:
        cursor = None
        collected = 0
        for _ in range(max_pages_per_query):
            remaining = max_posts_per_query - collected
            if remaining <= 0:
                break
            params = {"q": query, "sort": "latest", "limit": max(1, min(100, remaining))}
            if since: params["since"] = since
            if until: params["until"] = until
            if cursor: params["cursor"] = cursor
            response = session.get(endpoint, params=params, headers=headers, timeout=60)
            response.raise_for_status()
            payload = response.json()
            for item in payload.get("posts", []) or []:
                author, record = item.get("author") or {}, item.get("record") or {}
                uri = str(item.get("uri", "")); native_id = _at_uri_rkey(uri)
                handle = str(author.get("handle", ""))
                reply = record.get("reply") if isinstance(record.get("reply"), dict) else {}
                parent_ref = reply.get("parent") if isinstance(reply.get("parent"), dict) else {}
                root_ref = reply.get("root") if isinstance(reply.get("root"), dict) else {}
                parent_uri = str(parent_ref.get("uri", ""))
                root_uri = str(root_ref.get("uri", "")) or uri
                parent_id = _at_uri_rkey(parent_uri)
                root_id = _at_uri_rkey(root_uri) or native_id
                raw = {"reply_count": item.get("replyCount", 0), "repost_count": item.get("repostCount", 0),
                       "like_count": item.get("likeCount", 0), "quote_count": item.get("quoteCount", 0),
                       "uri": uri, "reply_parent_uri": parent_uri, "reply_root_uri": root_uri}
                langs = record.get("langs") or []
                url = f"https://bsky.app/profile/{handle}/post/{native_id}" if handle and native_id else ""
                _merge(records, PostRecord(
                    platform="bluesky", native_id=native_id or uri, canonical_url=url, query=query,
                    query_matches=[query],
                    parent_record_key=_platform_key("bluesky", parent_id),
                    thread_root_key=_platform_key("bluesky", root_id),
                    conversation_id=root_uri,
                    source_host=urlparse(endpoint).netloc, source_url=response.url,
                    published_at=str(record.get("createdAt", item.get("indexedAt", ""))), author_handle=handle,
                    author_name=str(author.get("displayName", "")), platform_language=",".join(map(str, langs)),
                    original_text=str(record.get("text", "")), raw_stats=raw,
                    engagement=normalize_engagement("bluesky", raw),
                ))
                collected += 1
                if collected >= max_posts_per_query: break
            cursor = payload.get("cursor")
            if not cursor or collected >= max_posts_per_query: break
    return list(records.values())


def _plain_html(value: str) -> str:
    return normalize_whitespace(BeautifulSoup(value or "", "html.parser").get_text(" "))


def collect_mastodon(*, instance_url: str, search_terms: Iterable[str], access_token: str = "",
                     since: str | None = None, until: str | None = None, include_reposts: bool = False,
                     max_posts_per_query: int = 40, max_pages_per_query: int = 1,
                     session: requests.Session | None = None) -> list[PostRecord]:
    session = session or create_session(); instance_url = instance_url.rstrip("/")
    records: OrderedDict[tuple[str, str], PostRecord] = OrderedDict()
    endpoint = f"{instance_url}/api/v2/search"; headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    for query in search_terms:
        offset = 0; collected = 0
        for _ in range(max_pages_per_query):
            limit = max(1, min(40, max_posts_per_query - collected))
            if limit <= 0: break
            params = {"q": query, "type": "statuses", "limit": limit}
            if access_token and offset: params["offset"] = offset
            response = session.get(endpoint, params=params, headers=headers, timeout=60); response.raise_for_status()
            statuses = response.json().get("statuses", []) or []
            for status in statuses:
                repost = bool(status.get("reblog")); content = status.get("reblog") or status
                if repost and not include_reposts: continue
                published = str(content.get("created_at", status.get("created_at", "")))
                if not in_inclusive_date_range(published, since, until): continue
                account = content.get("account") or status.get("account") or {}
                parent_id = str(content.get("in_reply_to_id", "") or "")
                raw = {"reply_count": content.get("replies_count", 0), "reblog_count": content.get("reblogs_count", 0),
                       "favourite_count": content.get("favourites_count", 0), "in_reply_to_id": parent_id}
                native_id = str(content.get("id", status.get("id", "")))
                root_key = "" if parent_id else _platform_key("mastodon", native_id)
                conversation_id = "" if parent_id else native_id
                _merge(records, PostRecord(
                    platform="mastodon", native_id=native_id, canonical_url=str(content.get("url", status.get("url", ""))),
                    query=query, query_matches=[query],
                    parent_record_key=_platform_key("mastodon", parent_id),
                    thread_root_key=root_key,
                    conversation_id=conversation_id,
                    source_host=urlparse(instance_url).netloc,
                    source_url=response.url, published_at=published,
                    author_handle=str(account.get("acct", account.get("username", ""))),
                    author_name=_plain_html(str(account.get("display_name", ""))),
                    platform_language=str(content.get("language", "") or ""), original_text=_plain_html(str(content.get("content", ""))),
                    raw_stats=raw, engagement=normalize_engagement("mastodon", raw), is_repost=repost,
                ))
                collected += 1
                if collected >= max_posts_per_query: break
            if not access_token or len(statuses) < limit or collected >= max_posts_per_query: break
            offset += len(statuses)
    return list(records.values())
