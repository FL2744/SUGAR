from __future__ import annotations

import json
import re
from collections import Counter, OrderedDict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote, urlparse

import requests

from .models import PostRecord, merge_record
from .storage import save_records
from .utils import normalize_whitespace, utc_iso
from .weibo import (
    WEIBO_MOBILE_BASE_URL,
    WEIBO_SEARCH_ENDPOINT,
    WeiboAccessError,
    _handle_http,
    _iter_mblogs,
    _status_to_record,
    _unwrap,
    collect_weibo_comments,
    create_weibo_session,
    fetch_weibo_status,
)

WEIBO_REPOSTS_ENDPOINT = f"{WEIBO_MOBILE_BASE_URL}/api/statuses/repostTimeline"
WEIBO_DETAIL_ENDPOINT = f"{WEIBO_MOBILE_BASE_URL}/detail"

_HASHTAG_RE = re.compile(r"#([^#\n\r]{1,80})#")
_MENTION_RE = re.compile(r"@([\w\-\u3400-\u9fff]{1,40})")


@dataclass
class WeiboInvestigation:
    seed: PostRecord
    comments: list[PostRecord]
    reposts: list[PostRecord]
    author_posts: list[PostRecord]
    original: PostRecord | None
    surface_status: dict[str, dict[str, str]]
    insights: dict[str, Any]

    @property
    def records(self) -> list[PostRecord]:
        merged: OrderedDict[str, PostRecord] = OrderedDict()
        for record in [self.seed, *(self.comments or []), *(self.reposts or []), *(self.author_posts or [])]:
            if not record.record_key:
                continue
            if record.record_key in merged:
                merge_record(merged[record.record_key], record)
            else:
                merged[record.record_key] = record
        if self.original and self.original.record_key:
            if self.original.record_key in merged:
                merge_record(merged[self.original.record_key], self.original)
            else:
                merged[self.original.record_key] = self.original
        return list(merged.values())


def parse_weibo_seed(value: str) -> str:
    """Normalize a public Weibo post URL, numeric mid, or alphanumeric bid to an identity."""
    text = normalize_whitespace(value)
    if not text:
        raise ValueError("A Weibo post URL or ID is required.")
    if "://" not in text:
        identity = text.strip("/ ")
        if not identity:
            raise ValueError("Could not identify a Weibo post ID.")
        return identity

    parsed = urlparse(text)
    host = parsed.netloc.casefold().split(":", 1)[0]
    if host not in {"m.weibo.cn", "weibo.com", "www.weibo.com"}:
        raise ValueError(f"Unsupported Weibo host: {parsed.netloc}")

    query = parse_qs(parsed.query)
    for key in ("id", "mid", "bid"):
        if query.get(key):
            return normalize_whitespace(unquote(query[key][0]))

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if not parts:
        raise ValueError("Could not identify a Weibo post ID from the URL.")
    if parts[0].casefold() in {"detail", "status"} and len(parts) >= 2:
        return normalize_whitespace(parts[1])
    # Desktop public status URLs conventionally use /{uid}/{bid}.
    if len(parts) >= 2:
        return normalize_whitespace(parts[-1])
    return normalize_whitespace(parts[0])


def _extract_status_from_detail_html(html: str) -> dict[str, Any]:
    """Extract the public `status` object embedded in m.weibo.cn detail HTML."""
    marker = '"status":'
    start = html.find(marker)
    if start < 0:
        raise RuntimeError("Weibo detail page did not expose an embedded status object.")
    start += len(marker)
    while start < len(html) and html[start].isspace():
        start += 1
    try:
        value, _ = json.JSONDecoder().raw_decode(html[start:])
    except json.JSONDecodeError as exc:
        raise RuntimeError("Could not decode the embedded Weibo status object.") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Embedded Weibo status object had an unexpected shape.")
    return value


def fetch_weibo_seed_status(
    seed: str,
    *,
    cookie: str = "",
    session: requests.Session | None = None,
) -> tuple[PostRecord, str]:
    """Fetch a known public post, falling back to the ordinary public detail page.

    The fallback is not an access-control bypass: it reads the same unauthenticated detail page a
    browser can open. Login/verification pages remain hard failures.
    """
    identity = parse_weibo_seed(seed)
    session = session or create_weibo_session(cookie)
    try:
        return fetch_weibo_status(identity, cookie=cookie, session=session), "pwa_json"
    except (WeiboAccessError, requests.RequestException, RuntimeError, ValueError) as primary_error:
        response = session.get(f"{WEIBO_DETAIL_ENDPOINT}/{identity}", timeout=30)
        _handle_http(response, "public detail-page retrieval")
        status = _extract_status_from_detail_html(response.text)
        record = _status_to_record(
            status,
            source_url=response.url,
            source_mode="weibo_public_detail_html",
        )
        if not record.native_id:
            raise RuntimeError(
                f"Weibo JSON route failed ({type(primary_error).__name__}) and the public detail page "
                "did not contain a stable status identifier."
            ) from primary_error
        return record, "detail_html"


