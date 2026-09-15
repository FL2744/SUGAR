from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from .enrichment import geocode_location
from .observations import ObservationLocation, ResearchObservation
from .utils import JsonCache, normalize_whitespace

Geocoder = Callable[[str, JsonCache], dict[str, Any]]

_PRECISION_DEFAULT_UNCERTAINTY_KM = {
    "exact": 0.10,
    "site": 0.75,
    "locality": 3.0,
    "city": 12.0,
    "region": 75.0,
    "country": 250.0,
    "unknown": 100.0,
}

_PRECISION_DEFAULT_CONFIDENCE = {
    "exact": 0.95,
    "site": 0.90,
    "locality": 0.82,
    "city": 0.75,
    "region": 0.62,
    "country": 0.50,
    "unknown": 0.45,
}

_PRECISION_RANK = {
    "exact": 0,
    "site": 1,
    "locality": 2,
    "city": 3,
    "region": 4,
    "country": 5,
    "unknown": 6,
}

_SITE_BASIS_HINTS = {"site", "venue", "institution", "address", "facility", "campus"}
_EXACT_BASIS_HINTS = {"gps", "exact", "native_geo", "native_geotag", "coordinates"}
_CITY_BASIS_HINTS = {"city", "locality", "profile"}
_REGION_BASIS_HINTS = {"region", "province", "state", "oblast", "prefecture"}
_COUNTRY_BASIS_HINTS = {"country"}

_PROVIDER_SITE_TYPES = {
    "house", "building", "amenity", "university", "college", "school", "office",
    "library", "museum", "theatre", "cinema", "stadium", "hotel", "hospital",
    "station", "attraction", "campus", "facility", "commercial", "retail",
}
_PROVIDER_LOCALITY_TYPES = {
    "suburb", "neighbourhood", "neighborhood", "quarter", "borough", "district",
    "locality", "hamlet", "isolated_dwelling",
}
_PROVIDER_CITY_TYPES = {
    "city", "town", "village", "municipality", "municipal", "city_district",
}
_PROVIDER_REGION_TYPES = {
    "state", "province", "region", "county", "oblast", "prefecture", "administrative",
}
_PROVIDER_COUNTRY_TYPES = {"country"}


@dataclass(frozen=True)
class ResolvedLocation:
    observation_id: str
    latitude: float | None
    longitude: float | None
    precision: str
    confidence: float
    basis: str
    label: str
    source: str
    location_id: str = ""
    country: str = ""
    region: str = ""
    city: str = ""
    source_ref: str = ""
    query: str = ""
    display_name: str = ""
    uncertainty_km: float | None = None
    derived: bool = False
    density_eligible: bool = False
    unresolved_reason: str = ""
    provider_type: str = ""
    provider_category: str = ""

    @property
    def resolved(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(value: Any) -> str:
    return normalize_whitespace(str(value or ""))


def _valid_coordinate_pair(latitude: Any, longitude: Any) -> tuple[float, float] | None:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


def _precision_from_basis(observation: ResearchObservation) -> str:
    basis = _clean(observation.location_basis).casefold().replace("-", "_")
    tokens = {token for token in basis.replace("/", "_").split("_") if token}
    if tokens & _EXACT_BASIS_HINTS or basis in _EXACT_BASIS_HINTS:
        return "exact"
    if tokens & _SITE_BASIS_HINTS or basis in _SITE_BASIS_HINTS:
        return "site"
    if tokens & _CITY_BASIS_HINTS or basis in _CITY_BASIS_HINTS:
        return "city"
    if tokens & _REGION_BASIS_HINTS or basis in _REGION_BASIS_HINTS:
        return "region"
    if tokens & _COUNTRY_BASIS_HINTS or basis in _COUNTRY_BASIS_HINTS:
        return "country"
    if observation.city:
        return "city"
    if observation.region:
        return "region"
    if observation.country:
        return "country"
    return "unknown"


def _provider_precision(result: dict[str, Any]) -> str | None:
    values = {
        _clean(result.get("addresstype")).casefold(),
        _clean(result.get("type")).casefold(),
    }
    values.discard("")
    if values & _PROVIDER_COUNTRY_TYPES:
        return "country"
    if values & _PROVIDER_REGION_TYPES:
        return "region"
    if values & _PROVIDER_CITY_TYPES:
        return "city"
    if values & _PROVIDER_LOCALITY_TYPES:
        return "locality"
    if values & _PROVIDER_SITE_TYPES:
        return "site"
    return None


def _conservative_precision(requested: str, provider: str | None) -> str:
    if provider is None:
        return requested
    return max((requested, provider), key=lambda value: _PRECISION_RANK.get(value, 6))


def _confidence(observation: ResearchObservation, precision: str, *, derived: bool) -> float:
    if observation.location_confidence is not None:
        value = max(0.0, min(1.0, float(observation.location_confidence)))
    else:
        value = _PRECISION_DEFAULT_CONFIDENCE.get(precision, 0.45)
    if derived:
        value = min(value, _PRECISION_DEFAULT_CONFIDENCE.get(precision, value))
    return value


def _location_confidence(location: ObservationLocation, precision: str, *, derived: bool) -> float:
    if location.confidence is not None:
        value = max(0.0, min(1.0, float(location.confidence)))
    else:
        value = _PRECISION_DEFAULT_CONFIDENCE.get(precision, 0.45)
    if derived:
        value = min(value, _PRECISION_DEFAULT_CONFIDENCE.get(precision, value))
    return value


def _haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    radius = 6371.0088
    lat1 = math.radians(a_lat)
    lat2 = math.radians(b_lat)
    dlat = lat2 - lat1
    dlon = math.radians(b_lon - a_lon)
    term = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(term), math.sqrt(max(0.0, 1.0 - term)))


