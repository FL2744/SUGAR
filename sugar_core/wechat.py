from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .models import PostRecord
from .utils import normalize_whitespace

WECHAT_PUBLIC_HOST = "mp.weixin.qq.com"


class WeChatAccessError(RuntimeError):
    """Raised when a public WeChat article is blocked by an access-control surface."""


def create_wechat_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "SUGAR/1.2 research-client (+Virginia Tech Diplomacy Lab; public WeChat article client)",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
    )
    return session


def _validated_public_url(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        raise ValueError("Enter a public WeChat Official Account article URL.")
    parsed = urlsplit(value)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme.casefold() != "https" or host != WECHAT_PUBLIC_HOST:
        raise ValueError("WeChat ingestion accepts only public https://mp.weixin.qq.com article URLs.")
    if parsed.username or parsed.password:
        raise ValueError("WeChat article URLs must not contain embedded credentials.")
    return urlunsplit(("https", WECHAT_PUBLIC_HOST, parsed.path or "/", parsed.query, ""))


def _meta(soup: BeautifulSoup, *, property_name: str = "", name: str = "") -> str:
    attrs: dict[str, str] = {}
    if property_name:
        attrs["property"] = property_name
    if name:
        attrs["name"] = name
    tag = soup.find("meta", attrs=attrs)
    return normalize_whitespace(tag.get("content", "")) if tag else ""


def _selector_text(soup: BeautifulSoup, selector: str) -> str:
    node = soup.select_one(selector)
    return normalize_whitespace(node.get_text(" ", strip=True)) if node else ""


def _unix_iso(value: str) -> str:
    try:
        stamp = int(str(value).strip())
        if stamp <= 0:
            return ""
        return datetime.fromtimestamp(stamp, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _published_at(soup: BeautifulSoup, html: str) -> tuple[str, str]:
    raw = (
        _meta(soup, property_name="article:published_time")
        or _meta(soup, name="publishdate")
        or _selector_text(soup, "#publish_time")
    )
    if raw:
        cleaned = raw.replace("年", "-").replace("月", "-").replace("日", " ").strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                local = datetime.strptime(cleaned, fmt).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
                return local.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), raw
            except ValueError:
                pass
    for pattern in (
        r"\b(?:ct|create_time|createTime)\s*[:=]\s*[\"']?(\d{10})",
        r"\bpublish_time\s*[:=]\s*[\"']?(\d{10})",
    ):
        match = re.search(pattern, html)
        if match:
            parsed = _unix_iso(match.group(1))
            if parsed:
                return parsed, match.group(1)
    return "", raw


def _article_identity(url: str) -> tuple[str, dict[str, str]]:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query, keep_blank_values=False)
    parts = {
        key: normalize_whitespace((query.get(key) or [""])[0])
        for key in ("__biz", "mid", "idx", "sn")
    }
    identity = ":".join(parts[key] for key in ("__biz", "mid", "idx", "sn") if parts[key])
    if not identity and parsed.path.startswith("/s/"):
        identity = normalize_whitespace(parsed.path.split("/s/", 1)[1].split("/", 1)[0])
    if not identity:
        identity = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return identity, parts


def _handle_http(response: requests.Response) -> None:
    if response.status_code in {401, 403}:
        raise WeChatAccessError(
            f"WeChat denied this public article request (HTTP {response.status_code}). "
            "SUGAR will not bypass login or access controls."
        )
    if response.status_code == 429:
        raise WeChatAccessError("WeChat rate-limited this public article request (HTTP 429). Stop and retry later.")
    response.raise_for_status()


def _get_public_article(session: requests.Session, requested_url: str) -> tuple[requests.Response, str]:
    current = requested_url
    for _ in range(6):
        response = session.get(current, timeout=30, allow_redirects=False)
        _handle_http(response)
        if response.status_code in {301, 302, 303, 307, 308}:
            location = str(response.headers.get("Location") or "").strip()
            if not location:
                raise RuntimeError("WeChat returned a redirect without a destination.")
            # Validate each redirect before requesting it so a public article URL
            # cannot turn the importer into a generic cross-origin HTTP client.
            current = _validated_public_url(urljoin(current, location))
            continue
        final_url = _validated_public_url(response.url or current)
        return response, final_url
    raise RuntimeError("WeChat public article retrieval exceeded the redirect limit.")


def fetch_wechat_article(
    article_url: str,
    *,
    query: str = "",
    session: requests.Session | None = None,
) -> PostRecord:
    """Ingest one ordinary public WeChat Official Account article.

    This intentionally does not perform keyword discovery, synthesize login state,
    solve challenges, or emulate private WeChat client surfaces.
    """

    requested_url = _validated_public_url(article_url)
    session = session or create_wechat_session()
    response, final_url = _get_public_article(session, requested_url)
    html = str(response.text or "")
    soup = BeautifulSoup(html, "html.parser")

    title = (
        _meta(soup, property_name="og:title")
        or _selector_text(soup, "#activity-name")
        or _selector_text(soup, "h1.rich_media_title")
    )
    content_node = soup.select_one("#js_content") or soup.select_one(".rich_media_content")
    body = normalize_whitespace(content_node.get_text(" ", strip=True)) if content_node else ""

    if not title or not body:
        visible = normalize_whitespace(soup.get_text(" ", strip=True))
        access_markers = (
            "环境异常",
            "访问过于频繁",
            "安全验证",
            "验证码",
            "请在微信客户端打开链接",
            "该内容已被发布者删除",
            "内容已被删除",
        )
        if any(marker in visible for marker in access_markers):
            raise WeChatAccessError(
                "WeChat returned an access-control or unavailable-content page instead of the public article. "
                "SUGAR will not attempt to bypass it."
            )
        raise RuntimeError(
            "WeChat did not return a recognizable public Official Account article. "
            "The page may require access state that SUGAR does not provide."
        )

    author = (
        _meta(soup, name="author")
        or _meta(soup, property_name="article:author")
        or _selector_text(soup, "#js_name")
        or _selector_text(soup, ".rich_media_meta_nickname")
    )
    published, published_raw = _published_at(soup, html)
    native_id, identity = _article_identity(final_url)
    original_text = normalize_whitespace(f"{title} — {body}")
    query = normalize_whitespace(query)

    return PostRecord(
        platform="wechat",
        native_id=native_id,
        canonical_url=final_url,
        query=query,
        query_matches=[query] if query else [],
        content_type="article",
        source_mode="wechat_public_article",
        source_host=WECHAT_PUBLIC_HOST,
        source_url=final_url,
        published_at=published,
        author_handle=identity.get("__biz") or author,
        author_name=author,
        original_text=original_text,
        engagement={},
        raw_stats={
            "article_title": title,
            "published_at_raw": published_raw,
            "identity": identity,
            "access_mode": "anonymous_public",
        },
    )
