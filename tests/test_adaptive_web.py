from sugar_core import web_sources as web
from sugar_core.research_items import record_to_item, start_chain
from test_web_sources import FakeResponse, FakeSession, public_dns


def page(title, body, links=""):
    return f'<html lang="en"><head><title>{title}</title></head><body><main>{body}</main><nav>{links}</nav></body></html>'.encode()


def test_query_driven_multihop_discovery_and_audit_trail(monkeypatch):
    public_dns(monkeypatch)
    root = "https://institution.example/"
    session = FakeSession({root: FakeResponse(page("Institution", "Welcome", '<a href="/departments">Education department</a><a href="/unrelated">Shop</a>')),
        root + "departments": FakeResponse(page("Department", "Our offices", '<a href="/partnerships">Education partnerships</a>')),
        root + "partnerships": FakeResponse(page("Education Partnerships Ghana", "Education exchange programs", '<a href="/agreement">Partnerships agreement</a>')),
        root + "agreement": FakeResponse(page("Agreement", "Education cooperation in Ghana"))})
    events = []
    rows = web.collect_web(search_terms=["education"], seeds=[root], session=session, delay=0, robots=False,
                           on_event=lambda kind, **data: events.append((kind, data)))
    assert {r.canonical_url for r in rows} == {root + "partnerships", root + "agreement"}
    deepest = next(r for r in rows if r.canonical_url.endswith("agreement"))
    assert deepest.raw_stats["discovery"]["path"] == [root, root + "departments", root + "partnerships", root + "agreement"]
    assert deepest.raw_stats["crawl_summary"]["model_calls"] == 0
    assert root + "unrelated" not in session.calls
    assert any(kind == "page.assessed" and data["relevant"] for kind, data in events)
    item, _ = record_to_item(deepest, run_id="r", project_id="p", query_id="q", query_text="education", dispatched="education")
    start_chain(item, query_id="q", query_text="education", dispatched="education")
    node = next(n for n in item.evidence_chain if n["type"] == "fetched_document")
    assert node["data"]["source_metadata"]["discovery"]["depth"] == 3


def test_per_run_cache_reuses_pages_across_queries_without_requests(monkeypatch):
    public_dns(monkeypatch)
    root = "https://institution.example/"
    session = FakeSession({root: FakeResponse(page("Education programs", "Education and culture exchange"))})
    state = web.WebCrawlState()
    first = web.collect_web(search_terms=["education"], seeds=[root], state=state, session=session, delay=0, robots=False)
    calls = list(session.calls)
    second = web.collect_web(search_terms=["culture"], seeds=[root], state=state, session=session, delay=0, robots=False)
    assert first and second and session.calls == calls
    assert second[0].raw_stats["crawl_summary"]["cache_hits"] == 1 and state.fetched == 1


def test_hard_run_budget_and_depth_prevent_unbounded_discovery(monkeypatch):
    public_dns(monkeypatch)
    root = "https://institution.example/"
    routes = {root: FakeResponse(page("Home", "Welcome", '<a href="/education1">Education updates</a>'))}
    for n in range(1, 8):
        routes[root + f"education{n}"] = FakeResponse(page(str(n), f"Education program {n}", f'<a href="/education{n + 1}">Education next</a>'))
    state = web.WebCrawlState(max_fetches=3)
    events = []
    rows = web.collect_web(search_terms=["education"], seeds=[root], state=state, session=FakeSession(routes), delay=0, robots=False,
                           max_depth=6, on_event=lambda kind, **data: events.append((kind, data)))
    assert len(rows) == 2 and state.fetched == 3
    assert events[-1][1]["stop_reason"] == "run_page_budget"


def test_diminishing_returns_stop_irrelevant_sites_early(monkeypatch):
    public_dns(monkeypatch)
    root = "https://institution.example/"
    links = "".join(f'<a href="/news/{n}">News {n}</a>' for n in range(15))
    routes = {root: FakeResponse(page("Home", "Welcome", links))}
    routes.update({root + f"news/{n}": FakeResponse(page(f"News {n}", f"Irrelevant content number {n}")) for n in range(15)})
    session, events = FakeSession(routes), []
    rows = web.collect_web(search_terms=["education"], seeds=[root], session=session, delay=0, robots=False, patience=3,
                           on_event=lambda kind, **data: events.append((kind, data)))
    assert rows == [] and len(session.calls) == 4
    assert events[-1][1]["stop_reason"] == "diminishing_relevance"


def test_crawl_checks_cooperative_controls_before_every_page(monkeypatch):
    import pytest
    public_dns(monkeypatch)
    root = "https://institution.example/"
    session = FakeSession({root: FakeResponse(page("Home", "Welcome", '<a href="/education">Education</a>'))})
    checkpoints = []
    def check():
        checkpoints.append(True)
        if len(checkpoints) > 1:
            raise RuntimeError("cancelled by researcher")
    with pytest.raises(RuntimeError, match="cancelled by researcher"):
        web.collect_web(search_terms=["education"], seeds=[root], session=session, delay=0, robots=False, checkpoint=check)
    assert session.calls == [root]


def test_rate_limit_stops_traversal_preserves_evidence_and_retains_retry_after(monkeypatch):
    import pytest
    from sugar_core.research_pipeline import classify_failure
    public_dns(monkeypatch)
    root = "https://institution.example/"
    session = FakeSession({root: FakeResponse(page("Education", "Education programs", '<a href="/education">Education details</a><a href="/news">News</a>')),
                           root + "education": FakeResponse(status=429, headers={"Retry-After": "120"})})
    with pytest.raises(RuntimeError, match="rate limit") as caught:
        web.collect_web(search_terms=["education"], seeds=[root], session=session, delay=0, robots=False)
    assert len(caught.value.partial_records) == 1
    assert classify_failure(caught.value, "web")["retry_after"] == 120
    assert session.calls == [root, root + "education"]
