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
    """Uncertainty-aware geographic proximity to one U.S. public-diplomacy site."""

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
    site_precision: str
    site_confidence: float | None
    site_uncertainty_km: float
    site_location_basis: str
    same_city: bool
    same_country: bool
    location_id: str = ""
    location_label: str = ""

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
    """Return the physically nearest active, mapped U.S. presence site for one resolved venue."""
    if not location.resolved:
        return None
    candidates = [
        site
        for site in sites
        if site.status not in {"closed", "inactive"} and site.is_spatial
    ]
    if not candidates:
        return None

    observation_uncertainty = max(0.0, float(location.uncertainty_km or 0.0))
    ranked: list[tuple[float, USPresenceSite]] = []
    for site in candidates:
        assert site.latitude is not None and site.longitude is not None
        center = haversine_km(
            float(location.latitude),
            float(location.longitude),
            float(site.latitude),
            float(site.longitude),
        )
        ranked.append((center, site))
    ranked.sort(key=lambda item: (item[0], item[1].site_id))
    center, site = ranked[0]
    effective_site_uncertainty = site.effective_location_uncertainty_km(site_uncertainty_km)
    minimum, maximum = distance_range_km(center, observation_uncertainty, effective_site_uncertainty)
    relation = classify_proximity(minimum, maximum, threshold_km)
    location_city = location.city or observation.city
    location_country = location.country or observation.country
    return StateProximity(
        observation_id=observation.observation_id,
        location_id=location.location_id,
        location_label=location.display_name or location.label,
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
        site_precision=site.location_precision,
        site_confidence=site.location_confidence,
        site_uncertainty_km=round(effective_site_uncertainty, 3),
        site_location_basis=site.location_basis,
        same_city=_same_place(location_city, site.city),
        same_country=_same_place(location_country, site.country),
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
    site_precision = (
        f" U.S. site precision: {proximity.site_precision}; site uncertainty {proximity.site_uncertainty_km:.1f} km."
        if proximity.site_precision != "unknown" or proximity.site_uncertainty_km > 0
        else ""
    )
    return (
        f"nearest mapped U.S. presence: {proximity.site_name}; center-to-center {center:.1f} km; "
        f"precision-aware range {minimum:.1f}–{maximum:.1f} km; {relation}."
        f"{site_precision} Geographic proximity alone is not evidence of strategic overlap or influence."
    )
