from __future__ import annotations

import pandas as pd

from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.source_conflicts import SourceClaim, SourceConflict
from sugar_core.state_conflict_package import (
    export_review_workbook_with_conflicts,
    save_state_package_with_conflicts,
)
from sugar_core.state_schema import StateAssessment


SOURCE_A = "https://example.gov/a"
SOURCE_B = "https://example.org/b"


def _fixture():
    observation = ResearchObservation(
        observation_type="program",
        title="Conflict safety fixture",
        summary="Source-derived text must remain inert in spreadsheet exports.",
        country="Example",
        evidence=[EvidenceReference(url=SOURCE_A)],
    )
    assessment = StateAssessment(observation_id=observation.observation_id)
    first = SourceClaim(
        statement="Current topology claim.",
        source_url=SOURCE_A,
        publisher="Official source",
        authority_type="official_authority",
    )
    second = SourceClaim(
        statement="Contradictory topology claim.",
        source_url=SOURCE_B,
        publisher="Operator source",
        authority_type="official_operator",
    )
    conflict = SourceConflict(
        topic="=HYPERLINK(\"https://example.invalid\",\"click\")",
        conflict_type="service_topology",
        status="provisional_treatment",
        claims=[first, second],
        preferred_claim_id=first.claim_id,
        treatment="+provisional treatment",
        preference_rationale="@source-derived rationale",
    )
    return observation, assessment, conflict


def test_state_package_conflict_spreadsheets_are_formula_safe(tmp_path):
    observation, assessment, conflict = _fixture()
    save_state_package_with_conflicts(
        [observation],
        [assessment],
        tmp_path,
        name="safe",
        source_conflicts=[conflict],
    )

    queue = pd.read_csv(tmp_path / "safe.review_queue.csv")
    assert queue.loc[0, "source_conflict_topics"].startswith("'=")

    conflict_sheet = pd.read_excel(
        tmp_path / "safe.state.xlsx",
        sheet_name="source_conflicts",
    )
    assert conflict_sheet.loc[0, "topic"].startswith("'=")
    assert conflict_sheet.loc[0, "treatment"].startswith("'+")
    assert conflict_sheet.loc[0, "preference_rationale"].startswith("'@")


def test_analyst_review_workbook_conflict_sheet_is_formula_safe(tmp_path):
    observation, assessment, conflict = _fixture()
    target = tmp_path / "review.xlsx"
    export_review_workbook_with_conflicts(
        [observation],
        [assessment],
        target,
        source_conflicts=[conflict],
    )

    conflict_sheet = pd.read_excel(target, sheet_name="source_conflicts")
    assert conflict_sheet.loc[0, "topic"].startswith("'=")
    assert conflict_sheet.loc[0, "treatment"].startswith("'+")
    assessments = pd.read_excel(target, sheet_name="assessments")
    assert assessments.loc[0, "source_conflict_topics"].startswith("'=")
