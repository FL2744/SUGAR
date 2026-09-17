from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .observations import ResearchObservation
from .state_entities import EntityRegistry
from .state_freshness import build_freshness_report
from .state_schema import StateAssessment, USPresenceSite
from .state_workflow import build_review_queue
from .utils import utc_iso


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _observation_names(observation: ResearchObservation, assessment: StateAssessment | None) -> list[str]:
    values = [observation.institution_name, observation.program_name, *observation.actors]
    if assessment:
        values.extend(assessment.sponsor_entities)
        values.extend(assessment.host_entities)
        values.extend(assessment.partner_entities)
    return [_clean(value) for value in values if _clean(value)]


def build_gap_report(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    *,
    entities: EntityRegistry | None = None,
    us_sites: Iterable[USPresenceSite] = (),
    current_activity_start: str = "2024-01-01",
    collection_stale_days: int = 90,
) -> dict[str, Any]:
    observations = list(observations)
    assessments = list(assessments)
    sites = list(us_sites)
    assessment_map = {row.observation_id: row for row in assessments}
    freshness = build_freshness_report(
        observations,
        assessments,
        current_activity_start=current_activity_start,
        collection_stale_days=collection_stale_days,
    )
    freshness_map = {row["observation_id"]: row for row in freshness["records"]}

    gaps: list[dict[str, Any]] = []

    def add(
        priority: int,
        category: str,
        subject_id: str,
        subject: str,
        country: str,
        city: str,
        reason: str,
        next_action: str,
    ) -> None:
        gaps.append(
            {
                "priority": priority,
                "category": category,
                "subject_id": subject_id,
                "subject": subject,
                "country": country,
                "city": city,
                "reason": reason,
                "next_action": next_action,
            }
        )

    for row in build_review_queue(observations, assessments):
        if int(row["review_priority"]) <= 0:
            continue
        add(
            min(10, int(row["review_priority"])),
            "human_review",
            row["assessment_id"],
            row["title"] or row["observation_id"],
            row["country"],
            row["city"],
            row["reasons"],
            "Review source evidence and resolve assessment/claim verification state.",
        )

    for observation in observations:
        state = freshness_map.get(observation.observation_id, {})
        if state.get("collection_stale"):
            add(
                4,
                "stale_collection",
                observation.observation_id,
                observation.title or observation.program_name or observation.institution_name,
                observation.country,
                observation.city,
                f"Latest collected evidence is {state.get('collection_age_days')} days old.",
                "Refresh the observation with current lawful sources; preserve the historical evidence rather than replacing it.",
            )
        if not observation.country and observation.latitude is None:
            add(
                3,
                "unresolved_location",
                observation.observation_id,
                observation.title or observation.observation_id,
                "",
                "",
                "Observation has no country or geocoded location.",
                "Resolve location from explicit source evidence before geographic comparison or mapping.",
            )

    if entities is not None:
        entity_hits: dict[str, list[tuple[ResearchObservation, StateAssessment | None]]] = defaultdict(list)
        for observation in observations:
            assessment = assessment_map.get(observation.observation_id)
            for name in _observation_names(observation, assessment):
                entity = entities.resolve(name)
                if entity:
                    entity_hits[entity.entity_id].append((observation, assessment))
        for entity in entities.entities.values():
            if not entity.active:
                continue
            hits = entity_hits.get(entity.entity_id, [])
            verified_current = [
                (obs, assessment)
                for obs, assessment in hits
                if assessment
                and assessment.brief_eligible
                and obs.verification_state == "human_verified"
                and freshness_map.get(obs.observation_id, {}).get("in_current_activity_period")
            ]
            if not verified_current:
                priority = {"urgent": 8, "high": 6, "normal": 4, "low": 2}[entity.priority]
                reason = (
                    "No human-verified current-period observation in this corpus for the monitored entity. "
                    "This is a coverage gap, not evidence that the entity is inactive."
                )
                add(
                    priority,
                    "entity_monitoring_gap",
                    entity.entity_id,
                    entity.canonical_name,
                    entity.country,
                    entity.city,
                    reason,
                    "Run the entity watch-query plan and check official, host-institution, local-media, and relevant social sources.",
                )

    verified_rows = [
        (obs, assessment)
        for obs in observations
        for assessment in [assessment_map.get(obs.observation_id)]
        if assessment and assessment.brief_eligible and obs.verification_state == "human_verified"
    ]
    for site in sites:
        same_city = [
            (obs, assessment)
            for obs, assessment in verified_rows
            if obs.country.casefold() == site.country.casefold()
            and site.city
            and obs.city.casefold() == site.city.casefold()
        ]
        same_country = [
            (obs, assessment) for obs, assessment in verified_rows if obs.country.casefold() == site.country.casefold()
        ]
        if not same_city:
            add(
                2 if same_country else 3,
                "us_presence_comparison_gap",
                site.site_id,
                site.name,
                site.country,
                site.city,
                "No human-verified same-city PRC-network observation is present in the current corpus. This is a comparison/collection gap, not proof of no PRC activity.",
                "Check current local-language and institution/program sources around this U.S. public-diplomacy location.",
            )

    gaps.sort(key=lambda row: (-int(row["priority"]), row["category"], row["country"], row["subject"]))
    counts: dict[str, int] = defaultdict(int)
    for gap in gaps:
        counts[gap["category"]] += 1
    return {
        "generated_at": utc_iso(),
        "current_activity_start": current_activity_start,
        "collection_stale_days": collection_stale_days,
        "gap_count": len(gaps),
        "by_category": dict(sorted(counts.items())),
        "guardrail": "A missing verified observation is a research/coverage gap. It must never be reported as evidence that no activity exists.",
        "gaps": gaps,
    }


def save_gap_report(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    output_directory: str | Path,
    *,
    entities: EntityRegistry | None = None,
    us_sites: Iterable[USPresenceSite] = (),
    name: str = "state_research",
    **kwargs,
) -> list[str]:
    payload = build_gap_report(observations, assessments, entities=entities, us_sites=us_sites, **kwargs)
    out_dir = Path(output_directory).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "_".join(str(name or "state_research").split())
    json_path = out_dir / f"{stem}.gaps.json"
    csv_path = out_dir / f"{stem}.gaps.csv"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    fields = ["priority", "category", "subject_id", "subject", "country", "city", "reason", "next_action"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(payload["gaps"])
    return [str(json_path), str(csv_path)]
