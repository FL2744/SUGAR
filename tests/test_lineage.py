from __future__ import annotations

from copy import deepcopy

import pytest

from sugar_core.lineage import build_lineage_index, save_lineage_index, validate_lineage_index
from sugar_core.models import PostRecord
from sugar_core.observations import observation_from_post
from sugar_core.source_conflicts import SourceClaim, SourceConflict
from sugar_core.state_schema import (
    AnalyticClaim,
    StateAssessment,
    SupportAssessment,
    USOverlapAssessment,
    USServiceSourceAttribution,
)


def test_lineage_resolves_claim_to_observation_record_and_collection_context():
    record = PostRecord(
        platform="example",
        native_id="1",
        canonical_url="https://example.test/source",
        query="example",
        query_matches=["example"],
        original_text="Original evidence text.",
        source_mode="external_import:partner",
        source_host="partner",
        source_url="https://collector.test/export",
        published_at="2026-09-01T00:00:00Z",
        collected_at="2026-09-02T00:00:00Z",
    )
    observation = observation_from_post(record)
    observation.set_ai_triage(
        labels=["program_activity"],
        confidence=0.79,
        provider="arc",
        model="gpt-oss-120b",
        workflow="diplomacy-lab-triage-v1",
    )
    observation.transition_verification(
        "human_verified",
        reviewer="Analyst",
        notes="Source checked.",
    )
    claim = AnalyticClaim(
        statement="The source documents a relationship.",
        claim_type="support_relationship",
        evidence_refs=[record.canonical_url],
        review_state="human_verified",
        reviewer="Analyst",
    )
    assessment = StateAssessment(
        observation_id=observation.observation_id,
        claims=[claim],
        ai_provider="arc",
        ai_model="gpt-oss-120b",
        ai_workflow="state-department-triage-v1",
        review_state="human_verified",
        reviewer="Analyst",
    )

    lineage = build_lineage_index(
        [observation],
        [assessment],
        records=[record],
        dataset_provenance={"source_system": "partner", "source_sha256": "a" * 64},
    )

    finding = next(item for item in lineage["findings"] if item["finding_id"] == claim.claim_id)
    assert finding["supporting_evidence_ids"] == [record.canonical_url]
    assert finding["unresolved_supporting_evidence_ids"] == []
    assert finding["supporting_evidence"][0]["source_record_keys"] == [record.record_key]
    linked = finding["supporting_evidence"][0]["source_records"][0]
    assert linked["source_mode"] == "external_import:partner"
    assert linked["has_original_text"] is True
    assert len(linked["original_text_sha256"]) == 64
    assert lineage["dataset_provenance"]["source_sha256"] == "a" * 64
    assert lineage["assessments"][0]["assessment_id"] == assessment.assessment_id
    assert lineage["assessments"][0]["observation_id"] == observation.observation_id
    assert lineage["assessments"][0]["ai_provider"] == "arc"
    assert lineage["assessments"][0]["ai_model"] == "gpt-oss-120b"
    assert lineage["assessments"][0]["ai_workflow"] == "state-department-triage-v1"
    assert lineage["observations"][0]["ai_provider"] == "arc"
    assert lineage["observations"][0]["ai_workflow"] == "diplomacy-lab-triage-v1"
    assert lineage["observations"][0]["reviewer"] == "Analyst"
    assert finding["reviewer"] == "Analyst"
    assert validate_lineage_index(lineage)["status"] == "pass"


def test_lineage_enumerates_exact_contradicting_source_claims_only_when_support_matches_conflict():
    supported_url = "https://example.test/official"
    contrary_url = "https://example.test/operator"
    record = PostRecord(
        platform="example",
        native_id="2",
        canonical_url=supported_url,
        query="example",
        original_text="Official source statement.",
    )
    observation = observation_from_post(record)
    supported = SourceClaim(statement="Service is online.", source_url=supported_url)
    contrary = SourceClaim(statement="Service is in person.", source_url=contrary_url)
    conflict = SourceConflict(topic="Service topology", claims=[supported, contrary])
    claim = AnalyticClaim(
        statement="The service is online.",
        claim_type="descriptive_fact",
        evidence_refs=[supported_url],
    )
    unrelated = AnalyticClaim(
        statement="An unrelated descriptive finding.",
        claim_type="descriptive_fact",
        evidence_refs=["https://example.test/unrelated"],
    )
    assessment = StateAssessment(observation_id=observation.observation_id, claims=[claim, unrelated])

    lineage = build_lineage_index([observation], [assessment], records=[record], source_conflicts=[conflict])
    finding = next(item for item in lineage["findings"] if item["finding_id"] == claim.claim_id)
    unrelated_finding = next(item for item in lineage["findings"] if item["finding_id"] == unrelated.claim_id)
    assert finding["contradicting_evidence_ids"] == [contrary.claim_id]
    assert finding["source_conflict_ids"] == [conflict.conflict_id]
    assert lineage["source_claims"][contrary.claim_id]["source_url"] == contrary_url
    assert unrelated_finding["contradicting_evidence_ids"] == []


