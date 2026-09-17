from __future__ import annotations

import csv
import json
import math
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .observation_storage import load_observations
from .observations import ResearchObservation
from .state_schema import (
    StateAssessment,
    USOverlapAssessment,
    USPresenceSite,
    USServiceSourceAttribution,
)
from .utils import safe_artifact_stem, safe_cell, utc_iso

DOMAIN_TO_US_SERVICES = {
    "higher_education": {"educationusa", "study_in_the_us", "higher_education"},
    "language_education": {"language_education"},
    "english_language": {"english_language", "english_learning"},
    "entrepreneurship": {"entrepreneurship", "business", "innovation"},
    "stem_technology": {"stem", "technology", "makerspace", "innovation"},
    "media_information_literacy": {"media_literacy", "information_literacy"},
    "civic_engagement": {"civic_engagement", "democracy", "community_engagement"},
    "culture_arts": {"culture", "arts"},
    "economic_commercial": {"business", "entrepreneurship", "economic"},
    "professional_skills": {"professional_skills", "career"},
    "exchange_alumni": {"alumni", "exchange", "exchange_alumni"},
    "digital_connectivity": {"digital_connectivity", "technology"},
    "other": set(),
}

AUDIENCE_TO_US_SERVICES = {
    "prospective_students": {"educationusa", "study_in_the_us"},
    "students": {"educationusa", "english_language", "youth"},
    "youth": {"youth", "english_language"},
    "emerging_leaders": {"leadership", "exchange_alumni"},
    "entrepreneurs": {"entrepreneurship", "business", "innovation"},
    "technical_professionals": {"stem", "technology", "professional_skills"},
    "educators": {"education", "english_language"},
    "researchers_academics": {"higher_education", "research"},
    "journalists_media": {"media_literacy", "journalism"},
    "civil_society": {"civic_engagement", "community_engagement"},
    "government_officials": {"leadership", "policy"},
    "exchange_alumni": {"alumni", "exchange_alumni"},
    "general_public": set(),
    "other": set(),
}

SENSITIVE_NARRATIVES = {"anti_us", "china_russia_coordination", "third_party_coordination"}
_REACH_METRIC_NAMES = ("attendance", "views", "likes", "comments", "shares_reposts", "followers")
_ENGAGEMENT_METRIC_NAMES = ("likes", "comments", "shares_reposts")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _key(value: Any) -> str:
    return _clean(value).casefold()


def _list_cell(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    text = _clean(value)
    if not text:
        return []
    if text.startswith("["):
        try:
            raw = json.loads(text)
            if isinstance(raw, list):
                return [_clean(item) for item in raw if _clean(item)]
        except json.JSONDecodeError:
            pass
    return [_clean(item) for item in text.replace("|", ";").split(";") if _clean(item)]


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none", "<na>"}:
        return None
    return float(value)


def load_us_presence_sites(path: str | Path) -> list[USPresenceSite]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() == ".csv":
        frame = pd.read_csv(source)
    elif source.suffix.lower() == ".xlsx":
        frame = pd.read_excel(source)
    else:
        raise ValueError("U.S. presence site input must be CSV or XLSX.")
    sites: list[USPresenceSite] = []
    for raw in frame.to_dict(orient="records"):
        sites.append(
            USPresenceSite(
                site_id=_clean(raw.get("site_id", "")),
                name=_clean(raw.get("name", "")),
                network=_clean(raw.get("network", "")),
                subtype=_clean(raw.get("subtype", "")),
                country=_clean(raw.get("country", "")),
                city=_clean(raw.get("city", "")),
                latitude=_float_or_none(raw.get("latitude")),
                longitude=_float_or_none(raw.get("longitude")),
                service_tags=_list_cell(raw.get("service_tags")),
                source_url=_clean(raw.get("source_url", "")),
                status=_clean(raw.get("status", "active")) or "active",
                delivery_mode=_clean(raw.get("delivery_mode", "physical")) or "physical",
                coverage_scope=_clean(raw.get("coverage_scope", "site")) or "site",
                location_precision=_clean(raw.get("location_precision", "unknown")) or "unknown",
                location_confidence=_float_or_none(raw.get("location_confidence")),
                location_uncertainty_km=_float_or_none(raw.get("location_uncertainty_km")),
                location_basis=_clean(raw.get("location_basis", "")),
            )
        )
    return sites


def write_us_presence_template(path: str | Path) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "site_id",
        "name",
        "network",
        "subtype",
        "country",
        "city",
        "latitude",
        "longitude",
        "service_tags",
        "source_url",
        "status",
        "delivery_mode",
        "coverage_scope",
        "location_precision",
        "location_confidence",
        "location_uncertainty_km",
        "location_basis",
    ]
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "name": "Example American Space",
                "network": "american_space",
                "subtype": "American Corner",
                "country": "Example Country",
                "city": "Example City",
                "latitude": "",
                "longitude": "",
                "service_tags": "english_language;entrepreneurship;stem",
                "source_url": "https://example.gov/source",
                "status": "active",
                "delivery_mode": "physical",
                "coverage_scope": "site",
                "location_precision": "city",
                "location_confidence": "0.75",
                "location_uncertainty_km": "12",
                "location_basis": "city_reference_replace_with_verified_site_data_when_available",
            }
        )
        writer.writerow(
            {
                "name": "Example virtual advising service",
                "network": "educationusa",
                "subtype": "Virtual advising",
                "country": "Example Country",
                "city": "",
                "latitude": "",
                "longitude": "",
                "service_tags": "educationusa;study_in_the_us;higher_education",
                "source_url": "https://example.gov/virtual-service",
                "status": "active",
                "delivery_mode": "virtual",
                "coverage_scope": "country",
                "location_precision": "unknown",
                "location_basis": "official_service_directory_nonspatial",
            }
        )
    return str(target.resolve())


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _observation_geo_contexts(observation: ResearchObservation) -> list[dict[str, Any]]:
    """Return the defensible geographic contexts used for observation-level service analysis.

    Structured locations are authoritative when present. The legacy scalar geography remains a
    compatibility fallback only for observations without structured locations; it is not mixed
    into a multi-location record because a stale summary city or country could otherwise make a
    service appear applicable to a venue the source does not support.
    """
    if observation.locations:
        return [
            {
                "location_id": location.location_id,
                "label": location.label,
                "country": location.country,
                "city": location.city,
                "latitude": location.latitude,
                "longitude": location.longitude,
            }
            for location in observation.locations
        ]
    return [
        {
            "location_id": "",
            "label": observation.location_label,
            "country": observation.country,
            "city": observation.city,
            "latitude": observation.latitude,
            "longitude": observation.longitude,
        }
    ]


