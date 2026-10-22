"""Read public web pages the way a careful analyst would, and see how a page has changed over time.

Most of what an institution says about itself is on its own website and its host's website, not on social
media. This module fetches pages you name and adaptively selects same-site links using query relevance and
feedback from the pages it reads. It extracts readable text and a publication date, and returns ordinary ``PostRecord`` rows so
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
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib import robotparser
from urllib.parse import parse_qsl, urlencode, urldefrag, urljoin, urlparse, urlunparse

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
        try:
            if response.status_code in {301, 302, 303, 307, 308} and response.headers.get("Location"):
                current = urljoin(current, response.headers["Location"])
                continue
            if response.status_code == 429:
                error = RuntimeError(f"{urlparse(current).netloc} rate limit reached (429); retry after {response.headers.get('Retry-After', 'a short wait')}.")
                error.response = response
                raise error
            response.raise_for_status()
            content = b""
            for chunk in response.iter_content(65536):
                content += chunk
                if len(content) > _MAX_BYTES:
                    break
            return current, content[:_MAX_BYTES], response
        finally:
            getattr(response, "close", lambda: None)()
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
    event_dates = []
    cancelled_events = []
    import json
    def structured_events(node):
        if isinstance(node, list):
            for value in node:
                structured_events(value)
        elif isinstance(node, dict):
            kinds = node.get("@type", [])
            kinds = kinds if isinstance(kinds, list) else [kinds]
            if any(str(k).endswith("Event") for k in kinds) and node.get("startDate"):
                event_dates.append(str(node["startDate"])[:40])
                if str(node.get("eventStatus", "")).endswith(("EventCancelled", "EventPostponed")):
                    cancelled_events.append(str(node["startDate"])[:40])
            for value in node.values():
                if isinstance(value, (list, dict)):
                    structured_events(value)
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            structured_events(json.loads(script.string or ""))
        except (ValueError, RecursionError):
            continue
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
            "links": list(OrderedDict.fromkeys(links)), "event_dates": list(dict.fromkeys(event_dates))[:100], "cancelled_events": list(dict.fromkeys(cancelled_events))[:100]}


def _terms_match(words: list[str], text: str) -> bool:
    low = text.casefold()
    return not words or all(w in low for w in words)


@dataclass
class WebCrawlState:
    """One run's fetched-page cache and hard network budget; never persisted as settings."""
    max_fetches: int = 240
    pages: dict[str, Any] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)
    fetched: int = 0


_STOPWORDS = set("a an the in on at of for and or to by with from is are about search find latest news website site".split())
_SKIP_PATH = re.compile(r"(?:\.(?:jpg|jpeg|png|gif|webp|svg|mp4|mp3|zip|pdf|docx?|xlsx?|css|js)$)|(?:/(?:login|logout|signin|cart|wp-admin)(?:/|$))", re.I)


def _crawl_url(url: str) -> str:
    parsed = urlparse(urldefrag(url)[0])
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if not k.casefold().startswith("utm_") and k.casefold() not in {"fbclid", "gclid"}]
    return urlunparse(parsed._replace(query=urlencode(sorted(query))))


def _query_words(query: str) -> list[str]:
    return [w for w in re.findall(r"[^\W_]+", query.casefold(), re.UNICODE) if w not in _STOPWORDS]


