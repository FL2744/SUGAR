from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import folium
from folium.plugins import HeatMap, MarkerCluster

from .observations import ResearchObservation
from .state_location import ResolvedLocation, default_state_geocode_cache, resolve_observation_locations
from .state_proximity import (
    DEFAULT_NEARBY_THRESHOLD_KM,
    DEFAULT_US_SITE_UNCERTAINTY_KM,
    StateProximity,
    nearest_us_presence,
    proximity_note,
)
from .state_schema import StateAssessment, USPresenceSite
from .utils import atomic_write_text

_PRECISION_LABELS = {
    "exact": "Exact/native coordinates",
    "site": "Site/venue level",
    "locality": "Locality level",
    "city": "City level",
    "region": "Region/province level",
    "country": "Country only",
    "unknown": "Unknown precision",
}

_PRECISION_COLORS = {
    "exact": "#166534",
    "site": "#15803d",
    "locality": "#0f766e",
    "city": "#2563eb",
    "region": "#7c3aed",
    "country": "#64748b",
    "unknown": "#64748b",
}


def _safe(value) -> str:
    return html.escape(str(value or ""))


def _location_summary(location: ResolvedLocation) -> str:
    precision = _PRECISION_LABELS.get(location.precision, location.precision)
    confidence = f"{location.confidence:.0%}"
    uncertainty = (
        f"; estimated uncertainty radius ≈ {location.uncertainty_km:.1f} km"
        if location.uncertainty_km is not None and location.uncertainty_km >= 1.0
        else ""
    )
    derived = "derived/geocoded" if location.derived else "recorded"
    return f"{precision}; {confidence} confidence; {derived}{uncertainty}"


def _popup(
    observation: ResearchObservation,
    assessment: StateAssessment,
    location: ResolvedLocation,
    proximity: StateProximity | None = None,
) -> str:
    reach = assessment.reach
    metrics = []
    for label, value in (
        ("Attendance", reach.attendance),
        ("Views", reach.views),
        ("Likes", reach.likes),
        ("Comments", reach.comments),
        ("Shares/reposts", reach.shares_reposts),
    ):
        if value is not None:
            metrics.append(f"{label}: {int(value):,}")
    source = observation.primary_source_url
    source_html = (
        f'<a href="{_safe(source)}" target="_blank" rel="noopener noreferrer">Primary source</a>'
        if source
        else "No primary URL"
    )
    resolved_name = (
        location.display_name
        or location.label
        or ", ".join(value for value in (location.city, location.region, location.country) if value)
    )
    location_query = f"<br>Resolution query: {_safe(location.query)}" if location.query else ""
    provider = ""
    if location.provider_type or location.provider_category:
        provider = f"<br>Geocoder feature: {_safe(location.provider_type or location.provider_category)}"
    source_ref = f"<br>Location source reference: {_safe(location.source_ref)}" if location.source_ref else ""
    map_proximity = f"<br>Map proximity: {_safe(proximity_note(proximity))}" if proximity is not None else ""
    multi = f"<br>Activity locations recorded: {len(observation.locations)}" if observation.locations else ""
    return (
        f"<b>{_safe(observation.title or observation.program_name or observation.institution_name or observation.observation_id)}</b><br>"
        f"Type: {_safe(observation.observation_type)}<br>"
        f"Mapped activity location: {_safe(resolved_name)}<br>"
        f"Location precision: {_safe(_location_summary(location))}<br>"
        f"Location basis: {_safe(location.basis)}; source: {_safe(location.source)}"
        f"{source_ref}{location_query}{provider}{multi}<br>"
        f"PRC support: {_safe(assessment.prc_support.level)}<br>"
        f"Observed level: {_safe(assessment.observability_level)}<br>"
        f"Audiences: {_safe(', '.join(assessment.strategic_audiences))}<br>"
        f"Domains: {_safe(', '.join(assessment.program_domains))}<br>"
        f"Narratives: {_safe(', '.join(assessment.narrative_tags))}<br>"
        f"Metrics: {_safe('; '.join(metrics) or 'none recorded')}<br>"
        f"U.S. overlap: {_safe(assessment.us_overlap.note or 'none coded')}"
        f"{map_proximity}<br>{source_html}"
    )


