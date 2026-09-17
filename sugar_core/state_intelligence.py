from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from .observations import ResearchObservation
from .state_schema import StateAssessment
from .utils import utc_iso

ANALYTIC_INTELLIGENCE_VERSION = "1.0"
OFFLINE_TYPES = {"institution", "program", "event", "partnership"}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _parse_time(value: str) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _month(value: str) -> str:
    parsed = _parse_time(value)
    return parsed.strftime("%Y-%m") if parsed else ""


def _entropy(counts: Counter[str]) -> float | None:
    total = sum(counts.values())
    if total <= 0:
        return None
    if len(counts) <= 1:
        return 0.0
    raw = -sum((count / total) * math.log(count / total) for count in counts.values() if count)
    return round(raw / math.log(len(counts)), 4)


def _hhi(counts: Counter[str]) -> float | None:
    total = sum(counts.values())
    if total <= 0:
        return None
    return round(sum((count / total) ** 2 for count in counts.values()), 4)


def _distribution(counts: Counter[str]) -> list[dict[str, Any]]:
    total = sum(counts.values())
    return [
        {"value": key, "count": count, "share": round(count / total, 4) if total else None}
        for key, count in counts.most_common()
    ]


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _verified(observation: ResearchObservation, assessment: StateAssessment) -> bool:
    return observation.verification_state == "human_verified" and assessment.brief_eligible


def _feature_set(observation: ResearchObservation, assessment: StateAssessment) -> set[str]:
    values: set[str] = set()
    values.update(f"domain:{x}" for x in assessment.program_domains)
    values.update(f"audience:{x}" for x in assessment.strategic_audiences)
    values.update(f"narrative:{x}" for x in assessment.narrative_tags)
    values.update(f"sponsor:{x.casefold()}" for x in assessment.sponsor_entities)
    values.update(f"host:{x.casefold()}" for x in assessment.host_entities)
    values.update(f"partner:{x.casefold()}" for x in assessment.partner_entities)
    values.update(f"actor:{x.casefold()}" for x in observation.actors)
    if observation.institution_name:
        values.add(f"institution:{observation.institution_name.casefold()}")
    if observation.program_name:
        values.add(f"program:{observation.program_name.casefold()}")
    return values


def evidence_profile(observation: ResearchObservation) -> dict[str, Any]:
    source_types = Counter(_clean(x.source_type).casefold() or "unspecified" for x in observation.evidence)
    platforms = Counter(_clean(x.platform).casefold() for x in observation.evidence if _clean(x.platform))
    identities = set(observation.source_record_keys)
    identities.update(x.url for x in observation.evidence if x.url)
    identities.update(f"{x.platform}:{x.native_id}" for x in observation.evidence if x.platform and x.native_id)
    return {
        "references": len(observation.evidence),
        "distinct_evidence_identities": len(identities),
        "source_types": _distribution(source_types),
        "platforms": _distribution(platforms),
        "source_type_diversity": _entropy(source_types),
        "has_primary_source": bool(observation.primary_source_url),
    }


def _reach(assessment: StateAssessment) -> dict[str, int | None]:
    return {
        "attendance": assessment.reach.attendance,
        "views": assessment.reach.views,
        "likes": assessment.reach.likes,
        "comments": assessment.reach.comments,
        "shares_reposts": assessment.reach.shares_reposts,
        "followers": assessment.reach.followers,
    }


def _case_priority(observation: ResearchObservation, assessment: StateAssessment) -> tuple[int, int, int, int]:
    priority = {"urgent": 4, "high": 3, "normal": 2, "low": 1}.get(assessment.analytic_priority, 2)
    support = {"confirmed": 4, "probable": 3, "possible": 2, "unsupported": 1, "not_assessed": 0}.get(
        assessment.prc_support.level, 0
    )
    return (
        priority,
        support,
        int(assessment.us_overlap.material),
        len(observation.evidence) + len(observation.source_record_keys),
    )