def _context_same_country(context: dict[str, Any], site: USPresenceSite) -> bool:
    country = _clean(context.get("country", ""))
    return bool(country and site.country and _key(site.country) == _key(country))


def _context_same_city(context: dict[str, Any], site: USPresenceSite) -> bool:
    city = _clean(context.get("city", ""))
    return bool(_context_same_country(context, site) and city and site.city and _key(site.city) == _key(city))


def _distance_from_context_to_site(context: dict[str, Any], site: USPresenceSite) -> float | None:
    latitude = context.get("latitude")
    longitude = context.get("longitude")
    if latitude is None or longitude is None or site.latitude is None or site.longitude is None:
        return None
    return _haversine_km(float(latitude), float(longitude), float(site.latitude), float(site.longitude))


def _distance_to_site(observation: ResearchObservation, site: USPresenceSite) -> float | None:
    distances = [
        distance
        for context in _observation_geo_contexts(observation)
        if (distance := _distance_from_context_to_site(context, site)) is not None
    ]
    return min(distances) if distances else None


def _program_services(assessment: StateAssessment) -> set[str]:
    services: set[str] = set()
    for domain in assessment.program_domains:
        services.update(DOMAIN_TO_US_SERVICES.get(domain, set()))
    return {value.casefold() for value in services}


def _audience_services(assessment: StateAssessment) -> set[str]:
    services: set[str] = set()
    for audience in assessment.strategic_audiences:
        services.update(AUDIENCE_TO_US_SERVICES.get(audience, set()))
    return {value.casefold() for value in services}


def _service_source_applies(
    observation: ResearchObservation,
    site: USPresenceSite,
    *,
    nearby_km: float,
) -> bool:
    scope = site.coverage_scope
    contexts = _observation_geo_contexts(observation)
    same_country_contexts = [context for context in contexts if _context_same_country(context, site)]
    same_city_contexts = [context for context in same_country_contexts if _context_same_city(context, site)]
    if scope == "global":
        return True
    if scope == "country":
        return bool(same_country_contexts)
    if scope == "city":
        return bool(same_city_contexts)
    if scope == "site":
        if not same_country_contexts:
            return False
        if same_city_contexts:
            return True
        distances = [
            distance
            for context in same_country_contexts
            if (distance := _distance_from_context_to_site(context, site)) is not None
        ]
        return bool(distances) and min(distances) <= nearby_km
    return False


def _applicable_service_sources(
    observation: ResearchObservation,
    sites: Iterable[USPresenceSite],
    *,
    nearby_km: float,
) -> list[USPresenceSite]:
    return sorted(
        [
            site
            for site in sites
            if site.status not in {"closed", "inactive"}
            and site.service_tags
            and _service_source_applies(observation, site, nearby_km=nearby_km)
        ],
        key=lambda site: site.site_id,
    )


def _nearest_physical_site(
    observation: ResearchObservation,
    sites: Iterable[USPresenceSite],
) -> tuple[USPresenceSite | None, float | None]:
    spatial = [site for site in sites if site.status not in {"closed", "inactive"} and site.is_spatial]
    if not spatial:
        return None, None

    ranked = [
        (distance, site.site_id, site)
        for site in spatial
        if (distance := _distance_to_site(observation, site)) is not None
    ]
    if ranked:
        ranked.sort(key=lambda item: (item[0], item[1]))
        return ranked[0][2], ranked[0][0]

    contexts = _observation_geo_contexts(observation)
    same_city = [site for site in spatial if any(_context_same_city(context, site) for context in contexts)]
    if same_city:
        return sorted(same_city, key=lambda site: site.site_id)[0], None
    same_country = [site for site in spatial if any(_context_same_country(context, site) for context in contexts)]
    if same_country:
        return sorted(same_country, key=lambda site: site.site_id)[0], None
    return sorted(spatial, key=lambda site: site.site_id)[0], None


