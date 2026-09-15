from __future__ import annotations

from sugar_core.source_conflicts import (
    SourceClaim,
    SourceConflict,
    source_conflict_summary,
    source_conflicts_to_dicts,
)


EDUCATIONUSA_STATE_URL = "https://educationusa.state.gov/node/421"
EDUCATIONUSA_OPERATOR_URL = "https://kyrgyzstan.americancouncils.org/edusa"


def build_source_conflicts() -> list[SourceConflict]:
    state_claim = SourceClaim(
        statement="EducationUSA Kyrgyzstan has no physical address and advising services became fully online beginning April 1, 2026.",
        source_url=EDUCATIONUSA_STATE_URL,
        source_label="EducationUSA Kyrgyzstan directory entry",
        publisher="U.S. Department of State EducationUSA",
        authority_type="official_authority",
        authority_scope="Current EducationUSA service topology",
        freshness="current",
        retrieved_at="2026-09-14",
        effective_date="2026-04-01",
        note="Current program-authority directory entry used for the case's operational service-topology representation.",
    )
    operator_claim = SourceClaim(
        statement="EducationUSA Kyrgyzstan provides in-person and virtual services and an advising center at the Bayalinov Youth and Children's Library / American Corner in Bishkek.",
        source_url=EDUCATIONUSA_OPERATOR_URL,
        source_label="EducationUSA Kyrgyzstan program page",
        publisher="American Councils for International Education Kyrgyzstan",
        authority_type="official_operator",
        authority_scope="Implementing-partner program description",
        freshness="unknown",
        retrieved_at="2026-09-14",
        note="The current page remained publicly accessible at the research cutoff, but the claim itself has no clear effective or update date establishing whether it supersedes the State directory.",
    )
    conflict = SourceConflict(
        topic="EducationUSA Kyrgyzstan service topology",
        conflict_type="service_topology",
        status="provisional_treatment",
        claims=[state_claim, operator_claim],
        preferred_claim_id=state_claim.claim_id,
        treatment="Represent EducationUSA Kyrgyzstan as a non-spatial, country-scoped virtual service for current case outputs while retaining the operator claim as contradictory evidence.",
        preference_rationale="The Department of State EducationUSA directory is the program-authority directory and supplies an explicit April 1, 2026 effective date for the fully online topology; the operator page supplies no clear update/effective date resolving the contradiction.",
        review_note="Operational treatment only. This conflict remains open to human review and must not be described as human-adjudicated or finally resolved.",
    )
    return [conflict]


def source_conflict_manifest() -> list[dict[str, object]]:
    return source_conflicts_to_dicts(build_source_conflicts())


def source_conflict_findings() -> list[dict[str, object]]:
    conflicts = build_source_conflicts()
    summary = source_conflict_summary(conflicts)
    conflict = conflicts[0]
    preferred = conflict.preferred_claim
    return [
        {
            "code": "source_conflict_provenance_resolved",
            "severity": "resolved",
            "affected_records": summary["conflicts"],
            "description": (
                "Reference-layer contradictions now use the shared SUGAR source-conflict schema with distinct source claims, authority/freshness metadata, stable claim IDs, an explicit conflict status, and a review-preserving operational treatment."
            ),
            "recommended_fix": "Use the shared source-conflict model for future contradictory reference records instead of bespoke dictionaries.",
        },
        {
            "code": "us_service_topology_source_conflict",
            "severity": "source_conflict",
            "affected_records": 1,
            "description": (
                "The current U.S. Department of State EducationUSA directory says EducationUSA Kyrgyzstan has no physical address and that advising services became fully online beginning April 1, 2026, while the current American Councils Kyrgyzstan program page still describes in-person services at the Bayalinov Youth and Children's Library / American Corner in Bishkek."
            ),
            "current_case_decision": conflict.treatment,
            "status": conflict.status,
            "requires_human_review": conflict.requires_human_review,
            "preferred_claim_id": preferred.claim_id if preferred else "",
            "sources": [claim.source_url for claim in conflict.claims],
            "recommended_fix": "Retain the contradiction for human review and update the provisional treatment when authoritative source topology changes or an analyst adjudicates the conflict.",
        },
    ]