def test_sponsor_support_is_materialized_as_a_finding():
    record = PostRecord(
        platform="example",
        native_id="3",
        canonical_url="https://example.test/support",
        query="example",
        original_text="Sponsorship evidence.",
    )
    observation = observation_from_post(record)
    assessment = StateAssessment(
        observation_id=observation.observation_id,
        sponsor_support=SupportAssessment(
            level="probable",
            rationale="Source indicates probable sponsorship.",
            evidence_refs=[record.canonical_url],
        ),
    )
    lineage = build_lineage_index([observation], [assessment], records=[record])
    finding = next(item for item in lineage["findings"] if item["finding_type"] == "sponsor_support")
    assert finding["supporting_evidence_ids"] == [record.canonical_url]


def test_unresolved_claim_evidence_fails_semantic_validation_and_cannot_be_saved(tmp_path):
    record = PostRecord(
        platform="example",
        native_id="4",
        canonical_url="https://example.test/real",
        original_text="Real source.",
        query="example",
    )
    observation = observation_from_post(record)
    claim = AnalyticClaim(
        statement="A claim points at a nonexistent source.",
        evidence_refs=["https://example.test/missing"],
    )
    assessment = StateAssessment(observation_id=observation.observation_id, claims=[claim])

    lineage = build_lineage_index([observation], [assessment], records=[record])
    validation = validate_lineage_index(lineage)
    codes = {item["code"] for item in validation["issues"]}
    assert validation["status"] == "fail"
    assert "unresolved_supporting_evidence" in codes
    with pytest.raises(ValueError, match="internally inconsistent"):
        save_lineage_index(lineage, tmp_path / "broken.lineage.json")


def test_record_elsewhere_in_corpus_cannot_resolve_evidence_for_unrelated_observation():
    first = PostRecord(
        platform="example",
        native_id="5",
        canonical_url="https://example.test/first",
        original_text="First source.",
        query="example",
    )
    second = PostRecord(
        platform="example",
        native_id="6",
        canonical_url="https://example.test/second",
        original_text="Second source.",
        query="example",
    )
    observation = observation_from_post(first)
    claim = AnalyticClaim(
        statement="This citation belongs to another observation.",
        evidence_refs=[second.canonical_url],
    )
    assessment = StateAssessment(observation_id=observation.observation_id, claims=[claim])

    lineage = build_lineage_index([observation], [assessment], records=[first, second])
    finding = next(item for item in lineage["findings"] if item["finding_id"] == claim.claim_id)
    chain = finding["supporting_evidence"][0]
    assert chain["resolved"] is False
    assert chain["source_record_keys"] == []
    assert chain["unlinked_candidate_record_keys"] == [second.record_key]
    assert validate_lineage_index(lineage)["status"] == "fail"


def test_validator_rejects_duplicate_ids_and_tampered_embedded_record_payload():
    record = PostRecord(
        platform="example",
        native_id="7",
        canonical_url="https://example.test/seven",
        original_text="Canonical text.",
        query="example",
    )
    observation = observation_from_post(record)
    claim = AnalyticClaim(statement="Documented.", evidence_refs=[record.canonical_url])
    assessment = StateAssessment(observation_id=observation.observation_id, claims=[claim])
    lineage = build_lineage_index([observation], [assessment], records=[record])
    assert validate_lineage_index(lineage)["status"] == "pass"

    duplicate = deepcopy(lineage)
    duplicate["findings"].append(deepcopy(duplicate["findings"][0]))
    validation = validate_lineage_index(duplicate)
    assert "duplicate_lineage_id" in {item["code"] for item in validation["issues"]}

    tampered = deepcopy(lineage)
    tampered["findings"][0]["supporting_evidence"][0]["source_records"][0][
        "original_text_sha256"
    ] = "0" * 64
    validation = validate_lineage_index(tampered)
    assert "embedded_record_payload_mismatch" in {
        item["code"] for item in validation["issues"]
    }


def test_overlap_finding_resolves_both_activity_and_external_us_service_sources():
    record = PostRecord(
        platform="example",
        native_id="8",
        canonical_url="https://example.test/activity",
        original_text="Activity evidence.",
        query="example",
    )
    observation = observation_from_post(record)
    service_source = USServiceSourceAttribution(
        site_id="us_site_1",
        name="American Space Example",
        network="american_space",
        delivery_mode="physical",
        coverage_scope="site",
        source_url="https://example.test/us-site",
        program_service_matches=["english_language"],
    )
    assessment = StateAssessment(
        observation_id=observation.observation_id,
        us_overlap=USOverlapAssessment(
            same_city=True,
            nearest_site_id="us_site_1",
            nearest_site_name="American Space Example",
            nearest_network="american_space",
            service_overlap=["english_language"],
            thematic_overlap=["english_language"],
            service_sources=[service_source],
            note="Same-city service overlap is documented.",
        ),
    )

    lineage = build_lineage_index([observation], [assessment], records=[record])
    finding = next(
        item for item in lineage["findings"]
        if item["finding_type"] == "us_public_diplomacy_overlap"
    )
    external = [
        chain
        for chain in finding["supporting_evidence"]
        if chain["external_evidence_references"]
    ]
    assert external
    assert any(
        ref["source_type"] == "us_public_diplomacy_service_source"
        for chain in external
        for ref in chain["external_evidence_references"]
    )
    assert validate_lineage_index(lineage)["status"] == "pass"