def assess_us_overlap(
    observation: ResearchObservation,
    assessment: StateAssessment,
    sites: Iterable[USPresenceSite],
    *,
    nearby_km: float = 50.0,
) -> USOverlapAssessment:
    sites = [site for site in sites if site.status not in {"closed", "inactive"}]
    contexts = _observation_geo_contexts(observation)
    same_country_sites = [site for site in sites if any(_context_same_country(context, site) for context in contexts)]
    same_city_sites = [
        site for site in same_country_sites if any(_context_same_city(context, site) for context in contexts)
    ]

    nearest, distance = _nearest_physical_site(observation, sites)
    service_sources = _applicable_service_sources(observation, sites, nearby_km=nearby_km)
    available_services = {tag.casefold() for site in service_sources for tag in site.service_tags}

    program_services = _program_services(assessment)
    audience_services = _audience_services(assessment)
    service_overlap = sorted(program_services & available_services)

    audience_overlap = [
        audience
        for audience in assessment.strategic_audiences
        if {value.casefold() for value in AUDIENCE_TO_US_SERVICES.get(audience, set())} & available_services
    ]
    thematic_overlap = [
        domain
        for domain in assessment.program_domains
        if {value.casefold() for value in DOMAIN_TO_US_SERVICES.get(domain, set())} & available_services
    ]

    relevant_services = program_services | audience_services
    contributing_sources = [
        site for site in service_sources if {tag.casefold() for tag in site.service_tags} & relevant_services
    ]
    structured_sources = [
        USServiceSourceAttribution(
            site_id=site.site_id,
            name=site.name,
            network=site.network,
            delivery_mode=site.delivery_mode,
            coverage_scope=site.coverage_scope,
            source_url=site.source_url,
            program_service_matches=sorted({tag.casefold() for tag in site.service_tags} & program_services),
            audience_service_matches=sorted({tag.casefold() for tag in site.service_tags} & audience_services),
        )
        for site in contributing_sources
    ]

    note_parts: list[str] = []
    if len(observation.locations) > 1:
        note_parts.append(
            f"service availability evaluated across {len(observation.locations)} structured activity locations"
        )
    if same_city_sites:
        note_parts.append("same-city U.S. public-diplomacy presence")
    elif distance is not None and distance <= nearby_km:
        note_parts.append(f"nearest physical U.S. presence within {distance:.1f} km")
    elif same_country_sites:
        note_parts.append("same-country U.S. public-diplomacy presence/service")
    if audience_overlap:
        note_parts.append("audience overlap: " + ", ".join(audience_overlap))
    if thematic_overlap:
        note_parts.append("thematic overlap: " + ", ".join(thematic_overlap))
    if service_overlap:
        note_parts.append("direct service overlap: " + ", ".join(service_overlap))
    if structured_sources:
        labels = [f"{source.name} [{source.delivery_mode}/{source.coverage_scope}]" for source in structured_sources]
        note_parts.append("applicable U.S. service sources: " + "; ".join(labels))

    return USOverlapAssessment(
        same_country=bool(same_country_sites),
        same_city=bool(same_city_sites),
        nearest_site_id=nearest.site_id if nearest else "",
        nearest_site_name=nearest.name if nearest else "",
        nearest_network=nearest.network if nearest else "",
        distance_km=round(distance, 2) if distance is not None else None,
        audience_overlap=audience_overlap,
        thematic_overlap=thematic_overlap,
        service_overlap=service_overlap,
        service_sources=structured_sources,
        note="; ".join(note_parts),
    )


def apply_us_overlaps(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    sites: Iterable[USPresenceSite],
    *,
    nearby_km: float = 50.0,
) -> list[StateAssessment]:
    observation_map = {row.observation_id: row for row in observations}
    sites = list(sites)
    result: list[StateAssessment] = []
    for assessment in assessments:
        observation = observation_map.get(assessment.observation_id)
        if observation:
            assessment.us_overlap = assess_us_overlap(observation, assessment, sites, nearby_km=nearby_km)
        result.append(assessment)
    return result


def _evidence_identities(observation: ResearchObservation) -> set[str]:
    identities = set(observation.source_record_keys)
    for item in observation.evidence:
        if item.url:
            identities.add(item.url)
        if item.platform and item.native_id:
            identities.add(f"{item.platform}:{item.native_id}")
    return identities


def _has_reach_metric(assessment: StateAssessment, metric_names: Iterable[str] = _REACH_METRIC_NAMES) -> bool:
    return any(assessment.reach.metric(name) is not None for name in metric_names)


def _reported_metric_meets_threshold(metric: Any, threshold: int) -> bool:
    if metric is None:
        return False
    qualifier = getattr(metric, "qualifier", "exact")
    if qualifier == "maximum":
        return False
    if qualifier == "range":
        lower = getattr(metric, "lower_bound", None)
        return lower is not None and lower >= threshold
    value = getattr(metric, "value", None)
    return value is not None and value >= threshold


