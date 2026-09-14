from __future__ import annotations


EDUCATIONUSA_STATE_URL = "https://educationusa.state.gov/node/421"
EDUCATIONUSA_OPERATOR_URL = "https://kyrgyzstan.americancouncils.org/edusa"


def source_conflict_findings() -> list[dict[str, object]]:
    return [
        {
            "code": "us_service_topology_source_conflict",
            "severity": "source_conflict",
            "affected_records": 1,
            "description": (
                "The current U.S. Department of State EducationUSA directory says EducationUSA Kyrgyzstan has no physical address and that advising services became fully online beginning April 1, 2026, while the current American Councils Kyrgyzstan program page still describes in-person services at the Bayalinov Youth and Children's Library / American Corner in Bishkek."
            ),
            "current_case_decision": (
                "Use the Department of State EducationUSA directory as the current service-topology authority and represent EducationUSA as a non-spatial national service, while preserving the implementing-partner page as contradictory evidence that requires analyst review."
            ),
            "sources": [EDUCATIONUSA_STATE_URL, EDUCATIONUSA_OPERATOR_URL],
            "recommended_fix": (
                "Add first-class reference-record provenance, source authority/freshness, contradiction tracking, and analyst adjudication so reference-layer conflicts are preserved instead of silently overwritten."
            ),
        }
    ]


def source_conflict_manifest() -> list[dict[str, object]]:
    return [
        {
            "topic": "EducationUSA Kyrgyzstan service topology",
            "preferred_current_source": EDUCATIONUSA_STATE_URL,
            "preferred_current_source_claim": "No physical Address; advising services fully online beginning April 1, 2026.",
            "conflicting_source": EDUCATIONUSA_OPERATOR_URL,
            "conflicting_source_claim": "Describes in-person and virtual services and an advising center at the Bayalinov Youth and Children's Library / American Corner in Bishkek.",
            "status": "unresolved_reference_source_conflict",
            "case_treatment": "Non-spatial EducationUSA service for current topology; conflict retained for human review.",
        }
    ]