def _uncertainty_from_geocode(result: dict[str, Any], precision: str) -> float:
    baseline = _PRECISION_DEFAULT_UNCERTAINTY_KM.get(precision, 100.0)
    bbox = result.get("boundingbox") or []
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        try:
            south, north, west, east = [float(value) for value in bbox]
            diagonal = _haversine_km(south, west, north, east)
            if math.isfinite(diagonal) and diagonal > 0:
                return max(baseline, diagonal / 2.0)
        except (TypeError, ValueError):
            pass
    return baseline


def _join_location(*parts: str) -> str:
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        value = _clean(part)
        key = value.casefold()
        if value and key not in seen:
            result.append(value)
            seen.add(key)
    return ", ".join(result)


def _candidate_queries(observation: ResearchObservation) -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    basis_precision = _precision_from_basis(observation)
    label = _clean(observation.location_label)
    if label and basis_precision in {"exact", "site", "locality"}:
        query = _join_location(label, observation.city, observation.region, observation.country)
        candidates.append((query, "site" if basis_precision != "exact" else "exact", "location_label"))
    if observation.city:
        candidates.append((_join_location(observation.city, observation.region, observation.country), "city", "city"))
    if observation.region:
        candidates.append((_join_location(observation.region, observation.country), "region", "region"))
    return _dedupe_queries(candidates)


def _location_candidate_queries(location: ObservationLocation) -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    if location.label and location.precision in {"exact", "site", "locality"}:
        query = _join_location(location.label, location.city, location.region, location.country)
        candidates.append((query, "exact" if location.precision == "exact" else "site", "location_label"))
    if location.city:
        candidates.append((_join_location(location.city, location.region, location.country), "city", "city"))
    if location.region:
        candidates.append((_join_location(location.region, location.country), "region", "region"))
    return _dedupe_queries(candidates)


