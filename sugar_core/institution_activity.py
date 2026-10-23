"""Evidence-based activity proposals, separate from the registry's reviewed status.

Group 1 section 10 supplies the six display labels. The historical window starts
in 2024; dated current programming uses a rolling twelve-month window.
Archive captures and retrieval timestamps never count as program activity.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .temporal import rolling_year_start, timestamp as parse_timestamp

BASELINE = "2024-01-01"
PROGRAM = re.compile(r"\b(courses?|classes|registration|enrol[l]?ment|programming|workshops?|conferences?|competitions?|held|hosted|events?|scholarships?|taller(?:es)?|inscripci[oó]n(?:es)?|eventos?|cursos?|oficinas?|forma[cç][aã]o|inscri[cç][aã]o|inscri[cç][oõ]es|cours|inscriptions?|ateliers?|formations?|[eé]v[eé]nements?)\b|课程|活动|招生|课程报名|课程注册", re.I)
# Latin text is accent-folded before matching; original evidence is preserved.
NEGATIVE = re.compile(r"\b(cancel(?:led|ed|lations?)|suspend(?:ed|u|ue|us|ues)|closed|closures?|closing|ceased|discontinued|terminated?|terminations?|shut[ -]+down|shutdowns?|no longer|will not|did not|not holding|cerr(?:o|aron|ar|ara|ad[oa]s?)|cierres?|clausur(?:a|ad[oa]s?)|cancelad[oa]s?|cancelacion(?:es)?|suspendid[oa]s?|suspensiones?|encerrad[oa]s?|encerramentos?|fechad[oa]s?|fechamentos?|suspens[oa]s?|suspensao|fermetures?|ferme(?:e|es|ees)?|annul(?:e|es|ee|ees|ations?)|cessation)\b|取消|关闭|暂停", re.I)
PRESENCE = re.compile(r"\b(staff|contact|address|director|institute|centre|center)\b|联系|地址|教师", re.I)
PERIOD = re.compile(r"(?:autumn|fall|spring|summer|winter|january|february|march|april|may|june|july|august|september|october|november|december|otoño|primavera|verano|invierno|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|outono|verão|inverno|janeiro|fevereiro|março|maio|junho|julho|setembro|outubro|automne|printemps|hiver|été|janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(?:de\s+)?((?:19|20)\d{2})|((?:19|20)\d{2})年(?:春|夏|秋|冬)季?", re.I)
REGISTRATION = re.compile(r"\b(?:registration|enrolment|enrollment|inscripcion(?:es)?|inscription(?:s)?|inscricao|inscricoes)\s+(?:(?:is|are|now|already|est[aá]n?|abierta[s]?|estao|sont|est|a|as|estara)\s+){0,3}(?:open|opens|opened|abiert[oa]s?|abert[oa]s?|ouvert(?:e|es|s)?)\b|\bregister\s+(?:now|for)\b|\bheld\s+on\b|\b(?:se\s+celebr(?:a|o)|realizado|teve lugar|a eu lieu)\b|报名(?:开放|开始)|开放报名|开始招生|举行于|举办于", re.I)


def _program_context(quote: str, event_dates: list[str], year: int) -> tuple[bool, str, str, bool]:
    """A menu keyword alone is never program evidence. Dates must share a clause."""
    periods: list[tuple[str, str]] = []
    explicit = False
    for clause in re.split(r"[.!?。！？\n|;]", quote):
        programs = list(PROGRAM.finditer(clause))
        if not programs:
            continue
        folded = "".join(c for c in unicodedata.normalize("NFD", clause) if not unicodedata.combining(c))
        explicit |= bool(REGISTRATION.search(folded))
        for period in PERIOD.finditer(clause):
            if any(max(period.start() - p.end(), p.start() - period.end(), 0) <= 100 for p in programs):
                periods.append((period.group(1) or period.group(2), period.group(0)))
        for date in re.finditer(r"\b(?:19|20)\d{2}(?:-\d{2}-\d{2})?\b", clause):
            if any(max(date.start() - p.end(), p.start() - date.end(), 0) <= 32 for p in programs):
                if not re.search(r"founded|fundad|fond[eé]|established|copyright|©", clause, re.I):
                    periods.append((date.group(0)[:4], date.group(0)))
    # Prefer the complete named period over the year alone; never invent a day.
    period_year, period = max(periods, key=lambda p: (p[0], len(p[1])), default=("", ""))
    historical = bool(period_year and int(period_year) < year - 1 and not event_dates)
    return bool(event_dates or periods or explicit) and not historical, period, period_year, historical


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
    current_start = rolling_year_start(now)
    horizon = now.date().replace(year=now.year + 1, day=28 if now.month == 2 and now.day == 29 else now.day).isoformat()
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
        folded = "".join(c for c in unicodedata.normalize("NFD", quote) if not unicodedata.combining(c))
        negative = bool(NEGATIVE.search(folded) or metadata.get("cancelled_events"))
        program, period, period_year, historical = _program_context(quote, event_dates, now.year)
        program = program and not negative
        event_date = max((d for d in event_dates if d <= today), default="")
        upcoming = min((d for d in event_dates if d > today), default="")
        date = event_date or stamp
        if date > today:
            date = ""  # Future publication timestamps do not prove activity.
        key = (url, date, kind, quote)
        if key in seen:
            continue
        seen.add(key)
        signals.append({"kind": kind, "date": date, "date_basis": "structured_event_date" if event_date else "publication_date" if date else "undated",
                        "url": url, "item_id": item.item_id if item else link.get("item_id", ""), "run_id": item.run_id if item else link.get("run_id", ""),
                        "quote": quote[:600], "official": official, "program": program, "negative_cue": negative,
                        "upcoming_date": upcoming, "presence": bool(PRESENCE.search(quote)), "historical_cue": historical,
                        "program_period": period, "program_year": period_year,
                        "association": str(link.get("association") or "recorded_link_or_citation")})
    dated = [s for s in signals if s["date"]]
    activity = [s for s in dated if (s["program"] or s["kind"] == "known_account_post") and not s["negative_cue"] and not s["historical_cue"]]
    for signal in signals:
        # Republished, undated prior-year program descriptions establish medium
        # confidence; an actual event/publication date can remain current across January 1.
        dated_current = bool(signal["date"] and current_start <= signal["date"] <= today)
        republished_old_period = bool(signal["program_year"] and signal["program_year"] < year and signal["date"].startswith(year) and signal["date_basis"] == "publication_date")
        future_period = bool(signal["program_year"] and signal["program_year"] > year)
        signal["current_program"] = bool(signal["official"] and signal["program"] and (
            (dated_current and not republished_old_period and not future_period)
            or today < signal["upcoming_date"] <= horizon or signal["program_year"] == year))
    current = [s for s in signals if s["current_program"]]
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
        reasons.append(f"An institution website supplies dated program evidence in the rolling window {current_start}–{today}, a current program year, or upcoming programming within twelve months.")
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
            "current_window_start": current_start,
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
