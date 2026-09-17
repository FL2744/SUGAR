from __future__ import annotations

import json

import pandas as pd

from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.source_conflicts import SourceClaim, SourceConflict
from sugar_core.state_conflict_package import (
    build_conflict_aware_review_queue,
    save_state_package_with_conflicts,
    source_conflicts_for_record,
)
from sugar_core.state_schema import StateAssessment, USPresenceSite
from sugar_core.state_workflow import build_review_queue


STATE_URL = "https://educationusa.state.gov/node/421"
OPERATOR_URL = "https://example_host_country.americancouncils.org/edusa"
OBSERVATION_URL = "https://example.org/observation"


def observation() -> ResearchObservation:
    return ResearchObservation(
        observation_type="program",
        title="University-facing activity",
        summary="Public reporting describes a higher-education activity.",
        country="example_host_country",
        city="Bishkek",
        latitude=42.8746,
        longitude=74.5698,
        evidence=[
            EvidenceReference(
                url=OBSERVATION_URL,
                source_type="official_host_source",
            )
        ],
        source_record_keys=[OBSERVATION_URL],
    )


def assessment(obs: ResearchObservation) -> StateAssessment:
    return StateAssessment(
        observation_id=obs.observation_id,
        strategic_audiences=["students"],
        program_domains=["higher_education"],
    )


def educationusa_site() -> USPresenceSite:
    return USPresenceSite(
        name="EducationUSA example_host_country",
        network="educationusa",
        country="example_host_country",
        service_tags=["educationusa", "study_in_the_us", "higher_education"],
        source_url=STATE_URL,
        delivery_mode="virtual",
        coverage_scope="country",
    )


def provisional_conflict() -> SourceConflict:
    state = SourceClaim(
        statement="EducationUSA example_host_country is fully online beginning April 1, 2026.",
        source_url=STATE_URL,
        publisher="U.S. Department of State EducationUSA",
        authority_type="official_authority",
        freshness="current",
        effective_date="2026-04-01",
    )
    operator = SourceClaim(
        statement="EducationUSA example_host_country provides in-person advising in Bishkek.",
        source_url=OPERATOR_URL,
        publisher="American Councils example_host_country",
        authority_type="official_operator",
        freshness="unknown",
    )
    return SourceConflict(
        topic="EducationUSA example_host_country service topology",
        conflict_type="service_topology",
        status="provisional_treatment",
        claims=[state, operator],
        preferred_claim_id=state.claim_id,
        treatment="Represent the current service as virtual while preserving the contradictory operator claim.",
        preference_rationale="The State directory supplies an explicit effective date; the operator page does not.",
    )


def human_adjudicated_conflict() -> SourceConflict:
    state = SourceClaim(
        statement="EducationUSA example_host_country is fully online beginning April 1, 2026.",
        source_url=STATE_URL,
        publisher="U.S. Department of State EducationUSA",
        authority_type="official_authority",
        freshness="current",
        effective_date="2026-04-01",
    )
    operator = SourceClaim(
        statement="EducationUSA example_host_country provides in-person advising in Bishkek.",
        source_url=OPERATOR_URL,
        publisher="American Councils example_host_country",
        authority_type="official_operator",
    )
    return SourceConflict(
        topic="EducationUSA example_host_country service topology",
        conflict_type="service_topology",
        status="human_adjudicated",
        claims=[state, operator],
        preferred_claim_id=state.claim_id,
        treatment="Use the State directory topology.",
        preference_rationale="Analyst reviewed both sources and confirmed the current State topology.",
        reviewer="Analyst One",
    )


def _apply_overlap(obs: ResearchObservation, row: StateAssessment) -> None:
    from sugar_core.state_workflow import apply_us_overlaps

    apply_us_overlaps([obs], [row], [educationusa_site()])


def test_provisional_conflict_is_linked_by_structured_service_source_and_prioritized():
    obs = observation()
    row = assessment(obs)
    _apply_overlap(obs, row)
    conflict = provisional_conflict()

    matched = source_conflicts_for_record(obs, row, [conflict])
    assert [item.conflict_id for item in matched] == [conflict.conflict_id]

    base = build_review_queue([obs], [row])[0]
    enriched = build_conflict_aware_review_queue([obs], [row], [conflict])[0]
    assert enriched["review_priority"] == base["review_priority"] + 4
    assert enriched["source_conflict_count"] == 1
    assert enriched["source_conflicts_requiring_human_review"] == 1
    assert enriched["source_conflict_ids"] == conflict.conflict_id
    assert "requires human review" in enriched["reasons"]


