import json
from pathlib import Path

from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_schema import AnalyticClaim, ReachMetrics, StateAssessment, SupportAssessment, USPresenceSite
from sugar_core.state_workflow import (
    assess_us_overlap,
    audit_state_records,
    compare_state_snapshots,
    render_state_bluf,
    save_state_package,
    state_geojson,
)


SOURCE = "https://example.org/verified-program"


def verified_observation() -> ResearchObservation:
    return ResearchObservation(
        observation_type="program",
        title="Technology and university advising program",
        summary="Verified reporting describes a technology program for university students in Bishkek.",
        country="Kyrgyzstan",
        city="Bishkek",
        latitude=42.8746,
        longitude=74.5698,
        institution_name="Example Institute",
        program_name="Technology Program",
        evidence=[EvidenceReference(url=SOURCE, source_type="official_source")],
        verification_state="human_verified",
        reviewer="analyst",
    )


def verified_assessment(obs: ResearchObservation) -> StateAssessment:
    return StateAssessment(
        observation_id=obs.observation_id,
        strategic_audiences=["students", "emerging_leaders"],
        program_domains=["higher_education", "stem_technology"],
        narrative_tags=["technology_innovation"],
        sponsor_entities=["Example PRC-linked sponsor"],
        prc_support=SupportAssessment(
            level="confirmed",
            bases=["official_prc_source"],
            rationale="Verified source identifies official sponsorship.",
            confidence=1.0,
            evidence_refs=[SOURCE],
            review_state="human_verified",
            reviewer="analyst",
        ),
        observability_level="reach_observed",
        reach=ReachMetrics(attendance=120, views=10000, likes=400, comments=50, shares_reposts=20),
        claims=[
            AnalyticClaim(
                statement="The program had official PRC sponsorship.",
                claim_type="support_relationship",
                epistemic_status="observed_fact",
                confidence=1.0,
                evidence_refs=[SOURCE],
                review_state="human_verified",
                reviewer="analyst",
            )
        ],
        review_state="human_verified",
        reviewer="analyst",
    )


def us_site() -> USPresenceSite:
    return USPresenceSite(
        name="American Space Bishkek",
        network="american_space",
        subtype="American Center",
        country="Kyrgyzstan",
        city="Bishkek",
        latitude=42.87,
        longitude=74.59,
        service_tags=["educationusa", "stem", "technology", "leadership"],
        source_url="https://example.gov/american-space",
    )


def test_overlap_identifies_geographic_audience_and_program_relevance():
    obs = verified_observation()
    assessment = verified_assessment(obs)
    overlap = assess_us_overlap(obs, assessment, [us_site()])
    assert overlap.same_country
    assert overlap.same_city
    assert overlap.distance_km is not None and overlap.distance_km < 10
    assert "students" in overlap.audience_overlap
    assert "higher_education" in overlap.thematic_overlap
    assert overlap.material


def test_audit_passes_verified_evidence_chain_and_bluf_is_guardrailed():
    obs = verified_observation()
    assessment = verified_assessment(obs)
    assessment.us_overlap = assess_us_overlap(obs, assessment, [us_site()])
    audit = audit_state_records([obs], [assessment])
    assert audit["status"] == "pass"
    assert audit["brief_eligible"] == 1

    brief = render_state_bluf([obs], [assessment])
    assert "1 human-verified" in brief
    assert "caused attitudinal or behavioral influence" in brief
    assert "10,000 views" in brief
    assert "American Space Bishkek" in brief


def test_audit_rejects_unverified_influence_claim():
    obs = verified_observation()
    assessment = StateAssessment(
        observation_id=obs.observation_id,
        observability_level="engagement_observed",
        reach=ReachMetrics(likes=10),
        claims=[
            AnalyticClaim(
                statement="The activity influenced students.",
                claim_type="influence",
                epistemic_status="hypothesis",
                evidence_refs=[SOURCE],
                review_state="needs_followup",
            )
        ],
        review_state="needs_followup",
    )
    audit = audit_state_records([obs], [assessment])
    codes = {item["code"] for item in audit["findings"]}
    assert audit["status"] == "fail"
    assert "unverified_influence_claim" in codes
    assert "influence_without_causal_evidence" in codes


def test_package_emits_state_outputs_and_verified_geojson(tmp_path: Path):
    obs = verified_observation()
    assessment = verified_assessment(obs)
    outputs = save_state_package(
        [obs],
        [assessment],
        tmp_path,
        name="kyrgyzstan",
        us_sites=[us_site()],
    )
    assert len(outputs) == 8
    for output in outputs:
        assert Path(output).is_file()
    audit = json.loads((tmp_path / "kyrgyzstan.audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "pass"
    geojson = json.loads((tmp_path / "kyrgyzstan.map.geojson").read_text(encoding="utf-8"))
    assert {feature["properties"]["layer"] for feature in geojson["features"]} == {"prc_observation", "us_presence"}


def test_snapshot_diff_calls_out_policy_relevant_changes():
    obs = verified_observation()
    old = StateAssessment(observation_id=obs.observation_id)
    new = StateAssessment(
        observation_id=obs.observation_id,
        strategic_audiences=["students"],
        program_domains=["higher_education"],
        review_state="ai_triaged",
    )
    diff = compare_state_snapshots([old], [new])
    assert len(diff["changed"]) == 1
    assert "strategic_audiences" in diff["changed"][0]["changed_fields"]
    assert "program_domains" in diff["changed"][0]["changed_fields"]
    assert "review_state" in diff["changed"][0]["changed_fields"]


def test_geojson_excludes_unverified_observations_by_default():
    obs = verified_observation()
    unverified = StateAssessment(observation_id=obs.observation_id, review_state="ai_triaged")
    geojson = state_geojson([obs], [unverified], [us_site()])
    layers = [feature["properties"]["layer"] for feature in geojson["features"]]
    assert layers == ["us_presence"]
