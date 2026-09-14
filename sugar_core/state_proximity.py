from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Iterable

from .observations import ResearchObservation
from .state_location import ResolvedLocation
from .state_schema import USPresenceSite

EARTH_RADIUS_KM = 6371.0088
DEFAULT_NEARBY_THRESHOLD_KM = 50.0
DEFAULT_US_SITE_UNCERTAINTY_KM = 0.75


@dataclass(frozen=True)
class StateProximity:
    """Uncertainty-aware geographic proximity to one U.S. public-diplomacy site.

    The distance range is a conservative interpretation aid built from the observation's
    geographic precision envelope plus a small site-location envelope. It is not a statistical
    confidence interval and must not be interpreted as evidence of strategic competition,
    displacement, persuasion, coordination, or influence.
    """

    observation_id: str
    site_id: str
    site_name: str
    network: str
    center_distance_km: float
    minimum_distance_km: float
    maximum_distance_km: float
    threshold_km: float
    relation: str
    observation_precision: str
    observation_confidence: float
    observation_uncertainty_km: float
    site_uncertainty_km: float
    same_city: bool
    same_country: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    @property
    def potentially_nearby(self) -> bool:
        return self.relation in {"within_threshold", "uncertainty_intersects_threshold"}


def haversine_km(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    lat1 = math.radians(float(latitude_a))
    lat2 = math.radians(float(latitude_b))
    delta_lat = math.radians(float(latitude_b) - float(latitude_a))
    delta_lon = math.radians(float(longitude_b) - float(longitude_a))
    a = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2.0) ** 2
    )
    return EARTH_RADIUS_KM * 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def distance_range_km(
    center_distance_km: float,
    observation_uncertainty_km: float,
    site_uncertainty_km: float = DEFAULT_US_SITE_UNCERTAINTY_KM,
) -> tuple[float, float]:
    """Return a conservative min/max separation implied by two location envelopes."""
    center = max(0.0, float(center_distance_km))
    combined = max(0.0, float(observation_uncertainty_km)) + max(0.0, float(site_uncertainty_km))
    return max(0.0, center - combined), center + combined


def classify_proximity(minimum_km: float, maximum_km: float, threshold_km: float) -> str:
    threshold = float(threshold_km)
    if threshold <= 0:
        raise ValueError("threshold_km must be positive")
    if float(maximum_km) <= threshold:
        return "within_threshold"
    if float(minimum_km) <= threshold:
        return "uncertainty_intersects_threshold"
    return "outside_threshold"


def _same_place(left: str, right: str) -> bool:
    return bool(left and right and " ".join(left.split()).casefold() == " ".join(right.split()).casefold())


def nearest_us_presence(
    observation: ResearchObservation,
    location: ResolvedLocation,
    sites: Iterable[USPresenceSite],
    *,
    threshold_km: float = DEFAULT_NEARBY_THRESHOLD_KM,
    site_uncertainty_km: float = DEFAULT_US_SITE_UNCERTAINTY_KM,
) -> StateProximity | None:
    """Return the physically nearest active, mapped U.S. presence site.

    Unlike older same-country-first logic, this is purely geographic: a site immediately across
    a border can be physically nearer than one elsewhere in the observation's country. Country
    and city agreement are retained as descriptive fields, not ranking constraints.
    """
    if not location.resolved:
        return None
    candidates = [
        site
        for site in sites
        if site.status not in {"closed", "inactive"}
        and site.latitude is not None
        and site.longitude is not None
    ]
    if not candidates:
        return None

    observation_uncertainty = max(0.0, float(location.uncertainty_km or 0.0))
    ranked: list[tuple[float, USPresenceSite]] = []
    for site in candidates:
        center = haversine_km(
            float(location.latitude),
            float(location.longitude),
            float(site.latitude),
            float(site.longitude),
        )
        ranked.append((center, site))
    ranked.sort(key=lambda item: (item[0], item[1].site_id))
    center, site = ranked[0]
    minimum, maximum = distance_range_km(center, observation_uncertainty, site_uncertainty_km)
    relation = classify_proximity(minimum, maximum, threshold_km)
    return StateProximity(
        observation_id=observation.observation_id,
        site_id=site.site_id,
        site_name=site.name,
        network=site.network,
        center_distance_km=round(center, 3),
        minimum_distance_km=round(minimum, 3),
        maximum_distance_km=round(maximum, 3),
        threshold_km=float(threshold_km),
        relation=relation,
        observation_precision=location.precision,
        observation_confidence=float(location.confidence),
        observation_uncertainty_km=round(observation_uncertainty, 3),
        site_uncertainty_km=round(max(0.0, float(site_uncertainty_km)), 3),
        same_city=_same_place(observation.city, site.city),
        same_country=_same_place(observation.country, site.country),
    )


def proximity_note(proximity: StateProximity) -> str:
    center = proximity.center_distance_km
    minimum = proximity.minimum_distance_km
    maximum = proximity.maximum_distance_km
    threshold = proximity.threshold_km
    if proximity.relation == "within_threshold":
        relation = f"entire location-uncertainty range is within the {threshold:g} km reference threshold"
    elif proximity.relation == "uncertainty_intersects_threshold":
        relation = f"location uncertainty intersects the {threshold:g} km reference threshold"
    else:
        relation = f"entire location-uncertainty range is outside the {threshold:g} km reference threshold"
    return (
        f"nearest mapped U.S. presence: {proximity.site_name}; center-to-center {center:.1f} km; "
        f"precision-aware range {minimum:.1f}–{maximum:.1f} km; {relation}. "
        "Geographic proximity alone is not evidence of strategic overlap or influence."
    )
