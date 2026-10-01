"""Reusable project-local research requirement templates."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .workspace import SugarWorkspace


_FIELDS = (
    "question", "geographies", "known_entities", "target_audiences", "languages",
    "excluded_topics", "preferred_sources", "since", "until", "notes",
)
STARTER_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "template_id": "public-service-access", "name": "Public service access",
        "question": "Where are public-facing services offered, who can access them, and what evidence supports their availability?",
        "geographies": [], "known_entities": [], "target_audiences": ["Policy researchers"],
        "languages": ["auto"], "excluded_topics": [], "preferred_sources": ["x", "bluesky"],
        "since": "", "until": "", "notes": "Record the source and geographic precision for each service claim.",
    },
    {
        "template_id": "cross-platform-narratives", "name": "Cross-platform public narratives",
        "question": "How do public narratives about this issue vary across platforms and over time?",
        "geographies": [], "known_entities": [], "target_audiences": ["Research analysts"],
        "languages": ["auto"], "excluded_topics": [], "preferred_sources": ["x", "bluesky", "mastodon"],
        "since": "", "until": "", "notes": "Compare only observed material and document platform access limits.",
    },
    {
        "template_id": "institutional-presence", "name": "Institutional presence and coverage",
        "question": "Which institutions or programs are publicly documented in scope, and where is coverage incomplete?",
        "geographies": [], "known_entities": [], "target_audiences": ["Program researchers"],
        "languages": ["auto"], "excluded_topics": [], "preferred_sources": ["x", "bluesky", "mastodon", "weibo", "bilibili"],
        "since": "", "until": "", "notes": "Track source coverage, last verification, and unresolved locations.",
    },
)


def _path(workspace: SugarWorkspace) -> Path:
    return workspace.internal_path / "research-requirement-templates.json"


def _read_custom(workspace: SugarWorkspace) -> list[dict[str, Any]]:
    path = _path(workspace)
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Research templates are unreadable; restore or remove .sugar/research-requirement-templates.json.") from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("Research templates must be a list of objects.")
    return value


def list_research_templates(workspace: SugarWorkspace) -> list[dict[str, Any]]:
    return [*STARTER_TEMPLATES, *_read_custom(workspace)]


def _string_list(value: Any, label: str) -> list[str]:
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        raise ValueError(f"Template {label} must be a list of text values.")
    result = [str(item).strip() for item in value if str(item).strip()]
    if len(result) > 100 or any(len(item) > 500 for item in result):
        raise ValueError(f"Template {label} has too many or overly long values.")
    return result


def save_research_template(workspace: SugarWorkspace, name: str, fields: dict[str, Any]) -> dict[str, Any]:
    label = str(name or "").strip()
    if not label or len(label) > 120:
        raise ValueError("Template name must contain 1 to 120 characters.")
    unknown = sorted(set(fields) - set(_FIELDS))
    if unknown:
        raise ValueError(f"Unsupported research template field(s): {', '.join(unknown)}.")
    template: dict[str, Any] = {"name": label}
    for field in _FIELDS:
        value = fields.get(field, [] if field in {"geographies", "known_entities", "target_audiences", "languages", "excluded_topics", "preferred_sources"} else "")
        if field in {"geographies", "known_entities", "target_audiences", "languages", "excluded_topics", "preferred_sources"}:
            template[field] = _string_list(value, field)
        else:
            template[field] = str(value or "").strip()
            if len(template[field]) > (10_000 if field == "question" else 100_000):
                raise ValueError(f"Template {field} is too long.")
    if not template["question"]:
        raise ValueError("A reusable research template needs a research question.")
    slug = re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")[:80] or "template"
    template["template_id"] = f"custom-{slug}"
    custom = _read_custom(workspace)
    custom = [row for row in custom if str(row.get("name", "")).casefold() != label.casefold()]
    custom.append(template)
    target = _path(workspace)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(custom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    workspace.register_artifact("research_templates", target, label="Reusable research requirement templates", metadata={"template_count": len(custom)})
    return template