def _qualified_reach_label(metric: Any) -> str:
    source_note = _clean(getattr(metric, "source_note", ""))
    if source_note:
        return source_note.rstrip(".")
    value = getattr(metric, "value", None)
    qualifier = getattr(metric, "qualifier", "exact")
    if qualifier == "approximate" and value is not None:
        return f"approximately {value:,}"
    if qualifier == "minimum" and value is not None:
        return f"at least {value:,}"
    if qualifier == "maximum" and value is not None:
        return f"at most {value:,}"
    if qualifier == "range":
        lower = getattr(metric, "lower_bound", None)
        upper = getattr(metric, "upper_bound", None)
        if lower is not None and upper is not None:
            return f"{lower:,}–{upper:,}"
    return f"{value:,}" if value is not None else "qualified value"


def audit_state_records(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
) -> dict[str, Any]:
    observations = list(observations)
    assessments = list(assessments)
    observation_map = {row.observation_id: row for row in observations}
    findings: list[dict[str, Any]] = []

    def finding(severity: str, code: str, assessment: StateAssessment | None, message: str) -> None:
        findings.append(
            {
                "severity": severity,
                "code": code,
                "assessment_id": assessment.assessment_id if assessment else "",
                "observation_id": assessment.observation_id if assessment else "",
                "message": message,
            }
        )

    seen_observations: set[str] = set()
    for assessment in assessments:
        if assessment.observation_id in seen_observations:
            finding(
                "error",
                "duplicate_assessment",
                assessment,
                "Multiple State assessments reference the same observation.",
            )
        seen_observations.add(assessment.observation_id)
        observation = observation_map.get(assessment.observation_id)
        if not observation:
            finding(
                "error",
                "missing_observation",
                assessment,
                "Assessment references an observation absent from the package.",
            )
            continue
        evidence = _evidence_identities(observation)
        if not evidence:
            finding("error", "no_observation_evidence", assessment, "Observation has no auditable source identity.")
        if assessment.review_state == "human_verified" and observation.verification_state != "human_verified":
            finding(
                "warning",
                "assessment_verified_before_observation",
                assessment,
                "State assessment is human-verified but the underlying observation is not human-verified.",
            )
        if assessment.prc_support.level in {"probable", "confirmed"}:
            missing = [ref for ref in assessment.prc_support.evidence_refs if ref not in evidence]
            if missing:
                finding(
                    "error",
                    "support_evidence_not_in_observation",
                    assessment,
                    f"PRC-support evidence references are not attached to the observation: {missing}",
                )
        if assessment.observability_level == "reach_observed" and not _has_reach_metric(assessment):
            finding(
                "warning",
                "reach_without_metric",
                assessment,
                "Reach is marked observed but no quantitative reach/engagement metric is stored.",
            )
        if assessment.observability_level == "engagement_observed" and not _has_reach_metric(
            assessment, _ENGAGEMENT_METRIC_NAMES
        ):
            finding(
                "warning",
                "engagement_without_metric",
                assessment,
                "Engagement is marked observed but no likes/comments/shares metric is stored.",
            )
        influence_claims = [claim for claim in assessment.claims if claim.claim_type == "influence"]
        if assessment.observability_level == "causal_influence_evidence" and not influence_claims:
            finding(
                "error",
                "causal_level_without_claim",
                assessment,
                "Causal influence evidence requires an explicit claim with evidence references.",
            )
        for claim in assessment.claims:
            missing = [ref for ref in claim.evidence_refs if ref not in evidence]
            if missing:
                finding(
                    "error",
                    "claim_evidence_not_in_observation",
                    assessment,
                    f"Claim {claim.claim_id} cites evidence not attached to the observation: {missing}",
                )
            if claim.claim_type == "influence":
                if claim.review_state != "human_verified":
                    finding(
                        "error",
                        "unverified_influence_claim",
                        assessment,
                        "Influence claims cannot enter State-facing output without human verification.",
                    )
                if assessment.observability_level != "causal_influence_evidence":
                    finding(
                        "error",
                        "influence_without_causal_evidence",
                        assessment,
                        "Influence claim exists without causal_influence_evidence observability level.",
                    )
            if (
                claim.claim_type == "support_relationship"
                and claim.review_state != "human_verified"
                and assessment.prc_support.level == "confirmed"
            ):
                finding(
                    "error",
                    "confirmed_support_unverified_claim",
                    assessment,
                    "Confirmed PRC support requires the supporting relationship claim to be human-verified.",
                )
        sensitive = SENSITIVE_NARRATIVES & set(assessment.narrative_tags)
        if sensitive:
            supported_types = {
                claim.claim_type for claim in assessment.claims if claim.review_state == "human_verified"
            }
            if "narrative" not in supported_types and "coordination" not in supported_types:
                finding(
                    "warning",
                    "sensitive_narrative_without_verified_claim",
                    assessment,
                    "Sensitive narrative/coordination labels should be backed by a human-verified claim before briefing.",
                )
        if assessment.brief_eligible and observation.verification_state != "human_verified":
            finding(
                "warning",
                "brief_eligible_unverified_observation",
                assessment,
                "Brief-eligible State assessment rests on an observation that still needs human verification.",
            )

    missing_assessments = sorted(set(observation_map) - seen_observations)
    for observation_id in missing_assessments:
        findings.append(
            {
                "severity": "info",
                "code": "observation_not_assessed",
                "assessment_id": "",
                "observation_id": observation_id,
                "message": "Observation has not yet received a State-specific assessment.",
            }
        )

    counts = Counter(item["severity"] for item in findings)
    if counts["error"]:
        status = "fail"
    elif counts["warning"]:
        status = "conditional"
    else:
        status = "pass"
    return {
        "generated_at": utc_iso(),
        "status": status,
        "observations": len(observations),
        "assessments": len(assessments),
        "brief_eligible": sum(row.brief_eligible for row in assessments),
        "errors": counts["error"],
        "warnings": counts["warning"],
        "info": counts["info"],
        "findings": findings,
    }


