"""Deterministic natural-language interpretation of a research request.

This is the *non-LLM* interpreter. It exists for offline use, reproducibility, tests, and as the
fallback when a model provider is unavailable. Unlike a keyword/`source=...` syntax it accepts
ordinary sentences ("Search democracy in the Middle East on all platforms") and produces a
plan payload for :func:`sugar_core.research_plan.build_plan`.

It records every default it applied as an *assumption* so the plan preview can show the
researcher what was inferred rather than stated.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from . import gazetteer as gz
from .research_plan import (
    _PLATFORM_ALIASES, KNOWN_UNSUPPORTED_PLATFORMS, default_question, ResearchPlanSpec,
)

_MONTHS = {name.casefold(): i for i, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.casefold(): i for i, name in enumerate(calendar.month_abbr) if name})
_MONTHS["sept"] = 9
_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "couple": 2, "few": 3, "several": 4,
}
_UNITS = {"day": "days", "week": "weeks", "month": "months", "year": "years"}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_PREP = r"(?:in|across|throughout|within|around|from|for|about|among|inside|of|regarding|concerning|over)"


@dataclass
class DeterministicResult:
    payload: dict[str, Any]
    assumptions: list[str] = field(default_factory=list)
    clarifications: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    defaulted_fields: list[str] = field(default_factory=list)
    confidence: float = 0.0


def _add_months(day: date, months: int) -> date:
    index = day.month - 1 + months
    year = day.year + index // 12
    month = index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _number(token: str) -> int:
    token = token.casefold()
    return int(token) if token.isdigit() else _NUMBER_WORDS.get(token, 0)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _blank(work: str, span: tuple[int, int]) -> str:
    return work[:span[0]] + " ; " + work[span[1]:]


def _parse_timeframe(work: str, today: date) -> tuple[str, dict[str, str] | None, str]:
    """Find one time expression, remove it from ``work``, and return (work, timeframe, note)."""
    y = r"(?P<{}>(?:19|20)\d{{2}})"
    month_or_none = rf"(?:(?P<{{}}>{_MONTH_RE})\.?\s+)?"

    def build(start: date | None, end: date | None, label: str) -> dict[str, str]:
        return {"start": start.isoformat() if start else "", "end": end.isoformat() if end else "", "label": label}

    # between/from A and/to B  (years or month-years)
    m = re.search(rf"\b(?:between|from)\s+{month_or_none.format('m1')}{y.format('y1')}\s*(?:and|to|through|until|till|-|–|—)\s*{month_or_none.format('m2')}{y.format('y2')}\b", work, re.I)
    if m:
        y1, y2 = int(m["y1"]), int(m["y2"])
        start = _month_bounds(y1, _MONTHS[m["m1"].casefold()])[0] if m["m1"] else date(y1, 1, 1)
        end = _month_bounds(y2, _MONTHS[m["m2"].casefold()])[1] if m["m2"] else date(y2, 12, 31)
        return _blank(work, m.span()), build(start, end, f"{y1} to {y2}"), ""
    m = re.search(r"\b((?:19|20)\d{2})\s*[-–—]\s*((?:19|20)\d{2})\b", work)
    if m:
        return _blank(work, m.span()), build(date(int(m[1]), 1, 1), date(int(m[2]), 12, 31), f"{m[1]} to {m[2]}"), ""
    # last/past N units
    m = re.search(r"\b(?:in\s+|over\s+|during\s+|within\s+)?(?:the\s+)?(?:last|past|previous|preceding)\s+(?:(\d+|" + "|".join(_NUMBER_WORDS) + r")(?:\s+of)?\s+)?(day|week|month|year)s?\b", work, re.I)
    if m:
        n = _number(m[1]) if m[1] else 1
        unit = m[2].casefold()
        if unit == "day":
            start = today - timedelta(days=n)
        elif unit == "week":
            start = today - timedelta(weeks=n)
        elif unit == "month":
            start = _add_months(today, -n)
        else:
            start = _add_months(today, -12 * n)
        label = f"Last {n} {unit}{'s' if n != 1 else ''}"
        note = "'A few/several/couple' was read as a number." if m[1] and m[1].casefold() in {"few", "several", "couple"} else ""
        return _blank(work, m.span()), build(start, today, label), note
    # since / after / from  (month year | year | last year)
    m = re.search(rf"\b(?:since|after|from|starting(?:\s+in)?|beginning(?:\s+in)?)\s+{month_or_none.format('m')}{y.format('y')}(?:\s+(?:onwards?|on|forward))?\b", work, re.I)
    if m:
        year = int(m["y"])
        start = _month_bounds(year, _MONTHS[m["m"].casefold()])[0] if m["m"] else date(year, 1, 1)
        return _blank(work, m.span()), build(start, None, f"Since {m['m'].capitalize() + ' ' if m['m'] else ''}{year}"), ""
    m = re.search(r"\bsince\s+last\s+(week|month|year)\b", work, re.I)
    if m:
        unit = m[1].casefold()
        start = today - timedelta(weeks=1) if unit == "week" else _add_months(today, -1 if unit == "month" else -12)
        return _blank(work, m.span()), build(start, None, f"Since last {unit}"), ""
    # before / until / through
    m = re.search(rf"\b(before|until|till|through|up\s+to|prior\s+to)\s+{month_or_none.format('m')}{y.format('y')}\b", work, re.I)
    if m:
        year = int(m["y"])
        first, last = _month_bounds(year, _MONTHS[m["m"].casefold()]) if m["m"] else (date(year, 1, 1), date(year, 12, 31))
        inclusive = m[1].casefold() in {"until", "till", "through", "up to"}
        end = last if inclusive else first - timedelta(days=1)
        return _blank(work, m.span()), build(None, end, f"{m[1].capitalize()} {m['m'].capitalize() + ' ' if m['m'] else ''}{year}"), ""
    # month + year / year / decade
    m = re.search(rf"\b(?:in|during|of|from|throughout)?\s*(?P<m>{_MONTH_RE})\.?\s+(?P<y>(?:19|20)\d{{2}})\b", work, re.I)
    if m:
        first, last = _month_bounds(int(m["y"]), _MONTHS[m["m"].casefold()])
        return _blank(work, m.span()), build(first, last, f"{m['m'].capitalize()} {m['y']}"), ""
    m = re.search(r"\b(?:in|during|throughout)?\s*(?:the\s+)?((?:19|20)\d0)'?s\b", work, re.I)
    if m:
        decade = int(m[1])
        return _blank(work, m.span()), build(date(decade, 1, 1), date(decade + 9, 12, 31), f"The {decade}s"), ""
    m = re.search(r"\b(?:in|during|throughout|of|for)\s+((?:19|20)\d{2})\b", work, re.I)
    if m:
        year = int(m[1])
        return _blank(work, m.span()), build(date(year, 1, 1), date(year, 12, 31), str(year)), ""
    m = re.search(r"\b(this|current)\s+(year|month|week)\b|\b(year[\s-]to[\s-]date|ytd)\b", work, re.I)
    if m:
        unit = (m[2] or "year").casefold()
        start = date(today.year, 1, 1) if unit == "year" else date(today.year, today.month, 1) if unit == "month" else today - timedelta(days=today.weekday())
        return _blank(work, m.span()), build(start, today, f"This {unit}"), ""
    m = re.search(r"\b(yesterday|today)\b", work, re.I)
    if m:
        day = today - timedelta(days=1) if m[1].casefold() == "yesterday" else today
        return _blank(work, m.span()), build(day, day, m[1].capitalize()), ""
    m = re.search(r"\b(recent(?:ly)?|latest|lately|these days|nowadays|right now|currently)\b", work, re.I)
    if m:
        return _blank(work, m.span()), build(today - timedelta(days=30), today, "Recent (last 30 days)"), "'Recent' was read as the last 30 days."
    # A bare year is more often part of a name ("Vision 2030"), so it is not treated as a date.
    return work, None, ""


def _split_terms(value: str) -> list[str]:
    parts = re.split(r"\s*(?:,|;|\band\b|\bor\b|&|/)\s*", value)
    return [p.strip(" .\"'“”") for p in parts if p.strip(" .\"'“”")]


_LEAD_PATTERNS = [
    r"^(?:hey|hi|hello|ok(?:ay)?|so)[,!\s]+",
    r"^(?:please|kindly)\s+",
    r"^(?:can|could|would|will)\s+you\s+(?:please\s+)?",
    r"^(?:i\s+(?:want|need|would\s+like|'d\s+like|wish)\s+(?:you\s+)?to\s+|i\s+(?:want|need)\s+to\s+|i'?d\s+like\s+to\s+|let'?s\s+|help\s+me\s+(?:to\s+)?|we\s+(?:want|need)\s+to\s+)",
    r"^(?:go\s+and\s+)?(?:search|searching|find|finding|look|looking|research|researching|investigate|investigating|explore|exploring|collect|collecting|gather|gathering|scan|scanning|monitor|monitoring|track|tracking|watch|watching|pull|get|show|display|analy[sz]e|analy[sz]ing|study|survey|see|check|discover|dig|scrape|fetch|learn|read|understand|query|run\s+a\s+search)(?:\s+(?:up|out|for|into|at|through|on|about|around|me|us|posts|content|data|info|information))*\b[\s:,-]*",
    r"^(?:what|how)\s+(?:(?:are|do|does|did|is|was|were)\s+)?(?:the\s+)?(?:people|users|folks|everyone|everybody|citizens|locals|residents|commentators|researchers|academics|analysts|others|they)\s+(?:(?:are|were|do|did)\s+)?(?:saying|talking|posting|writing|discussing|thinking|feeling|tweeting|sharing|reacting|reporting)(?:\s+(?:about|on|regarding|around|to|of))?\s*",
    r"^(?:(?:what|how)\s+)?(?:(?:do|does|did|would|will|should)\s+)?(?:people\s+)?(?:think|feel|say|see|view|believe|talk)\w*\s+(?:about|of|on|regarding|to)\s+",
    r"^(?:tell|give|show)\s+(?:me|us)\s+(?:(?:more|everything|something|anything|all|what\s+you\s+can\s+find)\s+)?(?:about|on|regarding|around)?\s*",
    r"^i(?:'m|\s+am)\s+(?:interested\s+in|researching|studying|looking\s+(?:at|into|for)|curious\s+about|investigating|exploring)\s+",
    r"^(?:what(?:'s|\s+is|\s+are|\s+was|\s+were)|how(?:'s|\s+is|\s+are|\s+was|\s+were)|why(?:\s+is|\s+are)?|where)\s+(?:the\s+)?(?:conversation|discourse|discussion|debate|narrative|sentiment|opinion|talk|buzz|coverage|chatter|reaction)s?\s+(?:on|about|around|regarding|of|to)\s+",
    r"^(?:what(?:'s|\s+is|\s+are)|how(?:'s|\s+is|\s+are)|why\s+is)\s+",
    r"^(?:public\s+)?(?:opinions?|sentiment|attitudes?|views?|perceptions?|reactions?|discussions?|discourse|conversations?|debate|narratives?|posts?|content|mentions?|coverage|chatter|information|everything|anything|news|talk|buzz)\s+(?:on|about|of|regarding|around|concerning|to)\s+",
    r"^(?:the\s+)?(?:topic|subject|issue|theme|question)\s+(?:of\s+)?",
]
_TRAIL_PATTERNS = [
    r"[\s,;.!?]*(?:please|thanks|thank\s+you|for\s+me|for\s+us|now|asap)\s*$",
    r"\s+(?:is|are|was|were|has\s+been|have\s+been|being)?\s*(?:discussed|talked\s+about|perceived|viewed|covered|received|framed|portrayed|debated|reported|described|reacted\s+to|mentioned|posted\s+about)\s*$",
    r"\s+(?:posts?|content|discussions?|conversations?|mentions?|discourse|chatter|opinions?)\s*$",
]


def _strip_edges(topic: str) -> str:
    topic = topic.strip(" \t;:,.!?-–—\"'“”()[]")
    previous = None
    while previous != topic:
        previous = topic
        topic = re.sub(r"^(?:about|regarding|concerning|for|on|of|into|around|the|to|and|in|with|by|that|whether|how|what|why)\s+", "", topic, flags=re.I).strip(" ;:,.-")
        topic = re.sub(r"\s+(?:in|on|of|about|across|for|and|or|the|to|with|by|from|at|regarding|through|throughout|within)$", "", topic, flags=re.I).strip(" ;:,.-")
    return re.sub(r"\s+", " ", topic)


def _platform_spans(text: str) -> tuple[list[tuple[int, int, str]], list[tuple[int, int, str]]]:
    """Return (supported, unsupported) platform mentions as (start, end, canonical/label)."""
    supported: list[tuple[int, int, str]] = []
    for alias, canonical in sorted(_PLATFORM_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if alias == "x":
            continue
        pattern = rf"(?<![\w.\-])({re.escape(alias)})(?![\w\-]|\.\w)"
        for m in re.finditer(pattern, text, re.I):
            supported.append((m.start(1), m.end(1), canonical))
    for m in re.finditer(r"(?<![\w.\-])X(?![\w\-])", text):     # capital X only
        before = text[:m.start()].rstrip().casefold()
        after = text[m.end():].lstrip().casefold()
        previous_word = before.split()[-1] if before.split() else ""
        listy = previous_word in {"on", "via", "using", "across", "and", "or", "from", "in", "through", "including", "plus", "with"} or before.endswith(",")
        following = re.match(r"(?:$|[,.;:!?]|and\b|or\b|only\b|posts?\b|platform\b|accounts?\b|users?\b|&)", after) is not None
        if (listy and following) or re.match(r"(?:posts?|platform|accounts?)\b", after):
            supported.append((m.start(), m.end(), "x"))
    unsupported: list[tuple[int, int, str]] = []
    for alias, label in KNOWN_UNSUPPORTED_PLATFORMS.items():
        for m in re.finditer(rf"(?<![\w.\-]){re.escape(alias)}(?![\w\-])", text, re.I):
            # 'threads'/'vk' are ordinary words in some contexts: require a platform-ish preposition.
            if alias in {"threads", "vk"} and not re.search(r"\b(?:on|via|using|across|from)\s+$", text[:m.start()], re.I):
                continue
            unsupported.append((m.start(), m.end(), label))
    supported.sort()
    # drop overlapping shorter spans
    merged: list[tuple[int, int, str]] = []
    for span in supported:
        if merged and span[0] < merged[-1][1]:
            continue
        merged.append(span)
    return merged, sorted(unsupported)


def _gazetteer_matches(text: str) -> list[tuple[int, int, str, str]]:
    """(start, end, canonical, kind) for regions/countries/demonyms, longest first, non-overlapping."""
    entries: list[tuple[str, str, str]] = []
    for name in gz.REGIONS:
        entries.append((name.casefold(), name, "region"))
    for alias, canonical in gz.REGION_ALIASES.items():
        entries.append((alias.casefold(), canonical, "region"))
    for name in gz.all_countries():
        entries.append((name.casefold(), name, "country"))
    for alias, canonical in gz.COUNTRY_ALIASES.items():
        if canonical:
            entries.append((alias.casefold(), canonical, "country"))
    for alias, canonical in gz.DEMONYMS.items():
        entries.append((alias.casefold(), canonical, "demonym"))
    entries.sort(key=lambda e: -len(e[0]))
    taken: list[tuple[int, int, str, str]] = []
    lowered = text.casefold()
    for key, canonical, kind in entries:
        for m in re.finditer(rf"(?<![\w'’\-]){re.escape(key)}(?![\w\-])", lowered):
            span = (m.start(), m.end())
            if any(span[0] < t[1] and t[0] < span[1] for t in taken):
                continue
            taken.append((span[0], span[1], canonical, kind))
    return sorted(taken)


def interpret_deterministic(
    text: str,
    *,
    today: date | None = None,
    available_platforms: set[str] | None = None,
) -> DeterministicResult:
    today = today or date.today()
    original = " ".join(str(text or "").split())
    result = DeterministicResult(payload={})
    if not original:
        result.clarifications.append("What would you like to research?")
        return result
    work = original
    assumptions = result.assumptions

    # 1. quoted phrases are exact search terms, but remain part of the topic text
    quoted = [q.strip() for q in re.findall(r"[\"“]([^\"”]{2,120})[\"”]", work)]
    work = re.sub(r"[\"“”]", "", work)

    # 2. exclusions
    exclusions: list[str] = []
    m = re.search(
        r"[,;(]?\s*\b(?:excluding|exclude|except(?:\s+for)?|but\s+not|not\s+including|ignoring|ignore|skip(?:ping)?|omit(?:ting)?|other\s+than|leaving\s+out|filter\s+out|without\s+(?:any\s+)?(?:mentions?\s+of\s+)?)\s+(.+?)(?=\s+(?:and\s+only|only|on|across|via|since|from|between|during|in\s+the\s+last|in\s+(?:19|20)\d{2}|over\s+the|within|using)\b|[.;!?)]|$)",
        work, re.I)
    if m:
        exclusions = _split_terms(m[1])
        work = _blank(work, m.span())

    # 3. translation policy
    translation_policy = ""
    target_language = ""
    m = re.search(r"\b(?:don'?t|do\s+not|no|without|skip)\s+translat\w*", work, re.I)
    if m:
        translation_policy = "never"
        work = _blank(work, m.span())
    else:
        m = re.search(r"\b(?:and\s+|then\s+|with\s+)?(?:auto[\s-]?)?translat(?:e|ed|ing|ion|ions)\b(?:\s+(?:it|them|everything|results|posts|all|the\s+results))?(?:\s+(?:to|into)\s+([A-Za-z]+))?", work, re.I)
        if m:
            translation_policy = "always"
            if m[1] and gz.language_code(m[1]) not in {"", "auto"}:
                target_language = gz.LANGUAGE_NAMES.get(gz.language_code(m[1]), m[1].capitalize())
            work = _blank(work, m.span())

    # 4. depth
    depth = ""
    m = re.search(r"\b(?:a\s+)?(deep(?:er|ly)?|in[\s-]depth|thorough(?:ly)?|comprehensive(?:ly)?|exhaustive(?:ly)?|extensive(?:ly)?|full)\s+(?:search|dive|scan|collection|sweep|review)\b|\b(?:go|dig)\s+deep\b|\b(?:very\s+)?(quick(?:ly)?|brief(?:ly)?|fast|light|shallow|rapid)\s+(?:search|scan|overview|check|pass)\b|\b(quick(?:ly)?|briefly)\b", work, re.I)
    if m:
        word = (m[1] or m[2] or m[3] or m[0]).casefold()
        depth = "deep" if any(k in word for k in ("deep", "depth", "thorough", "comprehensive", "exhaustive", "extensive", "full")) or "go deep" in m[0].casefold() or "dig deep" in m[0].casefold() else "quick"
        work = _blank(work, m.span())

    # 5. monitoring intent (only the cadence/alert words are removed; the verb is handled below)
    collection_mode = "discovery"
    refresh: dict[str, Any] = {}
    cadence_re = r"\b(?:(?:on\s+a\s+)?(?:daily|weekly|hourly)(?:\s+basis)?|every\s+(?:day|week|hour)|ongoing|continuous(?:ly)?|alert\s+me|notify\s+me|keep\s+(?:an\s+eye\s+on|watching|monitoring|tracking))\b"
    cadence = re.findall(cadence_re, work, re.I)
    if cadence:
        text_cadence = " ".join(cadence).casefold()
        collection_mode = "monitoring"
        hours = 168 if "week" in text_cadence else 1 if "hour" in text_cadence else 24
        refresh = {"mode": "scheduled", "interval_hours": hours, "change_detection": True,
                   "notify_on_new": bool(re.search(r"alert|notify", text_cadence))}
        assumptions.append(f"Monitoring intent detected; the plan refreshes every {hours} hours once scheduled collection is enabled.")
        work = re.sub(cadence_re, " ; ", work, flags=re.I)

    # 6. platforms
    all_platforms = False
    m = re.search(r"\b(?:on|across|via|through|from|in|using|over)?\s*(?:absolutely\s+)?(?:all|every|any|each)\s+(?:of\s+)?(?:the\s+)?(?:enabled\s+|available\s+|supported\s+|major\s+|possible\s+)?(?:platforms?|sources?|networks?|social(?:\s+media)?(?:\s+(?:platforms?|sites?|networks?|channels?))?|channels?|sites?|apps?|services?)\b|\beverywhere\b|\bacross\s+(?:the\s+)?(?:whole\s+)?(?:internet|web)\b", work, re.I)
    if m:
        all_platforms = True
        work = _blank(work, m.span())
    supported, unsupported = _platform_spans(work)
    named_platforms = [canonical for _, _, canonical in supported]
    unsupported_labels = [label for _, _, label in unsupported]
    marks = sorted([(s, e) for s, e, _ in supported] + [(s, e) for s, e, _ in unsupported])
    if marks:
        pieces: list[str] = []
        cursor = 0
        for s, e in marks:
            pieces.append(work[cursor:s])
            pieces.append("\x00")
            cursor = e
        pieces.append(work[cursor:])
        work = "".join(pieces)
        work = re.sub(r"(?:\b(?:on|via|using|across|from|in|through|including|with|only|just|both|the)\s+)*\x00(?:\s*(?:,|and|or|&|plus|as\s+well\s+as)\s*\x00)*(?:\s+(?:platforms?|accounts?|posts?|users?|only|too|as\s+well))*", " ; ", work, flags=re.I)
        work = work.replace("\x00", " ; ")

    # 7. languages
    languages: list[str] = []
    lang_names = "|".join(sorted(gz.LANGUAGES, key=len, reverse=True))
    m = re.search(rf"\b(?:written\s+)?(?:in|using|via)\s+((?:{lang_names})(?:\s*(?:,|and|or|&|plus|as\s+well\s+as)\s*(?:{lang_names}))*)\b(?:\s+(?:language|languages|text|posts?))?", work, re.I)
    if m:
        languages = [gz.language_code(x) for x in re.findall(lang_names, m[1], re.I)]
        work = _blank(work, m.span())
    else:
        found = re.findall(rf"\b({lang_names})[\s-]language\b", work, re.I)
        if found:
            languages = [gz.language_code(x) for x in found]
            work = re.sub(rf"\b(?:{lang_names})[\s-]language\b", " ; ", work, flags=re.I)
    languages = [x for x in dict.fromkeys(languages) if x]

    # 8. timeframe
    work, timeframe, time_note = _parse_timeframe(work, today)
    if time_note:
        assumptions.append(time_note)

    # 9. geography
    geography: list[str] = []
    geo_spans = _gazetteer_matches(work)
    if geo_spans:
        pieces = []
        cursor = 0
        for s, e, canonical, kind in geo_spans:
            if canonical not in geography:
                geography.append(canonical)
            pieces.append(work[cursor:s])
            pieces.append("\x01")
            cursor = e
        pieces.append(work[cursor:])
        work = "".join(pieces)
        work = re.sub(rf"(?:\b{_PREP}\s+)?(?:\b(?:the|and|between|both)\s+)*\x01(?:\s*(?:,|and|or|&|plus)\s*\x01)*(?:\s+(?:region|area|countries|states|nations|world))?", " ; ", work, flags=re.I)
        work = work.replace("\x01", " ; ")
    else:
        m = re.search(r"\b(?:in|across|throughout|within|around|inside)\s+(?:the\s+)?([A-Z][\w'’\-]+(?:\s+(?:of\s+|and\s+)?[A-Z][\w'’\-]+)*)", work)
        if m and m.start() > 0 and m[1].casefold() not in {"congress", "english", "arabic", "spanish", "french", "russian", "i", "us"}:
            geography.append(m[1])
            assumptions.append(f"Treating “{m[1]}” as a place name (it is not in SUGAR's built-in list).")
            work = _blank(work, m.span())

    # 10. strip command/filler and derive the topic (each ';'-separated fragment is cleaned separately)
    stop_only = re.compile(r"^(?:what|how|why|do|does|did|is|are|was|were|the|a|an|and|or|to|of|in|on|about|please|me|us|i|we|you|people|it|them)(?:\s+(?:what|how|why|do|does|did|is|are|was|were|the|a|an|and|or|to|of|in|on|about|please|me|us|i|we|you|people|it|them))*$", re.I)

    def clean_fragment(fragment: str) -> str:
        fragment = fragment.strip(" \t;:,.!?-–—")
        changed = True
        while changed:
            changed = False
            for pattern in _LEAD_PATTERNS:
                new = re.sub(pattern, "", fragment, count=1, flags=re.I)
                if new != fragment:
                    fragment, changed = new.strip(" \t;:,.-"), True
            for pattern in _TRAIL_PATTERNS:
                new = re.sub(pattern, "", fragment, count=1, flags=re.I)
                if new != fragment:
                    fragment, changed = new.strip(" \t;:,.-"), True
        fragment = _strip_edges(fragment)
        return "" if stop_only.match(fragment or "x x") and not re.search(r"[A-Z]{2,}", fragment) else fragment

    segments = [s for s in (clean_fragment(part) for part in work.split(";")) if s]
    topic = max(segments, key=len) if segments else ""
    if len(segments) > 1:
        rest = [s for s in segments if s != topic and len(s) > 3]
        if rest:
            assumptions.append("Extra phrases (" + "; ".join(rest[:3]) + ") were not treated as the topic.")

    # analysis goals
    goals: list[str] = []
    lowered = original.casefold()
    for pattern, goal in ((r"\bsentiment|opinion|attitude|perception|feel", "sentiment"), (r"\bsummar", "summary"),
                          (r"\btrend|over\s+time|timeline", "trends"), (r"\bcompar", "comparison"),
                          (r"\btheme|narrative|frame|framing", "themes"), (r"\binfluencer|key\s+voices|who\s+is\s+saying", "key voices")):
        if re.search(pattern, lowered) and goal not in goals:
            goals.append(goal)

    search_terms = list(dict.fromkeys(quoted))
    subtopics = [s for s in _split_terms(topic) if len(s) >= 3] if re.search(r",|\band\b|\bor\b|/|&", topic) else []
    if 1 < len(subtopics) <= 4:
        search_terms.extend(s for s in subtopics if s not in search_terms)

    # clarification is only requested when the essential property cannot be inferred
    if not topic:
        if geography:
            result.clarifications.append(f"What about {', '.join(geography)} would you like to research?")
        else:
            result.clarifications.append("What subject would you like to research?")

    payload: dict[str, Any] = {
        "topic": topic,
        "geography": geography,
        "exclusions": exclusions,
        "search_terms": search_terms,
        "analysis_goals": goals,
        "collection_mode": collection_mode,
    }
    if timeframe:
        payload["timeframe"] = timeframe
    else:
        result.defaulted_fields.append("timeframe")
    payload["languages"] = languages or ["auto"]
    if not languages:
        result.defaulted_fields.append("languages")
    if named_platforms and not all_platforms:
        payload["source_scope"] = "selected"
        payload["platforms"] = list(dict.fromkeys(named_platforms))
    else:
        payload["source_scope"] = "all_enabled"
        if named_platforms:
            payload["platforms"] = []
        if not all_platforms:
            result.defaulted_fields.append("platforms")
            assumptions.append("No platforms were named, so every enabled platform will be searched.")
    for label in dict.fromkeys(unsupported_labels):
        result.warnings.append(f"{label} is not a collector SUGAR supports yet, so it was left out.")
    if depth:
        payload["depth"] = depth
    else:
        result.defaulted_fields.append("depth")
    if refresh:
        payload["refresh"] = refresh
    if translation_policy or target_language:
        payload["translation"] = {"policy": translation_policy or "always", **({"target_language": target_language} if target_language else {})}
    is_question = original.rstrip().endswith("?") or bool(re.match(r"(?i)^(?:what|how|why|who|where|when|which|is|are|do|does)\b", original))
    if is_question and topic:
        payload["research_question"] = original if original.endswith("?") else original + "?"
    confidence = 0.55
    if topic:
        confidence = 0.85
        if len(topic.split()) > 8:
            confidence -= 0.2
            assumptions.append("The topic is long; review it in the plan preview.")
        if re.search(r"(?i)\b(?:search|find|look|research|show|get)\b", topic):
            confidence -= 0.15
    result.confidence = round(max(0.1, min(0.95, confidence)), 2)
    result.payload = payload
    if topic and "research_question" not in payload:
        # derived question mirrors the preview; the plan builder fills any remaining gaps
        payload["research_question"] = default_question(ResearchPlanSpec(topic=topic, geography=geography))
    return result
