"""Method profiles: the research method as data you can export, share, and apply to another project.

A profile captures *how* a study is done, not what it found: the networks and their roles, the plain-language request
and plan, extra search vocabulary, websites and feeds to read, wording that signals an audience or program, relevance
terms, optional starting institutions (each with a source), and monitor schedules. Applying it to a new project (another
region, another network) reproduces the method in one step; the person then adjusts what differs.

Profiles are plain JSON, checked and bounded on the way in, never contain credentials, and are imported at run time,
which keeps study-specific detail out of the program itself.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

PROFILE_VERSION = 1
MAX_BYTES = 1_000_000
_ROLES = {"subject", "reference"}
_SECRET_KEY = re.compile(r"(^|[_\-\s])(api[_\-]?key|token|secret|password|cookie|bearer|credential)s?($|[_\-\s])", re.I)


def _text(value: Any, limit: int = 200) -> str:
    return " ".join(str(value or "").split())[:limit]


def _urls(values: Any, limit: int = 50) -> list[str]:
    raw = values if isinstance(values, list) else []
    return list(dict.fromkeys(u.strip() for u in raw if isinstance(u, str) and u.strip().lower().startswith(("http://", "https://"))))[:limit]


def _strings(values: Any, limit: int = 60, width: int = 120) -> list[str]:
    raw = values if isinstance(values, list) else []
    return list(dict.fromkeys(_text(v, width) for v in raw if isinstance(v, (str, int)) and _text(v, width)))[:limit]


def parse_profile(raw: bytes | str | dict[str, Any]) -> dict[str, Any]:
    """Read and validate a profile. Raises ValueError with a plain message; unknown keys are ignored."""
    if isinstance(raw, (bytes, str)):
        size = len(raw if isinstance(raw, bytes) else raw.encode("utf-8"))
        if size > MAX_BYTES:
            raise ValueError("That profile is larger than 1 MB.")
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise ValueError("That file is not valid JSON.") from exc
    else:
        data = raw
    if not isinstance(data, dict):
        raise ValueError("A profile is a JSON object.")
    version = data.get("profile_version", PROFILE_VERSION)
    if version != PROFILE_VERSION:
        raise ValueError(f"This SUGAR reads profile version {PROFILE_VERSION}; the file is version {version}.")
    if any(_SECRET_KEY.search(str(k)) for k in data):
        raise ValueError("Profiles must not contain credentials. Remove keys, tokens and passwords from the file.")
    clean: dict[str, Any] = {"profile_version": PROFILE_VERSION, "name": _text(data.get("name"), 120), "description": _text(data.get("description"), 600)}
    if not clean["name"]:
        raise ValueError("Give the profile a name.")
    clean["networks"] = [{"name": _text(n.get("name"), 80), "role": n.get("role") if n.get("role") in _ROLES else "subject", "label": _text(n.get("label") or n.get("name"), 80)}
                         for n in (data.get("networks") or [])[:20] if isinstance(n, dict) and _text(n.get("name"), 80)]
    clean["request"] = _text(data.get("request"), 2000)
    clean["plan"] = {k: v for k, v in dict(data.get("plan") or {}).items() if isinstance(k, str) and not _SECRET_KEY.search(k)} if isinstance(data.get("plan"), dict) else {}
    clean["queries"] = _strings(data.get("queries"), 60, 160)
    sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
    clean["sources"] = {"web_seeds": _urls(sources.get("web_seeds")), "rss_feeds": _urls(sources.get("rss_feeds"))}
    glossary: dict[str, dict[str, Any]] = {}
    for term, entry in list((data.get("glossary") or {}).items())[:200] if isinstance(data.get("glossary"), dict) else []:
        if isinstance(entry, dict) and _text(term, 80):
            glossary[_text(term, 80).casefold()] = {**{str(lang)[:5]: _text(v, 120) for lang, v in entry.items() if lang != "synonyms" and isinstance(v, str)},
                                                      **({"synonyms": _strings(entry.get("synonyms"), 12, 80)} if entry.get("synonyms") else {})}
    clean["glossary"] = glossary
    from .reference_taxonomy import AUDIENCE_CATEGORIES, PROGRAM_DOMAINS
    coding: dict[str, dict[str, list[str]]] = {"audience": {}, "program": {}}
    allowed = {"audience": AUDIENCE_CATEGORIES, "program": PROGRAM_DOMAINS}
    for kind in coding:
        for label, terms in list((data.get("coding_terms") or {}).get(kind, {}).items())[:40] if isinstance(data.get("coding_terms"), dict) and isinstance(data["coding_terms"].get(kind), dict) else []:
            if _text(label, 60) not in allowed[kind]:
                raise ValueError(f"“{_text(label, 60)}” is not a standard {kind} label. Use one of: {', '.join(sorted(allowed[kind]))}.")
            coding[kind][_text(label, 60)] = _strings(terms, 40, 80)
    clean["coding_terms"] = coding
    relevance = data.get("relevance") if isinstance(data.get("relevance"), dict) else {}
    clean["relevance"] = {"include": _strings(relevance.get("include"), 60, 80), "exclude": _strings(relevance.get("exclude"), 60, 80)}
    seeds = []
    for row in (data.get("institutions") or [])[:500]:
        if not isinstance(row, dict) or not _text(row.get("name")):
            continue
        source = _text(row.get("source_url"), 500)
        if urlparse(source).scheme not in {"http", "https"}:
            raise ValueError(f"The starting institution “{_text(row.get('name'))}” needs a source address (an http or https link).")
        seeds.append({k: (row.get(k) if k in {"latitude", "longitude"} else _text(row.get(k), 300)) for k in ("name", "network", "country", "region", "city", "status", "latitude", "longitude", "source_url", "note") if row.get(k) not in (None, "")})
    clean["institutions"] = seeds
    clean["monitors"] = [{"name": _text(m.get("name"), 80), "cadence_hours": int(m.get("cadence_hours") or 168)} for m in (data.get("monitors") or [])[:5] if isinstance(m, dict) and _text(m.get("name"), 80)]
    return clean


def apply_profile(wb: Any, project: Any, profile: dict[str, Any], *, actor: str = "analyst", include_institutions: bool = True) -> dict[str, Any]:
    """Apply a parsed profile to a project. Existing plan, sources and monitors are replaced by the profile's; records are added."""
    from .monitoring import CADENCES_HOURS, save_monitor
    from .networks import set_network
    from .reference_registry import upsert_entity
    profile = parse_profile(profile)
    done: dict[str, Any] = {"name": profile["name"], "applied": []}
    for n in profile["networks"]:
        set_network(project, n["name"], role=n["role"], label=n["label"], actor=actor)
    if profile["networks"]:
        done["applied"].append(f"{len(profile['networks'])} network(s)")
    settings: dict[str, Any] = {}
    if profile["sources"]["web_seeds"] or profile["sources"]["rss_feeds"]:
        settings.update({"web_seeds": profile["sources"]["web_seeds"], "rss_feeds": profile["sources"]["rss_feeds"]})
    if any(profile["coding_terms"].values()):
        settings["coding_terms"] = profile["coding_terms"]
    if profile["relevance"]["include"] or profile["relevance"]["exclude"]:
        settings["relevance"] = profile["relevance"]
    if settings:
        project.update_settings(settings, actor=actor)
        done["applied"].append("sources and vocabulary")
    payload: dict[str, Any] | None = None
    if profile["plan"]:
        payload = dict(profile["plan"])
    elif profile["request"]:
        payload = wb.interpret(profile["request"], mode="deterministic", project=project)["plan"]
    if payload is not None:
        extra = dict(payload.get("extra") or {})
        if profile["glossary"]:
            extra["glossary"] = profile["glossary"]
        payload["extra"] = extra
        if profile["queries"]:
            payload["queries"] = [*list(payload.get("queries") or []), *[{"text": q, "origin": "analyst", "rationale": "From the method profile.", "enabled": True} for q in profile["queries"]]]
        saved = wb.save_plan(project, payload, reason="saved", request=profile["request"], actor=actor)
        done["applied"].append("research plan")
        done["issues"] = saved.get("issues", [])
    if include_institutions and profile["institutions"]:
        count = 0
        for row in profile["institutions"]:
            upsert_entity(project.workspace, {k: v for k, v in row.items() if k not in {"source_url", "note"}}, evidence_refs=[{"source_url": row["source_url"], "note": row.get("note", ""), "kind": "profile_seed"}],
                          actor=actor, reason="From the method profile", review_state="unreviewed")
            count += 1
        done["applied"].append(f"{count} starting institution(s), unreviewed")
    if profile["monitors"] and payload is not None:
        for m in profile["monitors"]:
            if m["cadence_hours"] in CADENCES_HOURS:
                save_monitor(project, name=m["name"], cadence_hours=m["cadence_hours"], actor=actor)
        done["applied"].append(f"{len(profile['monitors'])} monitor(s)")
    project.log("profile_applied", {"name": profile["name"], "applied": done["applied"]}, actor=actor)
    return done


