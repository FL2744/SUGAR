"""Typed, persistent research-plan schema.

A ``ResearchPlanSpec`` is the single structured object that connects every entry point:
the natural-language interpreter (LLM or deterministic), the plan preview/editor in the
UI (basic and advanced), the collection pipeline, and the stored ``Run`` record.  Validation
happens against this structure, never against the raw request sentence.

The schema is deliberately extensible: unknown keys survive round trips in ``extra`` so new
fields can be introduced without breaking stored plans or requiring UI rewrites (the UI
renders any scalar/list ``extra`` field generically in Advanced mode).
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field, fields
from datetime import date, datetime, timezone
from typing import Any

DEFAULT_LLM_CALLS = 500   # model calls per run before optional AI work pauses (0 = unlimited)

PLAN_SCHEMA_VERSION = "1.0"

DEPTHS = ("quick", "standard", "deep")
COLLECTION_MODES = ("discovery", "targeted", "monitoring")
SOURCE_SCOPES = ("all_enabled", "selected")
TRANSLATION_POLICIES = ("auto", "always", "never")
REFRESH_MODES = ("manual", "scheduled", "watch")
SOURCE_CATEGORIES = ("social_media", "microblog", "video", "forum", "news", "reference", "scholarly", "web")

# Documented defaults (section 8: optional unspecified fields receive documented defaults).
DEPTH_PRESETS: dict[str, dict[str, int]] = {
    "quick": {"query_count": 3, "max_posts_per_query": 10, "max_pages_per_query": 1},
    "standard": {"query_count": 6, "max_posts_per_query": 25, "max_pages_per_query": 1},
    "deep": {"query_count": 12, "max_posts_per_query": 50, "max_pages_per_query": 3},
}

DEFAULTS_DOC: dict[str, str] = {
    "timeframe": "No date restriction unless the request names one.",
    "languages": "Automatic: SUGAR detects each item's language and searches in the request language.",
    "source_scope": "All enabled platforms (those with a keyword-search collector and available credentials).",
    "collection_mode": "Discovery: broad collection to find out what exists, not a fixed list of targets.",
    "depth": "Standard: about six queries, 25 posts per query, one page per query.",
    "translation": "Automatic: translate non-English items when an LLM provider is configured.",
    "deduplication": "On, near-duplicate threshold 0.90.",
    "concurrency": "Up to 4 platforms searched in parallel, subject to per-platform delays.",
    "retry": "Up to 3 attempts per source with exponential backoff starting at 30 seconds.",
    "refresh": "Manual: nothing re-runs until the researcher asks.",
}

_PLATFORM_ALIASES = {
    "x": "x", "twitter": "x", "x.com": "x", "twitter.com": "x", "twitter/x": "x", "x/twitter": "x", "tweets": "x",
    "bluesky": "bluesky", "bsky": "bluesky", "bsky.app": "bluesky", "blue sky": "bluesky",
    "mastodon": "mastodon", "fediverse": "mastodon",
    "bilibili": "bilibili", "b站": "bilibili", "哔哩哔哩": "bilibili",
    "weibo": "weibo", "sina weibo": "weibo", "微博": "weibo",
    "wechat": "wechat", "weixin": "wechat",
    "wikipedia": "wikipedia", "wiki": "wikipedia", "encyclopedia": "wikipedia",
    "gdelt": "gdelt", "news": "gdelt", "news coverage": "gdelt", "gdelt news": "gdelt",
    "openalex": "openalex", "scholarly": "openalex", "academic": "openalex", "scholarship": "openalex", "papers": "openalex",
    "rss": "rss", "feeds": "rss", "rss feeds": "rss", "atom": "rss",
    "web": "web", "websites": "web", "website": "web", "web pages": "web", "webpages": "web", "sites": "web",
}
# Platforms people commonly name that SUGAR has no collector for; reported, never silently dropped.
KNOWN_UNSUPPORTED_PLATFORMS = {
    "reddit": "Reddit", "facebook": "Facebook", "instagram": "Instagram", "tiktok": "TikTok",
    "youtube": "YouTube", "telegram": "Telegram", "linkedin": "LinkedIn", "threads": "Threads",
    "whatsapp": "WhatsApp", "vk": "VK", "snapchat": "Snapchat", "tumblr": "Tumblr",
}
PLATFORM_CATEGORIES = {
    "x": "microblog", "bluesky": "microblog", "mastodon": "microblog",
    "weibo": "microblog", "bilibili": "video", "wechat": "social_media",
    "wikipedia": "reference", "gdelt": "news", "rss": "news", "openalex": "scholarly", "web": "web",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_platform(value: Any) -> str:
    """Map a user/model-supplied platform name to a SUGAR collector id ('' if unknown)."""
    text = re.sub(r"\s+", " ", str(value or "").strip().casefold())
    return _PLATFORM_ALIASES.get(text, "")


def unsupported_platform_label(value: Any) -> str:
    return KNOWN_UNSUPPORTED_PLATFORMS.get(re.sub(r"\s+", " ", str(value or "").strip().casefold()), "")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _clean_list(values: Any, *, casefold_unique: bool = True) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = re.split(r"[;\n,]", values)
    elif not isinstance(values, (list, tuple, set)):
        values = [values]
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean(value)
        key = text.casefold() if casefold_unique else text
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _iso_date(value: Any) -> str:
    """Return YYYY-MM-DD for common date spellings, or '' if empty; raises ValueError if unusable."""
    text = _clean(value)
    if not text:
        return ""
    if re.fullmatch(r"\d{4}", text):
        return f"{text}-01-01"
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return f"{text}-01"
    text = text.replace("/", "-")
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError as exc:
        raise ValueError(f"'{value}' is not a date; use YYYY-MM-DD.") from exc


def _bounded_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _bounded_float(value: Any, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


@dataclass
class QuerySpec:
    """One concrete search string, optionally bound to a platform, language, or place."""
    text: str
    id: str = ""
    platform: str = ""          # '' = every selected platform
    language: str = ""          # ISO 639-1 code or '' for the request language
    geography: str = ""
    origin: str = "generated"   # generated | analyst | llm | request
    enabled: bool = True
    rationale: str = ""

    def __post_init__(self) -> None:
        self.text = _clean(self.text)
        if not self.text:
            raise ValueError("A query needs text.")
        self.platform = normalize_platform(self.platform) if self.platform else ""
        self.language = _clean(self.language).casefold()
        self.geography = _clean(self.geography)
        self.origin = _clean(self.origin) or "generated"
        self.rationale = _clean(self.rationale)
        self.enabled = bool(self.enabled)
        if not self.id:
            digest = hashlib.sha256(f"{self.text}|{self.platform}|{self.language}".encode("utf-8")).hexdigest()
            self.id = f"q_{digest[:10]}"


@dataclass
class ResearchPlanSpec:
    research_question: str = ""
    topic: str = ""
    geography: list[str] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    timeframe: dict[str, str] = field(default_factory=lambda: {"start": "", "end": "", "label": ""})
    languages: list[str] = field(default_factory=lambda: ["auto"])
    source_scope: str = "all_enabled"
    source_categories: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    exclude_platforms: list[str] = field(default_factory=list)
    search_terms: list[str] = field(default_factory=list)      # analyst / request seed terms
    queries: list[dict[str, Any]] = field(default_factory=list)  # generated + edited QuerySpec rows
    exclusions: list[str] = field(default_factory=list)
    collection_mode: str = "discovery"
    depth: str = "standard"
    limits: dict[str, Any] = field(default_factory=dict)
    translation: dict[str, Any] = field(default_factory=dict)
    dedup: dict[str, Any] = field(default_factory=dict)
    analysis_goals: list[str] = field(default_factory=list)
    provider: dict[str, Any] = field(default_factory=dict)
    refresh: dict[str, Any] = field(default_factory=dict)
    concurrency: dict[str, Any] = field(default_factory=dict)
    retry: dict[str, Any] = field(default_factory=dict)
    extraction: dict[str, Any] = field(default_factory=dict)
    interpretation: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    plan_id: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    schema_version: str = PLAN_SCHEMA_VERSION

    # -- construction -----------------------------------------------------------------
    def __post_init__(self) -> None:
        self.research_question = _clean(self.research_question)
        self.topic = _clean(self.topic)
        self.geography = _clean_list(self.geography)
        self.actors = _clean_list(self.actors)
        tf = dict(self.timeframe or {})
        self.timeframe = {
            "start": _iso_date(tf.get("start")),
            "end": _iso_date(tf.get("end")),
            "label": _clean(tf.get("label")),
        }
        if self.timeframe["start"] and self.timeframe["end"] and self.timeframe["start"] > self.timeframe["end"]:
            raise ValueError("The timeframe start date is after its end date.")
        self.languages = [x.casefold() if x.casefold() == "auto" else x for x in _clean_list(self.languages)] or ["auto"]
        self.source_scope = _clean(self.source_scope).casefold()
        if self.source_scope not in SOURCE_SCOPES:
            raise ValueError(f"source_scope must be one of {', '.join(SOURCE_SCOPES)}.")
        self.source_categories = [c for c in _clean_list(self.source_categories) if c in SOURCE_CATEGORIES]
        self.platforms = _dedupe([normalize_platform(p) or _clean(p).casefold() for p in _clean_list(self.platforms)])
        self.exclude_platforms = _dedupe([normalize_platform(p) or _clean(p).casefold() for p in _clean_list(self.exclude_platforms)])
        self.search_terms = _clean_list(self.search_terms)
        self.exclusions = _clean_list(self.exclusions)
        self.analysis_goals = _clean_list(self.analysis_goals)
        self.collection_mode = _clean(self.collection_mode).casefold()
        if self.collection_mode not in COLLECTION_MODES:
            raise ValueError(f"collection_mode must be one of {', '.join(COLLECTION_MODES)}.")
        self.depth = _clean(self.depth).casefold()
        if self.depth not in DEPTHS:
            raise ValueError(f"depth must be one of {', '.join(DEPTHS)}.")

        preset = DEPTH_PRESETS[self.depth]
        lim = dict(self.limits or {})
        per_source = lim.get("per_source") if isinstance(lim.get("per_source"), dict) else {}
        self.limits = {
            "query_count": _bounded_int(lim.get("query_count"), preset["query_count"], 1, 60),
            "max_posts_per_query": _bounded_int(lim.get("max_posts_per_query"), preset["max_posts_per_query"], 1, 500),
            "max_pages_per_query": _bounded_int(lim.get("max_pages_per_query"), preset["max_pages_per_query"], 1, 20),
            "max_items_total": _bounded_int(lim.get("max_items_total"), 2000, 1, 100000),
            # Soft cap on model calls per run (0 = unlimited). Reaching it never fails a run; see LLMBudget.
            "llm_calls": _bounded_int(lim.get("llm_calls"), DEFAULT_LLM_CALLS, 0, 1000000),
            "per_source": {
                normalize_platform(k) or str(k).casefold(): {
                    kk: _bounded_int(vv, 0, 0, 100000) for kk, vv in dict(v).items()
                    if kk in {"max_posts_per_query", "max_pages_per_query", "max_items"} and _bounded_int(vv, 0, 0, 100000) > 0
                }
                for k, v in per_source.items() if isinstance(v, dict)
            },
        }
        tr = dict(self.translation or {})
        policy = _clean(tr.get("policy", "auto")).casefold()
        self.translation = {
            "policy": policy if policy in TRANSLATION_POLICIES else "auto",
            "target_language": _clean(tr.get("target_language")) or "English",
            "translate_queries": bool(tr.get("translate_queries", True)),
            "max_chars_per_item": _bounded_int(tr.get("max_chars_per_item"), 4000, 200, 20000),
            "workers": _bounded_int(tr.get("workers"), 3, 1, 16),
        }
        dd = dict(self.dedup or {})
        self.dedup = {
            "enabled": bool(dd.get("enabled", True)),
            "threshold": _bounded_float(dd.get("threshold"), 0.9, 0.5, 1.0),
        }
        prov = dict(self.provider or {})
        self.provider = {
            "profile_id": _clean(prov.get("profile_id")),
            "model": _clean(prov.get("model")),     # optional per-plan model override
            "use_for_planning": bool(prov.get("use_for_planning", True)),
        }
        rf = dict(self.refresh or {})
        mode = _clean(rf.get("mode", "manual")).casefold()
        self.refresh = {
            "mode": mode if mode in REFRESH_MODES else "manual",
            "interval_hours": _bounded_int(rf.get("interval_hours"), 24, 1, 24 * 90),
            "watch_queries": _clean_list(rf.get("watch_queries")),
            "watch_sources": _clean_list(rf.get("watch_sources")),
            "change_detection": bool(rf.get("change_detection", True)),
            "notify_on_new": bool(rf.get("notify_on_new", False)),
        }
        cc = dict(self.concurrency or {})
        self.concurrency = {
            "max_workers": _bounded_int(cc.get("max_workers"), 4, 1, 32),
            "per_source_delay_seconds": _bounded_float(cc.get("per_source_delay_seconds"), 0.5, 0.0, 60.0),
        }
        rt = dict(self.retry or {})
        self.retry = {
            "max_attempts": _bounded_int(rt.get("max_attempts"), 3, 1, 10),
            "base_backoff_seconds": _bounded_float(rt.get("base_backoff_seconds"), 30.0, 0.0, 3600.0),
        }
        ex = dict(self.extraction or {})
        self.extraction = {
            "min_chars": _bounded_int(ex.get("min_chars"), 1, 0, 10000),
            "fetch_full_text": bool(ex.get("fetch_full_text", False)),
            "paragraph_split": bool(ex.get("paragraph_split", True)),
        }
        self.queries = [asdict_query(QuerySpec(**_query_kwargs(q))) for q in (self.queries or [])]
        self.interpretation = dict(self.interpretation or {})
        self.extra = dict(self.extra or {})
        if self.version < 1:
            self.version = 1
        now = utc_now()
        self.created_at = self.created_at or now
        self.updated_at = self.updated_at or self.created_at
        if not self.plan_id:
            self.plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        if self.schema_version != PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported research plan schema {self.schema_version!r}; expected {PLAN_SCHEMA_VERSION!r}.")

    # -- accessors --------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy({f.name: getattr(self, f.name) for f in fields(self)})

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ResearchPlanSpec":
        """Strict load. Use ``repair_plan_dict`` first when the payload came from a model."""
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in payload.items() if k in known}
        extra = dict(data.get("extra") or {})
        extra.update({k: v for k, v in payload.items() if k not in known})
        data["extra"] = extra
        return cls(**data)

    def fingerprint(self) -> str:
        """Stable hash of everything that affects collection (not ids/timestamps/interpretation notes)."""
        body = self.to_dict()
        for volatile in ("plan_id", "created_at", "updated_at", "interpretation", "version"):
            body.pop(volatile, None)
        encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    def enabled_queries(self) -> list[QuerySpec]:
        return [QuerySpec(**_query_kwargs(q)) for q in self.queries if q.get("enabled", True)]

    def touch(self, *, bump_version: bool = True) -> None:
        self.updated_at = utc_now()
        if bump_version:
            self.version += 1

    def summary_rows(self) -> list[dict[str, str]]:
        """Human-readable preview rows (section 7) rendered by every client identically."""
        tf = self.timeframe
        if tf["start"] or tf["end"]:
            span = f"{_pretty_date(tf['start']) or 'earliest'} – {_pretty_date(tf['end']) or 'today'}"
            date_text = f"{tf['label']} ({span})" if tf["label"] else span
        else:
            date_text = "No restriction"
        if self.source_scope == "all_enabled":
            platform_text = "All enabled platforms"
            if self.exclude_platforms:
                platform_text += f" except {', '.join(self.exclude_platforms)}"
        else:
            platform_text = ", ".join(self.platforms) or "None selected"
        if self.languages == ["auto"]:
            lang = "Automatic"
        else:
            from .gazetteer import LANGUAGE_NAMES
            lang = ", ".join(LANGUAGE_NAMES.get(code, code) for code in self.languages)
        return [
            {"label": "Research topic", "value": self.topic or "—"},
            {"label": "Region", "value": ", ".join(self.geography) or "Not restricted"},
            {"label": "Platforms", "value": platform_text},
            {"label": "Languages", "value": lang},
            {"label": "Date range", "value": date_text},
            {"label": "Collection depth", "value": self.depth.capitalize()},
        ]


def _pretty_date(value: str) -> str:
    """'2026-04-01' -> '1 Apr 2026' (unparseable values pass through unchanged)."""
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value or "")
    return f"{parsed.day} {parsed.strftime('%b %Y')}"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _query_kwargs(row: dict[str, Any]) -> dict[str, Any]:
    allowed = {f.name for f in fields(QuerySpec)}
    return {k: v for k, v in dict(row).items() if k in allowed}


def asdict_query(query: QuerySpec) -> dict[str, Any]:
    return {f.name: getattr(query, f.name) for f in fields(query)}


# ---------------------------------------------------------------------------------------
# Validation and safe repair
# ---------------------------------------------------------------------------------------
@dataclass
class PlanIssue:
    field: str
    message: str
    severity: str = "warning"     # warning | error
    repaired: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"field": self.field, "message": self.message, "severity": self.severity, "repaired": self.repaired}


_DEPTH_ALIASES = {
    "fast": "quick", "brief": "quick", "light": "quick", "shallow": "quick", "basic": "quick", "quick": "quick",
    "normal": "standard", "default": "standard", "medium": "standard", "standard": "standard", "moderate": "standard",
    "thorough": "deep", "comprehensive": "deep", "exhaustive": "deep", "deep": "deep", "full": "deep", "extensive": "deep",
}
_MODE_ALIASES = {
    "explore": "discovery", "exploratory": "discovery", "discover": "discovery", "broad": "discovery", "discovery": "discovery",
    "targeted": "targeted", "specific": "targeted", "focused": "targeted",
    "monitor": "monitoring", "monitoring": "monitoring", "watch": "monitoring", "ongoing": "monitoring",
}
_POLICY_ALIASES = {"yes": "always", "true": "always", "on": "always", "no": "never", "false": "never", "off": "never", "none": "never"}


def repair_plan_dict(payload: Any, *, available_platforms: set[str] | None = None) -> tuple[dict[str, Any], list[PlanIssue]]:
    """Coerce a loosely-typed (typically model-generated) plan into a strictly valid dictionary.

    Only *safe* repairs are made: type coercion, alias resolution, clamping, dropping unusable
    optional values. Anything that would change meaning (an unparseable date, a missing topic)
    is reported instead of guessed.
    """
    issues: list[PlanIssue] = []
    if not isinstance(payload, dict):
        return {}, [PlanIssue("$", "The plan must be a JSON object.", "error")]
    data = copy.deepcopy(payload)

    def note(name: str, message: str) -> None:
        issues.append(PlanIssue(name, message, "warning", repaired=True))

    for key in ("research_question", "topic"):
        if key in data and not isinstance(data[key], str):
            data[key] = _clean(data[key] if not isinstance(data[key], list) else " ".join(map(str, data[key])))
            note(key, f"Converted {key} to text.")
    for key in ("geography", "actors", "languages", "platforms", "exclude_platforms", "search_terms",
                "exclusions", "analysis_goals", "source_categories"):
        if key in data and not isinstance(data[key], list):
            data[key] = _clean_list(data[key])
            note(key, f"Converted {key} to a list.")
        elif key in data:
            data[key] = [x for x in data[key] if isinstance(x, (str, int, float))]

    depth = _clean(data.get("depth", "standard")).casefold()
    if "depth" in data and depth not in DEPTHS:
        mapped = _DEPTH_ALIASES.get(depth)
        data["depth"] = mapped or "standard"
        note("depth", f"Unrecognized depth '{depth}' replaced with '{data['depth']}'.")
    mode = _clean(data.get("collection_mode", "discovery")).casefold()
    if "collection_mode" in data and mode not in COLLECTION_MODES:
        data["collection_mode"] = _MODE_ALIASES.get(mode, "discovery")
        note("collection_mode", f"Unrecognized collection_mode '{mode}' replaced with '{data['collection_mode']}'.")
    scope = _clean(data.get("source_scope", "")).casefold()
    if scope and scope not in SOURCE_SCOPES:
        data["source_scope"] = "all_enabled" if scope in {"all", "any", "everything", "all_platforms"} else "selected"
        note("source_scope", f"Unrecognized source_scope '{scope}' replaced with '{data['source_scope']}'.")

    # Platforms: resolve aliases, keep unsupported names out of the executable list but report them.
    if "platforms" in data or "exclude_platforms" in data:
        for key in ("platforms", "exclude_platforms"):
            resolved: list[str] = []
            for name in data.get(key) or []:
                canonical = normalize_platform(name)
                if canonical:
                    resolved.append(canonical)
                elif str(name).strip().casefold() in {"all", "all platforms", "everything", "any"} and key == "platforms":
                    data["source_scope"] = "all_enabled"
                    note("source_scope", "'all platforms' interpreted as every enabled platform.")
                else:
                    label = unsupported_platform_label(name) or _clean(name)
                    issues.append(PlanIssue(key, f"{label} is not a collector SUGAR supports; it was left out of the plan.", "warning", True))
            data[key] = _dedupe(resolved)
        if available_platforms is not None:
            kept = [p for p in data.get("platforms", []) if p in available_platforms]
            if len(kept) != len(data.get("platforms", [])):
                note("platforms", "Removed platforms that are not available in this installation.")
            data["platforms"] = kept
        if data.get("platforms") and "source_scope" not in data:
            data["source_scope"] = "selected"
            note("source_scope", "Named platforms imply a selected-platform scope.")
    if data.get("source_scope") == "selected" and not data.get("platforms"):
        data["source_scope"] = "all_enabled"
        note("source_scope", "No usable platforms were named, so all enabled platforms will be used.")

    tf = data.get("timeframe")
    if tf is not None:
        if not isinstance(tf, dict):
            data["timeframe"] = {"start": "", "end": "", "label": ""}
            note("timeframe", "Timeframe was not an object and was cleared.")
        else:
            fixed: dict[str, str] = {"label": _clean(tf.get("label"))}
            for edge in ("start", "end"):
                try:
                    fixed[edge] = _iso_date(tf.get(edge))
                except ValueError as exc:
                    fixed[edge] = ""
                    issues.append(PlanIssue(f"timeframe.{edge}", f"{exc} The date was cleared.", "warning", True))
            if fixed.get("start") and fixed.get("end") and fixed["start"] > fixed["end"]:
                fixed["start"], fixed["end"] = fixed["end"], fixed["start"]
                note("timeframe", "Start and end dates were reversed and have been swapped.")
            data["timeframe"] = fixed

    trans = data.get("translation")
    if isinstance(trans, dict) and "policy" in trans:
        policy = _clean(trans["policy"]).casefold()
        if policy not in TRANSLATION_POLICIES:
            trans["policy"] = _POLICY_ALIASES.get(policy, "auto")
            note("translation.policy", f"Unrecognized translation policy '{policy}' replaced with '{trans['policy']}'.")

    for key in ("limits", "translation", "dedup", "provider", "refresh", "concurrency", "retry", "extraction",
                "interpretation", "extra"):
        if key in data and not isinstance(data[key], dict):
            data[key] = {}
            note(key, f"{key} was not an object and was reset to defaults.")

    if isinstance(data.get("queries"), list):
        cleaned = []
        for row in data["queries"]:
            if isinstance(row, str):
                row = {"text": row, "origin": "llm"}
            if isinstance(row, dict) and _clean(row.get("text")):
                cleaned.append(row)
        if len(cleaned) != len(data["queries"]):
            note("queries", "Dropped empty or malformed queries.")
        data["queries"] = cleaned
    elif "queries" in data:
        data["queries"] = []
        note("queries", "queries was not a list and was cleared.")

    if not _clean(data.get("topic")):
        issues.append(PlanIssue("topic", "A research topic is required and could not be inferred.", "error"))
    return data, issues


def build_plan(payload: dict[str, Any], *, available_platforms: set[str] | None = None) -> tuple[ResearchPlanSpec | None, list[PlanIssue]]:
    """Repair then validate. Returns (plan, issues); plan is None when a blocking error remains."""
    repaired, issues = repair_plan_dict(payload, available_platforms=available_platforms)
    if any(i.severity == "error" for i in issues):
        return None, issues
    try:
        plan = ResearchPlanSpec.from_dict(repaired)
    except (ValueError, TypeError) as exc:
        issues.append(PlanIssue("$", str(exc), "error"))
        return None, issues
    if not plan.research_question:
        plan.research_question = default_question(plan)
        issues.append(PlanIssue("research_question", "Research question was derived from the topic and region.", "warning", True))
    return plan, issues


def default_question(plan: ResearchPlanSpec) -> str:
    where = f" in {', '.join(plan.geography)}" if plan.geography else ""
    return f"What is being said about {plan.topic}{where}?"


# ---------------------------------------------------------------------------------------
# JSON schema handed to a model for constrained output
# ---------------------------------------------------------------------------------------
def interpretation_json_schema() -> dict[str, Any]:
    """Schema for the *interpretation* an LLM fills in.

    It is a strict-mode compatible subset (every property required, no defaults, no additional
    properties). The application expands it to a full ``ResearchPlanSpec`` and applies the
    documented defaults for anything left empty, so a small model can satisfy it reliably.
    """
    strings = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "topic", "research_question", "geography", "actors", "timeframe_start", "timeframe_end",
            "languages", "all_platforms", "platforms", "search_terms", "exclusions", "depth",
            "collection_mode", "translation_policy", "analysis_goals", "assumptions", "clarifications",
        ],
        "properties": {
            "topic": {"type": "string", "description": "The core subject to research, without places, dates, platforms or command words."},
            "research_question": {"type": "string", "description": "One neutral sentence stating what is being researched."},
            "geography": {**strings, "description": "Places the research is about (regions, countries, cities). Empty if none."},
            "actors": {**strings, "description": "Named organizations, people, or groups in scope. Empty if none."},
            "timeframe_start": {"type": "string", "description": "YYYY-MM-DD or empty string if no start was implied."},
            "timeframe_end": {"type": "string", "description": "YYYY-MM-DD or empty string if no end was implied."},
            "languages": {**strings, "description": "Language names or ISO codes requested; ['auto'] when unspecified."},
            "all_platforms": {"type": "boolean", "description": "True when the request says all/any platforms or names none."},
            "platforms": {**strings, "description": "Specific platforms named (e.g. x, bluesky, mastodon, bilibili, weibo)."},
            "search_terms": {**strings, "description": "Extra search terms, synonyms, or quoted phrases the researcher would want."},
            "exclusions": {**strings, "description": "Topics or terms to exclude."},
            "depth": {"type": "string", "enum": list(DEPTHS)},
            "collection_mode": {"type": "string", "enum": list(COLLECTION_MODES)},
            "translation_policy": {"type": "string", "enum": list(TRANSLATION_POLICIES)},
            "analysis_goals": {**strings, "description": "Outputs the researcher asked for (e.g. summary, themes)."},
            "assumptions": {**strings, "description": "Defaults or inferences you made that the researcher should review."},
            "clarifications": {**strings, "description": "Questions ONLY if something essential cannot be inferred; otherwise empty."},
        },
    }
