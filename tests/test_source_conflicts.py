from __future__ import annotations

import json
from pathlib import Path

import pytest

from sugar_core.source_conflicts import (
    SourceClaim,
    SourceConflict,
    load_source_conflicts,
    save_source_conflicts,
    source_conflict_summary,
    source_conflicts_to_dicts,
)

STATE_URL = "https://educationusa.state.gov/node/421"
OPERATOR_URL = "https://kyrgyzstan.americancouncils.org/edusa"


def claims() -> tuple[SourceClaim, SourceClaim]:
    state = SourceClaim(
        statement="The service is fully online beginning April 1, 2026.",
        source_url=STATE_URL,
        publisher="U.S. Department of State EducationUSA",
        authority_type="official_authority",
        authority_scope="Current EducationUSA service topology",
        freshness="current",
        retrieved_at="2026-09-14",
        effective_date="2026-04-01",
    )
    operator = SourceClaim(
        statement="The service includes in-person advising at a Bishkek library.",
        source_url=OPERATOR_URL,
        publisher="American Councils Kyrgyzstan",
        authority_type="official_operator",
        authority_scope="Implementing-partner program description",
        freshness="unknown",
        retrieved_at="2026-09-14",
    )
    return state, operator


def provisional_conflict() -> SourceConflict:
    state, operator = claims()
    return SourceConflict(
        topic="EducationUSA Kyrgyzstan service topology",
        conflict_type="service_topology",
        status="provisional_treatment",
        claims=[state, operator],
        preferred_claim_id=state.claim_id,
        treatment="Represent the service as virtual while preserving both source claims.",
        preference_rationale="The authority directory supplies an explicit effective date; the operator page does not.",
    )


def test_provisional_treatment_preserves_conflict_and_requires_review():
    conflict = provisional_conflict()

    assert conflict.preferred_claim is not None
    assert conflict.preferred_claim.source_url == STATE_URL
    assert conflict.requires_human_review is True
    assert conflict.is_resolved is False
    assert conflict.is_human_adjudicated is False
    assert len(conflict.claims) == 2
    assert len({claim.claim_id for claim in conflict.claims}) == 2


def test_open_conflict_cannot_silently_prefer_claim():
    state, operator = claims()
    with pytest.raises(ValueError, match="cannot silently prefer"):
        SourceConflict(
            topic="Service topology",
            conflict_type="service_topology",
            status="open",
            claims=[state, operator],
            preferred_claim_id=state.claim_id,
        )


def test_human_adjudication_requires_named_reviewer():
    state, operator = claims()
    with pytest.raises(ValueError, match="named reviewer"):
        SourceConflict(
            topic="Service topology",
            conflict_type="service_topology",
            status="human_adjudicated",
            claims=[state, operator],
            preferred_claim_id=state.claim_id,
            treatment="Use the State directory topology.",
            preference_rationale="Analyst reviewed both sources.",
        )


def test_preferred_claim_must_exist_inside_conflict():
    state, operator = claims()
    with pytest.raises(ValueError, match="preferred_claim_id"):
        SourceConflict(
            topic="Service topology",
            conflict_type="service_topology",
            status="provisional_treatment",
            claims=[state, operator],
            preferred_claim_id="srcclaim_missing",
            treatment="Use one topology provisionally.",
            preference_rationale="Temporary operational treatment.",
        )


def test_conflict_requires_distinct_sources():
    state, _ = claims()
    duplicate_source = SourceClaim(
        statement="A contradictory statement on the same source URL.",
        source_url=STATE_URL,
        authority_type="official_authority",
    )
    with pytest.raises(ValueError, match="distinct source URLs"):
        SourceConflict(
            topic="Service topology",
            claims=[state, duplicate_source],
        )


def test_non_http_source_url_fails_closed():
    with pytest.raises(ValueError, match="absolute HTTP"):
        SourceClaim(
            statement="Unsupported local source reference.",
            source_url="file:///tmp/source.html",
        )


def test_iso_source_dates_are_validated():
    with pytest.raises(ValueError, match="ISO date"):
        SourceClaim(
            statement="Source claim.",
            source_url=STATE_URL,
            retrieved_at="September 14, 2026",
        )


def test_json_round_trip_preserves_nested_claims_and_ids(tmp_path: Path):
    conflict = provisional_conflict()
    path = Path(save_source_conflicts([conflict], tmp_path / "source-conflicts.json"))
    loaded = load_source_conflicts(path)

    assert len(loaded) == 1
    restored = loaded[0]
    assert restored.conflict_id == conflict.conflict_id
    assert restored.preferred_claim_id == conflict.preferred_claim_id
    assert [claim.claim_id for claim in restored.claims] == [claim.claim_id for claim in conflict.claims]
    assert restored.requires_human_review is True

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw[0]["status"] == "provisional_treatment"
    assert len(raw[0]["claims"]) == 2


def test_summary_keeps_provisional_treatment_separate_from_resolution():
    conflict = provisional_conflict()
    summary = source_conflict_summary([conflict])

    assert summary == {
        "conflicts": 1,
        "open": 0,
        "provisional_treatment": 1,
        "human_adjudicated": 0,
        "resolved_by_source_update": 0,
        "requiring_human_review": 1,
        "distinct_sources": 2,
    }


def test_dict_export_retains_authority_freshness_and_treatment_semantics():
    payload = source_conflicts_to_dicts([provisional_conflict()])[0]

    assert payload["status"] == "provisional_treatment"
    assert payload["treatment"]
    assert payload["preference_rationale"]
    assert {claim["authority_type"] for claim in payload["claims"]} == {
        "official_authority",
        "official_operator",
    }
    assert {claim["freshness"] for claim in payload["claims"]} == {"current", "unknown"}