def review_priority(
    assessment: StateAssessment, observation: ResearchObservation | None = None
) -> tuple[int, list[str]]:
    """Prioritize human review workload. This is not an influence score."""
    score = 0
    reasons: list[str] = []
    if assessment.review_state == "needs_followup":
        score += 5
        reasons.append("explicit follow-up required")
    if assessment.prc_support.level in {"probable", "confirmed"} and assessment.review_state != "human_verified":
        score += 4
        reasons.append(f"{assessment.prc_support.level} PRC-support assessment needs verification")
    if assessment.us_overlap.material:
        score += 3
        reasons.append("material overlap with U.S. public-diplomacy presence/audience")
    if SENSITIVE_NARRATIVES & set(assessment.narrative_tags):
        score += 3
        reasons.append("sensitive narrative/coordination tag")
    if _reported_metric_meets_threshold(assessment.reach.metric("views"), 10_000):
        score += 2
        reasons.append("high reported/observed digital reach")
    if _reported_metric_meets_threshold(assessment.reach.metric("attendance"), 100):
        score += 2
        reasons.append("high reported/observed event attendance")
    if any(
        claim.claim_type in {"support_relationship", "coordination", "influence"}
        and claim.review_state != "human_verified"
        for claim in assessment.claims
    ):
        score += 4
        reasons.append("high-consequence claim awaiting verification")
    if observation is not None and len(observation.evidence) <= 1:
        score += 1
        reasons.append("single-source observation")
    if assessment.review_state == "human_verified":
        score = max(0, score - 4)
        reasons.append("already human-verified")
    return score, reasons


def build_review_queue(
    observations: Iterable[ResearchObservation], assessments: Iterable[StateAssessment]
) -> list[dict[str, Any]]:
    observation_map = {row.observation_id: row for row in observations}
    rows: list[dict[str, Any]] = []
    for assessment in assessments:
        observation = observation_map.get(assessment.observation_id)
        score, reasons = review_priority(assessment, observation)
        rows.append(
            {
                "review_priority": score,
                "assessment_id": assessment.assessment_id,
                "observation_id": assessment.observation_id,
                "observation_type": observation.observation_type if observation else "",
                "title": observation.title if observation else "",
                "country": observation.country if observation else "",
                "city": observation.city if observation else "",
                "verification_state": assessment.review_state,
                "prc_support": assessment.prc_support.level,
                "observability_level": assessment.observability_level,
                "strategic_audiences": "; ".join(assessment.strategic_audiences),
                "program_domains": "; ".join(assessment.program_domains),
                "narrative_tags": "; ".join(assessment.narrative_tags),
                "us_overlap": assessment.us_overlap.note,
                "us_service_source_ids": "; ".join(assessment.us_overlap.service_source_ids),
                "us_service_source_names": "; ".join(source.name for source in assessment.us_overlap.service_sources),
                "reasons": "; ".join(reasons),
                "primary_source_url": observation.primary_source_url if observation else "",
            }
        )
    return sorted(rows, key=lambda row: (-int(row["review_priority"]), row["country"], row["title"]))


def _verified_records(
    observations: Iterable[ResearchObservation], assessments: Iterable[StateAssessment]
) -> list[tuple[ResearchObservation, StateAssessment]]:
    observation_map = {row.observation_id: row for row in observations}
    result: list[tuple[ResearchObservation, StateAssessment]] = []
    for assessment in assessments:
        observation = observation_map.get(assessment.observation_id)
        if observation and assessment.brief_eligible and observation.verification_state == "human_verified":
            result.append((observation, assessment))
    return result


