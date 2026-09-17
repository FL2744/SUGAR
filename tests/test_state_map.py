import json
from pathlib import Path

from sugar_core import __version__
from sugar_core.observations import EvidenceReference, ObservationLocation, ResearchObservation
from sugar_core.state_map import create_state_map
from sugar_core.state_schema import StateAssessment, USPresenceSite


def _assessment(observation: ResearchObservation) -> StateAssessment:
    return StateAssessment(
        observation_id=observation.observation_id,
        review_state="human_verified",
        reviewer="analyst",
    )


def test_state_map_labels_density_and_proximity_without_implying_influence(tmp_path: Path):
    observation = ResearchObservation(
        observation_type="event",
        title="Verified event",
        summary="Verified evidence",
        country="Kenya",
        city="Nairobi",
        latitude=-1.2864,
        longitude=36.8172,
        location_basis="reported_city",
        location_confidence=0.8,
        evidence=[EvidenceReference(url="https://example.org/event")],
        verification_state="human_verified",
        reviewer="analyst",
    )
    assessment = _assessment(observation)
    site = USPresenceSite(
        name="American Space Nairobi",
        network="american_space",
        country="Kenya",
        city="Nairobi",
        latitude=-1.29,
        longitude=36.82,
    )
    path = Path(create_state_map([observation], [assessment], tmp_path / "map.html", us_sites=[site]))
    assert path.is_file()
    html = path.read_text(encoding="utf-8")
    assert "not influence" in html
    assert "PRC activity locations" in html
    assert "Location precision" in html
    assert "City level" in html
    assert "U.S. proximity" in html
    assert "uncertainty range within threshold" in html

    metadata = json.loads((tmp_path / "map.html.metadata.json").read_text(encoding="utf-8"))
    assert metadata["sugar_version"] == __version__
    assert metadata["runtime"]["dependencies"]["requests"]
    assert metadata["mapped_observations"] == 1
    assert metadata["mapped_locations"] == 1
    assert metadata["precision_counts"] == {"city": 1}
    assert metadata["density_eligible_observations"] == 1
    assert metadata["density_eligible_locations"] == 1
    assert metadata["density_total_weight"] == 1.0
    assert metadata["activity_density_rendered"] is True
    assert metadata["density_semantics"].endswith("not influence")
    assert len(metadata["resolved_locations"]) == 1
    resolved = metadata["resolved_locations"][0]
    assert resolved["observation_id"] == observation.observation_id
    assert resolved["precision"] == "city"
    assert resolved["confidence"] == 0.8
    assert resolved["source"] == "recorded_coordinates"
    assert resolved["density_eligible"] is True

    assert metadata["us_proximity_counts"] == {"within_threshold": 1}
    assert len(metadata["us_proximity"]) == 1
    proximity = metadata["us_proximity"][0]
    assert proximity["observation_id"] == observation.observation_id
    assert proximity["site_id"] == site.site_id
    assert proximity["relation"] == "within_threshold"
    assert proximity["minimum_distance_km"] == 0.0
    assert proximity["maximum_distance_km"] > proximity["center_distance_km"]
    assert "not evidence of strategic overlap/influence" in metadata["proximity_semantics"]


def test_multi_site_map_renders_two_locations_but_one_activity_weight(tmp_path: Path):
    observation = ResearchObservation(
        observation_type="event",
        title="Multi-site activity",
        summary="One activity was reported at two universities.",
        country="Kyrgyzstan",
        city="Bishkek",
        evidence=[EvidenceReference(url="https://example.org/activity")],
        locations=[
            ObservationLocation(
                label="University A",
                country="Kyrgyzstan",
                city="Bishkek",
                latitude=42.85035,
                longitude=74.58509,
                precision="site",
                confidence=0.9,
                source_ref="https://example.org/a",
            ),
            ObservationLocation(
                label="University B campus unresolved",
                country="Kyrgyzstan",
                city="Bishkek",
                latitude=42.8746,
                longitude=74.5698,
                precision="city",
                confidence=0.75,
                uncertainty_km=12,
                source_ref="https://example.org/activity",
            ),
        ],
        verification_state="human_verified",
        reviewer="analyst",
    )
    site = USPresenceSite(
        name="American Space Bishkek",
        network="american_space",
        country="Kyrgyzstan",
        city="Bishkek",
        latitude=42.8776,
        longitude=74.6105,
    )
    path = Path(create_state_map([observation], [_assessment(observation)], tmp_path / "map.html", us_sites=[site]))
    metadata = json.loads(path.with_suffix(".html.metadata.json").read_text(encoding="utf-8"))

    assert metadata["mapped_observations"] == 1
    assert metadata["mapped_locations"] == 2
    assert metadata["multi_location_observations"] == 1
    assert metadata["precision_counts"] == {"city": 1, "site": 1}
    assert metadata["density_eligible_observations"] == 1
    assert metadata["density_eligible_locations"] == 2
    assert metadata["density_multi_location_observations"] == 1
    assert metadata["density_total_weight"] == 1.0
    assert len(metadata["resolved_locations"]) == 2
    assert len({row["location_id"] for row in metadata["resolved_locations"]}) == 2
    assert len(metadata["us_proximity"]) == 2
    assert {row["location_id"] for row in metadata["us_proximity"]} == {
        row["location_id"] for row in metadata["resolved_locations"]
    }
    html = path.read_text(encoding="utf-8")
    assert "one activity may have multiple venue markers" in html


def test_state_map_marks_threshold_intersection_instead_of_false_binary_nearby(tmp_path: Path):
    observation = ResearchObservation(
        observation_type="event",
        title="City-level event",
        summary="Event is only localized to the city.",
        country="Exampleland",
        city="Example City",
        latitude=0.0,
        longitude=0.0,
        location_basis="reported_city",
        location_confidence=0.8,
        evidence=[EvidenceReference(url="https://example.org/event")],
        verification_state="human_verified",
        reviewer="analyst",
    )
    site = USPresenceSite(
        name="American Space Example",
        network="american_space",
        country="Exampleland",
        city="Example City",
        latitude=0.0,
        longitude=0.404,
    )
    path = Path(create_state_map([observation], [_assessment(observation)], tmp_path / "map.html", us_sites=[site]))
    metadata = json.loads(path.with_suffix(".html.metadata.json").read_text(encoding="utf-8"))
    assert metadata["us_proximity_counts"] == {"uncertainty_intersects_threshold": 1}
    proximity = metadata["us_proximity"][0]
    assert proximity["minimum_distance_km"] < 50.0 < proximity["maximum_distance_km"]
    assert "uncertainty intersects threshold" in path.read_text(encoding="utf-8")


def test_state_map_reports_country_only_observation_as_unresolved(tmp_path: Path):
    observation = ResearchObservation(
        observation_type="program",
        title="Country-wide program",
        summary="Only country-level location evidence is available.",
        country="Kenya",
        location_basis="country",
        evidence=[EvidenceReference(url="https://example.org/program")],
        verification_state="human_verified",
        reviewer="analyst",
    )
    path = Path(create_state_map([observation], [_assessment(observation)], tmp_path / "map.html"))
    metadata = json.loads(path.with_suffix(".html.metadata.json").read_text(encoding="utf-8"))
    assert metadata["mapped_observations"] == 0
    assert metadata["mapped_locations"] == 0
    assert metadata["resolved_locations"] == []
    assert metadata["us_proximity"] == []
    assert metadata["unresolved_eligible_observations"] == 1
    assert metadata["unresolved_activity_locations"] == 1
    assert metadata["unresolved"][0]["observation_id"] == observation.observation_id
