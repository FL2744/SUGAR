from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from .models import PostRecord

USER_AGENT = "SUGAR/1.2 (+public-source research; Virginia Tech Diplomacy Lab)"
REQUEST_TIMEOUT_SECONDS = 20

PLATFORM_HOSTS: dict[str, set[str]] = {
    "wechat": {"mp.weixin.qq.com", "weixin.qq.com"},
    "zhihu": {"www.zhihu.com", "zhihu.com", "zhuanlan.zhihu.com"},
    "douyin": {
        "www.douyin.com",
        "douyin.com",
        "v.douyin.com",
        "www.iesdouyin.com",
        "iesdouyin.com",
    },
}

ACCESS_GATE_MARKERS = (
    "verify you are human",
    "captcha",
    "访问过于频繁",
    "环境异常",
    "安全验证",
)


def _allowed_host(platform: str, host: str) -> bool:
    host = host.casefold().split(":", 1)[0].rstrip(".")
    return host in PLATFORM_HOSTS[platform]


def _validate_url(platform: str, raw_url: str) -> str:
    value = str(raw_url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{platform} public-item import requires a full http(s) URL.")
    if not _allowed_host(platform, parsed.hostname):
        allowed = ", ".join(sorted(PLATFORM_HOSTS[platform]))
        raise ValueError(f"URL host {parsed.hostname!r} is not an allowed {platform} public host ({allowed}).")
    return value


def _meta(soup: BeautifulSoup, *keys: tuple[str, str]) -> str:
    for attribute, value in keys:
        tag = soup.find("meta", attrs={attribute: value})
        if tag and tag.get("content"):
            return str(tag.get("content")).strip()
    return ""


def _text(node: Any) -> str:
    if node is None:
        return ""
    return "\n".join(part.strip() for part in node.stripped_strings if part.strip()).strip()


def _iso_from_epoch(value: str | int | float | None) -> str:
    if value in (None, ""):
        return ""
    try:
        stamp = int(float(value))
    except (TypeError, ValueError):
        return str(value).strip()
    if stamp > 10_000_000_000:
        stamp //= 1000
    try:
        return datetime.fromtimestamp(stamp, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return ""


def _stable_fallback_id(platform: str, canonical_url: str) -> str:
    digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:20]
    return f"url-{digest}"


def _wechat_identity(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    parts = [
        (query.get("__biz") or [""])[0],
        (query.get("mid") or [""])[0],
        (query.get("idx") or [""])[0],
        (query.get("sn") or [""])[0],
    ]
    joined = ":".join(part for part in parts if part)
    return joined or _stable_fallback_id("wechat", url)


def _zhihu_identity(url: str) -> str:
    for pattern, prefix in (
        (r"/answer/(\d+)", "answer"),
        (r"/question/(\d+)", "question"),
        (r"/p/(\d+)", "article"),
    ):
        match = re.search(pattern, url)
        if match:
            return f"{prefix}-{match.group(1)}"
    return _stable_fallback_id("zhihu", url)


def _douyin_identity(url: str) -> str:
    parsed = urlparse(url)
    for candidate in (url, parsed.path):
        match = re.search(r"/(?:video|note)/(\d+)", candidate)
        if match:
            return match.group(1)
    query = parse_qs(parsed.query)
    for key in ("modal_id", "aweme_id", "item_id"):
        value = (query.get(key) or [""])[0]
        if value:
            return value
    return _stable_fallback_id("douyin", url)


def _published_from_html(platform: str, soup: BeautifulSoup, html: str) -> str:
    published = _meta(
        soup,
        ("property", "article:published_time"),
        ("name", "article:published_time"),
        ("name", "publishdate"),
        ("name", "date"),
    )
    if published:
        return published
    patterns = []
    if platform == "wechat":
        patterns = [r"\bct\s*=\s*[\"'](\d{9,13})[\"']", r"\bpublish_time\s*[:=]\s*[\"']?(\d{9,13})"]
    elif platform == "douyin":
        patterns = [r"\bcreate_time\s*[\"']?\s*[:=]\s*[\"']?(\d{9,13})"]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return _iso_from_epoch(match.group(1))
    return ""


def _extract_public_page(platform: str, raw_url: str, *, session: requests.Session | None = None) -> PostRecord:
    url = _validate_url(platform, raw_url)
    client = session or requests.Session()
    response = client.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=REQUEST_TIMEOUT_SECONDS,
        allow_redirects=True,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"{platform} returned HTTP {response.status_code} for this public URL.")
    final_url = str(response.url or url)
    final_host = urlparse(final_url).hostname or ""
    if not _allowed_host(platform, final_host):
        raise RuntimeError(
            f"{platform} public URL redirected to an unexpected host ({final_host or 'unknown'}); refusing to follow it as evidence."
        )
    content_type = response.headers.get("Content-Type", "")
    if content_type and "html" not in content_type.casefold():
        raise RuntimeError(f"{platform} public URL returned unsupported content type {content_type!r}.")

    html = response.text
    lowered = html.casefold()
    marker = next((value for value in ACCESS_GATE_MARKERS if value.casefold() in lowered), None)
    if marker:
        raise RuntimeError(
            f"{platform} did not expose the requested item as an ordinary public page (access/verification marker: {marker})."
        )

    soup = BeautifulSoup(html, "html.parser")
    canonical_tag = soup.find("link", rel="canonical")
    canonical_url = str(canonical_tag.get("href")).strip() if canonical_tag and canonical_tag.get("href") else final_url
    canonical_host = urlparse(canonical_url).hostname or final_host
    if not _allowed_host(platform, canonical_host):
        canonical_url = final_url

    title = _meta(soup, ("property", "og:title"), ("name", "twitter:title"))
    if not title and soup.title:
        title = _text(soup.title)
    description = _meta(
        soup,
        ("property", "og:description"),
        ("name", "description"),
        ("name", "twitter:description"),
    )
    author = _meta(soup, ("name", "author"), ("property", "article:author"))

    if platform == "wechat":
        article = soup.select_one("#js_content")
        original_text = _text(article) or description or title
        author = _text(soup.select_one("#js_name")) or author
        native_id = _wechat_identity(canonical_url)
        content_type_name = "article"
    elif platform == "zhihu":
        article = soup.select_one("article") or soup.select_one(".RichContent-inner")
        original_text = _text(article) or description or title
        native_id = _zhihu_identity(canonical_url)
        content_type_name = "answer" if "/answer/" in canonical_url else "article"
    else:
        original_text = description or title
        native_id = _douyin_identity(canonical_url)
        content_type_name = "video"

    if not original_text.strip():
        raise RuntimeError(
            f"{platform} page loaded but did not expose enough public text/metadata to create a defensible research record."
        )

    published_at = _published_from_html(platform, soup, html)
    return PostRecord(
        platform=platform,
        native_id=native_id,
        canonical_url=canonical_url,
        query=raw_url,
        query_matches=[raw_url],
        content_type=content_type_name,
        source_mode=f"{platform}_public_url",
        source_host=final_host,
        source_url=raw_url,
        published_at=published_at,
        author_name=author,
        original_text=original_text,
        raw_stats={
            "page_title": title,
            "retrieved_url": final_url,
            "access_mode": "anonymous_public_url",
        },
    )


def fetch_wechat_article(url: str, *, session: requests.Session | None = None) -> PostRecord:
    return _extract_public_page("wechat", url, session=session)


def fetch_zhihu_public_item(url: str, *, session: requests.Session | None = None) -> PostRecord:
    return _extract_public_page("zhihu", url, session=session)


def fetch_douyin_public_item(url: str, *, session: requests.Session | None = None) -> PostRecord:
    return _extract_public_page("douyin", url, session=session)
