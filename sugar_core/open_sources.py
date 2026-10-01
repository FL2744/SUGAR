"""Reliable, low-friction sources that are not social platforms.

Social platforms are the least dependable part of a research pipeline: access changes, paid tiers,
anonymous blocks. These collectors read stable public interfaces instead and return the same
``PostRecord`` shape, so de-duplication, translation, provenance and export treat them identically.

* ``wikipedia`` - encyclopedia articles (MediaWiki API), any language edition, for institution
  background, histories and lists.
* ``gdelt``     - news coverage worldwide in 100+ languages (GDELT DOC 2.0): headline, outlet,
  country, language, date. Headlines only; follow the link for the article.
* ``openalex``  - scholarly works (OpenAlex): title, abstract, authors, venue, citations.
* ``rss``       - any news, ministry, embassy or institution feed you name (RSS/Atom).

Each is a polite client: a descriptive User-Agent, a minimum interval between calls where the service
asks for one, and a 429 surfaces as an ordinary rate-limit failure so the pipeline backs off and retries.
Nothing here needs a credential; ``openalex_api_key`` is optional and only raises OpenAlex's limits.
"""
from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable
from urllib.parse import quote, urlparse

import requests

from .models import PostRecord
from .utils import in_inclusive_date_range, normalize_whitespace

USER_AGENT = "SUGAR research client (+https://github.com/FL2744/SUGAR; Virginia Tech Diplomacy Lab)"
_TIMEOUT = 45

# GDELT asks clients for no more than one request every five seconds.
_gdelt_lock = threading.Lock()
_gdelt_last = 0.0