def _dedupe_queries(candidates: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    unique: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for query, precision, source in candidates:
        key = query.casefold()
        if query and key not in seen:
            unique.append((query, precision, source))
            seen.add(key)
    return unique


def _resolve_structured_location(
    observation: ResearchObservation,
    location: ObservationLocation,
    *,
    cache: JsonCache | None,
    geocoder: Geocoder,
    resolve_missing: bool,
    minimum_confidence: float,
) -> ResolvedLocation:
    pair = _valid_coordinate_pair(location.latitude, location.longitude)
    precision = location.precision
    confidence = _location_confidence(location, precision, derived=False)
    label = location.label or _join_location(location.city, location.region, location.country)
    uncertainty = (
        location.uncertainty_km
        if location.uncertainty_km is not None
        else _PRECISION_DEFAULT_UNCERTAINTY_KM.get(precision, 100.0)
    )
    common = {
        "observation_id": observation.observation_id,
        "location_id": location.location_id,
        "country": location.country,
        "region": location.region,
        "city": location.city,
        "source_ref": location.source_ref,
        "basis": location.basis or "unknown",
        "label": label,
    }
    if pair is not None:
        return ResolvedLocation(
            **common,
            latitude=pair[0],
            longitude=pair[1],
            precision=precision,
            confidence=confidence,
            source="structured_location_coordinates",
            display_name=label,
            uncertainty_km=uncertainty,
            derived=False,
            density_eligible=precision in {"exact", "site", "locality", "city"} and confidence >= minimum_confidence,
        )
    if not resolve_missing:
        return ResolvedLocation(
            **common,
            latitude=None,
            longitude=None,
            precision=precision,
            confidence=confidence,
            source="structured_location_unresolved",
            uncertainty_km=uncertainty,
            unresolved_reason="No coordinate pair is recorded for this evidenced activity location and location resolution is disabled.",
        )
    if cache is None:
        raise ValueError("A geocode cache is required when resolve_missing=True.")
    candidates = _location_candidate_queries(location)
    if not candidates:
        reason = "Country-only location is not plotted at a national centroid." if location.country else "No site, city, or region evidence is available."
        return ResolvedLocation(
            **common,
            latitude=None,
            longitude=None,
            precision=precision,
            confidence=_location_confidence(location, precision, derived=True),
            source="structured_location_unresolved",
            uncertainty_km=uncertainty,
            unresolved_reason=reason,
        )
    for query, candidate_precision, source in candidates:
        result = geocoder(query, cache)
        pair = _valid_coordinate_pair(result.get("latitude"), result.get("longitude"))
        if pair is None:
            continue
        resolved_precision = _conservative_precision(candidate_precision, _provider_precision(result))
        if resolved_precision == "country":
            continue
        derived_confidence = _location_confidence(location, resolved_precision, derived=True)
        return ResolvedLocation(
            **common,
            latitude=pair[0],
            longitude=pair[1],
            precision=resolved_precision,
            confidence=derived_confidence,
            source=f"structured_geocoded_{source}",
            query=query,
            display_name=_clean(result.get("display_name")) or query,
            uncertainty_km=max(
                float(location.uncertainty_km or 0.0),
                _uncertainty_from_geocode(result, resolved_precision),
            ),
            derived=True,
            density_eligible=resolved_precision in {"exact", "site", "locality", "city"} and derived_confidence >= minimum_confidence,
            provider_type=_clean(result.get("addresstype") or result.get("type")),
            provider_category=_clean(result.get("category")),
        )
    return ResolvedLocation(
        **common,
        latitude=None,
        longitude=None,
        precision=precision,
        confidence=_location_confidence(location, precision, derived=True),
        source="structured_geocode_no_match",
        uncertainty_km=uncertainty,
        unresolved_reason="No site/city/region geocode candidate returned a defensible coordinate for this activity location.",
    )


def _resolve_legacy_location(
    observation: ResearchObservation,
    *,
    cache: JsonCache | None,
    geocoder: Geocoder,
    resolve_missing: bool,
    minimum_confidence: float,
) -> ResolvedLocation:
    pair = _valid_coordinate_pair(observation.latitude, observation.longitude)
    precision = _precision_from_basis(observation)
    label = _clean(observation.location_label) or _join_location(observation.city, observation.region, observation.country)
    basis = _clean(observation.location_basis) or "unknown"
    if pair is not None:
        confidence = _confidence(observation, precision, derived=False)
        return ResolvedLocation(
            observation_id=observation.observation_id,
            latitude=pair[0], longitude=pair[1], precision=precision, confidence=confidence,
            basis=basis, label=label, source="recorded_coordinates",
            country=observation.country, region=observation.region, city=observation.city,
            display_name=label,
            uncertainty_km=_PRECISION_DEFAULT_UNCERTAINTY_KM.get(precision, 100.0),
            derived=False,
            density_eligible=precision in {"exact", "site", "locality", "city"} and confidence >= minimum_confidence,
        )
    if not resolve_missing:
        return ResolvedLocation(
            observation_id=observation.observation_id,
            latitude=None, longitude=None, precision=precision,
            confidence=_confidence(observation, precision, derived=True), basis=basis, label=label,
            source="unresolved", country=observation.country, region=observation.region, city=observation.city,
            unresolved_reason="No recorded coordinate pair and location resolution is disabled.",
        )
    if cache is None:
        raise ValueError("A geocode cache is required when resolve_missing=True.")
    candidates = _candidate_queries(observation)
    if not candidates:
        reason = "Country-only location is not plotted at a national centroid." if observation.country else "No site, city, or region evidence is available."
        return ResolvedLocation(
            observation_id=observation.observation_id,
            latitude=None, longitude=None, precision=precision,
            confidence=_confidence(observation, precision, derived=True), basis=basis, label=label,
            source="unresolved", country=observation.country, region=observation.region, city=observation.city,
            unresolved_reason=reason,
        )
    for query, candidate_precision, source in candidates:
        result = geocoder(query, cache)
        pair = _valid_coordinate_pair(result.get("latitude"), result.get("longitude"))
        if pair is None:
            continue
        resolved_precision = _conservative_precision(candidate_precision, _provider_precision(result))
        if resolved_precision == "country":
            continue
        confidence = _confidence(observation, resolved_precision, derived=True)
        return ResolvedLocation(
            observation_id=observation.observation_id,
            latitude=pair[0], longitude=pair[1], precision=resolved_precision, confidence=confidence,
            basis=basis, label=label or query, source=f"geocoded_{source}", query=query,
            country=observation.country, region=observation.region, city=observation.city,
            display_name=_clean(result.get("display_name")) or query,
            uncertainty_km=_uncertainty_from_geocode(result, resolved_precision), derived=True,
            density_eligible=resolved_precision in {"exact", "site", "locality", "city"} and confidence >= minimum_confidence,
            provider_type=_clean(result.get("addresstype") or result.get("type")),
            provider_category=_clean(result.get("category")),
        )
    return ResolvedLocation(
        observation_id=observation.observation_id,
        latitude=None, longitude=None, precision=precision,
        confidence=_confidence(observation, precision, derived=True), basis=basis, label=label,
        source="geocode_no_match", country=observation.country, region=observation.region, city=observation.city,
        unresolved_reason="No site/city/region geocode candidate returned a defensible coordinate.",
    )


def resolve_observation_locations(
    observation: ResearchObservation,
    *,
    cache: JsonCache | None = None,
    geocoder: Geocoder = geocode_location,
    resolve_missing: bool = False,
    minimum_confidence: float = 0.45,
) -> list[ResolvedLocation]:
    """Resolve every evidenced activity location without multiplying the observation itself."""
    if observation.locations:
        return [
            _resolve_structured_location(
                observation,
                location,
                cache=cache,
                geocoder=geocoder,
                resolve_missing=resolve_missing,
                minimum_confidence=minimum_confidence,
            )
            for location in observation.locations
        ]
    return [
        _resolve_legacy_location(
            observation,
            cache=cache,
            geocoder=geocoder,
            resolve_missing=resolve_missing,
            minimum_confidence=minimum_confidence,
        )
    ]


def resolve_observation_location(
    observation: ResearchObservation,
    *,
    cache: JsonCache | None = None,
    geocoder: Geocoder = geocode_location,
    resolve_missing: bool = False,
    minimum_confidence: float = 0.45,
) -> ResolvedLocation:
    """Backward-compatible primary location resolver.

    Multi-site observations return their first resolved location when one exists, otherwise the
    first structured location. Call ``resolve_observation_locations`` when every venue matters.
    """
    locations = resolve_observation_locations(
        observation,
        cache=cache,
        geocoder=geocoder,
        resolve_missing=resolve_missing,
        minimum_confidence=minimum_confidence,
    )
    return next((location for location in locations if location.resolved), locations[0])


def default_state_geocode_cache(path: str | Path) -> JsonCache:
    return JsonCache(Path(path).expanduser() / "state-map-geocode.json")
