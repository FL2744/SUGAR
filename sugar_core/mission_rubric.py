"""Local, editable study priorities. All output is a proposal with source words.

Study-specific names and multilingual aliases belong in the project's plain JSON
file, rather than in the application. No provider is called by this module.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

AUDIENCE_GROUPS = ("students", "k12", "teachers", "technical_professionals", "officials", "business")
DEFAULT_RUBRIC = {
    "version": 1,
    "description": "Proposed A–D program priorities; review against your study's agreed rubric.",
    "tiers": [
        {"tier": "A", "label": "Strategic policy and commercial priorities", "terms": ["Freedom 250", "commercial diplomacy", "AI standards", "artificial intelligence standards", "technology standards", "critical minerals", "mining sector"]},
        {"tier": "B", "label": "Next-generation leaders and sector audiences", "terms": ["next-generation leaders", "emerging leaders", "young leaders", "technical professionals", "business leaders", "mining professionals"]},
        {"tier": "C", "label": "Education and professional exchange", "terms": ["scholarship", "course registration", "language course", "teacher training", "student exchange", "test center", "test centre", "competition"]},
        {"tier": "D", "label": "General cultural programming", "terms": ["tea ceremony", "cultural festival", "calligraphy", "dance performance", "cooking class"]},
    ],
    "audiences": {
        "students": ["university students", "college students", "undergraduates", "estudiantes universitarios", "étudiants universitaires", "大学生"],
        "k12": ["schoolchildren", "high school students", "school pupils", "secondary students", "alumnos de secundaria", "中学生"],
        "teachers": ["teachers", "educators", "docentes", "profesores", "enseignants", "教师"],
        "technical_professionals": ["technical professionals", "engineers", "mining professionals", "ingenieros", "工程师"],
        "officials": ["government officials", "civil servants", "funcionarios", "公務員", "公务员"],
        "business": ["entrepreneurs", "business leaders", "business owners", "empresarios", "企业家"],
    },
    "aliases": {},
    "alert_terms": [],
}


def validate_rubric(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or len(json.dumps(value, ensure_ascii=False)) > 120_000:
        raise ValueError("The rubric must be a JSON object smaller than 120 KB.")
    if not isinstance(value.get("version"), int) or value["version"] < 1:
        raise ValueError("Give the rubric a positive integer version.")
    tiers = value.get("tiers")
    if not isinstance(tiers, list) or len(tiers) != 4 or not all(isinstance(r, dict) for r in tiers) or [r.get("tier") for r in tiers] != list("ABCD"):
        raise ValueError("List tiers A, B, C, D in that order.")
    def terms(raw: Any) -> list[str]:
        if not isinstance(raw, list) or len(raw) > 150 or any(not isinstance(t, str) or not 1 <= len(t.strip()) <= 160 for t in raw):
            raise ValueError("Terms must be lists of up to 150 nonempty strings, each at most 160 characters.")
        return list(dict.fromkeys(t.strip() for t in raw))
    audiences = value.get("audiences", {})
    aliases = value.get("aliases", {})
    if not isinstance(audiences, dict) or set(audiences) - set(AUDIENCE_GROUPS):
        raise ValueError("Use the six fixed audience groups.")
    if not isinstance(aliases, dict) or len(aliases) > 100:
        raise ValueError("Aliases must map up to 100 program names to term lists.")
    return {"version": value["version"], "description": str(value.get("description", ""))[:1000],
            "tiers": [{"tier": r["tier"], "label": str(r.get("label", ""))[:160], "terms": terms(r.get("terms", []))} for r in tiers],
            "audiences": {k: terms(audiences.get(k, [])) for k in AUDIENCE_GROUPS},
            "aliases": {str(k)[:160]: terms(v) for k, v in aliases.items()}, "alert_terms": terms(value.get("alert_terms", []))}


def load_rubric(project: Any, *, strict: bool = False) -> dict[str, Any]:
    path = project.root / "study-rubric.json"
    if path.is_file():
        try:
            return validate_rubric(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as exc:
            if strict:
                raise ValueError(f"study-rubric.json needs repair: {exc}") from exc
            # A malformed optional config must never take down the map or collection.
            fallback = validate_rubric(DEFAULT_RUBRIC)
            fallback["configuration_warning"] = f"study-rubric.json needs repair; built-in rules used: {exc}"
            return fallback
    return validate_rubric(DEFAULT_RUBRIC)


def save_rubric(project: Any, value: Any, *, actor: str = "analyst") -> dict[str, Any]:
    rubric = validate_rubric(value)
    with project._lock:
        project.root.mkdir(parents=True, exist_ok=True)
        path = project.root / "study-rubric.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(rubric, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)
    project.log("study_rubric_saved", {"version": rubric["version"], "fingerprint": fingerprint(rubric)}, actor=actor)
    return rubric


def fingerprint(rubric: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(rubric, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def match_term(text: str, term: str) -> re.Match | None:
    # Whole words for spaced/alphabetic languages; substring for CJK scripts.
    pattern = re.escape(term)
    if not re.search(r"[\u3400-\u9fff\u3040-\u30ff]", term):
        pattern = r"(?<!\w)" + pattern + r"(?!\w)"
    return re.search(pattern, text, re.I)


def classify_text(text: str, rubric: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    def code(field: str, label: str, terms: list[str]) -> bool:
        for term in terms:
            match = match_term(text, term)
            if match:
                start = max(0, match.start() - 100)
                out.append({"field": field, "label": label, "quote": text[start:match.end() + 180][:400],
                            "method": "study_rubric", "rule": term, "rubric_version": rubric["version"], "rubric_fingerprint": fingerprint(rubric)})
                return True
        return False
    for tier in rubric["tiers"]:
        if code("priority_tier", tier["tier"], tier["terms"]):
            break  # Strategic programming wins over incidental ceremony mentions.
    for group, terms in rubric["audiences"].items():
        code("audience_group", group, terms)
    for canonical, aliases in rubric["aliases"].items():
        code("program_alias", canonical, [canonical, *aliases])
    for term in rubric["alert_terms"]:
        code("narrative_flag", term, [term])
    return out


def entity_programs(entity: dict[str, Any], rubric: dict[str, Any]) -> dict[str, Any]:
    fields = ("description", "program_domains", "program_descriptions", "audiences", "audience_descriptions")
    text = "\n".join(str(entity.get(k) or "") for k in fields)
    return {"codes": classify_text(text, rubric), "review_state": "proposed", "basis": "Imported or recorded row wording; not independently verified", "rubric_fingerprint": fingerprint(rubric)}
