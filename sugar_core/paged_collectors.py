from __future__ import annotations

from collections import OrderedDict
from typing import Any

import requests

from .models import PostRecord, merge_record
from .utils import in_inclusive_date_range, normalize_whitespace


def _merge(records: OrderedDict[tuple[str, str], PostRecord], record: PostRecord) -> None:
    key = (record.platform, record.native_id or record.canonical_url)
    if key in records:
        merge_record(records[key], record)
    else:
        for query in record.query_matches or [record.query]:
            record.add_query_match(query)
        records[key] = record


def collect_bilibili_page_range(request: Any) -> list[PostRecord]:
    """Collect a bounded Bilibili page range using the same fail-closed public primitives.

    This exists only to make high-volume harvests checkpointable between page ranges. It does not
    change the access model, synthesize WBI/device state, or bypass any Bilibili response gate.
    """
    from .bilibili import (
        BILIBILI_API_BASE_URL,
        BilibiliAccessError,
        _handle_http,
        _search_item_to_record,
        _unwrap,
        create_bilibili_session,
        fetch_bilibili_video,
        warm_public_session,
    )

    start_page = max(1, int(request.config.get("_harvest_page_start", 1)))
    page_count = max(1, int(request.config.get("_harvest_page_count", request.max_pages_per_query)))
    end_page = start_page + page_count - 1
    order = str(request.config.get("bilibili_order", "pubdate"))
    hydrate = bool(request.config.get("bilibili_hydrate_details", True))
    initialize_session = bool(request.config.get("bilibili_initialize_session", True))
    session = create_bilibili_session()
    if initialize_session:
        warm_public_session(session)
    endpoint = f"{BILIBILI_API_BASE_URL}/x/web-interface/wbi/search/type"
    records: OrderedDict[tuple[str, str], PostRecord] = OrderedDict()

    for raw_query in request.search_terms:
        query = normalize_whitespace(raw_query)
        if not query:
            continue
        collected = 0
        for page in range(start_page, end_page + 1):
            remaining = request.max_posts_per_query - collected
            if remaining <= 0:
                break
            params = {
                "search_type": "video",
                "keyword": query,
                "page": page,
                "page_size": min(20, remaining),
                "order": order,
            }
            response = session.get(endpoint, params=params, timeout=30)
            _handle_http(response, "video search")
            data = _unwrap(response.json(), "video search")
            items = data.get("result") or []
            if not isinstance(items, list):
                raise RuntimeError("Bilibili video search returned an unexpected result shape.")
            if not items:
                break

            before_page = collected
            for item in items:
                if not isinstance(item, dict):
                    continue
                search_record = _search_item_to_record(item, query=query, source_url=response.url)
                record = search_record
                if hydrate and search_record.native_id.startswith("BV"):
                    try:
                        detail = fetch_bilibili_video(search_record.native_id, query=query, session=session)
                        detail.source_mode = "bilibili_public_search+video"
                        detail.source_url = response.url
                        record = detail
                    except BilibiliAccessError:
                        raise
                    except (requests.RequestException, RuntimeError, ValueError):
                        record = search_record
                if not in_inclusive_date_range(record.published_at, request.since, request.until):
                    continue
                _merge(records, record)
                collected += 1
                if collected >= request.max_posts_per_query:
                    break

            if len(items) < params["page_size"] or collected >= request.max_posts_per_query:
                break
            if collected == before_page and (request.since or request.until):
                continue

    return list(records.values())


def collect_weibo_page_range(request: Any) -> list[PostRecord]:
    """Collect a bounded Weibo page range using ordinary mobile-web access only."""
    from .weibo import (
        WEIBO_SEARCH_ENDPOINT,
        WeiboAccessError,
        _handle_http,
        _iter_mblogs,
        _status_identity,
        _status_to_record,
        _unwrap,
        create_weibo_session,
        fetch_weibo_status,
    )

    start_page = max(1, int(request.config.get("_harvest_page_start", 1)))
    page_count = max(1, int(request.config.get("_harvest_page_count", request.max_pages_per_query)))
    end_page = start_page + page_count - 1
    cookie = str(request.secrets.get("weibo_cookie", "") or "")
    hydrate = bool(request.config.get("weibo_hydrate_details", True))
    session = create_weibo_session(cookie)
    records: OrderedDict[tuple[str, str], PostRecord] = OrderedDict()

    for raw_query in request.search_terms:
        query = normalize_whitespace(raw_query)
        if not query:
            continue
        collected = 0
        seen_page_ids: set[str] = set()
        for page in range(start_page, end_page + 1):
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

            unseen_on_page = 0
            accepted_on_page = 0
            for status in mblogs:
                native_id, _ = _status_identity(status)
                if not native_id or native_id in seen_page_ids:
                    continue
                seen_page_ids.add(native_id)
                unseen_on_page += 1
                record = _status_to_record(
                    status,
                    query=query,
                    source_url=response.url,
                    source_mode="weibo_public_search",
                )
                if hydrate:
                    try:
                        detail = fetch_weibo_status(native_id, query=query, cookie=cookie, session=session)
                        detail.source_mode = "weibo_public_search+status"
                        detail.source_url = response.url
                        record = detail
                    except WeiboAccessError:
                        record = record
                    except (requests.RequestException, RuntimeError, ValueError):
                        record = record
                if not in_inclusive_date_range(record.published_at, request.since, request.until):
                    continue
                _merge(records, record)
                collected += 1
                accepted_on_page += 1
                if collected >= request.max_posts_per_query:
                    break

            if collected >= request.max_posts_per_query:
                break
            # Stop only if the server repeated/emptied the page. A page with new records that are
            # merely outside the requested date range is not evidence that later pages are useless.
            if unseen_on_page == 0:
                break
            _ = accepted_on_page

    return list(records.values())