def render_state_bluf(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    *,
    title: str = "PRC Cultural Influence Network Research Update",
) -> str:
    observations = list(observations)
    assessments = list(assessments)
    verified = _verified_records(observations, assessments)
    countries = Counter(obs.country or "Unspecified" for obs, _ in verified)
    domains = Counter(domain for _, assessment in verified for domain in assessment.program_domains)
    audiences = Counter(audience for _, assessment in verified for audience in assessment.strategic_audiences)
    narratives = Counter(tag for _, assessment in verified for tag in assessment.narrative_tags)
    support = Counter(assessment.prc_support.level for _, assessment in verified)
    overlaps = [(obs, assessment) for obs, assessment in verified if assessment.us_overlap.material]
    gaps = Counter(assessment.review_state for assessment in assessments if not assessment.brief_eligible)

    lines = [f"# {title}", "", "## BLUF", ""]
    if verified:
        lines.append(
            f"SUGAR contains {len(verified)} human-verified, State-brief-eligible observations across "
            f"{len(countries)} countries from {len(observations)} total research observations. "
            f"{len(overlaps)} verified observations show material geographic, audience, thematic, or service overlap "
            "with an entered American Spaces/EducationUSA/U.S. public-diplomacy presence. "
            f"PRC support is confirmed in {support.get('confirmed', 0)} verified observations and probable in "
            f"{support.get('probable', 0)}. These are evidence-status statements, not a claim that observed activity or "
            "engagement caused attitudinal or behavioral influence."
        )
    else:
        lines.append(
            "No observations currently meet the package's verified-only briefing standard. Collection or AI triage may exist, "
            "but the system will not convert unverified material into State-facing judgments."
        )

    lines.extend(["", "## Key Judgments", ""])
    if verified:
        if countries:
            top = ", ".join(f"{name} ({count})" for name, count in countries.most_common(6))
            lines.append(f"- **Verified footprint:** The largest verified observation counts are in {top}.")
        if domains:
            top = ", ".join(f"{name} ({count})" for name, count in domains.most_common(6))
            lines.append(f"- **Programming:** The leading coded program domains are {top}.")
        if audiences:
            top = ", ".join(f"{name} ({count})" for name, count in audiences.most_common(6))
            lines.append(f"- **Strategic audiences:** Verified activity most often targets {top}.")
        if narratives:
            top = ", ".join(f"{name} ({count})" for name, count in narratives.most_common(6))
            lines.append(f"- **Narratives/themes:** The most frequent verified coded themes are {top}.")
        if overlaps:
            examples = []
            for obs, assessment in overlaps[:5]:
                label = obs.title or obs.program_name or obs.institution_name or obs.observation_id
                nearest = assessment.us_overlap.nearest_site_name or "U.S. presence"
                examples.append(f"{label} ↔ {nearest}")
            lines.append(
                f"- **U.S. overlap:** {len(overlaps)} verified observations have material overlap; examples include "
                + "; ".join(examples)
                + "."
            )
    else:
        lines.append("- No key judgment is released until evidence and human verification gates are satisfied.")

    lines.extend(["", "## Observable Reach and Engagement", ""])
    attendance = sum(assessment.reach.attendance or 0 for _, assessment in verified)
    views = sum(assessment.reach.views or 0 for _, assessment in verified)
    likes = sum(assessment.reach.likes or 0 for _, assessment in verified)
    comments = sum(assessment.reach.comments or 0 for _, assessment in verified)
    shares = sum(assessment.reach.shares_reposts or 0 for _, assessment in verified)
    lines.append(
        f"Verified records contain exact observed metrics totaling {attendance:,} reported/observed attendees, {views:,} views, "
        f"{likes:,} likes, {comments:,} comments, and {shares:,} shares/reposts. Exact totals exclude approximate and bounded values. "
        "These metrics remain separate because cross-platform engagement units are not directly comparable and should not be collapsed into a single influence score."
    )
    qualified_metrics: list[str] = []
    for observation, assessment in verified:
        label = (
            observation.title or observation.program_name or observation.institution_name or observation.observation_id
        )
        for metric_name in _REACH_METRIC_NAMES:
            metric = assessment.reach.metric(metric_name)
            if metric is None or metric.is_exact:
                continue
            qualified_metrics.append(f"{label} — {metric_name}: {_qualified_reach_label(metric)}")
    if qualified_metrics:
        displayed = qualified_metrics[:8]
        suffix = (
            f"; plus {len(qualified_metrics) - len(displayed)} additional qualified metrics"
            if len(qualified_metrics) > len(displayed)
            else ""
        )
        lines.append(
            "Qualified source-reported metrics are retained separately and not summed into exact totals: "
            + "; ".join(displayed)
            + suffix
            + "."
        )

    lines.extend(["", "## Verification and Collection Gaps", ""])
    lines.append(
        f"The package contains {len(assessments) - len(verified)} State assessments that are not yet briefing-eligible. "
        + (
            "Current review-state counts: " + ", ".join(f"{key}={value}" for key, value in sorted(gaps.items())) + "."
            if gaps
            else ""
        )
    )
    no_location = sum(1 for obs in observations if not obs.country and obs.latitude is None and not obs.locations)
    no_evidence = sum(1 for obs in observations if not obs.evidence and not obs.source_record_keys)
    lines.append(
        f"Location remains unresolved for {no_location} observations; {no_evidence} observations lack an auditable evidence identity."
    )

    lines.extend(
        [
            "",
            "## Analytic Guardrails",
            "",
            "- Presence, activity, reach, engagement, outcomes, and causal influence are separate concepts in this package.",
            "- Confirmed PRC support requires explicit evidence and human verification; Chinese identity, language, branding, or location alone is insufficient.",
            "- Anti-U.S. or coordination labels should not enter briefing judgments without a human-verified narrative/coordination claim tied to source evidence.",
            "- Public comments and social engagement are observable response surfaces, not representative public-opinion samples.",
            "- American Spaces/EducationUSA overlap identifies geographic, audience, thematic, or service co-presence; it does not itself establish competition, displacement, persuasion, or complementarity.",
            "",
        ]
    )
    return "\n".join(lines)


