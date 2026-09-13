from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import pandas as pd

from .observations import ResearchObservation, SpatialMatch
from .utils import safe_cell, utc_iso

EARTH_RADIUS_KM = 6371.0088
DEFAULT_DISTANCE_BANDS_KM = (5.0, 25.0, 100.0, 250.0)


@dataclass(frozen=True)
class SpatialOverlapConfig:
    distance_bands_km: tuple[float, ...] = DEFAULT_DISTANCE_BANDS_KM
    max_distance_km: float | None = None
    stored_matches_per_observation: int = 5
    include_rejected: bool = False

    def __post_init__(self) -> None:
        bands = tuple(sorted({float(value) for value in self.distance_bands_km if float(value) > 0}))
        if not bands:
            raise ValueError("At least one positive spatial distance band is required.")
        object.__setattr__(self, "distance_bands_km", bands)
        max_distance = self.max_distance_km
        if max_distance is None:
            max_distance = bands[-1]
        max_distance = float(max_distance)
        if max_distance <= 0:
            raise ValueError("max_distance_km must be positive.")
        object.__setattr__(self, "max_distance_km", max_distance)
        if int(self.stored_matches_per_observation) < 1:
            raise ValueError("stored_matches_per_observation must be at least 1.")
        object.__setattr__(self, "stored_matches_per_observation", int(self.stored_matches_per_observation))


@dataclass(frozen=True)
class ReferencePoint:
    layer: str
    reference_id: str
    name: str
    category: str
    latitude: float
    longitude: float
    city: str = ""
    country: str = ""
    source_url: str = ""


def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = " ".join(str(value).split())
    return "" if text.casefold() == "nan" else text


def _safe_url(value: Any) -> str:
    url = _clean(value)
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def _first(row: pd.Series, *names: str) -> str:
    for name in names:
        if name in row:
            value = _clean(row.get(name))
            if value:
                return value
    return ""


def _valid_coordinate(latitude: Any, longitude: Any) -> tuple[float, float] | None:
    try:
        lat = float(str(latitude).lstrip("'"))
        lon = float(str(longitude).lstrip("'"))
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


def haversine_km(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    """Return great-circle distance in kilometers using the IUGG mean Earth radius."""
    lat1 = math.radians(float(latitude_a))
    lat2 = math.radians(float(latitude_b))
    delta_lat = math.radians(float(latitude_b) - float(latitude_a))
    delta_lon = math.radians(float(longitude_b) - float(longitude_a))
    a = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2.0) ** 2
    )
    return EARTH_RADIUS_KM * 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def distance_band(distance_km: float, bands_km: Iterable[float]) -> str:
    distance = float(distance_km)
    lower = 0.0
    for upper in sorted(float(value) for value in bands_km):
        if distance <= upper:
            if lower == 0.0:
                return f"0–{upper:g} km"
            return f"{lower:g}–{upper:g} km"
        lower = upper
    return f">{lower:g} km"


def reference_points_from_frame(frame: pd.DataFrame, layer_name: str) -> list[ReferencePoint]:
    layer = _clean(layer_name) or "Reference"
    points: list[ReferencePoint] = []
    seen: set[tuple[str, float, float]] = set()
    for index, row in frame.iterrows():
        coords = _valid_coordinate(row.get("latitude"), row.get("longitude"))
        if coords is None:
            continue
        latitude, longitude = coords
        name = _first(row, "name", "title", "institution_name", "program_name", "location_label") or f"{layer} {index + 1}"
        reference_id = _first(row, "id", "reference_id", "observation_id", "native_id") or f"{layer.casefold().replace(' ', '_')}:{index + 1}"
        identity = (reference_id.casefold(), round(latitude, 7), round(longitude, 7))
        if identity in seen:
            continue
        seen.add(identity)
        points.append(
            ReferencePoint(
                layer=layer,
                reference_id=reference_id,
                name=name,
                category=_first(row, "category", "type", "space_type", "observation_type") or "reference",
                latitude=latitude,
                longitude=longitude,
                city=_first(row, "city"),
                country=_first(row, "country"),
                source_url=_safe_url(_first(row, "url", "source_url", "primary_source_url", "website")),
            )
        )
    return points


def _same_place(left: str, right: str) -> bool:
    return bool(left and right and _clean(left).casefold() == _clean(right).casefold())