def _eligible(observation: ResearchObservation, assessment: StateAssessment, verified_only: bool) -> bool:
    if not verified_only:
        return True
    return bool(assessment.brief_eligible and observation.verification_state == "human_verified")


def _add_uncertainty_circle(group, location: ResolvedLocation, tooltip: str) -> None:
    if not location.resolved or location.uncertainty_km is None:
        return
    if location.precision not in {"city", "region", "locality"} and not location.derived:
        return
    radius_m = max(250.0, float(location.uncertainty_km) * 1000.0)
    color = _PRECISION_COLORS.get(location.precision, "#64748b")
    folium.Circle(
        location=[location.latitude, location.longitude],
        radius=radius_m,
        color=color,
        weight=1,
        opacity=0.45,
        fill=True,
        fill_color=color,
        fill_opacity=0.06,
        tooltip=f"Approximate location envelope — {tooltip}",
    ).add_to(group)


def _resolution_ledger(
    mapped: list[tuple[ResearchObservation, StateAssessment, ResolvedLocation]],
) -> list[dict[str, object]]:
    ledger: list[dict[str, object]] = []
    for observation, _, location in mapped:
        ledger.append(
            {
                "observation_id": observation.observation_id,
                "location_id": location.location_id,
                "title": observation.title or observation.program_name or observation.institution_name,
                "recorded_country": location.country or observation.country,
                "recorded_region": location.region or observation.region,
                "recorded_city": location.city or observation.city,
                "location_label": location.label,
                "source_ref": location.source_ref,
                "latitude": location.latitude,
                "longitude": location.longitude,
                "precision": location.precision,
                "confidence": location.confidence,
                "basis": location.basis,
                "source": location.source,
                "derived": location.derived,
                "query": location.query,
                "display_name": location.display_name,
                "provider_type": location.provider_type,
                "provider_category": location.provider_category,
                "uncertainty_km": location.uncertainty_km,
                "density_eligible": location.density_eligible,
            }
        )
    return ledger


def _proximity_ledger(
    mapped: list[tuple[ResearchObservation, StateAssessment, ResolvedLocation]],
    proximity_by_key: dict[tuple[str, str], StateProximity],
) -> list[dict[str, object]]:
    titles = {
        (observation.observation_id, location.location_id): observation.title
        or observation.program_name
        or observation.institution_name
        for observation, _, location in mapped
    }
    result: list[dict[str, object]] = []
    for key in sorted(proximity_by_key):
        proximity = proximity_by_key[key]
        row = proximity.as_dict()
        row["title"] = titles.get(key, "")
        result.append(row)
    return result


