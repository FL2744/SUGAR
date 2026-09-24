"""Conservative, exact-label normalization for registry program and audience fields.

Source wording is always retained separately. This module only normalizes explicit
program/audience columns; it does not infer an audience from an institution name,
program title, or unrelated description text.
"""
from __future__ import annotations

import re
from typing import Any


TAXONOMY_VERSION = "1.0"

PROGRAM_DOMAINS: dict[str, tuple[str, ...]] = {
    "language_learning": (
        "language learning", "language education", "english teaching", "english learning",
        "english language teaching", "english language learning", "english classes",
        "english club", "mandarin language education", "chinese language learning",
    ),
    "education_advising": (
        "education advising", "educational advising", "study abroad advising",
        "college advising", "university admissions advising",
    ),
    "vocational_technical_training": (
        "vocational education", "technical training", "vocational technical training",
        "tvet", "workforce technical training", "technical skills training",
        "vocational skills training",
    ),
    "entrepreneurship": (
        "entrepreneurship", "entrepreneurship education", "business development",
        "startup skills",
    ),
    "professional_development": (
        "professional development", "professional skills", "workforce development",
        "career skills",
    ),
    "cultural_programming": (
        "cultural programming", "cultural activities", "arts and culture",
        "cultural events",
    ),
    "alumni_networking": (
        "exchange alumni", "alumni networking", "alumni engagement",
    ),
    "information_media": (
        "information resources", "media literacy", "information about the united states",
    ),
    "steam": (
        "steam", "stem", "science technology engineering arts mathematics",
    ),
    "academic_exchange": (
        "academic exchange", "student exchange", "higher education exchange",
        "research exchange",
    ),
    "public_dialogue": (
        "public dialogue", "policy dialogue", "public diplomacy dialogue",
    ),
    "civil_society_engagement": (
        "civil society engagement", "community engagement",
    ),
}

AUDIENCE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "secondary_students": ("secondary students", "high school students", "secondary school students"),
    "university_students": ("university students", "college students", "higher education students"),
    "technical_vocational_students": (
        "technical students", "vocational students", "technical and vocational students",
        "tvet students",
    ),
    "educators": ("educators", "teachers", "faculty", "education professionals"),
    "academics_researchers": ("academics", "researchers", "scholars", "academic researchers"),
    "young_professionals": ("young professionals", "early career professionals"),
    "entrepreneurs": ("entrepreneurs", "small business owners", "startup founders"),
    "emerging_leaders": ("emerging leaders", "future leaders"),
    "opinion_leaders": ("opinion leaders", "thought leaders", "influencers"),
    "media": ("journalists", "media professionals", "media"),
    "government_officials": ("government officials", "public officials", "civil servants"),
    "civil_society_groups": ("civil society", "civil society organizations", "ngo staff"),
    "underserved_communities": ("underserved communities", "underserved populations"),
    "general_public": ("general public", "public audiences"),
}

DELIVERY_MODE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "physical": ("in person", "in person service", "on site", "onsite", "at a physical site"),
    "mobile": ("pop up", "mobile service", "mobile programming", "traveling program"),
    "virtual": ("online", "remote", "virtual service", "virtual programming"),
    "hybrid": ("online and in person", "virtual and physical", "hybrid programming"),
    "digital": ("digital platform", "social media", "app based", "digital service"),
}


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _lookup(categories: dict[str, tuple[str, ...]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for canonical, aliases in categories.items():
        result[_key(canonical)] = canonical
        for alias in aliases:
            result[_key(alias)] = canonical
    return result


_PROGRAM_LOOKUP = _lookup(PROGRAM_DOMAINS)
_AUDIENCE_LOOKUP = _lookup(AUDIENCE_CATEGORIES)
_DELIVERY_LOOKUP = _lookup(DELIVERY_MODE_CATEGORIES)


def normalize_labels(values: Any, *, category: str) -> list[str]:
    """Return only exact known taxonomy matches, preserving first-seen order."""
    raw = values if isinstance(values, (list, tuple, set)) else [values]
    lookup = (
        _PROGRAM_LOOKUP if category == "program"
        else _AUDIENCE_LOOKUP if category == "audience"
        else _DELIVERY_LOOKUP if category == "delivery"
        else None
    )
    if lookup is None:
        raise ValueError("category must be 'program', 'audience', or 'delivery'.")
    normalized: list[str] = []
    for value in raw:
        canonical = lookup.get(_key(value))
        if canonical and canonical not in normalized:
            normalized.append(canonical)
    return normalized
