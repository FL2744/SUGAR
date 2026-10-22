"""Evidence-based activity proposals, separate from the registry's reviewed status.

Group 1 section 10 supplies the six display labels. The historical window starts
in 2024; 'current' follows the assessment year rather than a hardcoded year.
Archive captures and retrieval timestamps never count as program activity.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .temporal import timestamp as parse_timestamp

BASELINE = "2024-01-01"
PROGRAM = re.compile(r"\b(courses?|classes|registration|enrol[l]?ment|programming|workshops?|conferences?|competitions?|held|hosted|events?|scholarships?)\b|课程|活动|招生|课程报名|课程注册|taller|inscripci[oó]n|evento|curso", re.I)
NEGATIVE = re.compile(r"\b(cancelled|canceled|suspended|closed|closure|ceased|discontinued|no longer|will not|did not|not holding)\b|取消|关闭|暂停", re.I)
PRESENCE = re.compile(r"\b(staff|contact|address|director|institute|centre|center)\b|联系|地址|教师", re.I)


def evidence_index(items: dict[str, Any]) -> dict[str, Any]:
    hosts: dict[str, list[str]] = {}
    words: dict[str, set[str]] = {}
    for iid, item in items.items():
        try:
            for url in [item.url, str((item.source_metadata or {}).get("feed") or "")]:
                host = (urlsplit(url).hostname or "").removeprefix("www.")
                hosts.setdefault(host, []).append(iid)
        except ValueError:
            pass
        if item.platform in {"rss", "gdelt"}:
            for word in set(re.findall(r"\w{3,}", item.original_text.casefold())):
                words.setdefault(word, set()).add(iid)
    return {"hosts": hosts, "words": words}


def candidate_links(entity: dict[str, Any], items: dict[str, Any], index: dict[str, Any]) -> list[dict[str, Any]]:
    """Associate recorded URL scopes and exact institution-name news mentions locally.

    These stay marked as automatic candidates; no registry link or human finding
    is created. A hostname alone is insufficient for a shared university path.
    """
    from .mission_rubric import match_term
    roots = [*_urls(entity.get("public_links")), *_urls(entity.get("accounts"))]
    candidates = set()
    for root in roots:
        try:
            candidates.update(index["hosts"].get((urlsplit(root).hostname or "").removeprefix("www."), []))
        except ValueError:
            pass
    found = {iid for iid in candidates if _under(items[iid].url, roots) or _account_match(items[iid], _urls(entity.get("accounts")))}
    aliases = entity.get("aliases") or []
    aliases = aliases if isinstance(aliases, list) else [aliases]
    for name in [entity.get("name", ""), *aliases]:
        name = str(name)
        if len(name) < 8:
            continue
        tokens = re.findall(r"\w{3,}", name.casefold())
        if not tokens:
            continue
        token = max(tokens, key=len)
        pool = index["words"].get(token, set())
        if re.search(r"[\u3400-\u9fff]", name):
            pool = {iid for iid, i in items.items() if i.platform in {"rss", "gdelt"}}
        found.update(iid for iid in pool if match_term(items[iid].original_text, name))
    return [{"item_id": iid, "run_id": items[iid].run_id, "url": items[iid].url, "association": "automatic_url_or_exact_name_candidate"} for iid in sorted(found)]


def _date(value: Any) -> str:
    stamp = parse_timestamp(str(value or ""))
    return stamp.date().isoformat() if stamp else ""


def _urls(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [str(v) for v in values if str(v).startswith(("https://", "http://"))]


def _under(url: str, roots: list[str]) -> bool:
    try:
        parsed = urlsplit(url)
        for root in roots:
            target = urlsplit(root)
            prefix = target.path.rstrip("/")
            if parsed.hostname == target.hostname and (not prefix or parsed.path == prefix or parsed.path.startswith(prefix + "/")):
                return True
    except ValueError:
        pass
    return False


def _account_match(item: Any, accounts: list[str]) -> bool:
    if _under(item.url, accounts):
        return True
    try:
        feed = urlsplit(str((item.source_metadata or {}).get("feed") or ""))
        if feed.hostname not in {"youtube.com", "www.youtube.com"} or feed.path != "/feeds/videos.xml":
            return False
        channel = parse_qs(feed.query).get("channel_id", [""])[0]
        if not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", channel):
            return False
        return any(urlsplit(a).hostname in {"youtube.com", "www.youtube.com"} and urlsplit(a).path.rstrip("/") == "/channel/" + channel for a in accounts)
    except ValueError:
        return False


def assess(entity: dict[str, Any], links: list[dict[str, Any]], items: dict[str, Any], *, archives: list[dict] | None = None,
           now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    today, year = now.date().isoformat(), str(now.year)
    roots = _urls(entity.get("public_links"))
    accounts = _urls(entity.get("accounts"))
    signals: list[dict[str, Any]] = []
    seen = set()
    refs = []
    for claim in entity.get("claims", []):
        if claim.get("review_state") != "rejected":
            refs.extend(r for r in claim.get("evidence_refs", []) if isinstance(r, dict))
    for link in [*links, *refs]:
        item = items.get(str(link.get("item_id") or ""))
        if item is not None and item.status not in {"collected", "processed"}:
            continue
        url = str(link.get("url") or link.get("source_url") or (item.url if item else ""))
        quote = str(item.original_text if item else link.get("quote") or "")
        if not quote:
            continue  # A citation with no captured wording is a lead, not dated activity.
        metadata = getattr(item, "source_metadata", {}) or {}
        stamp = _date(item.published_at if item else link.get("published_at"))
        official = _under(url, roots)
        account = _account_match(item, accounts) if item else _under(url, accounts)
        platform = item.platform if item else str(link.get("platform") or "")
        kind = "known_account_post" if account else "official_webpage" if official else "news_mention" if platform in {"gdelt", "rss"} else "linked_evidence"
        event_dates = metadata.get("event_dates", []) if official else []
        if not isinstance(event_dates, list):
            event_dates = []
        event_dates = sorted({_date(d) for d in event_dates if _date(d)})
        negative = bool(NEGATIVE.search(quote) or metadata.get("cancelled_events"))
        old_years = {y for y in re.findall(r"\b(?:19|20)\d{2}\b", quote) if y < year}
        historical = not event_dates and year not in quote and any(re.search(rf"\b(?:in|from|during)\s+{y}\b|\b{y}\s+(?:courses|events|programs|programming)\b", quote, re.I) for y in old_years)
        program = bool(PROGRAM.search(quote)) and not negative and not historical
        period_pattern = r"(?:autumn|fall|spring|summer|winter|january|february|march|april|may|june|july|august|september|october|november|december|otoño|primavera|octubre|automne)\s+(?:de\s+)?((?:19|20)\d{2})"
        period = re.search(period_pattern, quote, re.I) if official and program else None
        period_year = period.group(1) if period else ""
        if period_year and period_year < year and stamp.startswith(year) and year not in quote and not event_dates:
            historical, program = True, False
        event_date = max((d for d in event_dates if d <= today), default="")
        upcoming = min((d for d in event_dates if d > today), default="")
        date = event_date or stamp
        if date > today:
            date = ""  # Future publication timestamps do not prove activity.
        key = (url, date, kind)
        if key in seen:
            continue
        seen.add(key)
        signals.append({"kind": kind, "date": date, "date_basis": "structured_event_date" if event_date else "publication_date" if date else "undated",
                        "url": url, "item_id": item.item_id if item else link.get("item_id", ""), "run_id": item.run_id if item else link.get("run_id", ""),
                        "quote": quote[:600], "official": official, "program": program, "negative_cue": negative,
                        "upcoming_date": upcoming, "presence": bool(PRESENCE.search(quote)), "historical_cue": historical,
                        "program_period": period.group(0) if period else "", "program_year": period_year,
                        "association": str(link.get("association") or "recorded_link_or_citation")})
    dated = [s for s in signals if s["date"]]
    activity = [s for s in dated if (s["program"] or s["kind"] == "known_account_post") and not s["negative_cue"]]
    current = [s for s in signals if s["official"] and s["program"] and (s["date"].startswith(year) or s["upcoming_date"].startswith(year) or s["program_year"] == year)]
    recent = [s for s in signals if not s["negative_cue"] and not s["historical_cue"] and ((s["date"] and s["date"] >= BASELINE) or ("2024" <= s["program_year"] <= year))]
    # Only a human-verified lifecycle claim can yield a terminal status proposal.
    verified = [c for c in entity.get("claims", []) if c.get("field") == "status" and c.get("review_state") == "human_verified"]
    verified_value = entity.get("status") if verified and "status" not in entity.get("conflicted_fields", []) else ""
    status, confidence, label = "unknown", "low", "Status unclear"
    reasons = []
    if verified_value in {"closed", "renamed", "relocated"}:
        status = verified_value
        confidence = "high"
        label = {"closed": "Closed", "renamed": "Renamed/restructured", "relocated": "Relocated"}[status]
        reasons.append("A person verified the registry's lifecycle status; see its source claims.")
    elif current:
        status, confidence, label = "active", "high", "Active, high confidence"
        reasons.append(f"An institution website recorded in Public links supplies {year} program evidence.")
    elif recent:
        status, confidence, label = "active", "medium", "Active, medium confidence"
        reasons.append("Dated evidence exists in the 2024–present window; current official programming is not established.")
    else:
        reasons.append("No dated evidence since 2024 was found in the linked material. Review is required; this does not establish closure.")
    if any(s["negative_cue"] for s in signals):
        reasons.append("Closure, suspension or cancellation wording requires human review.")
    if any(s["historical_cue"] for s in signals):
        reasons.append("Historical program wording was excluded from current activity evidence.")
    if "status" in entity.get("conflicted_fields", []):
        status, confidence, label = "unknown", "low", "Status unclear"
        reasons.append("Status claims conflict.")
    return {"status": status, "confidence": confidence, "label": label, "review_state": "proposed", "baseline": BASELINE,
            "assessed_at": now.isoformat(), "last_evidence_date": max((s["date"] for s in dated), default=""),
            "last_activity_date": max((s["date"] for s in activity), default=""),
            "current_program_periods": list(dict.fromkeys(s["program_period"] for s in current if s["program_period"])),
            "needs_review": not recent or bool(verified_value == "closed" and current) or any(s["negative_cue"] or s["historical_cue"] for s in signals) or "status" in entity.get("conflicted_fields", []),
            "signals": signals, "archive_availability": archives or [], "reasons": reasons,
            "method": "Group 1 section 10; suspended and merged await a final scale. Affiliation is a separate field. Capture dates establish archive availability only."}


def project_context(project: Any, links: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    run_ids = ({str(l.get("run_id") or "") for l in links} | {r["run_id"] for r in project.list_runs()}) - {""}
    items = {}
    ordered_ids = [r["run_id"] for r in project.list_runs()]
    for run_id in [*ordered_ids, *sorted(run_ids - set(ordered_ids))]:
        for item in project.load_items(run_id):
            prior = items.get(item.item_id)
            if prior is None or (parse_timestamp(item.retrieved_at) or datetime.min.replace(tzinfo=timezone.utc)) > (parse_timestamp(prior.retrieved_at) or datetime.min.replace(tzinfo=timezone.utc)):
                items[item.item_id] = item
    try:
        archives = json.loads((project.root / "archive-availability.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        archives = {}
    if not isinstance(archives, dict):
        archives = {}
    archives = {k: v for k, v in archives.items() if isinstance(v, dict) and isinstance(v.get("pages", []), list)}
    return items, archives


def save_history(project: Any, entity_id: str, result: dict[str, Any]) -> None:
    with project._lock:
        _, histories = project_context(project, [])
        histories[entity_id] = {"checked_at": datetime.now(timezone.utc).isoformat(), **result}
        path = project.root / "archive-availability.json"
        project.root.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(histories, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
