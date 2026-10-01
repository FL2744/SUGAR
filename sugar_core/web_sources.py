"""Read public web pages the way a careful analyst would, and see how a page has changed over time.

Most of what an institution says about itself is on its own website and its host's website, not on social
media. This module fetches pages you name (and, one step deep, the news/event pages they link to on the same
site), extracts readable text and a publication date, and returns ordinary ``PostRecord`` rows so
de-duplication, translation, change detection, provenance and review work exactly as they do for any source.

It is deliberately polite and safe:

* ``robots.txt`` is honoured, one request per second per site, and a descriptive User-Agent identifies SUGAR.
* Only public http(s) addresses are fetched. Addresses that resolve to this computer, a private network or a
  link-local range are refused, and every redirect is checked again, so a project member cannot use a seed
  address to reach internal services.

``wayback_history`` asks the Internet Archive which captures of a page exist and how they changed, which is
how a closure, a rename or a quiet disappearance shows up.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib import robotparser
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .models import PostRecord
from .open_sources import USER_AGENT, _iso
from .utils import in_inclusive_date_range, normalize_whitespace

_TIMEOUT = 30
_MAX_BYTES = 2_000_000
_MAX_TEXT = 8000
_HOST_LOCK = threading.Lock()
_HOST_LAST: dict[str, float] = {}
_ROBOTS: dict[str, robotparser.RobotFileParser | None] = {}

# Link text or paths that usually lead to dated, readable updates on an institution's site.
_LISTING_HINTS = re.compile(r"news|event|activit|program|notice|announce|press|update|blog|story|stories|calendar|class|workshop|"
                            r"新闻|活动|动态|公告|通知|资讯|课程|讲座", re.I)


class UnsafeAddress(ValueError):
    pass


def check_public_address(url: str) -> str:
    """Return the url if it is a public http(s) address; raise ``UnsafeAddress`` otherwise."""
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeAddress("Only full http(s) addresses can be read.")
    host = parsed.hostname
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeAddress(f"Could not look up {host}.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast or address.is_unspecified:
            raise UnsafeAddress(f"{host} is not a public address, so it is not read.")
    return url


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5", "Accept-Language": "en,*;q=0.5"})
    return session


def _wait_for_host(host: str, delay: float) -> None:
    with _HOST_LOCK:
        wait = delay - (time.monotonic() - _HOST_LAST.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _HOST_LAST[host] = time.monotonic()


def allowed_by_robots(session: requests.Session, url: str, *, check: bool = True) -> bool:
    if not check:
        return True
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in _ROBOTS:
        parser = robotparser.RobotFileParser()
        try:
            check_public_address(origin + "/robots.txt")
            response = session.get(origin + "/robots.txt", timeout=_TIMEOUT)
            if response.status_code in {401, 403}:
                parser.disallow_all = True
            elif response.status_code >= 400:
                parser.allow_all = True
            else:
                parser.parse(response.text.splitlines())
            _ROBOTS[origin] = parser
        except (requests.RequestException, UnsafeAddress):
            _ROBOTS[origin] = None            # unreachable robots.txt: treat as no restrictions, the page fetch will fail on its own
    parser = _ROBOTS[origin]
    return True if parser is None else parser.can_fetch(USER_AGENT, url)


def fetch(session: requests.Session, url: str, *, delay: float = 1.0, robots: bool = True) -> tuple[str, bytes, requests.Response]:
    """GET a public page: checks robots, spaces requests per host, follows at most five redirects, caps the size."""
    current = url
    for _ in range(6):
        check_public_address(current)
        if not allowed_by_robots(session, current, check=robots):
            raise PermissionError(f"{urlparse(current).netloc} asks automated readers not to fetch {urlparse(current).path or '/'} (robots.txt).")
        _wait_for_host(urlparse(current).netloc, delay)
        response = session.get(current, timeout=_TIMEOUT, allow_redirects=False, stream=True)
        if response.status_code in {301, 302, 303, 307, 308} and response.headers.get("Location"):
            current = urljoin(current, response.headers["Location"])
            continue
        if response.status_code == 429:
            raise RuntimeError(f"{urlparse(current).netloc} rate limit reached (429); retry after {response.headers.get('Retry-After', 'a short wait')}.")
        response.raise_for_status()
        content = b""
        for chunk in response.iter_content(65536):
            content += chunk
            if len(content) > _MAX_BYTES:
                break
        return current, content, response
    raise RuntimeError("Too many redirects.")


# ------------------------------------------------------------------------------------------ extraction
def _meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
    return ""


def extract_page(html: bytes | str, url: str = "") -> dict[str, Any]:
    """Readable text, title, language, date and same-site links from an HTML page."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template", "svg", "iframe", "form"]):
        tag.decompose()
    title = normalize_whitespace((soup.title.string if soup.title and soup.title.string else "") or _meta(soup, "og:title"))
    published = _meta(soup, "article:published_time", "og:published_time", "datePublished", "date", "DC.date.issued", "pubdate")
    if not published:
        time_tag = soup.find("time", attrs={"datetime": True})
        published = str(time_tag["datetime"]) if time_tag else ""
    if not published:
        import json
        for script in BeautifulSoup(html, "lxml").find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(script.string or "")
            except ValueError:
                continue
            for node in data if isinstance(data, list) else [data]:
                if isinstance(node, dict) and node.get("datePublished"):
                    published = str(node["datePublished"])
                    break
            if published:
                break
    links: list[tuple[str, str]] = []
    base_host = urlparse(url).netloc.lower()
    for a in soup.find_all("a", href=True):
        target = urldefrag(urljoin(url, str(a["href"])))[0]
        parsed = urlparse(target)
        if parsed.scheme in {"http", "https"} and parsed.netloc.lower() == base_host:
            links.append((target, normalize_whitespace(a.get_text(" "))))
    for tag in soup(["nav", "footer", "header", "aside"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = normalize_whitespace(main.get_text(" "))
    lang = (soup.html.get("lang") if soup.html else "") or _meta(soup, "og:locale", "language")
    return {"title": title, "text": text, "published": _iso(published) if published else "", "language": str(lang or "").split("-")[0].split("_")[0].lower()[:3],
            "links": list(OrderedDict.fromkeys(links))}


def _terms_match(words: list[str], text: str) -> bool:
    low = text.casefold()
    return not words or all(w in low for w in words)


def collect_web(*, search_terms: Iterable[str], seeds: Iterable[str], since: str | None = None, until: str | None = None,
                max_posts_per_query: int = 25, follow: bool = True, delay: float = 1.0, robots: bool = True,
                session: requests.Session | None = None, **_: Any) -> list[PostRecord]:
    """Pages from the sites you named whose text mentions the query (every word, any order)."""
    urls = [str(s).strip() for s in seeds if str(s).strip().lower().startswith(("http://", "https://"))]
    if not urls:
        raise ValueError("Websites need at least one address. Add the sites to read under Research → Your own sources.")
    session = session or _session()
    pages: dict[str, dict[str, Any]] = {}
    failures: list[str] = []

    def read(url: str) -> dict[str, Any] | None:
        if url in pages:
            return pages[url]
        try:
            final, content, response = fetch(session, url, delay=delay, robots=robots)
        except (requests.RequestException, UnsafeAddress, PermissionError, RuntimeError) as exc:
            failures.append(f"{urlparse(url).netloc}: {exc}")
            return None
        page = extract_page(content, final)
        page.update({"url": final, "etag": response.headers.get("ETag", ""), "last_modified": response.headers.get("Last-Modified", ""),
                     "status": response.status_code, "hash": hashlib.sha256(page["text"].encode("utf-8")).hexdigest()[:16]})
        pages[url] = page
        return page

    seed_pages = [read(u) for u in urls]
    if not any(seed_pages):
        raise RuntimeError("None of the websites could be read. " + "; ".join(failures)[:300])
    if follow:
        budget = 12
        for seed, page in zip(urls, seed_pages):
            if not page:
                continue
            ranked = sorted(page["links"], key=lambda l: (0 if _LISTING_HINTS.search(l[1] + " " + urlparse(l[0]).path) else 1))
            for target, _text in ranked:
                if budget <= 0:
                    break
                if target != seed and target not in pages and _LISTING_HINTS.search(_text + " " + urlparse(target).path):
                    read(target)
                    budget -= 1
    records: OrderedDict[tuple[str, str], PostRecord] = OrderedDict()
    for query in search_terms:
        words = [w for w in re.findall(r"[^\W_]+", query.casefold(), re.UNICODE) if w]
        matched = 0
        for url, page in pages.items():
            if not page or not page["text"] or not _terms_match(words, f"{page['title']} {page['text']}"):
                continue
            published = page["published"]
            if published and not in_inclusive_date_range(published, since, until):
                continue
            key = ("web", page["url"])
            record = PostRecord(
                platform="web", native_id=page["url"], canonical_url=page["url"], query=query, query_matches=[query], content_type="web_page",
                source_mode="web_fetch", source_host=urlparse(page["url"]).netloc, source_url=page["url"], published_at=published,
                author_name=urlparse(page["url"]).netloc, platform_language=page["language"],
                original_text=normalize_whitespace(f"{page['title']}. {page['text']}")[:_MAX_TEXT],
                raw_stats={"content_hash": page["hash"], "http_status": page["status"], "etag": page["etag"], "last_modified": page["last_modified"],
                           "date_meaning": "published" if published else "no date found on the page"})
            if key in records:
                records[key].add_query_match(query)
            else:
                record.add_query_match(query)
                records[key] = record
            matched += 1
            if matched >= max_posts_per_query:
                break
    return list(records.values())


# ------------------------------------------------------------------------------------------ Wayback
def wayback_history(url: str, *, session: requests.Session | None = None, limit: int = 200) -> dict[str, Any]:
    """Captures of a page held by the Internet Archive and what they suggest about its life.

    Returns the snapshots (oldest first, one per distinct content), and signals such as 'the last good capture was on X and
    every later capture is an error or a redirect'. Signals are leads to check, not findings.
    """
    session = session or _session()
    response = session.get("https://web.archive.org/cdx/search/cdx", timeout=_TIMEOUT,
                           params={"url": url, "output": "json", "fl": "timestamp,original,statuscode,mimetype,digest", "limit": limit, "filter": "mimetype:text/html"})
    if response.status_code == 429:
        raise RuntimeError("web.archive.org rate limit reached (429); retry after a short wait.")
    response.raise_for_status()
    rows = response.json()
    header, data = (rows[0], rows[1:]) if rows else ([], [])
    snapshots = []
    for row in data:
        record = dict(zip(header, row))
        stamp = str(record.get("timestamp", ""))
        try:
            when = datetime.strptime(stamp[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        snapshots.append({"timestamp": stamp, "captured_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "status": str(record.get("statuscode", "")),
                          "digest": str(record.get("digest", "")), "archive_url": f"https://web.archive.org/web/{stamp}/{record.get('original', url)}"})
    snapshots.sort(key=lambda s: s["timestamp"])
    ok = [s for s in snapshots if s["status"].startswith("2")]
    signals: list[str] = []
    if ok:
        last_ok = ok[-1]
        later = [s for s in snapshots if s["timestamp"] > last_ok["timestamp"]]
        if later and all(not s["status"].startswith("2") for s in later):
            kinds = sorted({s["status"] for s in later})
            signals.append(f"The last good capture is from {last_ok['captured_at'][:10]}; {len(later)} later capture(s) returned {', '.join(kinds)}. The page may have been removed, moved or redirected.")
        digests = {s["digest"] for s in ok}
        if len(digests) > 1:
            signals.append(f"The page's content changed {len(digests) - 1} time(s) between {ok[0]['captured_at'][:10]} and {last_ok['captured_at'][:10]}.")
    if not snapshots:
        signals.append("The Internet Archive holds no captures of this address.")
    return {"url": url, "snapshots": snapshots[-60:], "total": len(snapshots), "first_seen": snapshots[0]["captured_at"] if snapshots else "",
            "last_ok": ok[-1]["captured_at"] if ok else "", "signals": signals}