def build_case_profile(
    observation: ResearchObservation,
    assessment: StateAssessment,
    *,
    corpus_pairs: Iterable[tuple[ResearchObservation, StateAssessment]] = (),
    comparable_limit: int = 5,
) -> dict[str, Any]:
    pairs = list(corpus_pairs)
    features = _feature_set(observation, assessment)
    comparable: list[tuple[float, ResearchObservation, StateAssessment]] = []
    for other_observation, other_assessment in pairs:
        if other_observation.observation_id == observation.observation_id:
            continue
        score = _jaccard(features, _feature_set(other_observation, other_assessment))
        if score > 0:
            comparable.append((score, other_observation, other_assessment))
    comparable.sort(key=lambda row: (-row[0], row[1].country != observation.country, row[1].observation_id))

    uncertainty: list[str] = []
    if observation.location_confidence is not None and observation.location_confidence < 0.6:
        uncertainty.append("low_location_confidence")
    if not observation.evidence and not observation.source_record_keys:
        uncertainty.append("no_auditable_evidence_identity")
    if observation.verification_state != "human_verified":
        uncertainty.append("observation_not_human_verified")
    if assessment.review_state != "human_verified":
        uncertainty.append("assessment_not_human_verified")
    if assessment.prc_support.level in {"possible", "probable"}:
        uncertainty.append("prc_support_not_confirmed")
    if assessment.prc_support.level == "confirmed" and len(assessment.prc_support.evidence_refs) < 2:
        uncertainty.append("confirmed_support_single_evidence_identity")
    if assessment.observability_level in {"reach_observed", "engagement_observed"}:
        uncertainty.append("reach_or_engagement_is_not_outcome_evidence")

    source_refs = set(observation.source_record_keys)
    source_refs.update(x.url for x in observation.evidence if x.url)
    return {
        "observation_id": observation.observation_id,
        "assessment_id": assessment.assessment_id,
        "title": observation.title
        or observation.program_name
        or observation.institution_name
        or observation.summary[:120],
        "summary": observation.summary,
        "observation_type": observation.observation_type,
        "observed_at": observation.observed_at,
        "location": {
            "country": observation.country,
            "region": observation.region,
            "city": observation.city,
            "basis": observation.location_basis,
            "confidence": observation.location_confidence,
        },
        "institution_name": observation.institution_name,
        "program_name": observation.program_name,
        "actors": observation.actors,
        "sponsors": assessment.sponsor_entities,
        "hosts": assessment.host_entities,
        "partners": assessment.partner_entities,
        "strategic_audiences": assessment.strategic_audiences,
        "program_domains": assessment.program_domains,
        "narrative_tags": assessment.narrative_tags,
        "delivery_modes": assessment.delivery_modes,
        "policy_relevance": assessment.policy_relevance,
        "prc_support": asdict(assessment.prc_support),
        "observability_level": assessment.observability_level,
        "reach": _reach(assessment),
        "us_overlap": asdict(assessment.us_overlap),
        "verification": {
            "observation": observation.verification_state,
            "assessment": assessment.review_state,
            "brief_eligible": assessment.brief_eligible,
        },
        "evidence_profile": evidence_profile(observation),
        "high_consequence_claims": [
            asdict(claim)
            for claim in assessment.claims
            if claim.claim_type in {"support_relationship", "coordination", "influence"}
        ],
        "uncertainty_flags": uncertainty,
        "comparables": [
            {
                "observation_id": other_observation.observation_id,
                "assessment_id": other_assessment.assessment_id,
                "similarity": round(score, 4),
                "country": other_observation.country,
                "city": other_observation.city,
                "title": other_observation.title or other_observation.summary[:100],
                "shared_features": sorted(features & _feature_set(other_observation, other_assessment))[:30],
            }
            for score, other_observation, other_assessment in comparable[:comparable_limit]
        ],
        "source_refs": sorted(source_refs),
    }


