import socket

import pytest
import requests

from sugar_core import web_sources as web
from sugar_core.collector_registry import COLLECTORS


def public_dns(monkeypatch, mapping=None):
    mapping = mapping or {}

    def fake(host, port, proto=0, **kw):
        ip = mapping.get(host, "93.184.216.34")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
    monkeypatch.setattr(web.socket, "getaddrinfo", fake)
    web._ROBOTS.clear()
    web._HOST_LAST.clear()


class FakeResponse:
    def __init__(self, body=b"", status=200, headers=None, text=None, payload=None):
        self.content, self.status_code, self.headers = body, status, headers or {}
        self.text = text if text is not None else body.decode("utf-8", "ignore")
        self._payload = payload
        self.url = ""

    def iter_content(self, size):
        yield self.content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, routes):
        self.routes, self.headers, self.calls = routes, {}, []

    def get(self, url, params=None, timeout=None, allow_redirects=True, stream=False):
        self.calls.append(url)
        base = url.split("?")[0]
        if base not in self.routes:
            return FakeResponse(status=404)
        route = self.routes[base]
        return route() if callable(route) else route


HOME = b"""<html lang="en-GB"><head><title>Harbor Reading Room</title><meta property="article:published_time" content="2025-03-01T09:00:00Z"></head>
<body><nav><a href="/about">About</a></nav><main><h1>Welcome</h1><p>We offer English classes and cultural events for students.</p>
<a href="/news/spring-programs">Spring programs</a> <a href="/contact">Contact</a> <a href="https://other.example/news">Elsewhere</a></main><footer>Copyright</footer></body></html>"""
NEWS = b"""<html lang="en"><head><title>Spring programs</title></head><body><article><time datetime="2025-04-02">April 2</time>
<p>New workshops for university students begin this month.</p></article></body></html>"""
OLD = b"""<html><head><title>Old news</title><meta property="article:published_time" content="2019-01-01"></head><body><p>Reading room workshop archive.</p></body></html>"""


def test_addresses_that_reach_inside_a_network_are_refused(monkeypatch):
    public_dns(monkeypatch)
    assert web.check_public_address("https://library.example.org/a")
    for bad in ("file:///etc/passwd", "ftp://x.example/", "http:///nohost", "gopher://x"):
        with pytest.raises(web.UnsafeAddress):
            web.check_public_address(bad)
    for ip in ("127.0.0.1", "10.0.0.5", "192.168.1.9", "169.254.169.254", "::1", "0.0.0.0"):
        public_dns(monkeypatch, {"internal.example": ip})
        with pytest.raises(web.UnsafeAddress, match="not a public address"):
            web.check_public_address("http://internal.example/")


def test_extract_reads_text_date_language_and_same_site_links():
    page = web.extract_page(HOME, "https://library.example.org/")
    assert page["title"] == "Harbor Reading Room" and page["language"] == "en" and page["published"] == "2025-03-01T09:00:00Z"
    assert "English classes" in page["text"] and "Copyright" not in page["text"]
    targets = [t for t, _ in page["links"]]
    assert "https://library.example.org/news/spring-programs" in targets and "https://other.example/news" not in targets
    assert web.extract_page(NEWS, "https://x.example/n")["published"] == "2025-04-02T00:00:00Z"
    jsonld = b'<html><head><script type="application/ld+json">{"@type":"Article","datePublished":"2024-12-25"}</script></head><body><p>Hi</p></body></html>'
    assert web.extract_page(jsonld, "https://x.example/")["published"].startswith("2024-12-25")


def test_collect_follows_news_pages_filters_by_query_and_window(monkeypatch):
    public_dns(monkeypatch)
    session = FakeSession({"https://library.example.org/robots.txt": FakeResponse(text="User-agent: *\nDisallow: /private", status=200),
                           "https://library.example.org/": FakeResponse(HOME), "https://library.example.org/news/spring-programs": FakeResponse(NEWS),
                           "https://library.example.org/contact": FakeResponse(OLD)})
    rows = web.collect_web(search_terms=["workshops students"], seeds=["https://library.example.org/"], session=session, delay=0)
    urls = {r.canonical_url for r in rows}
    assert urls == {"https://library.example.org/news/spring-programs"}                 # the home page lacks the word "workshops"
    assert rows[0].published_at == "2025-04-02T00:00:00Z" and rows[0].platform == "web" and rows[0].raw_stats["content_hash"]
    assert "https://library.example.org/contact" not in session.calls                    # only listing-style pages are followed
    rows = web.collect_web(search_terms=["students"], seeds=["https://library.example.org/"], since="2025-03-15", session=session, delay=0)
    assert {r.canonical_url for r in rows} == {"https://library.example.org/news/spring-programs"}   # the dated home page falls before the window


def test_robots_refusals_failed_sites_and_bad_seeds_are_reported(monkeypatch):
    public_dns(monkeypatch)
    blocked = FakeSession({"https://closed.example/robots.txt": FakeResponse(text="User-agent: *\nDisallow: /", status=200), "https://closed.example/": FakeResponse(HOME)})
    with pytest.raises(RuntimeError, match="None of the websites could be read"):
        web.collect_web(search_terms=["english"], seeds=["https://closed.example/"], session=blocked, delay=0)
    assert "https://closed.example/" not in blocked.calls
    with pytest.raises(ValueError, match="at least one address"):
        web.collect_web(search_terms=["x"], seeds=["not-a-url"])
    monkeypatch.setattr(web, "_ROBOTS", {})
    mixed = FakeSession({"https://ok.example/": FakeResponse(HOME)})
    rows = web.collect_web(search_terms=["english classes"], seeds=["https://down.example/", "https://ok.example/"], session=mixed, delay=0, follow=False)
    assert len(rows) == 1                                                                 # one bad site does not stop the others


def test_redirects_to_private_addresses_are_blocked(monkeypatch):
    public_dns(monkeypatch, {"sneaky.example": "93.184.216.34", "internal.example": "10.0.0.7"})
    session = FakeSession({"http://sneaky.example/": FakeResponse(status=302, headers={"Location": "http://internal.example/admin"})})
    with pytest.raises(web.UnsafeAddress):
        web.fetch(session, "http://sneaky.example/", delay=0, robots=False)


def test_wayback_history_flags_a_page_that_stopped_responding():
    header = ["timestamp", "original", "statuscode", "mimetype", "digest"]
    rows = [header, ["20230101000000", "http://a.example/", "200", "text/html", "AAA"], ["20240101000000", "http://a.example/", "200", "text/html", "BBB"],
            ["20250101000000", "http://a.example/", "404", "text/html", "CCC"], ["20250601000000", "http://a.example/", "404", "text/html", "CCC"]]
    session = FakeSession({"https://web.archive.org/cdx/search/cdx": FakeResponse(payload=rows)})
    history = web.wayback_history("http://a.example/", session=session)
    assert history["first_seen"].startswith("2023-01-01") and history["last_ok"].startswith("2024-01-01") and history["total"] == 4
    assert any("last good capture is from 2024-01-01" in s for s in history["signals"]) and any("changed 1 time" in s for s in history["signals"])
    assert history["snapshots"][-1]["archive_url"].startswith("https://web.archive.org/web/20250601000000/")
    empty = web.wayback_history("http://b.example/", session=FakeSession({"https://web.archive.org/cdx/search/cdx": FakeResponse(payload=[])}))
    assert "no captures" in empty["signals"][0]


def test_registered_as_an_opt_in_source():
    spec = COLLECTORS["web"]
    assert spec.enabled_by == "web_seeds" and spec.capabilities.keyword_search and not spec.required_secrets
