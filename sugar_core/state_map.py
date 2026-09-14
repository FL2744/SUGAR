from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Iterable

import folium
from folium.plugins import MarkerCluster, HeatMap

from .observations import ResearchObservation
from .state_schema import StateAssessment, USPresenceSite


def _safe(value) -> str:
    return html.escape(str(value or ""))


def _popup(observation: ResearchObservation, assessment: StateAssessment) -> str:
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
    source_html = f'<a href="{_safe(source)}" target="_blank" rel="noopener noreferrer">Primary source</a>' if source else "No primary URL"
    return (
        f"<b>{_safe(observation.title or observation.program_name or observation.institution_name or observation.observation_id)}</b><br>"
        f"Type: {_safe(observation.observation_type)}<br>"
        f"Location: {_safe(observation.city)}, {_safe(observation.country)}<br>"
        f"PRC support: {_safe(assessment.prc_support.level)}<br>"
        f"Observed level: {_safe(assessment.observability_level)}<br>"
        f"Audiences: {_safe(', '.join(assessment.strategic_audiences))}<br>"
        f"Domains: {_safe(', '.join(assessment.program_domains))}<br>"
        f"Narratives: {_safe(', '.join(assessment.narrative_tags))}<br>"
        f"Metrics: {_safe('; '.join(metrics) or 'none recorded')}<br>"
        f"U.S. overlap: {_safe(assessment.us_overlap.note or 'none coded')}<br>"
        f"{source_html}"
    )


def create_state_map(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    output_file: str | Path,
    *,
    us_sites: Iterable[USPresenceSite] = (),
    verified_only: bool = True,
    include_activity_density: bool = True,
) -> str:
    observations = list(observations)
    assessments = list(assessments)
    sites = list(us_sites)
    observation_map = {row.observation_id: row for row in observations}

    mapped = []
    for assessment in assessments:
        obs = observation_map.get(assessment.observation_id)
        if not obs or obs.latitude is None or obs.longitude is None:
            continue
        if verified_only and not (assessment.brief_eligible and obs.verification_state == "human_verified"):
            continue
        mapped.append((obs, assessment))

    coordinates = [(obs.latitude, obs.longitude) for obs, _ in mapped]
    coordinates += [(site.latitude, site.longitude) for site in sites if site.latitude is not None and site.longitude is not None]
    if coordinates:
        center = [sum(lat for lat, _ in coordinates) / len(coordinates), sum(lon for _, lon in coordinates) / len(coordinates)]
        zoom = 2
    else:
        center = [20.0, 0.0]
        zoom = 2

    # Use a no-key-required default basemap. Provider-specific paid/keyed tiles can be
    # added deliberately later without making ordinary State-map generation fragile.
    map_obj = folium.Map(location=center, zoom_start=zoom, control_scale=True, tiles="OpenStreetMap")

    prc_group = folium.FeatureGroup(name="Verified PRC-network observations" if verified_only else "PRC-network observations", show=True)
    cluster = MarkerCluster(name="Observation markers").add_to(prc_group)
    for obs, assessment in mapped:
        folium.Marker(
            location=[obs.latitude, obs.longitude],
            tooltip=obs.title or obs.program_name or obs.institution_name or "Research observation",
            popup=folium.Popup(_popup(obs, assessment), max_width=480),
        ).add_to(cluster)
    prc_group.add_to(map_obj)

    if include_activity_density and mapped:
        density_group = folium.FeatureGroup(
            name="Verified observation density (activity locations, not influence)",
            show=False,
        )
        # Every observation receives equal weight. This avoids silently turning heterogeneous reach/engagement units into influence weights.
        HeatMap([[obs.latitude, obs.longitude, 1] for obs, _ in mapped], radius=20, blur=15, min_opacity=0.25).add_to(density_group)
        density_group.add_to(map_obj)

    site_groups: dict[str, folium.FeatureGroup] = {}
    for site in sites:
        if site.latitude is None or site.longitude is None:
            continue
        group = site_groups.get(site.network)
        if group is None:
            group = folium.FeatureGroup(name=f"U.S. presence — {site.network}", show=True)
            site_groups[site.network] = group
            group.add_to(map_obj)
        popup = (
            f"<b>{_safe(site.name)}</b><br>Network: {_safe(site.network)}<br>Subtype: {_safe(site.subtype)}<br>"
            f"Location: {_safe(site.city)}, {_safe(site.country)}<br>Services: {_safe(', '.join(site.service_tags))}<br>"
            + (f'<a href="{_safe(site.source_url)}" target="_blank" rel="noopener noreferrer">Source</a>' if site.source_url else "")
        )
        folium.Marker(
            location=[site.latitude, site.longitude],
            tooltip=site.name,
            popup=folium.Popup(popup, max_width=420),
        ).add_to(group)

    unlocated = sum(
        1
        for assessment in assessments
        for obs in [observation_map.get(assessment.observation_id)]
        if obs
        and (obs.latitude is None or obs.longitude is None)
        and (not verified_only or (assessment.brief_eligible and obs.verification_state == "human_verified"))
    )
    legend = f"""
    <div style="position: fixed; bottom: 20px; left: 20px; z-index: 9999; background: white; border: 1px solid #888; padding: 10px; max-width: 340px; font-size: 12px;">
      <b>SUGAR State research map</b><br>
      PRC-network layer: {len(mapped)} mapped {'verified ' if verified_only else ''}observations.<br>
      U.S. presence layer: {sum(1 for site in sites if site.latitude is not None and site.longitude is not None)} mapped sites.<br>
      Unlocated eligible observations omitted: {unlocated}.<br>
      <b>Guardrail:</b> the optional density layer is observation/activity density. It is not an influence heatmap and is not weighted by likes, views, or attendance.
    </div>
    """
    map_obj.get_root().html.add_child(folium.Element(legend))
    folium.LayerControl(collapsed=False).add_to(map_obj)

    target = Path(output_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    map_obj.save(str(target))
    metadata = target.with_suffix(target.suffix + ".metadata.json")
    metadata.write_text(
        json.dumps(
            {
                "verified_only": verified_only,
                "mapped_observations": len(mapped),
                "unlocated_eligible_observations": unlocated,
                "mapped_us_sites": sum(1 for site in sites if site.latitude is not None and site.longitude is not None),
                "density_semantics": "equal-weight verified observation/activity locations; not influence",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return str(target.resolve())