# GDELT reports languages by English name; map the common ones to ISO 639-1.
_GDELT_LANGS = {
    "english": "en", "chinese": "zh", "spanish": "es", "french": "fr", "german": "de", "russian": "ru", "arabic": "ar",
    "portuguese": "pt", "japanese": "ja", "korean": "ko", "italian": "it", "turkish": "tr", "persian": "fa", "hindi": "hi",
    "indonesian": "id", "vietnamese": "vi", "thai": "th", "ukrainian": "uk", "polish": "pl", "dutch": "nl", "swahili": "sw",
    "bengali": "bn", "urdu": "ur", "hebrew": "he", "greek": "el", "czech": "cs", "romanian": "ro", "swedish": "sv",
}


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, application/xml;q=0.9, */*;q=0.5"})
    return session


def _get(session: requests.Session, url: str, *, params: dict[str, Any] | None = None) -> requests.Response:
    response = session.get(url, params=params, timeout=_TIMEOUT)
    if response.status_code == 429:
        raise RuntimeError(f"{urlparse(url).netloc} rate limit reached (429); retry after "
                           f"{response.headers.get('Retry-After', 'a short wait')}.")
    response.raise_for_status()
    return response


def _iso(value: Any) -> str:
    """Best-effort ISO-8601 UTC timestamp from the date formats these services use ('' if unreadable)."""
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    try:
        return parsedate_to_datetime(text).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return text


def _merge(records: "OrderedDict[tuple[str, str], PostRecord]", record: PostRecord) -> None:
    key = (record.platform, record.native_id or record.canonical_url)
    if key in records:
        for query in record.query_matches or [record.query]:
            records[key].add_query_match(query)
    else:
        for query in record.query_matches or [record.query]:
            record.add_query_match(query)
        records[key] = record


def _strip(value: str) -> str:
    return normalize_whitespace(re.sub(r"<[^>]+>", " ", value or ""))


# ------------------------------------------------------------------------------------ Wikipedia
def collect_wikipedia(*, search_terms: Iterable[str], max_posts_per_query: int = 10, languages: Iterable[str] = ("en",),
                      session: requests.Session | None = None, **_: Any) -> list[PostRecord]:
    """Articles matching each query, from each requested language edition. Dates do not apply to encyclopedias."""
    session = session or _session()
    records: OrderedDict[tuple[str, str], PostRecord] = OrderedDict()
    langs = [str(code).casefold()[:3] for code in languages if re.fullmatch(r"[A-Za-z-]{2,8}", str(code))] or ["en"]
    for query in search_terms:
        for lang in dict.fromkeys(langs[:4]):
            endpoint = f"https://{lang}.wikipedia.org/w/api.php"
            search = _get(session, endpoint, params={"action": "query", "list": "search", "srsearch": query, "srlimit": min(50, max(1, max_posts_per_query)),
                                                     "format": "json", "formatversion": 2}).json()
            hits = (search.get("query") or {}).get("search") or []
            if not hits:
                continue
            ids = "|".join(str(h["pageid"]) for h in hits if "pageid" in h)
            extracts = _get(session, endpoint, params={"action": "query", "prop": "extracts|info", "pageids": ids, "exintro": 1, "explaintext": 1,
                                                       "inprop": "url", "format": "json", "formatversion": 2}).json()
            pages = {str(p.get("pageid")): p for p in (extracts.get("query") or {}).get("pages") or []}
            for hit in hits:
                page = pages.get(str(hit.get("pageid")), {})
                title = str(hit.get("title") or page.get("title") or "")
                body = normalize_whitespace(str(page.get("extract") or _strip(str(hit.get("snippet") or ""))))
                url = str(page.get("fullurl") or f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}")
                _merge(records, PostRecord(
                    platform="wikipedia", native_id=f"{lang}:{hit.get('pageid')}", canonical_url=url, query=query, query_matches=[query],
                    content_type="article", source_mode="wikipedia_search", source_host=f"{lang}.wikipedia.org", source_url=url,
                    published_at=_iso(hit.get("timestamp") or page.get("touched")), author_name="Wikipedia contributors",
                    platform_language=lang, original_text=normalize_whitespace(f"{title}. {body}"),
                    raw_stats={"title": title, "wordcount": hit.get("wordcount", 0), "date_meaning": "last edited"}))
    return list(records.values())


# ------------------------------------------------------------------------------------ GDELT news
def _gdelt_query(term: str) -> str:
    term = normalize_whitespace(term)
    return f'"{term}"' if " " in term and not term.startswith('"') else term


def collect_gdelt(*, search_terms: Iterable[str], since: str | None = None, until: str | None = None, max_posts_per_query: int = 25,
                  session: requests.Session | None = None, min_interval: float = 5.2, **_: Any) -> list[PostRecord]:
    """News articles from GDELT's DOC 2.0 index. Headline-level records; the article itself is at the link."""
    global _gdelt_last
    session = session or _session()
    records: OrderedDict[tuple[str, str], PostRecord] = OrderedDict()
    for query in search_terms:
        params: dict[str, Any] = {"query": _gdelt_query(query), "mode": "artlist", "format": "json", "sort": "datedesc",
                                  "maxrecords": min(250, max(1, max_posts_per_query))}
        if since:
            params["startdatetime"] = re.sub(r"\D", "", since)[:8] + "000000"
        if until:
            params["enddatetime"] = re.sub(r"\D", "", until)[:8] + "235959"
        with _gdelt_lock:
            wait = min_interval - (time.monotonic() - _gdelt_last)
            if wait > 0:
                time.sleep(wait)
            try:
                response = _get(session, "https://api.gdeltproject.org/api/v2/doc/doc", params=params)
            finally:
                _gdelt_last = time.monotonic()
        try:
            articles = response.json().get("articles") or []
        except ValueError:      # GDELT answers with plain text for queries it rejects (too short, too common)
            raise ValueError(f"GDELT could not run “{query}”: {normalize_whitespace(response.text)[:160]}") from None
        for article in articles:
            url = str(article.get("url") or "")
            if not url:
                continue
            published = _iso(article.get("seendate"))
            if not in_inclusive_date_range(published, since, until):
                continue
            domain = str(article.get("domain") or urlparse(url).netloc)
            language = _GDELT_LANGS.get(str(article.get("language") or "").casefold(), "")
            _merge(records, PostRecord(
                platform="gdelt", native_id=url, canonical_url=url, query=query, query_matches=[query], content_type="news_article",
                source_mode="gdelt_doc", source_host=domain, source_url=response.url, published_at=published, author_name=domain,
                author_location=str(article.get("sourcecountry") or ""), platform_language=language,
                original_text=normalize_whitespace(str(article.get("title") or "")),
                raw_stats={"outlet": domain, "source_country": article.get("sourcecountry", ""), "language_name": article.get("language", ""),
                           "text_scope": "headline only"}))
    return list(records.values())


# ------------------------------------------------------------------------------------ OpenAlex
def _abstract(inverted: dict[str, list[int]] | None) -> str:
    if not inverted:
        return ""
    slots: dict[int, str] = {}
    for word, positions in inverted.items():
        for position in positions:
            slots[position] = word
    return " ".join(slots[i] for i in sorted(slots))


def collect_openalex(*, search_terms: Iterable[str], since: str | None = None, until: str | None = None, max_posts_per_query: int = 25,
                     api_key: str = "", session: requests.Session | None = None, **_: Any) -> list[PostRecord]:
    """Scholarly works matching each query (title, abstract, authors, venue, citation count)."""
    session = session or _session()
    records: OrderedDict[tuple[str, str], PostRecord] = OrderedDict()
    for query in search_terms:
        filters = []
        if since:
            filters.append(f"from_publication_date:{since[:10]}")
        if until:
            filters.append(f"to_publication_date:{until[:10]}")
        params: dict[str, Any] = {"search": query, "per-page": min(200, max(1, max_posts_per_query)), "sort": "relevance_score:desc"}
        if filters:
            params["filter"] = ",".join(filters)
        if api_key.strip():
            params["api_key"] = api_key.strip()
        payload = _get(session, "https://api.openalex.org/works", params=params).json()
        for work in payload.get("results") or []:
            work_id = str(work.get("id") or "")
            if not work_id:
                continue
            doi = str(work.get("doi") or "")
            url = doi or work_id
            authors = [str((a.get("author") or {}).get("display_name") or "") for a in (work.get("authorships") or [])]
            authors = [a for a in authors if a]
            venue = str(((work.get("primary_location") or {}).get("source") or {}).get("display_name") or "")
            title = normalize_whitespace(str(work.get("title") or work.get("display_name") or ""))
            raw = {"cited_by_count": work.get("cited_by_count", 0), "venue": venue, "type": work.get("type", ""), "doi": doi, "authors": authors[:20]}
            _merge(records, PostRecord(
                platform="openalex", native_id=work_id.rsplit("/", 1)[-1], canonical_url=url, query=query, query_matches=[query],
                content_type="scholarly_work", source_mode="openalex_works", source_host="openalex.org", source_url=work_id,
                published_at=_iso(work.get("publication_date")), author_name="; ".join(authors[:6]) + (" et al." if len(authors) > 6 else ""),
                platform_language=str(work.get("language") or ""), original_text=normalize_whitespace(f"{title}. {_abstract(work.get('abstract_inverted_index'))}"),
                raw_stats=raw, engagement={"citations": int(work.get("cited_by_count") or 0)}))
    return list(records.values())


# ------------------------------------------------------------------------------------ RSS / Atom feeds
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_feed(content: bytes) -> list[dict[str, str]]:
    """Entries from an RSS 2.0 or Atom document. External entities and network access are disabled."""
    from lxml import etree
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=True, huge_tree=False)
    root = etree.fromstring(content, parser)
    if root is None:
        return []
    entries: list[dict[str, str]] = []
    for node in root.iter():
        if not isinstance(node.tag, str) or _local(node.tag) not in {"item", "entry"}:
            continue
        row = {"title": "", "link": "", "summary": "", "date": "", "author": "", "id": ""}
        for child in node:
            if not isinstance(child.tag, str):
                continue
            name = _local(child.tag)
            text = normalize_whitespace("".join(child.itertext()))
            if name == "title":
                row["title"] = text
            elif name == "link":
                row["link"] = row["link"] or (child.get("href") or text)
            elif name in {"description", "summary", "content", "encoded"}:
                row["summary"] = row["summary"] or _strip(text)
            elif name in {"pubDate", "published", "updated", "date"}:
                row["date"] = row["date"] or text
            elif name in {"author", "creator"}:
                row["author"] = row["author"] or text
            elif name in {"guid", "id"}:
                row["id"] = row["id"] or text
        if row["title"] or row["summary"]:
            entries.append(row)
    return entries


def collect_rss(*, search_terms: Iterable[str], feeds: Iterable[str], since: str | None = None, until: str | None = None,
                max_posts_per_query: int = 25, session: requests.Session | None = None, **_: Any) -> list[PostRecord]:
    """Entries from the feeds you name whose title or summary mentions the query (every word, any order)."""
    urls = [str(f).strip() for f in feeds if str(f).strip().lower().startswith(("http://", "https://"))]
    if not urls:
        raise ValueError("News and institution feeds need at least one feed address. Add feed URLs under Settings → Sources.")
    session = session or _session()
    fetched: dict[str, list[dict[str, str]]] = {}
    failures: list[str] = []
    for url in urls:
        try:
            fetched[url] = parse_feed(_get(session, url).content)
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            failures.append(f"{urlparse(url).netloc}: {exc}")
    if not fetched:
        raise RuntimeError("None of the configured feeds could be read. " + "; ".join(failures)[:300])
    records: OrderedDict[tuple[str, str], PostRecord] = OrderedDict()
    for query in search_terms:
        words = [w for w in re.findall(r"[^\W_]+", query.casefold(), re.UNICODE) if w]
        matched = 0
        for url, entries in fetched.items():
            host = urlparse(url).netloc
            for entry in entries:
                haystack = f"{entry['title']} {entry['summary']}".casefold()
                if words and not all(w in haystack for w in words):
                    continue
                published = _iso(entry["date"])
                if published and not in_inclusive_date_range(published, since, until):
                    continue
                link = entry["link"] or entry["id"]
                _merge(records, PostRecord(
                    platform="rss", native_id=entry["id"] or link, canonical_url=link, query=query, query_matches=[query], content_type="feed_entry",
                    source_mode="rss_feed", source_host=host, source_url=url, published_at=published, author_name=entry["author"] or host,
                    original_text=normalize_whitespace(f"{entry['title']}. {entry['summary']}"), raw_stats={"feed": url}))
                matched += 1
                if matched >= max_posts_per_query:
                    break
            if matched >= max_posts_per_query:
                break
    return list(records.values())