def export_profile(wb: Any, project: Any, *, name: str = "", include_institutions: bool = False) -> dict[str, Any]:
    """The project's method as a profile. No credentials, no collected items; institutions only if asked, each with its first source."""
    from .monitoring import list_monitors
    from .networks import network_settings
    from .reference_registry import list_entities
    meta = project.meta()
    settings = meta.get("settings") or {}
    plan = project.load_plan()
    plan_dict = plan.to_dict() if plan is not None else {}
    glossary = (plan_dict.get("extra") or {}).get("glossary", {}) if plan_dict else {}
    for key in ("plan_id", "version", "created_at", "updated_at", "fingerprint"):
        plan_dict.pop(key, None)
    profile: dict[str, Any] = {
        "profile_version": PROFILE_VERSION, "name": name or meta.get("name") or "Method profile", "description": "Exported from a SUGAR project.",
        "networks": [{"name": n, **v} for n, v in network_settings(project).items()], "request": meta.get("requirement_text", ""), "plan": plan_dict,
        "queries": [], "sources": {"web_seeds": settings.get("web_seeds", []), "rss_feeds": settings.get("rss_feeds", [])}, "glossary": glossary,
        "coding_terms": settings.get("coding_terms", {"audience": {}, "program": {}}), "relevance": settings.get("relevance", {"include": [], "exclude": []}),
        "monitors": [{"name": m["name"], "cadence_hours": m["cadence_hours"]} for m in list_monitors(project)],
    }
    if include_institutions:
        rows = []
        for e in list_entities(project.workspace):
            ref = next((r for c in e.get("claims", []) for r in c.get("evidence_refs", []) if isinstance(r, dict) and str(r.get("source_url", "")).startswith("http")), None)
            if ref:
                rows.append({"name": e.get("name", ""), "network": e.get("network", ""), "country": e.get("country", ""), "city": e.get("city", ""), "status": e.get("status", ""),
                             "latitude": e.get("latitude") if e.get("latitude") not in ("", None) else None, "longitude": e.get("longitude") if e.get("longitude") not in ("", None) else None,
                             "source_url": ref["source_url"]})
        profile["institutions"] = [{k: v for k, v in r.items() if v not in (None, "")} for r in rows]
    return profile