def analyze_spatial_overlap(
    observations: Iterable[ResearchObservation],
    reference_layers: Iterable[tuple[str, pd.DataFrame]],
    *,
    config: SpatialOverlapConfig | None = None,
) -> tuple[list[ResearchObservation], pd.DataFrame, dict[str, Any]]:
    """Compute reproducible geographic proximity without asserting strategic overlap.

    The full retained match table contains every observation/reference pair inside max_distance_km.
    Each observation stores only its nearest N matches for portability. Existing manual `us_overlap`
    judgments are not modified.
    """
    config = config or SpatialOverlapConfig()
    observations = list(observations)
    references: list[ReferencePoint] = []
    reference_counts: dict[str, int] = {}
    for layer_name, frame in reference_layers:
        points = reference_points_from_frame(frame, layer_name)
        references.extend(points)
        reference_counts[_clean(layer_name) or "Reference"] = len(points)
    if not references:
        raise ValueError("No valid geocoded reference points were provided.")

    match_rows: list[dict[str, Any]] = []
    analyzed = 0
    skipped_unmapped = 0
    skipped_rejected = 0
    matched_observations = 0

    for observation in observations:
        had_spatial_matches = bool(observation.spatial_matches)
        observation.spatial_matches = []
        coords = _valid_coordinate(observation.latitude, observation.longitude)
        if coords is None:
            skipped_unmapped += 1
            if had_spatial_matches:
                observation.touch()
            continue
        if observation.verification_state == "rejected" and not config.include_rejected:
            skipped_rejected += 1
            if had_spatial_matches:
                observation.touch()
            continue
        analyzed += 1
        latitude, longitude = coords
        local_rows: list[dict[str, Any]] = []
        for reference in references:
            distance = haversine_km(latitude, longitude, reference.latitude, reference.longitude)
            if distance > float(config.max_distance_km):
                continue
            row = {
                "observation_id": observation.observation_id,
                "observation_type": observation.observation_type,
                "observation_title": observation.title,
                "observation_city": observation.city,
                "observation_country": observation.country,
                "reference_layer": reference.layer,
                "reference_id": reference.reference_id,
                "reference_name": reference.name,
                "reference_category": reference.category,
                "distance_km": round(distance, 3),
                "distance_band": distance_band(distance, config.distance_bands_km),
                "same_city": _same_place(observation.city, reference.city),
                "same_country": _same_place(observation.country, reference.country),
                "reference_latitude": reference.latitude,
                "reference_longitude": reference.longitude,
                "reference_source_url": reference.source_url,
            }
            local_rows.append(row)
            match_rows.append(row)

        local_rows.sort(key=lambda item: (float(item["distance_km"]), item["reference_layer"], item["reference_id"]))
        if local_rows:
            matched_observations += 1
        observation.spatial_matches = [
            SpatialMatch(
                reference_layer=row["reference_layer"],
                reference_id=row["reference_id"],
                reference_name=row["reference_name"],
                reference_category=row["reference_category"],
                distance_km=row["distance_km"],
                distance_band=row["distance_band"],
                same_city=row["same_city"],
                same_country=row["same_country"],
                latitude=row["reference_latitude"],
                longitude=row["reference_longitude"],
                source_url=row["reference_source_url"],
            )
            for row in local_rows[: config.stored_matches_per_observation]
        ]
        if observation.spatial_matches or had_spatial_matches:
            observation.touch()

    matches = pd.DataFrame(match_rows)
    if not matches.empty:
        matches = matches.sort_values(
            ["observation_id", "distance_km", "reference_layer", "reference_id"],
            kind="stable",
        ).reset_index(drop=True)

    nearest_band_counts: dict[str, int] = {}
    nearest_distance_values: list[float] = []
    for observation in observations:
        if not observation.spatial_matches:
            continue
        nearest = observation.spatial_matches[0]
        nearest_band_counts[nearest.distance_band] = nearest_band_counts.get(nearest.distance_band, 0) + 1
        nearest_distance_values.append(nearest.distance_km)

    summary = {
        "generated_at": utc_iso(),
        "observations_total": len(observations),
        "observations_analyzed": analyzed,
        "observations_matched": matched_observations,
        "observations_unmapped": skipped_unmapped,
        "rejected_skipped": skipped_rejected,
        "reference_points": len(references),
        "reference_layers": reference_counts,
        "distance_bands_km": list(config.distance_bands_km),
        "max_distance_km": config.max_distance_km,
        "stored_matches_per_observation": config.stored_matches_per_observation,
        "retained_pair_matches": len(matches),
        "nearest_band_counts": nearest_band_counts,
        "nearest_distance_km_median": (
            round(float(pd.Series(nearest_distance_values).median()), 3)
            if nearest_distance_values
            else None
        ),
        "interpretation": "Geographic proximity is a computed fact, not evidence of strategic overlap, influence, coordination, competition, or causation.",
    }
    return observations, matches, summary


def save_spatial_matches(frame: pd.DataFrame, output_file: str | Path) -> list[str]:
    output_file = Path(output_file)
    csv_path = output_file if output_file.suffix.casefold() == ".csv" else output_file.with_suffix(".csv")
    xlsx_path = csv_path.with_suffix(".xlsx")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    export = frame.copy()
    for column in export.columns:
        if column not in {"distance_km", "same_city", "same_country", "reference_latitude", "reference_longitude"}:
            export[column] = export[column].map(lambda value: safe_cell(value, formula_safe=True))
    export.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        export.to_excel(writer, index=False, sheet_name="spatial_matches")
    return [str(csv_path.resolve()), str(xlsx_path.resolve())]


def save_spatial_summary(summary: dict[str, Any], output_file: str | Path) -> str:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return str(path.resolve())