def _observation_geo_features(observation: ResearchObservation, assessment: StateAssessment) -> list[dict[str, Any]]:
    """Return one GeoJSON feature per defensible recorded activity location.

    Structured locations supersede the legacy scalar point for mapping. An unresolved structured
    location is not converted into a point here; interactive map resolution is handled separately.
    All venue features retain one observation/assessment identity so feature count never implies
    activity count.
    """
    common = {
        "layer": "prc_observation",
        "observation_id": observation.observation_id,
        "assessment_id": assessment.assessment_id,
        "title": observation.title,
        "observation_type": observation.observation_type,
        "verification_state": assessment.review_state,
        "prc_support": assessment.prc_support.level,
        "observability_level": assessment.observability_level,
        "reach": asdict(assessment.reach),
        "strategic_audiences": assessment.strategic_audiences,
        "program_domains": assessment.program_domains,
        "narrative_tags": assessment.narrative_tags,
        "us_overlap_material": assessment.us_overlap.material,
        "us_service_sources": [asdict(source) for source in assessment.us_overlap.service_sources],
        "primary_source_url": observation.primary_source_url,
    }
    if observation.locations:
        features: list[dict[str, Any]] = []
        total = len(observation.locations)
        for index, location in enumerate(observation.locations, 1):
            if location.latitude is None or location.longitude is None:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [location.longitude, location.latitude]},
                    "properties": {
                        **common,
                        "country": location.country or observation.country,
                        "region": location.region or observation.region,
                        "city": location.city or observation.city,
                        "location_id": location.location_id,
                        "location_label": location.label,
                        "location_precision": location.precision,
                        "location_confidence": location.confidence,
                        "location_uncertainty_km": location.uncertainty_km,
                        "location_basis": location.basis,
                        "location_source_ref": location.source_ref,
                        "activity_location_index": index,
                        "activity_location_count": total,
                    },
                }
            )
        return features
    if observation.latitude is None or observation.longitude is None:
        return []
    return [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [observation.longitude, observation.latitude]},
            "properties": {
                **common,
                "country": observation.country,
                "region": observation.region,
                "city": observation.city,
                "location_id": "",
                "location_label": observation.location_label,
                "location_precision": "",
                "location_confidence": observation.location_confidence,
                "location_uncertainty_km": None,
                "location_basis": observation.location_basis,
                "location_source_ref": "",
                "activity_location_index": 1,
                "activity_location_count": 1,
            },
        }
    ]


