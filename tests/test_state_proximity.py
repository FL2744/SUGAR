from sugar_core.observations import ResearchObservation
from sugar_core.state_location import resolve_observation_location
from sugar_core.state_proximity import (
    classify_proximity,
    distance_range_km,
    nearest_us_presence,
    proximity_note,
)
from sugar_core.state_schema import USPresenceSite


def _observation(*, longitude: float = 0.0, basis: str = "reported_city") -> ResearchObservation:
    return ResearchObservation(
        observation_type="event",
        summary="Mapped activity.",
        country="Exampleland",
        city="Example City",
        latitude=0.0,
        longitude=longitude,
        location_basis=basis,
        location_confidence=0.8,
    )


def _site(*, longitude: float) -> USPresenceSite:
    return USPresenceSite(
        name="American Space Example",
        network="american_space",
        country="Exampleland",
        city="Example City",
        latitude=0.0,
        longitude=longitude,
    )


def test_distance_range_never_goes_negative():
    minimum, maximum = distance_range_km(4.0, 12.0, 0.75)
    assert minimum == 0.0
    assert maximum == 16.75


def test_threshold_classifier_distinguishes_inside_intersection_and_outside():
    assert classify_proximity(5.0, 20.0, 50.0) == "within_threshold"
    assert classify_proximity(40.0, 60.0, 50.0) == "uncertainty_intersects_threshold"
    assert classify_proximity(55.0, 70.0, 50.0) == "outside_threshold"


def test_city_precision_can_turn_point_distance_into_threshold_intersection():
    observation = _observation()
    location = resolve_observation_location(observation)
    # Roughly 45 km east at the equator. A city-level observation has a 12 km default
    # uncertainty envelope, so the 50 km threshold should be treated as intersecting rather
    # than categorically inside.
    proximity = nearest_us_presence(observation, location, [_site(longitude=0.404)], threshold_km=50.0)

    assert proximity is not None
    assert 44.0 < proximity.center_distance_km < 46.0
    assert proximity.minimum_distance_km < 50.0 < proximity.maximum_distance_km
    assert proximity.relation == "uncertainty_intersects_threshold"
    assert proximity.observation_precision == "city"
    assert "not evidence of strategic overlap or influence" in proximity_note(proximity)


def test_exact_precision_can_be_definitively_within_threshold():
    observation = _observation(basis="native_geotag")
    location = resolve_observation_location(observation)
    proximity = nearest_us_presence(observation, location, [_site(longitude=0.1)], threshold_km=50.0)

    assert proximity is not None
    assert proximity.relation == "within_threshold"
    assert proximity.observation_precision == "exact"
    assert proximity.maximum_distance_km < 50.0


def test_nearest_site_is_geographic_not_same_country_first():
    observation = _observation()
    location = resolve_observation_location(observation)
    same_country_far = USPresenceSite(
        name="Far Same-Country Space",
        network="american_space",
        country="Exampleland",
        city="Far City",
        latitude=0.0,
        longitude=2.0,
    )
    cross_border_near = USPresenceSite(
        name="Near Cross-Border Space",
        network="american_space",
        country="Neighborland",
        city="Border City",
        latitude=0.0,
        longitude=0.1,
    )

    proximity = nearest_us_presence(observation, location, [same_country_far, cross_border_near])

    assert proximity is not None
    assert proximity.site_name == "Near Cross-Border Space"
    assert proximity.same_country is False
