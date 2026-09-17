from sugar_core.observations import EvidenceReference, ObservationLocation, ResearchObservation
from sugar_core.state_schema import StateAssessment, USPresenceSite
from sugar_core.state_workflow import state_geojson


def _verified_multi_site_observation() -> ResearchObservation:
    return ResearchObservation(
        observation_type="event",
        title="Two-venue activity",
        summary="One activity was reported at two universities.",
        country="example_host_country",
        city="Bishkek",
        # Deliberately different legacy summary point. Structured locations must supersede it.
        latitude=42.8746,
        longitude=74.5698,
        location_basis="multi_site_summary_city",
        evidence=[EvidenceReference(url="https://example.org/activity")],
        locations=[
            ObservationLocation(
                label="University A",
                country="example_host_country",
                city="Bishkek",
                latitude=42.85035,
                longitude=74.58509,
                precision="site",
                confidence=0.9,
                uncertainty_km=0.75,
                basis="official_address",
                source_ref="https://example.org/university-a",
            ),
            ObservationLocation(
                label="University B campus unresolved",
                country="example_host_country",
                city="Bishkek",
                latitude=42.88,
                longitude=74.61,
                precision="city",
                confidence=0.75,
                uncertainty_km=12.0,
                basis="campus_unresolved_city_centroid",
                source_ref="https://example.org/activity",
            ),
        ],
        verification_state="human_verified",
        reviewer="analyst",
    )


def _verified_assessment(observation: ResearchObservation) -> StateAssessment:
    return StateAssessment(
        observation_id=observation.observation_id,
        review_state="human_verified",
        reviewer="analyst",
    )


def test_geojson_emits_two_venue_features_for_one_multi_site_observation():
    observation = _verified_multi_site_observation()
    assessment = _verified_assessment(observation)

    payload = state_geojson([observation], [assessment])
    features = [row for row in payload["features"] if row["properties"]["layer"] == "sponsor_observation"]

    assert len(features) == 2
    assert {row["properties"]["observation_id"] for row in features} == {observation.observation_id}
    assert {row["properties"]["assessment_id"] for row in features} == {assessment.assessment_id}
    assert len({row["properties"]["location_id"] for row in features}) == 2
    assert {row["properties"]["location_precision"] for row in features} == {"site", "city"}
    assert {row["properties"]["activity_location_index"] for row in features} == {1, 2}
    assert {row["properties"]["activity_location_count"] for row in features} == {2}
    assert [74.5698, 42.8746] not in [row["geometry"]["coordinates"] for row in features]
    assert all(row["properties"]["location_source_ref"] for row in features)


def test_geojson_skips_unresolved_structured_location_without_falling_back_to_summary_point():
    observation = _verified_multi_site_observation()
    unresolved = ObservationLocation(
        label="Unresolved third campus",
        country="example_host_country",
        city="Bishkek",
        precision="site",
        source_ref="https://example.org/source",
    )
    observation.locations.append(unresolved)
    assessment = _verified_assessment(observation)

    payload = state_geojson([observation], [assessment])
    features = [row for row in payload["features"] if row["properties"]["layer"] == "sponsor_observation"]

    assert len(features) == 2
    assert {row["properties"]["activity_location_count"] for row in features} == {3}
    assert unresolved.location_id not in {row["properties"]["location_id"] for row in features}


def test_geojson_keeps_virtual_us_service_nonspatial():
    observation = _verified_multi_site_observation()
    assessment = _verified_assessment(observation)
    virtual = USPresenceSite(
        name="Virtual advising",
        network="educationusa",
        country="example_host_country",
        delivery_mode="virtual",
        coverage_scope="country",
        latitude=42.87,
        longitude=74.57,
    )

    payload = state_geojson([observation], [assessment], [virtual])
    assert not any(row["properties"]["layer"] == "us_presence" for row in payload["features"])
