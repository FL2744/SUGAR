from pathlib import Path

import pytest
from openpyxl import load_workbook

from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_review import apply_review_workbook, export_review_workbook
from sugar_core.state_schema import AnalyticClaim, StateAssessment, SupportAssessment

SOURCE = "https://example.org/evidence"


def observation() -> ResearchObservation:
    return ResearchObservation(
        observation_type="program",
        title="Reviewed program",
        summary="Evidence for a reviewed program.",
        country="Kyrgyzstan",
        city="Bishkek",
        evidence=[EvidenceReference(url=SOURCE)],
        verification_state="human_verified",
        reviewer="source-reviewer",
    )


def assessment(obs: ResearchObservation) -> StateAssessment:
    return StateAssessment(
        observation_id=obs.observation_id,
        strategic_audiences=["students"],
        program_domains=["higher_education"],
        prc_support=SupportAssessment(
            level="probable",
            bases=["official_prc_source"],
            evidence_refs=[SOURCE],
            review_state="ai_triaged",
        ),
        claims=[
            AnalyticClaim(
                statement="The source indicates official sponsorship.",
                claim_type="support_relationship",
                epistemic_status="analytic_assessment",
                evidence_refs=[SOURCE],
                review_state="ai_triaged",
            )
        ],
        review_state="ai_triaged",
    )


def _set_cell(ws, row: int, header: str, value):
    headers = {cell.value: cell.column for cell in ws[1]}
    ws.cell(row=row, column=headers[header]).value = value


def test_review_workbook_can_promote_assessment_support_and_claim_with_named_reviewers(tmp_path: Path):
    obs = observation()
    original = assessment(obs)
    path = Path(export_review_workbook([obs], [original], tmp_path / "review.xlsx"))
    workbook = load_workbook(path)
    assessments = workbook["assessments"]
    _set_cell(assessments, 2, "decision", "human_verified")
    _set_cell(assessments, 2, "reviewer", "Alice Analyst")
    _set_cell(assessments, 2, "support_level_decision", "confirmed")
    _set_cell(assessments, 2, "support_review_decision", "human_verified")
    _set_cell(assessments, 2, "support_reviewer", "Alice Analyst")
    claims = workbook["claims"]
    _set_cell(claims, 2, "decision", "human_verified")
    _set_cell(claims, 2, "reviewer", "Alice Analyst")
    workbook.save(path)

    reviewed = apply_review_workbook([original], path)[0]
    assert reviewed.review_state == "human_verified"
    assert reviewed.prc_support.level == "confirmed"
    assert reviewed.prc_support.review_state == "human_verified"
    assert reviewed.claims[0].review_state == "human_verified"
    assert reviewed.brief_eligible


def test_review_workbook_rejects_verification_without_reviewer(tmp_path: Path):
    obs = observation()
    original = assessment(obs)
    path = Path(export_review_workbook([obs], [original], tmp_path / "review.xlsx"))
    workbook = load_workbook(path)
    _set_cell(workbook["assessments"], 2, "decision", "human_verified")
    workbook.save(path)
    with pytest.raises(ValueError, match="requires a reviewer"):
        apply_review_workbook([original], path)


def test_review_workbook_will_not_verify_influence_without_causal_evidence(tmp_path: Path):
    obs = observation()
    original = StateAssessment(
        observation_id=obs.observation_id,
        observability_level="outcome_evidence",
        claims=[
            AnalyticClaim(
                statement="The program may have shifted participant attitudes.",
                claim_type="influence",
                epistemic_status="hypothesis",
                evidence_refs=[SOURCE],
                review_state="needs_followup",
            )
        ],
        review_state="needs_followup",
    )
    path = Path(export_review_workbook([obs], [original], tmp_path / "review.xlsx"))
    workbook = load_workbook(path)
    _set_cell(workbook["claims"], 2, "decision", "human_verified")
    _set_cell(workbook["claims"], 2, "reviewer", "Alice Analyst")
    workbook.save(path)
    with pytest.raises(ValueError, match="causal_influence_evidence"):
        apply_review_workbook([original], path)


def test_review_workbook_rejects_unknown_taxonomy_edit(tmp_path: Path):
    obs = observation()
    original = assessment(obs)
    path = Path(export_review_workbook([obs], [original], tmp_path / "review.xlsx"))
    workbook = load_workbook(path)
    _set_cell(workbook["assessments"], 2, "strategic_audiences", "students; invented_group")
    workbook.save(path)
    with pytest.raises(ValueError, match="Unsupported strategic_audience"):
        apply_review_workbook([original], path)