def _list_from_payload(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("data", "statuses", "reposts"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def collect_weibo_reposts(
    status_id: str,
    *,
    max_reposts: int = 100,
    max_pages: int = 5,
    cookie: str = "",
    session: requests.Session | None = None,
) -> list[PostRecord]:
    """Collect the public repost sample exposed by Weibo's mobile repost surface."""
    status_id = parse_weibo_seed(status_id)
    if max_reposts < 1 or max_pages < 1:
        return []
    session = session or create_weibo_session(cookie)
    records: OrderedDict[str, PostRecord] = OrderedDict()
    for page in range(1, max_pages + 1):
        response = session.get(
            WEIBO_REPOSTS_ENDPOINT,
            params={"id": status_id, "page": page},
            timeout=30,
        )
        _handle_http(response, "repost retrieval")
        data = _unwrap(response.json(), "repost retrieval")
        items = _list_from_payload(data)
        if not items:
            break
        new_on_page = 0
        for item in items:
            record = _status_to_record(
                item,
                source_url=response.url,
                source_mode="weibo_public_repost",
            )
            if not record.native_id:
                continue
            record.content_type = "repost"
            record.parent_record_key = f"weibo:{status_id}"
            record.thread_root_key = f"weibo:{status_id}"
            record.conversation_id = status_id
            if record.record_key in records:
                continue
            records[record.record_key] = record
            new_on_page += 1
            if len(records) >= max_reposts:
                return list(records.values())
        if new_on_page == 0:
            break
    return list(records.values())


def collect_weibo_user_timeline(
    user_id: str,
    *,
    max_posts: int = 40,
    max_pages: int = 2,
    cookie: str = "",
    session: requests.Session | None = None,
) -> list[PostRecord]:
    """Collect a bounded recent public timeline for contextual/account-baseline analysis."""
    uid = normalize_whitespace(user_id)
    if not uid or max_posts < 1 or max_pages < 1:
        return []
    session = session or create_weibo_session(cookie)
    records: OrderedDict[str, PostRecord] = OrderedDict()
    for page in range(1, max_pages + 1):
        response = session.get(
            WEIBO_SEARCH_ENDPOINT,
            params={
                "type": "uid",
                "value": uid,
                "containerid": f"107603{uid}",
                "page": page,
            },
            timeout=30,
        )
        _handle_http(response, "user-timeline retrieval")
        data = _unwrap(response.json(), "user-timeline retrieval")
        if not isinstance(data, dict):
            break
        posts = list(_iter_mblogs(data.get("cards") or []))
        if not posts:
            break
        new_on_page = 0
        for status in posts:
            record = _status_to_record(
                status,
                source_url=response.url,
                source_mode="weibo_public_user_timeline",
            )
            if not record.record_key or record.record_key in records:
                continue
            records[record.record_key] = record
            new_on_page += 1
            if len(records) >= max_posts:
                return list(records.values())
        if new_on_page == 0:
            break
    return list(records.values())


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _engagement_value(record: PostRecord, key: str) -> int:
    try:
        return max(0, int((record.engagement or {}).get(key, 0) or 0))
    except (TypeError, ValueError):
        return 0


def _extract_tags(records: Iterable[PostRecord]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hashtags: Counter[str] = Counter()
    mentions: Counter[str] = Counter()
    for record in records:
        text = record.original_text or ""
        hashtags.update(normalize_whitespace(tag) for tag in _HASHTAG_RE.findall(text) if normalize_whitespace(tag))
        mentions.update(normalize_whitespace(name) for name in _MENTION_RE.findall(text) if normalize_whitespace(name))
    return (
        [{"value": value, "count": count} for value, count in hashtags.most_common(15)],
        [{"value": value, "count": count} for value, count in mentions.most_common(15)],
    )


def _top_responses(records: Iterable[PostRecord], limit: int = 8) -> list[dict[str, Any]]:
    ranked = sorted(
        records,
        key=lambda row: (_engagement_value(row, "likes"), _engagement_value(row, "replies")),
        reverse=True,
    )
    return [
        {
            "record_key": row.record_key,
            "type": row.content_type,
            "author": row.author_name or row.author_handle,
            "region": row.author_location,
            "published_at": row.published_at,
            "likes": _engagement_value(row, "likes"),
            "replies": _engagement_value(row, "replies"),
            "text": row.original_text[:500],
            "url": row.canonical_url,
        }
        for row in ranked[:limit]
    ]


def build_weibo_insights(
    seed: PostRecord,
    comments: list[PostRecord],
    reposts: list[PostRecord],
    author_posts: list[PostRecord],
    *,
    surface_status: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    reported_comments = _engagement_value(seed, "replies")
    reported_reposts = _engagement_value(seed, "reposts")
    reported_likes = _engagement_value(seed, "likes")
    responses = [*comments, *reposts]
    hashtags, mentions = _extract_tags([seed, *responses, *author_posts])
    regions = Counter(row.author_location for row in responses if row.author_location)

    baseline = [row for row in author_posts if row.record_key != seed.record_key]
    baseline_likes = [_engagement_value(row, "likes") for row in baseline]
    baseline_comments = [_engagement_value(row, "replies") for row in baseline]
    baseline_reposts = [_engagement_value(row, "reposts") for row in baseline]

    def comparison(seed_value: int, values: list[int]) -> dict[str, Any]:
        if not values:
            return {"sample": 0, "median": None, "seed_to_median_ratio": None, "percentile": None}
        med = float(median(values))
        ratio = round(seed_value / med, 3) if med > 0 else None
        percentile = round(sum(value <= seed_value for value in values) / len(values), 3)
        return {"sample": len(values), "median": med, "seed_to_median_ratio": ratio, "percentile": percentile}

    return {
        "generated_at": utc_iso(),
        "interpretation_guardrail": (
            "Retrieved comments/reposts are a public surface sample, not the complete audience and not a sentiment poll. "
            "Proximity, engagement, repetition, or popularity do not by themselves establish influence or persuasion."
        ),
        "seed": {
            "record_key": seed.record_key,
            "url": seed.canonical_url,
            "author": seed.author_name,
            "author_id": seed.author_handle,
            "published_at": seed.published_at,
            "text": seed.original_text,
            "reported_engagement": {
                "likes": reported_likes,
                "comments": reported_comments,
                "reposts": reported_reposts,
            },
        },
        "retrieval": {
            "comments_retrieved": len(comments),
            "reposts_retrieved": len(reposts),
            "comment_retrieved_to_reported_ratio": _safe_ratio(len(comments), reported_comments),
            "repost_retrieved_to_reported_ratio": _safe_ratio(len(reposts), reported_reposts),
            "unique_public_responders": len({row.author_handle or row.author_name for row in responses if row.author_handle or row.author_name}),
            "surface_status": surface_status or {},
        },
        "response_context": {
            "top_regions": [{"region": region, "count": count} for region, count in regions.most_common(12)],
            "top_public_responses": _top_responses(responses),
        },
        "content_signals": {
            "hashtags": hashtags,
            "mentions": mentions,
        },
        "author_context": {
            "timeline_posts_retrieved": len(author_posts),
            "seed_vs_recent_likes": comparison(reported_likes, baseline_likes),
            "seed_vs_recent_comments": comparison(reported_comments, baseline_comments),
            "seed_vs_recent_reposts": comparison(reported_reposts, baseline_reposts),
        },
    }


def investigate_weibo_seed(
    seed: str,
    *,
    max_comments: int = 100,
    comment_pages: int = 5,
    max_reposts: int = 100,
    repost_pages: int = 5,
    author_posts: int = 40,
    author_pages: int = 2,
    cookie: str = "",
    session: requests.Session | None = None,
) -> WeiboInvestigation:
    session = session or create_weibo_session(cookie)
    seed_record, seed_mode = fetch_weibo_seed_status(seed, cookie=cookie, session=session)
    surface_status: dict[str, dict[str, str]] = {
        "seed": {"status": "ok", "mode": seed_mode}
    }

    def capture(name: str, fn):
        try:
            rows = fn()
            surface_status[name] = {"status": "ok", "records": str(len(rows))}
            return rows
        except WeiboAccessError as exc:
            surface_status[name] = {"status": "access_limited", "error": str(exc)}
            return []
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            surface_status[name] = {"status": "unavailable", "error": str(exc)}
            return []

    comments = capture(
        "comments",
        lambda: collect_weibo_comments(
            seed_record.native_id,
            max_comments=max_comments,
            max_pages=comment_pages,
            cookie=cookie,
            session=session,
        ),
    )
    reposts = capture(
        "reposts",
        lambda: collect_weibo_reposts(
            seed_record.native_id,
            max_reposts=max_reposts,
            max_pages=repost_pages,
            cookie=cookie,
            session=session,
        ),
    )
    timeline = capture(
        "author_timeline",
        lambda: collect_weibo_user_timeline(
            seed_record.author_handle,
            max_posts=author_posts,
            max_pages=author_pages,
            cookie=cookie,
            session=session,
        ),
    ) if seed_record.author_handle else []

    original = None
    original_id = normalize_whitespace((seed_record.raw_stats or {}).get("retweeted_status_id", ""))
    if original_id:
        try:
            original, original_mode = fetch_weibo_seed_status(original_id, cookie=cookie, session=session)
            surface_status["original_status"] = {"status": "ok", "mode": original_mode}
        except (WeiboAccessError, requests.RequestException, RuntimeError, ValueError) as exc:
            surface_status["original_status"] = {"status": "unavailable", "error": str(exc)}

    insights = build_weibo_insights(
        seed_record,
        comments,
        reposts,
        timeline,
        surface_status=surface_status,
    )
    return WeiboInvestigation(
        seed=seed_record,
        comments=comments,
        reposts=reposts,
        author_posts=timeline,
        original=original,
        surface_status=surface_status,
        insights=insights,
    )


def render_weibo_brief(investigation: WeiboInvestigation) -> str:
    insight = investigation.insights
    seed = insight["seed"]
    retrieval = insight["retrieval"]
    author = insight["author_context"]
    lines = [
        "# Weibo Seed Investigation",
        "",
        f"**Author:** {seed.get('author') or seed.get('author_id') or 'Unknown'}  ",
        f"**Post:** {seed.get('url') or investigation.seed.canonical_url}  ",
        f"**Published:** {seed.get('published_at') or 'Unknown'}",
        "",
        "## BLUF",
        "",
        (
            f"The public post reports {seed['reported_engagement']['likes']} likes, "
            f"{seed['reported_engagement']['comments']} comments, and {seed['reported_engagement']['reposts']} reposts. "
            f"SUGAR retrieved {retrieval['comments_retrieved']} public comments and "
            f"{retrieval['reposts_retrieved']} public reposts, plus "
            f"{author['timeline_posts_retrieved']} recent public posts from the same account for context."
        ),
        "",
        "The response set is an observable public sample, not a complete audience or sentiment measure.",
        "",
        "## Seed text",
        "",
        seed.get("text", ""),
        "",
        "## Retrieval coverage",
        "",
        f"- Comments: {retrieval['comments_retrieved']} retrieved / {seed['reported_engagement']['comments']} reported.",
        f"- Reposts: {retrieval['reposts_retrieved']} retrieved / {seed['reported_engagement']['reposts']} reported.",
        f"- Unique visible responders: {retrieval['unique_public_responders']}.",
        "",
        "## Account context",
        "",
        f"- Recent timeline sample: {author['timeline_posts_retrieved']} posts.",
        f"- Like percentile within retrieved recent baseline: {author['seed_vs_recent_likes']['percentile']}.",
        f"- Comment percentile within retrieved recent baseline: {author['seed_vs_recent_comments']['percentile']}.",
        f"- Repost percentile within retrieved recent baseline: {author['seed_vs_recent_reposts']['percentile']}.",
        "",
        "## Observable content signals",
        "",
    ]
    for item in insight["content_signals"]["hashtags"][:10]:
        lines.append(f"- Hashtag: #{item['value']}# ({item['count']} occurrences in retrieved corpus)")
    for item in insight["content_signals"]["mentions"][:10]:
        lines.append(f"- Mention: @{item['value']} ({item['count']} occurrences in retrieved corpus)")
    if not insight["content_signals"]["hashtags"] and not insight["content_signals"]["mentions"]:
        lines.append("- No repeated hashtags or @mentions were extracted from the retrieved corpus.")

    lines.extend(["", "## Top visible responses", ""])
    for row in insight["response_context"]["top_public_responses"]:
        text = normalize_whitespace(row.get("text", ""))
        lines.append(
            f"- {row.get('type', 'response')} by {row.get('author') or 'unknown'} "
            f"({row.get('likes', 0)} likes): {text[:220]}"
        )
    if not insight["response_context"]["top_public_responses"]:
        lines.append("- No public response records were retrievable from the tested surfaces.")

    lines.extend([
        "",
        "## Methodological note",
        "",
        insight["interpretation_guardrail"],
        "",
    ])
    return "\n".join(lines)


def save_weibo_investigation(
    investigation: WeiboInvestigation,
    output_directory: str | Path,
    *,
    name: str = "weibo_investigation",
) -> list[str]:
    out = Path(output_directory).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    stem = out / name
    csv_path = stem.with_suffix(".csv")
    save_records(
        investigation.records,
        csv_path,
        metadata={
            "operation": "weibo_investigation",
            "seed_record_key": investigation.seed.record_key,
            "surface_status": investigation.surface_status,
        },
    )
    insights_path = out / f"{name}.insights.json"
    insights_path.write_text(json.dumps(investigation.insights, ensure_ascii=False, indent=2), encoding="utf-8")
    brief_path = out / f"{name}.brief.md"
    brief_path.write_text(render_weibo_brief(investigation), encoding="utf-8")
    return [
        str(csv_path),
        str(csv_path.with_suffix(".xlsx")),
        str(csv_path.with_suffix(".metadata.json")),
        str(insights_path),
        str(brief_path),
    ]
