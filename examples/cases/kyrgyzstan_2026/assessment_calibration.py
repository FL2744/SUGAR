from __future__ import annotations

from sugar_core.state_schema import (
    AnalyticClaim,
    QualifiedReachValue,
    ReachMetrics,
    StateAssessment,
    SupportAssessment,
)


# The case seed captures observable activities first. This calibration step prevents the real-case
# assessment layer from treating every China-linked activity as equally strong evidence of PRC
# state/institutional support. Because the case remains AI-triaged, no support judgment is allowed
# to use `confirmed`, which requires human verification in the core State schema.
_SUPPORT_LEVEL_BY_TITLE = {
    "Chinese painting exhibition at the National Historical Museum": "probable",
    "Osh State University–Xinjiang Normal University Confucius Institute cooperation extended": "probable",
    "Chinese-language university teaching materials presented in Bishkek": "probable",
    "International Chinese Language Day events at Bishkek universities": "probable",
    "Chinese Bridge school competition Kyrgyzstan qualifier": "probable",
    "Chinese cultural programming at Kyrgyz diplomatic charity bazaar": "probable",
    "Kyrgyz and Chinese writers organizations sign cooperation agreement": "possible",
    "Presentation of Xi Jinping's The Governance of China in Bishkek": "possible",
    "SCO Civilizations Dialogue at the National Historical Museum": "probable",
    "Chinese-produced Manas dance drama premieres in Kyrgyzstan": "probable",
    "Nanjing Week opens at the Osmonov National Library": "probable",
}

# These values preserve the language used by the underlying public sources. In particular,
# `minimum` means the source reported "more than" the encoded threshold; it is not an exact count.
_REACH_BY_TITLE = {
    "Presentation of Xi Jinping's The Governance of China in Bishkek": {
        "value": 300,
        "qualifier": "approximate",
        "source_note": "Related public reporting describes roughly 300 participants.",
        "claim": "Public reporting describes roughly 300 participants at the book presentation.",
    },
    "SCO Civilizations Dialogue at the National Historical Museum": {
        "value": 200,
        "qualifier": "approximate",
        "source_note": "The public source reports roughly 200 government, media, cultural, and academic representatives.",
        "claim": "The public source reports roughly 200 representatives at the SCO Civilizations Dialogue.",
    },
    "Chinese-produced Manas dance drama premieres in Kyrgyzstan": {
        "value": 1000,
        "qualifier": "minimum",
        "source_note": "The public source reports attendance by more than 1,000 officials and members of the public.",
        "claim": "The public source reports attendance by more than 1,000 officials and members of the public.",
    },
}


def calibrate_support_assessments(observations, assessments: list[StateAssessment]) -> dict[str, int]:
    observation_by_id = {row.observation_id: row for row in observations}
    counts = {"probable": 0, "possible": 0}

    for assessment in assessments:
        observation = observation_by_id.get(assessment.observation_id)
        title = observation.title if observation else ""
        level = _SUPPORT_LEVEL_BY_TITLE.get(title)
        if level is None:
            raise ValueError(f"No support calibration is defined for observation: {title or assessment.observation_id}")

        existing = assessment.prc_support
        assessment.prc_support = SupportAssessment(
            level=level,
            bases=list(existing.bases),
            rationale=existing.rationale,
            confidence=(0.90 if level == "probable" else 0.65),
            evidence_refs=list(existing.evidence_refs),
            review_state="ai_triaged",
        )
        counts[level] += 1

        # Migrate language records away from the historical `other` fallback now that the core
        # State schema has a generic language_education domain. This does not equate Chinese-
        # language activity with English-language programming; those remain distinct domains.
        if observation and "language_education" in observation.triage_labels:
            domains = [value for value in assessment.program_domains if value != "other"]
            if "language_education" not in domains:
                domains.append("language_education")
            assessment.program_domains = domains

        reach_spec = _REACH_BY_TITLE.get(title)
        if observation and reach_spec:
            source = observation.primary_source_url
            assessment.reach = ReachMetrics(
                qualified={
                    "attendance": QualifiedReachValue(
                        value=reach_spec["value"],
                        qualifier=reach_spec["qualifier"],
                        source_note=reach_spec["source_note"],
                        source_ref=source,
                    )
                }
            )
            assessment.observability_level = "reach_observed"
            assessment.claims.append(
                AnalyticClaim(
                    statement=reach_spec["claim"],
                    claim_type="reach",
                    epistemic_status="observed_fact",
                    confidence=0.90,
                    evidence_refs=[source],
                    review_state="ai_triaged",
                    review_note="Reported reach wording preserved without converting the source qualifier into an exact count.",
                )
            )

    return counts
