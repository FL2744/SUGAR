from __future__ import annotations

from sugar_core.state_schema import StateAssessment, SupportAssessment


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


def calibrate_support_assessments(observations, assessments: list[StateAssessment]) -> dict[str, int]:
    observation_by_id = {row.observation_id: row for row in observations}
    counts = {"probable": 0, "possible": 0, "language_domain_migrations": 0}

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

        if observation and "language_education" in observation.triage_labels:
            domains = [value for value in assessment.program_domains if value != "other"]
            if "language_education" not in domains:
                domains.append("language_education")
                counts["language_domain_migrations"] += 1
            assessment.program_domains = domains

    return counts
