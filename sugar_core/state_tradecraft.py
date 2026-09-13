from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlparse

from .observations import ResearchObservation
from .state_schema import StateAssessment
from .utils import utc_iso


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.casefold().removeprefix("www.")
    except Exception:
        return ""


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


def source_adequacy_profile(observation: ResearchObservation) -> dict[str, Any]:
    source_types = Counter(_clean(item.source_type).casefold() or "unspecified" for item in observation.evidence)
    platforms = Counter(_clean(item.platform).casefold() for item in observation.evidence if _clean(item.platform))
    domains = Counter(_host(item.url) for item in observation.evidence if _host(item.url))
    evidence_ids = set(observation.source_record_keys)
    evidence_ids.update(item.url for item in observation.evidence if item.url)
    evidence_ids.update(
        f"{item.platform}:{item.native_id}"
        for item in observation.evidence if item.platform and item.native_id
    )
    dates = [
        value for item in observation.evidence
        for value in (_parse_time(item.published_at), _parse_time(item.collected_at))
        if value is not None
    ]
    oldest = min(dates).isoformat().replace("+00:00", "Z") if dates else None
    newest = max(dates).isoformat().replace("+00:00", "Z") if dates else None
    distinct_channels = len({*source_types, *domains, *platforms})
    if len(evidence_ids) >= 3 and distinct_channels >= 2:
        adequacy = "multi_source_diverse"
    elif len(evidence_ids) >= 2:
        adequacy = "multi_evidence_limited_diversity"
    elif len(evidence_ids) == 1:
        adequacy = "single_evidence_identity"
    else:
        adequacy = "no_auditable_evidence_identity"
    return {
        "adequacy": adequacy,
        "evidence_identities": len(evidence_ids),
        "source_types": dict(source_types),
        "platforms": dict(platforms),
        "source_domains": dict(domains),
        "distinct_source_channels": distinct_channels,
        "oldest_evidence_time": oldest,
        "newest_evidence_time": newest,
        "single_domain_dependence": len(domains) == 1 and sum(domains.values()) > 1,
        "single_source_type_dependence": len(source_types) == 1 and sum(source_types.values()) > 1,
        "guardrail": "Source diversity is an adequacy diagnostic, not a blanket reliability rating. Multiple sources can repeat the same underlying claim.",
    }


def _tension(
    severity: str,
    kind: str,
    observation: ResearchObservation,
    assessment: StateAssessment,
    explanation: str,
    next_step: str,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "type": kind,
        "observation_id": observation.observation_id,
        "assessment_id": assessment.assessment_id,
        "country": observation.country,
        "title": observation.title or observation.summary[:100],
        "explanation": explanation,
        "next_step": next_step,
    }


def analytic_tensions(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
) -> list[dict[str, Any]]:
    observations = list(observations)
    observation_map = {row.observation_id: row for row in observations}
    result: list[dict[str, Any]] = []
    for assessment in assessments:
        observation = observation_map.get(assessment.observation_id)
        if observation is None:
            continue
        source = source_adequacy_profile(observation)
        high_consequence = [
            claim for claim in assessment.claims
            if claim.claim_type in {"support_relationship", "coordination", "influence"}
            and claim.review_state != "rejected"
        ]
        if assessment.review_state == "human_verified" and observation.verification_state != "human_verified":
            result.append(_tension(
                "high", "assessment_verified_over_unverified_observation", observation, assessment,
                "The State assessment is human-verified while the underlying ResearchObservation is not.",
                "Reconcile the underlying observation verification state before briefing.",
            ))
        if assessment.prc_support.level == "confirmed" and source["evidence_identities"] <= 1:
            result.append(_tension(
                "high", "confirmed_support_single_evidence_identity", observation, assessment,
                "Confirmed PRC support rests on one auditable evidence identity in this observation.",
                "Seek independent corroboration or document why a single authoritative source is sufficient.",
            ))
        if high_consequence and source["adequacy"] in {"single_evidence_identity", "no_auditable_evidence_identity"}:
            result.append(_tension(
                "high", "high_consequence_claim_weak_corroboration", observation, assessment,
                "A support/coordination/influence claim has limited source diversity.",
                "Prioritize corroboration and contrary-evidence search before increasing confidence.",
            ))
        if assessment.observability_level == "causal_influence_evidence" and not any(
            claim.claim_type == "influence" and claim.review_state == "human_verified"
            for claim in assessment.claims
        ):
            result.append(_tension(
                "high", "causal_evidence_without_verified_influence_claim", observation, assessment,
                "The observability level says causal-influence evidence exists, but no influence claim is human-verified.",
                "Review the causal evidence and either verify a properly bounded claim or lower the observability level.",
            ))
        if assessment.observability_level in {"reach_observed", "engagement_observed"} and any(
            value is not None for value in (
                assessment.reach.views, assessment.reach.likes, assessment.reach.comments,
                assessment.reach.shares_reposts, assessment.reach.attendance,
            )
        ):
            result.append(_tension(
                "normal", "reach_without_outcome_evidence", observation, assessment,
                "The case has observable reach/engagement but not outcome or causal evidence.",
                "Treat it as a candidate for outcome collection rather than an influence result.",
            ))
        if "anti_us" in assessment.narrative_tags and not any(
            claim.claim_type == "narrative" and claim.review_state == "human_verified"
            for claim in assessment.claims
        ):
            result.append(_tension(
                "normal", "anti_us_tag_without_verified_narrative_claim", observation, assessment,
                "The anti-U.S. tag is present without a human-verified narrative claim in the assessment.",
                "Verify explicit source language/context before elevating the label into synthesis.",
            ))
        if any(tag in assessment.narrative_tags for tag in ("china_russia_coordination", "third_party_coordination")) and not any(
            claim.claim_type == "coordination" and claim.review_state == "human_verified"
            for claim in assessment.claims
        ):
            result.append(_tension(
                "high", "coordination_tag_without_verified_coordination_claim", observation, assessment,
                "A coordination narrative tag is present without a human-verified coordination claim.",
                "Require evidence of joint activity, co-sponsorship, planning, or other actual coordination.",
            ))
        if assessment.us_overlap.material and not (
            assessment.us_overlap.nearest_site_id
            or assessment.us_overlap.same_city
            or assessment.us_overlap.audience_overlap
            or assessment.us_overlap.thematic_overlap
            or assessment.us_overlap.service_overlap
        ):
            result.append(_tension(
                "normal", "material_us_overlap_without_explanatory_component", observation, assessment,
                "The overlap object is material but exposes no component explaining why.",
                "Recalculate or document the overlap basis before using it analytically.",
            ))
    severity_order = {"high": 0, "normal": 1, "low": 2}
    return sorted(result, key=lambda row: (severity_order.get(row["severity"], 9), row["country"], row["observation_id"], row["type"]))