def state_geojson(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    sites: Iterable[USPresenceSite] = (),
    *,
    verified_only: bool = True,
) -> dict[str, Any]:
    observation_map = {row.observation_id: row for row in observations}
    features: list[dict[str, Any]] = []
    for assessment in assessments:
        observation = observation_map.get(assessment.observation_id)
        if not observation:
            continue
        if verified_only and not (assessment.brief_eligible and observation.verification_state == "human_verified"):
            continue
        features.extend(_observation_geo_features(observation, assessment))
    for site in sites:
        if not site.is_spatial:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [site.longitude, site.latitude]},
                "properties": {
                    "layer": "us_presence",
                    "site_id": site.site_id,
                    "name": site.name,
                    "network": site.network,
                    "subtype": site.subtype,
                    "country": site.country,
                    "city": site.city,
                    "delivery_mode": site.delivery_mode,
                    "coverage_scope": site.coverage_scope,
                    "location_precision": site.location_precision,
                    "location_confidence": site.location_confidence,
                    "location_uncertainty_km": site.location_uncertainty_km,
                    "location_basis": site.location_basis,
                    "service_tags": site.service_tags,
                    "source_url": site.source_url,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def save_state_assessments(assessments: Iterable[StateAssessment], path: str | Path) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as stream:
        for assessment in assessments:
            stream.write(json.dumps(asdict(assessment), ensure_ascii=False, sort_keys=True) + "\n")
    return str(target.resolve())


def load_state_assessments(path: str | Path) -> list[StateAssessment]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    rows: list[StateAssessment] = []
    with source.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            text = line.strip()
            if not text:
                continue
            try:
                raw = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid State assessment JSON on line {line_number}") from exc
            rows.append(StateAssessment.from_dict(raw))
    return rows


def blank_state_assessments(observations: Iterable[ResearchObservation]) -> list[StateAssessment]:
    return [StateAssessment(observation_id=row.observation_id) for row in observations]


def compare_state_snapshots(previous: Iterable[StateAssessment], current: Iterable[StateAssessment]) -> dict[str, Any]:
    old = {row.observation_id: row for row in previous}
    new = {row.observation_id: row for row in current}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed: list[dict[str, Any]] = []
    for observation_id in sorted(set(old) & set(new)):
        left = old[observation_id]
        right = new[observation_id]
        if left.fingerprint() == right.fingerprint():
            continue
        fields: list[str] = []
        if left.prc_support.level != right.prc_support.level:
            fields.append("prc_support")
        if left.review_state != right.review_state:
            fields.append("review_state")
        if left.observability_level != right.observability_level:
            fields.append("observability_level")
        if asdict(left.reach) != asdict(right.reach):
            fields.append("reach")
        if asdict(left.us_overlap) != asdict(right.us_overlap):
            fields.append("us_overlap")
        if left.strategic_audiences != right.strategic_audiences:
            fields.append("strategic_audiences")
        if left.program_domains != right.program_domains:
            fields.append("program_domains")
        if left.narrative_tags != right.narrative_tags:
            fields.append("narrative_tags")
        if len(left.claims) != len(right.claims):
            fields.append("claims")
        changed.append({"observation_id": observation_id, "changed_fields": fields or ["other"]})
    return {
        "generated_at": utc_iso(),
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": len(set(old) & set(new)) - len(changed),
    }


def _assessment_frame(assessments: Iterable[StateAssessment]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for assessment in assessments:
        raw = asdict(assessment)
        for key in (
            "strategic_audiences",
            "program_domains",
            "narrative_tags",
            "sponsor_entities",
            "host_entities",
            "partner_entities",
            "delivery_modes",
            "policy_relevance",
            "prc_support",
            "reach",
            "us_overlap",
            "claims",
        ):
            raw[key] = json.dumps(raw[key], ensure_ascii=False, sort_keys=True)
        rows.append(raw)
    frame = pd.DataFrame(rows)
    if not frame.empty:
        for column in frame.columns:
            frame[column] = frame[column].map(lambda value: safe_cell(value, formula_safe=True))
    return frame


def save_state_package(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    output_directory: str | Path,
    *,
    name: str = "state_research",
    us_sites: Iterable[USPresenceSite] = (),
    previous_assessments: Iterable[StateAssessment] | None = None,
    title: str = "PRC Cultural Influence Network Research Update",
) -> list[str]:
    observations = list(observations)
    assessments = list(assessments)
    sites = list(us_sites)
    out_dir = Path(output_directory).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_artifact_stem(name, "state_research")

    if sites:
        apply_us_overlaps(observations, assessments, sites)

    jsonl_path = out_dir / f"{stem}.state.jsonl"
    csv_path = out_dir / f"{stem}.state.csv"
    xlsx_path = out_dir / f"{stem}.state.xlsx"
    audit_path = out_dir / f"{stem}.audit.json"
    queue_path = out_dir / f"{stem}.review_queue.csv"
    brief_path = out_dir / f"{stem}.brief.md"
    geojson_path = out_dir / f"{stem}.map.geojson"
    snapshot_path = out_dir / f"{stem}.snapshot.json"

    save_state_assessments(assessments, jsonl_path)
    frame = _assessment_frame(assessments)
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL, lineterminator="\n")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="state_assessments")
        pd.DataFrame(build_review_queue(observations, assessments)).to_excel(
            writer, index=False, sheet_name="review_queue"
        )
        pd.DataFrame([asdict(site) for site in sites]).to_excel(writer, index=False, sheet_name="us_presence")

    audit = audit_state_records(observations, assessments)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame(build_review_queue(observations, assessments)).to_csv(queue_path, index=False, encoding="utf-8-sig")
    brief_path.write_text(render_state_bluf(observations, assessments, title=title), encoding="utf-8")
    geojson_path.write_text(
        json.dumps(state_geojson(observations, assessments, sites), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    snapshot: dict[str, Any] = {
        "generated_at": utc_iso(),
        "name": stem,
        "observations": len(observations),
        "assessments": len(assessments),
        "us_presence_sites": len(sites),
        "audit_status": audit["status"],
        "brief_eligible": audit["brief_eligible"],
        "assessment_fingerprints": {row.observation_id: row.fingerprint() for row in assessments},
    }
    if previous_assessments is not None:
        snapshot["change_detection"] = compare_state_snapshots(previous_assessments, assessments)
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    return [
        str(jsonl_path),
        str(csv_path),
        str(xlsx_path),
        str(audit_path),
        str(queue_path),
        str(brief_path),
        str(geojson_path),
        str(snapshot_path),
    ]


def package_from_files(
    observations_file: str | Path,
    output_directory: str | Path,
    *,
    assessments_file: str | Path | None = None,
    us_sites_file: str | Path | None = None,
    previous_assessments_file: str | Path | None = None,
    name: str = "state_research",
    title: str = "PRC Cultural Influence Network Research Update",
) -> list[str]:
    observations = load_observations(observations_file)
    assessments = (
        load_state_assessments(assessments_file) if assessments_file else blank_state_assessments(observations)
    )
    sites = load_us_presence_sites(us_sites_file) if us_sites_file else []
    previous = load_state_assessments(previous_assessments_file) if previous_assessments_file else None
    return save_state_package(
        observations,
        assessments,
        output_directory,
        name=name,
        us_sites=sites,
        previous_assessments=previous,
        title=title,
    )