def test_service_topology_conflict_ignores_audience_only_service_association():
    obs = observation()
    row = StateAssessment(
        observation_id=obs.observation_id,
        strategic_audiences=["students"],
        program_domains=["culture_arts"],
    )
    _apply_overlap(obs, row)

    source = next(
        item for item in row.us_overlap.service_sources if item.source_url == STATE_URL
    )
    assert source.program_service_matches == []
    assert source.audience_service_matches
    assert source_conflicts_for_record(obs, row, [provisional_conflict()]) == []


def test_exact_source_identity_prevents_topic_only_conflict_linkage():
    obs = observation()
    row = assessment(obs)
    unrelated_site = USPresenceSite(
        name="Different Education Service",
        network="educationusa",
        country="example_host_country",
        service_tags=["educationusa", "higher_education"],
        source_url="https://example.gov/different-service",
        delivery_mode="virtual",
        coverage_scope="country",
    )
    from sugar_core.state_workflow import apply_us_overlaps

    apply_us_overlaps([obs], [row], [unrelated_site])
    assert source_conflicts_for_record(obs, row, [provisional_conflict()]) == []


def test_state_package_persists_provisional_conflict_across_analyst_surfaces(tmp_path):
    obs = observation()
    row = assessment(obs)
    conflict = provisional_conflict()

    outputs = save_state_package_with_conflicts(
        [obs],
        [row],
        tmp_path,
        name="case",
        us_sites=[educationusa_site()],
        source_conflicts=[conflict],
    )

    conflict_path = tmp_path / "case.source_conflicts.json"
    assert str(conflict_path.resolve()) in outputs
    conflict_payload = json.loads(conflict_path.read_text(encoding="utf-8"))
    assert conflict_payload[0]["conflict_id"] == conflict.conflict_id
    assert conflict_payload[0]["status"] == "provisional_treatment"

    audit = json.loads((tmp_path / "case.audit.json").read_text(encoding="utf-8"))
    assert audit["errors"] == 0
    assert audit["status"] == "conditional"
    assert audit["source_conflicts"]["requiring_human_review"] == 1
    assert any(item["code"] == "source_conflict_requires_human_review" for item in audit["findings"])

    snapshot = json.loads((tmp_path / "case.snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["audit_status"] == "conditional"
    assert snapshot["source_conflicts"]["provisional_treatment"] == 1
    assert snapshot["source_conflict_ids"] == [conflict.conflict_id]

    queue = pd.read_csv(tmp_path / "case.review_queue.csv")
    assert int(queue.loc[0, "source_conflict_count"]) == 1
    assert int(queue.loc[0, "source_conflicts_requiring_human_review"]) == 1
    assert queue.loc[0, "source_conflict_ids"] == conflict.conflict_id

    with pd.ExcelFile(tmp_path / "case.state.xlsx") as workbook:
        assert "source_conflicts" in workbook.sheet_names
        assert "review_queue" in workbook.sheet_names
    conflict_sheet = pd.read_excel(tmp_path / "case.state.xlsx", sheet_name="source_conflicts")
    assert conflict_sheet.loc[0, "conflict_id"] == conflict.conflict_id
    assert bool(conflict_sheet.loc[0, "requires_human_review"]) is True

    brief = (tmp_path / "case.brief.md").read_text(encoding="utf-8")
    assert "## Source Conflicts" in brief
    assert "not a human adjudication" in brief
    assert "EducationUSA example_host_country service topology" in brief


def test_human_adjudicated_conflict_is_preserved_without_unresolved_review_penalty(tmp_path):
    obs = observation()
    row = assessment(obs)
    conflict = human_adjudicated_conflict()

    outputs = save_state_package_with_conflicts(
        [obs],
        [row],
        tmp_path,
        name="resolved",
        us_sites=[educationusa_site()],
        source_conflicts=[conflict],
    )
    assert outputs

    audit = json.loads((tmp_path / "resolved.audit.json").read_text(encoding="utf-8"))
    assert audit["errors"] == 0
    assert audit["warnings"] == 0
    assert audit["status"] == "pass"
    assert audit["source_conflicts"]["human_adjudicated"] == 1
    assert audit["source_conflicts"]["requiring_human_review"] == 0

    snapshot = json.loads((tmp_path / "resolved.snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["audit_status"] == "pass"

    base = build_review_queue([obs], [row])[0]
    queue = pd.read_csv(tmp_path / "resolved.review_queue.csv")
    assert int(queue.loc[0, "review_priority"]) == int(base["review_priority"])
    assert int(queue.loc[0, "source_conflicts_requiring_human_review"]) == 0
