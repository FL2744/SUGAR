from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_intelligence import build_case_profile, build_intelligence_packet
from sugar_core.state_schema import StateAssessment


def _observation(kind, title, date, country, city, actor, url, source_type="official_host_source"):
    return ResearchObservation(
        observation_type=kind,
        title=title,
        summary=f"Evidence for {title}",
        observed_at=date,
        country=country,
        city=city,
        actors=[actor],
        evidence=[EvidenceReference(url=url, source_type=source_type, published_at=date)],
        verification_state="human_verified",
        reviewer="analyst",
    )


def _assessment(obs, *, domain="stem_technology", audience="students", narrative="technology_innovation", actor="Partner", overlap=False):
    assessment = StateAssessment(
        observation_id=obs.observation_id,
        program_domains=[domain],
        strategic_audiences=[audience],
        narrative_tags=[narrative],
        host_entities=[actor],
        review_state="human_verified",
        reviewer="analyst",
    )
    if overlap:
        assessment.us_overlap.same_city = True
    return assessment


def test_packet_builds_macro_micro_comparability_and_coupling_without_influence_score():
    event = _observation(
        "event", "Bishkek technology event", "2026-08-01T12:00:00Z",
        "example_host_country", "Bishkek", "Shared Actor", "https://example.org/event",
    )
    digital = _observation(
        "digital_post", "Bishkek event promotion", "2026-08-05T12:00:00Z",
        "example_host_country", "Bishkek", "Shared Actor", "https://example.org/post", "social_media",
    )
    comparison = _observation(
        "program", "Tashkent technology program", "2026-08-03T12:00:00Z",
        "Uzbekistan", "Tashkent", "Other Actor", "https://example.org/uz",
    )
    observations = [event, digital, comparison]
    assessments = [
        _assessment(event, actor="Shared Actor", overlap=True),
        _assessment(digital, actor="Shared Actor"),
        _assessment(comparison, actor="Other Actor"),
    ]
    packet = build_intelligence_packet(observations, assessments)
    assert packet["corpus"]["verified_brief_eligible"] == 3
    assert packet["macro_structure"]["countries"][0]["count"] >= 1
    assert packet["network_patterns"]["digital_offline_coupling_candidates"]
    assert packet["network_patterns"]["archetype_clusters"]
    assert packet["comparative_diagnostics"]["country_pair_comparability"]
    serialized = str(packet).casefold()
    assert "influence score" not in serialized
    assert "not proof of coordination or influence" in serialized


def test_case_profile_identifies_comparables_and_uncertainty():
    first = _observation(
        "program", "Program A", "2026-07-01T12:00:00Z",
        "example_host_country", "Bishkek", "Actor A", "https://example.org/a",
    )
    second = _observation(
        "program", "Program B", "2026-07-15T12:00:00Z",
        "Kazakhstan", "Almaty", "Actor B", "https://example.org/b",
    )
    first_assessment = _assessment(first)
    second_assessment = _assessment(second)
    profile = build_case_profile(
        first, first_assessment,
        corpus_pairs=[(first, first_assessment), (second, second_assessment)],
    )
    assert profile["comparables"][0]["observation_id"] == second.observation_id
    assert "domain:stem_technology" in profile["comparables"][0]["shared_features"]
    assert profile["evidence_profile"]["distinct_evidence_identities"] >= 1
