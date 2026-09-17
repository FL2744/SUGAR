from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .observations import ResearchObservation
from .state_schema import StateAssessment
from .utils import atomic_path, atomic_write_text, safe_artifact_stem, utc_iso


def _sorted_counts(values: Iterable[str]) -> list[dict[str, Any]]:
    counts = Counter(value for value in values if value)
    return [{"value": key, "count": count} for key, count in counts.most_common()]


def build_state_rollups(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
) -> dict[str, Any]:
    observations = list(observations)
    assessments = list(assessments)
    observation_map = {row.observation_id: row for row in observations}
    grouped: dict[tuple[str, str], list[tuple[ResearchObservation, StateAssessment]]] = defaultdict(list)
    for assessment in assessments:
        observation = observation_map.get(assessment.observation_id)
        if observation is None:
            continue
        grouped[(observation.country or "Unspecified", observation.city or "")].append((observation, assessment))

    places: list[dict[str, Any]] = []
    country_accumulator: dict[str, list[tuple[ResearchObservation, StateAssessment]]] = defaultdict(list)
    for (country, city), rows in sorted(grouped.items()):
        country_accumulator[country].extend(rows)
        verified = [
            (obs, assessment)
            for obs, assessment in rows
            if assessment.brief_eligible and obs.verification_state == "human_verified"
        ]
        places.append(_rollup_row(country, city, rows, verified))

    countries: list[dict[str, Any]] = []
    for country, rows in sorted(country_accumulator.items()):
        verified = [
            (obs, assessment)
            for obs, assessment in rows
            if assessment.brief_eligible and obs.verification_state == "human_verified"
        ]
        countries.append(_rollup_row(country, "", rows, verified))

    overall_verified = [
        (observation_map[assessment.observation_id], assessment)
        for assessment in assessments
        if assessment.observation_id in observation_map
        and assessment.brief_eligible
        and observation_map[assessment.observation_id].verification_state == "human_verified"
    ]
    return {
        "generated_at": utc_iso(),
        "guardrail": "These rollups describe verified observations, activity, reach, engagement, themes, and review coverage. They are not an influence index or a representative public-opinion measure.",
        "overall": _rollup_row(
            "ALL",
            "",
            [(observation_map[a.observation_id], a) for a in assessments if a.observation_id in observation_map],
            overall_verified,
        ),
        "countries": countries,
        "places": places,
    }


def _rollup_row(
    country: str,
    city: str,
    rows: list[tuple[ResearchObservation, StateAssessment]],
    verified: list[tuple[ResearchObservation, StateAssessment]],
) -> dict[str, Any]:
    support = Counter(assessment.prc_support.level for _, assessment in verified)
    review = Counter(assessment.review_state for _, assessment in rows)
    return {
        "country": country,
        "city": city,
        "observations_total": len(rows),
        "observations_verified": len(verified),
        "observations_pending": len(rows) - len(verified),
        "us_overlap_verified": sum(assessment.us_overlap.material for _, assessment in verified),
        "confirmed_prc_support_verified": support.get("confirmed", 0),
        "probable_prc_support_verified": support.get("probable", 0),
        "reported_attendance_verified": sum(assessment.reach.attendance or 0 for _, assessment in verified),
        "views_verified": sum(assessment.reach.views or 0 for _, assessment in verified),
        "likes_verified": sum(assessment.reach.likes or 0 for _, assessment in verified),
        "comments_verified": sum(assessment.reach.comments or 0 for _, assessment in verified),
        "shares_reposts_verified": sum(assessment.reach.shares_reposts or 0 for _, assessment in verified),
        "program_domains": _sorted_counts(
            domain for _, assessment in verified for domain in assessment.program_domains
        ),
        "strategic_audiences": _sorted_counts(
            audience for _, assessment in verified for audience in assessment.strategic_audiences
        ),
        "narrative_tags": _sorted_counts(tag for _, assessment in verified for tag in assessment.narrative_tags),
        "observation_types": _sorted_counts(observation.observation_type for observation, _ in verified),
        "review_states": [{"value": key, "count": count} for key, count in sorted(review.items())],
    }


def save_state_rollups(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    output_directory: str | Path,
    *,
    name: str = "state_research",
) -> list[str]:
    payload = build_state_rollups(observations, assessments)
    out_dir = Path(output_directory).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_artifact_stem(name, "state_research")
    json_path = out_dir / f"{stem}.rollups.json"
    country_path = out_dir / f"{stem}.countries.csv"
    place_path = out_dir / f"{stem}.places.csv"
    atomic_write_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))

    flat_fields = [
        "country",
        "city",
        "observations_total",
        "observations_verified",
        "observations_pending",
        "us_overlap_verified",
        "confirmed_prc_support_verified",
        "probable_prc_support_verified",
        "reported_attendance_verified",
        "views_verified",
        "likes_verified",
        "comments_verified",
        "shares_reposts_verified",
        "program_domains",
        "strategic_audiences",
        "narrative_tags",
        "observation_types",
        "review_states",
    ]
    for path, rows in ((country_path, payload["countries"]), (place_path, payload["places"])):
        with atomic_path(path) as temporary:
            with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=flat_fields)
                writer.writeheader()
                for row in rows:
                    raw = dict(row)
                    for key in (
                        "program_domains",
                        "strategic_audiences",
                        "narrative_tags",
                        "observation_types",
                        "review_states",
                    ):
                        raw[key] = json.dumps(raw[key], ensure_ascii=False, sort_keys=True)
                    writer.writerow(raw)
    return [str(json_path), str(country_path), str(place_path)]