def collect_web(*, search_terms: Iterable[str], seeds: Iterable[str], since: str | None = None, until: str | None = None,
                max_posts_per_query: int = 25, follow: bool = True, delay: float = 1.0, robots: bool = True,
                session: requests.Session | None = None, state: WebCrawlState | None = None, on_event: Any = None,
                max_pages_per_query: int = 1, page_budget: int | None = None, max_depth: int = 3, patience: int = 6, checkpoint: Any = None, **_: Any) -> list[PostRecord]:
    """Observe → rank links → read → reassess until a relevance or hard budget stop.

    All decisions are local. Seed origins bound discovery, robots and host pacing
    still apply, and every kept page records its path and selection reason.
    """
    urls = list(dict.fromkeys(_crawl_url(str(s).strip()) for s in seeds if str(s).strip().lower().startswith(("http://", "https://"))))[:50]
    if not urls:
        raise ValueError("Websites need at least one address. Add the sites to read under Research → Your own sources.")
    session = session or _session()
    state = state if state is not None else WebCrawlState()
    budget = max(1, min(200, page_budget if page_budget is not None else max(24, max_pages_per_query * 4)))
    records: OrderedDict[tuple[str, str], PostRecord] = OrderedDict()

    def emit(kind: str, **data: Any) -> None:
        if on_event:
            on_event(kind, **data)

    def read(url: str) -> tuple[dict[str, Any] | None, bool]:
        if url in state.pages:
            return state.pages[url], True
        if url in state.failures or state.fetched >= state.max_fetches:
            return None, True
        state.fetched += 1
        try:
            final, content, response = fetch(session, url, delay=delay, robots=robots)
        except (requests.RequestException, UnsafeAddress, PermissionError, RuntimeError) as exc:
            if getattr(getattr(exc, "response", None), "status_code", None) == 429:
                exc.partial_records = list(records.values())
                raise
            state.failures[url] = str(exc)[:300]
            emit("page.skipped", url=url, message=str(exc)[:300])
            return None, False
        page = extract_page(content, final)
        page.update({"url": final, "etag": response.headers.get("ETag", ""), "last_modified": response.headers.get("Last-Modified", ""),
                     "status": response.status_code, "hash": hashlib.sha256(page["text"].encode("utf-8")).hexdigest()[:16]})
        state.pages[url] = page
        return page, False

    for query in search_terms:
        words = _query_words(query)
        frontier: dict[str, dict] = {u: {"url": u, "anchor": "", "depth": 0, "path": [u], "reason": "analyst-provided seed"} for u in urls}
        visited: set[str] = set()
        hashes: set[str] = set()
        learned: Counter[str] = Counter()
        fetched = cache_hits = matched = misses = readable = 0
        stop = "frontier_exhausted"
        query_records = []

        def rank(candidate: dict) -> float:
            if candidate["depth"] == 0:
                return 1000
            text = (candidate["anchor"] + " " + urlparse(candidate["url"]).path).casefold()
            hits = sum(w in text for w in words)
            feedback = min(2, sum(w in text for w, _n in learned.most_common(12)))
            return 4 * hits + 2 * bool(_LISTING_HINTS.search(text)) + feedback - .2 * candidate["depth"]

        while frontier:
            if checkpoint:
                checkpoint()
            candidate = max(frontier.values(), key=lambda c: (rank(c), -len(c["url"]), c["url"]))
            url = candidate["url"]
            del frontier[url]
            if url in visited:
                continue
            if candidate["depth"] and rank(candidate) <= 0:
                stop = "low_relevance_frontier"
                break
            cached = url in state.pages or url in state.failures
            if not cached and (fetched >= budget or state.fetched >= state.max_fetches):
                stop = "query_page_budget" if fetched >= budget else "run_page_budget"
                # Cached pages can still provide evidence without another request.
                frontier = {u: c for u, c in frontier.items() if u in state.pages}
                continue
            visited.add(url)
            priority = round(rank(candidate), 3)
            emit("page.selected", url=url, parent_url=candidate["path"][-2] if candidate["depth"] else "", depth=candidate["depth"], priority=priority,
                 cached=cached, message=f"{'Reusing' if cached else 'Reading'} {url}: {candidate['reason']}")
            page, hit = read(url)
            cache_hits += int(hit)
            fetched += int(not hit)
            if not page:
                continue
            readable += 1
            relevant = bool(page["text"]) and _terms_match(words, f"{page['title']} {page['text']}")
            in_window = not page["published"] or in_inclusive_date_range(page["published"], since, until)
            emit("page.assessed", url=page["url"], relevant=relevant, in_window=in_window, cached=hit,
                 message=f"{'Query matched' if relevant else 'Query not matched'}: {page['title'][:120]}")
            misses = 0 if relevant else misses + int(candidate["depth"] > 0)
            if relevant:
                learned.update(w for w in _query_words(page["title"]) if len(w) > 3 and w not in words)
            if relevant and in_window:
                key = ("web", page["url"])
                record = PostRecord(
                    platform="web", native_id=page["url"], canonical_url=page["url"], query=query, query_matches=[query], content_type="web_page",
                    source_mode="web_fetch", source_host=urlparse(page["url"]).netloc, source_url=page["url"], published_at=page["published"],
                    author_name=urlparse(page["url"]).netloc, platform_language=page["language"],
                    original_text=normalize_whitespace(f"{page['title']}. {page['text']}")[:_MAX_TEXT],
                    raw_stats={"content_hash": page["hash"], "http_status": page["status"], "etag": page["etag"], "last_modified": page["last_modified"], "event_dates": page.get("event_dates", []), "cancelled_events": page.get("cancelled_events", []),
                               "date_meaning": "published" if page["published"] else "no date found on the page",
                               "discovery": {"method": "local_adaptive_crawl_v1", "path": candidate["path"], "depth": candidate["depth"], "priority": priority,
                                             "reason": candidate["reason"], "query_terms": words, "cached": hit}})
                if key in records:
                    records[key].add_query_match(query)
                else:
                    record.add_query_match(query)
                    records[key] = record
                query_records.append(records[key])
                matched += 1
            if matched >= max_posts_per_query:
                stop = "item_target_reached"
                break
            if misses >= max(1, patience):
                stop = "diminishing_relevance"
                break
            if follow and candidate["depth"] < min(6, max_depth) and page["hash"] not in hashes:
                hashes.add(page["hash"])
                for target, anchor in page["links"][:500]:
                    target = _crawl_url(target)
                    if target in visited or _SKIP_PATH.search(urlparse(target).path):
                        continue
                    hint = (anchor + " " + urlparse(target).path).casefold()
                    keyword_hits = [w for w in words if w in hint]
                    reason = "query terms in link: " + ", ".join(keyword_hits) if keyword_hits else "news, event or program listing"
                    row = {"url": target, "anchor": anchor, "depth": candidate["depth"] + 1, "path": candidate["path"] + [target], "reason": reason}
                    if rank(row) > 0 and (target not in frontier or rank(row) > rank(frontier[target])):
                        frontier[target] = row
                if len(frontier) > 1000:
                    frontier = dict(sorted(frontier.items(), key=lambda kv: rank(kv[1]), reverse=True)[:1000])
        summary = {"query": query, "stop_reason": stop, "pages_fetched": fetched, "cache_hits": cache_hits, "pages_assessed": readable,
                   "matched": matched, "run_fetches": state.fetched, "run_fetch_budget": state.max_fetches, "model_calls": 0}
        for record in query_records:
            record.raw_stats["crawl_summary"] = summary
        emit("crawl.completed", **summary, message=f"Website search stopped: {stop.replace('_', ' ')}; {matched} matches, {fetched} pages fetched, {cache_hits} cached pages, no model calls.")
        if not readable and not state.pages:
            raise RuntimeError("None of the websites could be read. " + "; ".join(state.failures.values())[:300])
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