def _monthly_series(pairs: list[tuple[ResearchObservation, StateAssessment]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for observation, assessment in pairs:
        month = _month(observation.observed_at)
        if not month:
            continue
        row = buckets.setdefault(
            month,
            {
                "month": month,
                "observations": 0,
                "verified_observations": 0,
                "countries": set(),
                "cities": set(),
                "actors": set(),
                "domains": set(),
                "audiences": set(),
                "narratives": set(),
            },
        )
        row["observations"] += 1
        row["verified_observations"] += int(_verified(observation, assessment))
        if observation.country:
            row["countries"].add(observation.country)
        if observation.city:
            row["cities"].add(f"{observation.country}|{observation.city}")
        row["actors"].update(observation.actors)
        row["domains"].update(assessment.program_domains)
        row["audiences"].update(assessment.strategic_audiences)
        row["narratives"].update(assessment.narrative_tags)
    return [
        {
            "month": key,
            "observations": raw["observations"],
            "verified_observations": raw["verified_observations"],
            "countries": len(raw["countries"]),
            "cities": len(raw["cities"]),
            "actors": len(raw["actors"]),
            "domains": len(raw["domains"]),
            "audiences": len(raw["audiences"]),
            "narratives": len(raw["narratives"]),
        }
        for key, raw in sorted(buckets.items())
    ]


def _entity_recurrence(pairs: list[tuple[ResearchObservation, StateAssessment]]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for observation, assessment in pairs:
        for role, values in (
            ("sponsor", assessment.sponsor_entities),
            ("host", assessment.host_entities),
            ("partner", assessment.partner_entities),
            ("actor", observation.actors),
        ):
            for value in values:
                key = f"{role}|{value.casefold()}"
                row = rows.setdefault(
                    key,
                    {
                        "role": role,
                        "entity": value,
                        "observations": set(),
                        "countries": set(),
                        "cities": set(),
                        "domains": set(),
                        "audiences": set(),
                        "narratives": set(),
                    },
                )
                row["observations"].add(observation.observation_id)
                if observation.country:
                    row["countries"].add(observation.country)
                if observation.city:
                    row["cities"].add(f"{observation.country}|{observation.city}")
                row["domains"].update(assessment.program_domains)
                row["audiences"].update(assessment.strategic_audiences)
                row["narratives"].update(assessment.narrative_tags)
    result = []
    for row in rows.values():
        result.append(
            {
                "role": row["role"],
                "entity": row["entity"],
                "observations": len(row["observations"]),
                "countries": sorted(row["countries"]),
                "country_count": len(row["countries"]),
                "city_count": len(row["cities"]),
                "program_domains": sorted(row["domains"]),
                "strategic_audiences": sorted(row["audiences"]),
                "narrative_tags": sorted(row["narratives"]),
                "cross_border_recurrence": len(row["countries"]) >= 2,
            }
        )
    return sorted(
        result, key=lambda row: (-row["country_count"], -row["observations"], row["role"], row["entity"].casefold())
    )


def _digital_offline_coupling(
    pairs: list[tuple[ResearchObservation, StateAssessment]], max_days: int = 45
) -> list[dict[str, Any]]:
    digital = [pair for pair in pairs if pair[0].observation_type == "digital_post"]
    offline = [pair for pair in pairs if pair[0].observation_type in OFFLINE_TYPES]
    result: list[dict[str, Any]] = []
    for digital_obs, digital_assessment in digital:
        digital_time = _parse_time(digital_obs.observed_at)
        digital_entities = set(
            digital_obs.actors
            + digital_assessment.sponsor_entities
            + digital_assessment.host_entities
            + digital_assessment.partner_entities
        )
        digital_entities.update(x for x in (digital_obs.institution_name, digital_obs.program_name) if x)
        digital_entities = {x.casefold() for x in digital_entities if x}
        for offline_obs, offline_assessment in offline:
            if digital_obs.country and offline_obs.country and digital_obs.country != offline_obs.country:
                continue
            offline_entities = set(
                offline_obs.actors
                + offline_assessment.sponsor_entities
                + offline_assessment.host_entities
                + offline_assessment.partner_entities
            )
            offline_entities.update(x for x in (offline_obs.institution_name, offline_obs.program_name) if x)
            shared = digital_entities & {x.casefold() for x in offline_entities if x}
            if not shared:
                continue
            offline_time = _parse_time(offline_obs.observed_at)
            days = abs((digital_time - offline_time).days) if digital_time and offline_time else None
            if days is not None and days > max_days:
                continue
            result.append(
                {
                    "digital_observation_id": digital_obs.observation_id,
                    "offline_observation_id": offline_obs.observation_id,
                    "country": digital_obs.country or offline_obs.country,
                    "shared_entities": sorted(shared),
                    "days_apart": days,
                    "shared_domains": sorted(
                        set(digital_assessment.program_domains) & set(offline_assessment.program_domains)
                    ),
                    "shared_audiences": sorted(
                        set(digital_assessment.strategic_audiences) & set(offline_assessment.strategic_audiences)
                    ),
                    "interpretation": "Observed digital/offline coupling candidate; not proof of coordination or influence.",
                }
            )
    return sorted(
        result,
        key=lambda row: (
            row["days_apart"] if row["days_apart"] is not None else 10**9,
            row["country"],
            row["digital_observation_id"],
        ),
    )


def _clusters(
    pairs: list[tuple[ResearchObservation, StateAssessment]], threshold: float = 0.45
) -> list[dict[str, Any]]:
    if len(pairs) < 2:
        return []
    parent = list(range(len(pairs)))
    features = [_feature_set(*pair) for pair in pairs]
    scores: dict[tuple[int, int], float] = {}

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a

    for left in range(len(pairs)):
        for right in range(left + 1, len(pairs)):
            score = _jaccard(features[left], features[right])
            scores[(left, right)] = score
            if score >= threshold:
                union(left, right)
    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(pairs)):
        groups[find(index)].append(index)
    result = []
    for members in groups.values():
        if len(members) < 2:
            continue
        pair_scores = [
            scores.get((min(a, b), max(a, b)), 0.0) for pos, a in enumerate(members) for b in members[pos + 1 :]
        ]
        domains = Counter(x for i in members for x in pairs[i][1].program_domains)
        audiences = Counter(x for i in members for x in pairs[i][1].strategic_audiences)
        narratives = Counter(x for i in members for x in pairs[i][1].narrative_tags)
        countries = Counter(pairs[i][0].country or "Unspecified" for i in members)
        common = set.intersection(*(features[i] for i in members)) if members else set()
        result.append(
            {
                "cluster_id": f"archetype_{len(result) + 1}",
                "size": len(members),
                "mean_pair_similarity": round(sum(pair_scores) / len(pair_scores), 4) if pair_scores else 1.0,
                "countries": _distribution(countries),
                "program_domains": _distribution(domains),
                "strategic_audiences": _distribution(audiences),
                "narrative_tags": _distribution(narratives),
                "common_features": sorted(common),
                "observation_ids": [pairs[i][0].observation_id for i in members],
                "guardrail": "Similarity cluster is a descriptive archetype, not evidence of common direction, coordination, or influence.",
            }
        )
    return sorted(result, key=lambda row: (-row["size"], -row["mean_pair_similarity"]))


def _source_mix(pairs: list[tuple[ResearchObservation, StateAssessment]]) -> dict[str, Counter[str]]:
    result: dict[str, Counter[str]] = defaultdict(Counter)
    for observation, _ in pairs:
        country = observation.country or "Unspecified"
        if observation.evidence:
            for item in observation.evidence:
                result[country][_clean(item.source_type).casefold() or "unspecified"] += 1
        else:
            result[country]["no_structured_source_type"] += 1
    return result


def _distribution_overlap(left: Counter[str], right: Counter[str]) -> float:
    left_total, right_total = sum(left.values()), sum(right.values())
    if not left_total or not right_total:
        return 0.0
    keys = set(left) | set(right)
    total_variation = 0.5 * sum(abs(left.get(k, 0) / left_total - right.get(k, 0) / right_total) for k in keys)
    return max(0.0, 1.0 - total_variation)


def _comparability(pairs: list[tuple[ResearchObservation, StateAssessment]]) -> list[dict[str, Any]]:
    by_country: dict[str, list[tuple[ResearchObservation, StateAssessment]]] = defaultdict(list)
    for pair in pairs:
        by_country[pair[0].country or "Unspecified"].append(pair)
    source_mix = _source_mix(pairs)
    countries = sorted(by_country)
    result = []
    for pos, left in enumerate(countries):
        for right in countries[pos + 1 :]:
            left_rows, right_rows = by_country[left], by_country[right]
            source_similarity = _distribution_overlap(source_mix[left], source_mix[right])
            left_months = {_month(obs.observed_at) for obs, _ in left_rows if _month(obs.observed_at)}
            right_months = {_month(obs.observed_at) for obs, _ in right_rows if _month(obs.observed_at)}
            temporal_similarity = _jaccard(left_months, right_months)
            left_verified = sum(_verified(*x) for x in left_rows) / max(1, len(left_rows))
            right_verified = sum(_verified(*x) for x in right_rows) / max(1, len(right_rows))
            verification_similarity = 1 - abs(left_verified - right_verified)
            score = 0.5 * source_similarity + 0.3 * temporal_similarity + 0.2 * verification_similarity
            result.append(
                {
                    "country_a": left,
                    "country_b": right,
                    "comparability": round(score, 4),
                    "label": "strong" if score >= 0.75 else "moderate" if score >= 0.5 else "weak",
                    "source_mix_similarity": round(source_similarity, 4),
                    "temporal_coverage_similarity": round(temporal_similarity, 4),
                    "verification_rate_similarity": round(verification_similarity, 4),
                    "guardrail": "Corpus comparability is not country similarity or relative influence.",
                }
            )
    return sorted(result, key=lambda row: (-row["comparability"], row["country_a"], row["country_b"]))


def _anomalies(pairs: list[tuple[ResearchObservation, StateAssessment]]) -> list[dict[str, Any]]:
    by_country: dict[str, list[tuple[ResearchObservation, StateAssessment]]] = defaultdict(list)
    for pair in pairs:
        by_country[pair[0].country or "Unspecified"].append(pair)
    result = []
    for country, rows in by_country.items():
        for metric in ("attendance", "views", "likes", "comments", "shares_reposts"):
            values = [getattr(a.reach, metric) for _, a in rows if getattr(a.reach, metric) is not None]
            if len(values) < 3:
                continue
            med = median(values)
            mad = median(abs(x - med) for x in values)
            if not mad:
                continue
            for observation, assessment in rows:
                value = getattr(assessment.reach, metric)
                if value is None:
                    continue
                robust_z = 0.6745 * (value - med) / mad
                if robust_z >= 3.5:
                    result.append(
                        {
                            "observation_id": observation.observation_id,
                            "country": country,
                            "metric": metric,
                            "value": value,
                            "country_median": med,
                            "robust_z": round(robust_z, 3),
                            "interpretation": "Reach/engagement outlier within the observed corpus; not evidence of influence.",
                        }
                    )
    return sorted(result, key=lambda row: (-row["robust_z"], row["country"]))


def _signals(
    pairs: list[tuple[ResearchObservation, StateAssessment]], monthly: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if len(monthly) >= 4:
        recent, prior = monthly[-2:], monthly[-4:-2]
        recent_obs = sum(x["verified_observations"] for x in recent)
        prior_obs = sum(x["verified_observations"] for x in prior)
        if recent_obs >= 3 and recent_obs > prior_obs * 1.5:
            result.append(
                {
                    "signal": "observed_activity_acceleration_candidate",
                    "basis": {"recent_verified": recent_obs, "prior_verified": prior_obs},
                    "confidence": "low",
                    "caveat": "Collection volume, access, query design, or verification tempo may explain the increase.",
                }
            )
        if max((x["countries"] for x in recent), default=0) > max((x["countries"] for x in prior), default=0):
            result.append(
                {
                    "signal": "observed_geographic_broadening_candidate",
                    "confidence": "low",
                    "caveat": "Not coverage-adjusted.",
                }
            )
        if max((x["domains"] for x in recent), default=0) > max((x["domains"] for x in prior), default=0):
            result.append(
                {
                    "signal": "observed_program_diversification_candidate",
                    "confidence": "low",
                    "caveat": "Not coverage-adjusted.",
                }
            )
    recurrent: dict[str, Counter[str]] = defaultdict(Counter)
    for observation, assessment in pairs:
        country = observation.country or "Unspecified"
        for value in (
            observation.actors + assessment.sponsor_entities + assessment.host_entities + assessment.partner_entities
        ):
            if value:
                recurrent[country][value.casefold()] += 1
    for country, counts in recurrent.items():
        top = [(entity, count) for entity, count in counts.items() if count >= 3]
        if top:
            result.append(
                {
                    "signal": "recurrent_actor_embedding",
                    "country": country,
                    "confidence": "moderate",
                    "basis": [
                        {"entity": entity, "observations": count}
                        for entity, count in sorted(top, key=lambda x: -x[1])[:8]
                    ],
                    "caveat": "Repeated participation is not proof of control or strategic intent.",
                }
            )
    return result


def _collection_questions(
    observations: list[ResearchObservation],
    assessments: list[StateAssessment],
    verified_pairs: list[tuple[ResearchObservation, StateAssessment]],
) -> list[dict[str, Any]]:
    result = []
    unresolved_support = [
        a for a in assessments if a.prc_support.level in {"possible", "probable"} and a.review_state != "rejected"
    ]
    if unresolved_support:
        result.append(
            {
                "question": "Which probable/possible PRC-support relationships can be confirmed or rejected with independent primary or credible host-source evidence?",
                "priority": "high",
                "affected_assessment_ids": [x.assessment_id for x in unresolved_support[:50]],
            }
        )
    unresolved_location = [x for x in observations if not x.country or x.location_basis == "unknown"]
    if unresolved_location:
        result.append(
            {
                "question": "Which unresolved locations materially affect country/city comparison or American Spaces overlap?",
                "priority": "high" if len(unresolved_location) >= 5 else "normal",
                "affected_observation_ids": [x.observation_id for x in unresolved_location[:50]],
            }
        )
    weak_high_consequence = [
        obs.observation_id
        for obs, assessment in verified_pairs
        if evidence_profile(obs)["distinct_evidence_identities"] <= 1
        and assessment.prc_support.level in {"probable", "confirmed"}
    ]
    if weak_high_consequence:
        result.append(
            {
                "question": "Which high-consequence verified cases depend on only one evidence identity and need corroboration?",
                "priority": "high",
                "affected_observation_ids": weak_high_consequence[:50],
            }
        )
    influence_claims = [
        claim.claim_id
        for a in assessments
        for claim in a.claims
        if claim.claim_type == "influence" and claim.review_state != "rejected"
    ]
    if influence_claims:
        result.append(
            {
                "question": "What evidence would discriminate persuasion or behavioral influence from exposure, reach, or engagement?",
                "priority": "high",
                "affected_claim_ids": influence_claims[:50],
            }
        )
    return result


def build_intelligence_packet(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    *,
    country: str = "",
    observation_id: str = "",
    representative_case_limit: int = 20,
) -> dict[str, Any]:
    observations, assessments = list(observations), list(assessments)
    observation_map = {x.observation_id: x for x in observations}
    pairs = [(observation_map[a.observation_id], a) for a in assessments if a.observation_id in observation_map]
    if country:
        pairs = [x for x in pairs if x[0].country.casefold() == country.casefold()]
    if observation_id:
        pairs = [x for x in pairs if x[0].observation_id == observation_id]
    scoped_observations, scoped_assessments = [x[0] for x in pairs], [x[1] for x in pairs]
    verified_pairs = [x for x in pairs if _verified(*x)]
    analysis_pairs = verified_pairs or pairs

    countries = Counter(obs.country or "Unspecified" for obs, _ in verified_pairs)
    cities = Counter(f"{obs.country}|{obs.city}" for obs, _ in verified_pairs if obs.city)
    domains = Counter(x for _, a in verified_pairs for x in a.program_domains)
    audiences = Counter(x for _, a in verified_pairs for x in a.strategic_audiences)
    narratives = Counter(x for _, a in verified_pairs for x in a.narrative_tags)
    support = Counter(a.prc_support.level for _, a in verified_pairs)
    types = Counter(obs.observation_type for obs, _ in verified_pairs)
    delivery = Counter(x for _, a in verified_pairs for x in a.delivery_modes)
    source_types = Counter(
        _clean(item.source_type).casefold() or "unspecified" for obs, _ in pairs for item in obs.evidence
    )
    monthly = _monthly_series(pairs)
    recurrence = _entity_recurrence(verified_pairs)

    multi_source = sum(evidence_profile(obs)["distinct_evidence_identities"] >= 2 for obs, _ in verified_pairs)
    ranked = sorted(analysis_pairs, key=lambda pair: _case_priority(*pair), reverse=True)
    return {
        "intelligence_version": ANALYTIC_INTELLIGENCE_VERSION,
        "generated_at": utc_iso(),
        "scope": {
            "country": country,
            "observation_id": observation_id,
            "mode": "micro" if observation_id else "country" if country else "global",
        },
        "guardrails": [
            "This describes the research corpus, not the full universe of PRC public-diplomacy activity.",
            "Counts and time movement are not coverage-adjusted unless explicitly stated.",
            "Presence, activity, reach, engagement, outcomes, and causal influence are separate concepts.",
            "Cross-country quantitative comparisons require corpus-comparability review.",
            "Similarity, recurrence, and digital/offline coupling are discovery signals, not proof of coordination, intent, or influence.",
        ],
        "corpus": {
            "observations": len(scoped_observations),
            "assessments": len(scoped_assessments),
            "verified_brief_eligible": len(verified_pairs),
            "verification_rate": round(len(verified_pairs) / len(pairs), 4) if pairs else 0.0,
            "verified_multi_source_cases": multi_source,
            "verified_multi_source_share": round(multi_source / len(verified_pairs), 4) if verified_pairs else 0.0,
            "unresolved_country": sum(not obs.country for obs, _ in pairs),
            "material_us_overlap_verified": sum(a.us_overlap.material for _, a in verified_pairs),
        },
        "macro_structure": {
            "countries": _distribution(countries),
            "cities": _distribution(cities),
            "observation_types": _distribution(types),
            "program_domains": _distribution(domains),
            "strategic_audiences": _distribution(audiences),
            "narrative_tags": _distribution(narratives),
            "delivery_modes": _distribution(delivery),
            "prc_support": _distribution(support),
            "source_types_all_records": _distribution(source_types),
            "audience_concentration_hhi": _hhi(audiences),
            "domain_concentration_hhi": _hhi(domains),
            "narrative_concentration_hhi": _hhi(narratives),
            "audience_diversity_entropy": _entropy(audiences),
            "domain_diversity_entropy": _entropy(domains),
            "narrative_diversity_entropy": _entropy(narratives),
            "institution_program_share_verified": round(
                sum(obs.observation_type in {"institution", "program", "partnership"} for obs, _ in verified_pairs)
                / len(verified_pairs),
                4,
            )
            if verified_pairs
            else 0.0,
            "host_or_partner_embedding_share_verified": round(
                sum(bool(a.host_entities or a.partner_entities) for _, a in verified_pairs) / len(verified_pairs), 4
            )
            if verified_pairs
            else 0.0,
            "us_overlap_share_verified": round(
                sum(a.us_overlap.material for _, a in verified_pairs) / len(verified_pairs), 4
            )
            if verified_pairs
            else 0.0,
        },
        "temporal": {
            "monthly": monthly,
            "signals": _signals(verified_pairs, monthly),
            "guardrail": "Reconcile apparent movement against collection-plan/access changes before strategic interpretation.",
        },
        "network_patterns": {
            "recurrent_entities": recurrence[:50],
            "cross_border_entities": [x for x in recurrence if x["cross_border_recurrence"]][:30],
            "digital_offline_coupling_candidates": _digital_offline_coupling(verified_pairs)[:50],
            "archetype_clusters": _clusters(verified_pairs)[:20],
        },
        "comparative_diagnostics": {"country_pair_comparability": _comparability(pairs)[:100]},
        "anomalies": _anomalies(verified_pairs)[:40],
        "representative_cases": [
            build_case_profile(obs, a, corpus_pairs=analysis_pairs) for obs, a in ranked[:representative_case_limit]
        ],
        "collection_questions": _collection_questions(scoped_observations, scoped_assessments, verified_pairs),
    }


def save_intelligence_packet(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    output_file: str | Path,
    *,
    country: str = "",
    observation_id: str = "",
    representative_case_limit: int = 20,
) -> str:
    target = Path(output_file).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            build_intelligence_packet(
                observations,
                assessments,
                country=country,
                observation_id=observation_id,
                representative_case_limit=representative_case_limit,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return str(target)