def create_state_map(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    output_file: str | Path,
    *,
    us_sites: Iterable[USPresenceSite] = (),
    verified_only: bool = True,
    include_activity_density: bool = True,
    resolve_missing_locations: bool = False,
    geocode_cache: str | Path | None = None,
    minimum_location_confidence: float = 0.45,
    proximity_threshold_km: float = DEFAULT_NEARBY_THRESHOLD_KM,
    us_site_uncertainty_km: float = DEFAULT_US_SITE_UNCERTAINTY_KM,
) -> str:
    observations = list(observations)
    assessments = list(assessments)
    sites = list(us_sites)
    target = Path(output_file).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    observation_map = {row.observation_id: row for row in observations}

    cache = None
    if resolve_missing_locations:
        cache_root = Path(geocode_cache).expanduser() if geocode_cache else target.parent / ".sugar-cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        cache = default_state_geocode_cache(cache_root)

    mapped: list[tuple[ResearchObservation, StateAssessment, ResolvedLocation]] = []
    unresolved: list[dict[str, str]] = []
    eligible_observation_ids: set[str] = set()
    for assessment in assessments:
        observation = observation_map.get(assessment.observation_id)
        if not observation or not _eligible(observation, assessment, verified_only):
            continue
        eligible_observation_ids.add(observation.observation_id)
        locations = resolve_observation_locations(
            observation,
            cache=cache,
            resolve_missing=resolve_missing_locations,
            minimum_confidence=minimum_location_confidence,
        )
        for location in locations:
            if location.resolved:
                mapped.append((observation, assessment, location))
            else:
                unresolved.append(
                    {
                        "observation_id": observation.observation_id,
                        "location_id": location.location_id,
                        "title": observation.title or observation.program_name or observation.institution_name,
                        "country": location.country or observation.country,
                        "region": location.region or observation.region,
                        "city": location.city or observation.city,
                        "location_label": location.label,
                        "location_basis": location.basis,
                        "source_ref": location.source_ref,
                        "reason": location.unresolved_reason,
                    }
                )

    proximity_by_key: dict[tuple[str, str], StateProximity] = {}
    for observation, _, location in mapped:
        proximity = nearest_us_presence(
            observation,
            location,
            sites,
            threshold_km=proximity_threshold_km,
            site_uncertainty_km=us_site_uncertainty_km,
        )
        if proximity is not None:
            proximity_by_key[(observation.observation_id, location.location_id)] = proximity

    spatial_sites = [site for site in sites if site.is_spatial]
    site_coordinates = [(float(site.latitude), float(site.longitude)) for site in spatial_sites]
    coordinates = [
        (float(loc.latitude), float(loc.longitude)) for _, _, loc in mapped if loc.resolved
    ] + site_coordinates
    if coordinates:
        center = [
            sum(lat for lat, _ in coordinates) / len(coordinates),
            sum(lon for _, lon in coordinates) / len(coordinates),
        ]
    else:
        center = [20.0, 0.0]
    zoom_start = 10 if len(coordinates) == 1 else 2
    map_obj = folium.Map(location=center, zoom_start=zoom_start, control_scale=True, tiles="OpenStreetMap")

    groups: dict[str, folium.FeatureGroup] = {}
    clusters: dict[str, MarkerCluster] = {}
    precision_order = ("exact", "site", "locality", "city", "region", "country", "unknown")
    for precision in precision_order:
        if not any(loc.precision == precision for _, _, loc in mapped):
            continue
        label = _PRECISION_LABELS.get(precision, precision)
        group = folium.FeatureGroup(
            name=f"{'Verified ' if verified_only else ''}PRC activity locations — {label}",
            show=precision in {"exact", "site", "locality", "city"},
        )
        cluster = MarkerCluster(name=f"{label} markers").add_to(group)
        groups[precision] = group
        clusters[precision] = cluster
        group.add_to(map_obj)

    for observation, assessment, location in mapped:
        precision = location.precision
        group = groups[precision]
        cluster = clusters[precision]
        color = _PRECISION_COLORS.get(precision, "#64748b")
        title = observation.title or observation.program_name or observation.institution_name or "Research observation"
        venue = location.display_name or location.label
        tooltip = f"{title} · {venue}" if venue else title
        proximity = proximity_by_key.get((observation.observation_id, location.location_id))
        folium.CircleMarker(
            location=[location.latitude, location.longitude],
            radius=7 if precision in {"exact", "site"} else 6,
            color=color,
            weight=2,
            fill=True,
            fill_color=color,
            fill_opacity=0.82 if precision in {"exact", "site"} else 0.64,
            tooltip=f"{tooltip} · {_PRECISION_LABELS.get(precision, precision)}",
            popup=folium.Popup(_popup(observation, assessment, location, proximity), max_width=560),
        ).add_to(cluster)
        _add_uncertainty_circle(group, location, tooltip)

    density_by_observation: dict[str, list[ResolvedLocation]] = defaultdict(list)
    for observation, _, location in mapped:
        if location.density_eligible:
            density_by_observation[observation.observation_id].append(location)
    density_rows: list[list[float]] = []
    for observation_id, locations in density_by_observation.items():
        weight = 1.0 / len(locations)
        for location in locations:
            density_rows.append([float(location.latitude), float(location.longitude), weight])
    density_scope = "Verified" if verified_only else "Eligible"
    density_rendered = bool(include_activity_density and density_rows)
    if density_rendered:
        density_group = folium.FeatureGroup(
            name=f"{density_scope} activity density — one total weight per observation (not influence)",
            show=False,
        )
        HeatMap(density_rows, radius=20, blur=15, min_opacity=0.25).add_to(density_group)
        density_group.add_to(map_obj)

    site_groups: dict[str, folium.FeatureGroup] = {}
    site_by_id: dict[str, USPresenceSite] = {}
    for site in spatial_sites:
        assert site.latitude is not None and site.longitude is not None
        site_by_id[site.site_id] = site
        group = site_groups.get(site.network)
        if group is None:
            group = folium.FeatureGroup(name=f"U.S. presence — {site.network}", show=True)
            site_groups[site.network] = group
            group.add_to(map_obj)
        popup = (
            f"<b>{_safe(site.name)}</b><br>Network: {_safe(site.network)}<br>Subtype: {_safe(site.subtype)}<br>"
            f"Location: {_safe(site.city)}, {_safe(site.country)}<br>Services: {_safe(', '.join(site.service_tags))}<br>"
            + (
                f'<a href="{_safe(site.source_url)}" target="_blank" rel="noopener noreferrer">Source</a>'
                if site.source_url
                else ""
            )
        )
        folium.Marker(
            location=[site.latitude, site.longitude],
            tooltip=site.name,
            popup=folium.Popup(popup, max_width=420),
        ).add_to(group)

    mapped_location_by_key = {
        (observation.observation_id, location.location_id): location for observation, _, location in mapped
    }
    proximity_groups: dict[str, folium.FeatureGroup] = {}
    proximity_group_labels = {
        "within_threshold": "U.S. proximity — uncertainty range within threshold",
        "uncertainty_intersects_threshold": "U.S. proximity — uncertainty intersects threshold",
    }
    for relation, group_label in proximity_group_labels.items():
        if not any(item.relation == relation for item in proximity_by_key.values()):
            continue
        group = folium.FeatureGroup(name=group_label, show=False)
        proximity_groups[relation] = group
        group.add_to(map_obj)
    for key, proximity in proximity_by_key.items():
        if proximity.relation not in proximity_groups:
            continue
        location = mapped_location_by_key.get(key)
        site = site_by_id.get(proximity.site_id)
        if location is None or site is None:
            continue
        uncertain = proximity.relation == "uncertainty_intersects_threshold"
        folium.PolyLine(
            locations=[
                [float(location.latitude), float(location.longitude)],
                [float(site.latitude), float(site.longitude)],
            ],
            weight=2,
            opacity=0.58,
            color="#a16207" if uncertain else "#475569",
            dash_array="7, 7" if uncertain else None,
            tooltip=proximity_note(proximity),
        ).add_to(proximity_groups[proximity.relation])

    if len(coordinates) >= 2:
        map_obj.fit_bounds([[lat, lon] for lat, lon in coordinates], padding=(24, 24))

    mapped_observation_ids = {observation.observation_id for observation, _, _ in mapped}
    precision_counts = Counter(location.precision for _, _, location in mapped)
    proximity_counts = Counter(item.relation for item in proximity_by_key.values())
    derived_count = sum(int(location.derived) for _, _, location in mapped)
    density_eligible_observations = len(density_by_observation)
    density_eligible_locations = sum(len(locations) for locations in density_by_observation.values())
    density_multi_location_observations = sum(len(locations) > 1 for locations in density_by_observation.values())
    density_total_weight = sum(row[2] for row in density_rows)
    precision_text = (
        ", ".join(
            f"{_PRECISION_LABELS.get(key, key)}: {precision_counts[key]}"
            for key in precision_order
            if precision_counts.get(key)
        )
        or "none"
    )
    proximity_text = (
        f"within {proximity_threshold_km:g} km after uncertainty: {proximity_counts.get('within_threshold', 0)}; "
        f"threshold intersects uncertainty: {proximity_counts.get('uncertainty_intersects_threshold', 0)}; "
        f"outside: {proximity_counts.get('outside_threshold', 0)}"
        if proximity_by_key
        else "no mapped U.S. reference proximity available"
    )
    legend = f"""
    <div style="position: fixed; bottom: 20px; left: 20px; z-index: 9999; background: white; border: 1px solid #888; padding: 10px; max-width: 440px; font-size: 12px;">
      <b>SUGAR State research map</b><br>
      Mapped {"verified " if verified_only else ""}observations: {len(mapped_observation_ids)}; mapped activity locations: {len(mapped)}.<br>
      Location precision: {_safe(precision_text)}.<br>
      Derived/geocoded locations: {derived_count}; unresolved activity locations: {len(unresolved)}.<br>
      U.S. presence sites: {len(site_coordinates)}.<br>
      U.S. proximity: {_safe(proximity_text)}.<br>
      Density-eligible observations: {density_eligible_observations}; density locations: {density_eligible_locations}; total density weight: {density_total_weight:.1f}.<br>
      <b>Multi-site rule:</b> one activity may have multiple venue markers, but its defensible density locations split a total weight of 1.0 so venue count does not inflate activity count.<br>
      <b>Precision rule:</b> translucent circles show approximate geographic uncertainty; a centroid is not presented as an exact venue.<br>
      <b>Analytic guardrail:</b> density and proximity describe mapped activity/reference geography, not influence, and are never weighted by likes, views, or attendance.
    </div>
    """
    map_obj.get_root().html.add_child(folium.Element(legend))
    folium.LayerControl(collapsed=False).add_to(map_obj)

    map_obj.save(str(target))
    metadata = target.with_suffix(target.suffix + ".metadata.json")
    atomic_write_text(
        metadata,
        json.dumps(
            {
                "verified_only": verified_only,
                "location_resolution_enabled": resolve_missing_locations,
                "minimum_location_confidence": minimum_location_confidence,
                "eligible_observations": len(eligible_observation_ids),
                "mapped_observations": len(mapped_observation_ids),
                "mapped_locations": len(mapped),
                "multi_location_observations": sum(
                    1
                    for observation_id in mapped_observation_ids
                    if sum(obs.observation_id == observation_id for obs, _, _ in mapped) > 1
                ),
                "derived_geocoded_observations": len({obs.observation_id for obs, _, loc in mapped if loc.derived}),
                "derived_geocoded_locations": derived_count,
                "precision_counts": dict(sorted(precision_counts.items())),
                "resolved_locations": _resolution_ledger(mapped),
                "unresolved_eligible_observations": len({row["observation_id"] for row in unresolved}),
                "unresolved_activity_locations": len(unresolved),
                "unresolved": unresolved,
                "mapped_us_sites": len(site_coordinates),
                "us_proximity_threshold_km": float(proximity_threshold_km),
                "us_site_default_uncertainty_km": float(us_site_uncertainty_km),
                "us_proximity_counts": dict(sorted(proximity_counts.items())),
                "us_proximity": _proximity_ledger(mapped, proximity_by_key),
                "activity_density_requested": include_activity_density,
                "activity_density_rendered": density_rendered,
                "density_eligible_observations": density_eligible_observations,
                "density_eligible_locations": density_eligible_locations,
                "density_multi_location_observations": density_multi_location_observations,
                "density_total_weight": round(density_total_weight, 6),
                "density_excluded_for_precision": len(eligible_observation_ids) - density_eligible_observations,
                "density_semantics": "equal total weight per observation across all defensible exact/site/locality/city activity locations with sufficient confidence; multiple venues do not multiply one activity; not influence",
                "proximity_semantics": "proximity is evaluated per resolved activity location; center-to-center distance is accompanied by a conservative range derived from activity-location precision plus the U.S.-site location envelope; not evidence of strategic overlap/influence",
                "precision_semantics": "activity locations retain location-specific provenance and precision; geocoder results may downgrade query precision; country-only records without coordinates are not plotted at national centroids",
            },
            indent=2,
            sort_keys=True,
        ),
    )
    return str(target)