def build_tradecraft_audit(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
) -> dict[str, Any]:
    observations, assessments = list(observations), list(assessments)
    observation_map = {row.observation_id: row for row in observations}
    source_profiles = {row.observation_id: source_adequacy_profile(row) for row in observations}
    source_types = Counter()
    domains = Counter()
    platforms = Counter()
    for profile in source_profiles.values():
        source_types.update(profile["source_types"])
        domains.update(profile["source_domains"])
        platforms.update(profile["platforms"])
    tensions = analytic_tensions(observations, assessments)
    verified = [
        (observation_map[a.observation_id], a)
        for a in assessments
        if a.observation_id in observation_map
        and observation_map[a.observation_id].verification_state == "human_verified"
        and a.brief_eligible
    ]
    single_evidence_verified = sum(
        source_profiles[obs.observation_id]["evidence_identities"] <= 1
        for obs, _ in verified
    )
    digital = sum(obs.observation_type == "digital_post" for obs, _ in verified)
    offline = sum(obs.observation_type != "digital_post" for obs, _ in verified)
    return {
        "generated_at": utc_iso(),
        "corpus": {
            "observations": len(observations),
            "assessments": len(assessments),
            "verified_brief_eligible": len(verified),
            "verified_single_or_zero_evidence_identity": single_evidence_verified,
            "verified_digital_observations": digital,
            "verified_non_digital_observations": offline,
        },
        "source_environment": {
            "source_types": source_types.most_common(),
            "source_domains": domains.most_common(30),
            "platforms": platforms.most_common(),
            "single_source_type_cases": sum(p["single_source_type_dependence"] for p in source_profiles.values()),
            "single_domain_cases": sum(p["single_domain_dependence"] for p in source_profiles.values()),
        },
        "source_profiles": source_profiles,
        "analytic_tensions": tensions,
        "high_severity_tensions": [row for row in tensions if row["severity"] == "high"],
        "epistemic_debt": {
            "possible_or_probable_support_pending": sum(
                a.prc_support.level in {"possible", "probable"} and a.review_state != "rejected"
                for a in assessments
            ),
            "high_priority_not_verified": sum(
                a.analytic_priority in {"high", "urgent"} and a.review_state != "human_verified"
                for a in assessments
            ),
            "unresolved_location": sum(not obs.country or obs.location_basis == "unknown" for obs in observations),
            "high_consequence_claims_not_verified": sum(
                claim.claim_type in {"support_relationship", "coordination", "influence"}
                and claim.review_state not in {"human_verified", "rejected"}
                for a in assessments for claim in a.claims
            ),
        },
        "guardrails": [
            "Source adequacy describes diversity/corroboration structure, not inherent source truthfulness.",
            "Multiple URLs or outlets may repeat one underlying assertion and should not automatically be treated as independent corroboration.",
            "Analytic tensions are review prompts, not automatic findings that an assessment is wrong.",
        ],
    }
