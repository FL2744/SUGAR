import json
from pathlib import Path

from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_network import build_state_network, save_state_network
from sugar_core.state_schema import (
    AnalyticClaim,
    StateAssessment,
    SupportAssessment,
    USOverlapAssessment,
    USPresenceSite,
)

SOURCE = "https://example.org/source"


def fixtures():
    observation = ResearchObservation(
        observation_type="program",
        title="Student innovation workshop",
        summary="Verified workshop evidence.",
        country="Kyrgyzstan",
        city="Bishkek",
        institution_name="Host University",
        program_name="Innovation Workshop",
        actors=["Program Director"],
        evidence=[EvidenceReference(url=SOURCE)],
        verification_state="human_verified",
        reviewer="analyst",
    )
    site = USPresenceSite(
        name="American Space Bishkek",
        network="american_space",
        country="Kyrgyzstan",
        city="Bishkek",
        site_id="us_bishkek",
    )
    assessment = StateAssessment(
        observation_id=observation.observation_id,
        sponsor_entities=["Sponsor A"],
        host_entities=["Host University"],
        partner_entities=["Partner B"],
        strategic_audiences=["students"],
        program_domains=["stem_technology"],
        narrative_tags=["technology_innovation"],
        prc_support=SupportAssessment(
            level="confirmed",
            bases=["official_prc_source"],
            evidence_refs=[SOURCE],
            review_state="human_verified",
            reviewer="analyst",
        ),
        claims=[
            AnalyticClaim(
                statement="Official sponsorship is documented.",
                claim_type="support_relationship",
                evidence_refs=[SOURCE],
                review_state="human_verified",
                reviewer="analyst",
            )
        ],
        us_overlap=USOverlapAssessment(
            same_country=True,
            same_city=True,
            nearest_site_id=site.site_id,
            nearest_site_name=site.name,
            nearest_network=site.network,
            audience_overlap=["students"],
        ),
        review_state="human_verified",
        reviewer="analyst",
    )
    return observation, assessment, site


def test_network_uses_typed_relationships_with_source_evidence():
    observation, assessment, site = fixtures()
    nodes, edges = build_state_network([observation], [assessment], [site])
    relationships = {edge["relationship"] for edge in edges}
    assert {
        "sponsors",
        "hosts",
        "partners",
        "targets_audience",
        "program_domain",
        "expresses_or_advances",
        "overlaps_us_public_diplomacy",
    } <= relationships
    assert all(SOURCE in edge["evidence_refs"] for edge in edges)
    assert any(node["node_type"] == "us_presence" and node["label"] == site.name for node in nodes)


def test_network_excludes_unverified_by_default_and_can_include_for_working_analysis():
    observation, assessment, site = fixtures()
    assessment.review_state = "ai_triaged"
    nodes, edges = build_state_network([observation], [assessment], [site])
    assert nodes == []
    assert edges == []
    nodes, edges = build_state_network([observation], [assessment], [site], verified_only=False)
    assert nodes
    assert edges


def test_network_files_include_guardrail(tmp_path: Path):
    observation, assessment, site = fixtures()
    outputs = save_state_network([observation], [assessment], tmp_path, us_sites=[site], name="network")
    assert len(outputs) == 3
    payload = json.loads((tmp_path / "network.network.json").read_text(encoding="utf-8"))
    assert "not a claim of causal influence" in payload["guardrail"]
