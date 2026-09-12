from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import pandas as pd


OBSERVATION_COLORS = {
    "institution": "#2563eb",
    "program": "#16a34a",
    "event": "#ea580c",
    "digital_post": "#7c3aed",
    "narrative": "#475569",
    "partnership": "#0891b2",
    "other": "#be123c",
}
VERIFICATION_COLORS = {
    "human_verified": "#15803d",
    "ai_triaged": "#7c3aed",
    "needs_followup": "#d97706",
    "unreviewed": "#64748b",
    "rejected": "#b91c1c",
}


@dataclass(frozen=True)
class MapOptions:
    title: str = "SUGAR Research Activity Map"
    subtitle: str = "Public-source activity, evidence, and geographic overlap"
    heat_windows: tuple[int, ...] = (30, 90, 365)
    default_heat_window: int = 90
    max_popup_chars: int = 2200
    cluster_disable_at_zoom: int = 11
    show_minimap: bool = True
    show_measure_control: bool = True
    show_mouse_position: bool = True


def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.casefold() == "nan" else text


def _first(row: pd.Series, *names: str) -> str:
    for name in names:
        if name in row:
            value = _clean(row.get(name))
            if value:
                return value
    return ""


def _json_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        text = _clean(value)
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                items = parsed if isinstance(parsed, list) else [text]
            except (json.JSONDecodeError, TypeError):
                items = [text]
        else:
            items = [part.strip() for part in text.split(";") if part.strip()]
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _clean(item)
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _safe_url(value: Any) -> str:
    url = _clean(value)
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def _numeric(value: Any) -> float | None:
    if value is None:
        return None
    text = _clean(value).lstrip("'")
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _stable_color(label: str) -> str:
    digest = hashlib.sha256(label.casefold().encode("utf-8")).hexdigest()
    hue = int(digest[:6], 16) % 360
    return f"hsl({hue}, 62%, 43%)"


def detect_dataset_type(df: pd.DataFrame) -> str:
    columns = {str(column) for column in df.columns}
    if {"observation_id", "observation_type"} & columns:
        return "research_observations"
    return "source_records"


def load_map_frame(path: str | Path) -> pd.DataFrame:
    """Load either a source-record or research-observation dataset for mapping.

    Observation workbooks use an ``observations`` sheet while source-record workbooks use ``posts``.
    This loader makes the map agnostic to which SUGAR data product it receives.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".xlsx":
        workbook = pd.ExcelFile(path)
        for preferred in ("observations", "posts"):
            if preferred in workbook.sheet_names:
                return pd.read_excel(path, sheet_name=preferred)
        if workbook.sheet_names:
            return pd.read_excel(path, sheet_name=workbook.sheet_names[0])
        raise ValueError("Workbook contains no readable sheets.")
    raise ValueError("Map source must be CSV or XLSX.")


def _coordinates(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    for name in ("latitude", "longitude"):
        if name not in work:
            return work.iloc[0:0]
        work[name] = pd.to_numeric(
            work[name].astype("string").str.replace(r"^'", "", regex=True),
            errors="coerce",
        )
    work = work.dropna(subset=["latitude", "longitude"])
    return work[
        work["latitude"].between(-90, 90, inclusive="both")
        & work["longitude"].between(-180, 180, inclusive="both")
    ].copy()


def _normalize_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    work = _coordinates(df)
    dataset_type = detect_dataset_type(df)
    if work.empty:
        return work, dataset_type

    normalized: list[dict[str, Any]] = []
    for index, row in work.iterrows():
        if dataset_type == "research_observations":
            kind = _first(row, "observation_type") or "other"
            record_id = _first(row, "observation_id") or f"row-{index}"
            title = _first(row, "title") or _first(row, "institution_name", "program_name") or kind.replace("_", " ").title()
            summary = _first(row, "summary")
            date_value = _first(row, "observed_at")
            location = _first(row, "location_label")
            country = _first(row, "country")
            region = _first(row, "region")
            city = _first(row, "city")
            institution = _first(row, "institution_name")
            program = _first(row, "program_name")
            actors = _json_list(row.get("actors", ""))
            audiences = _json_list(row.get("audiences", ""))
            themes = _json_list(row.get("themes", ""))
            overlap = _json_list(row.get("us_overlap", ""))
            overlap_note = _first(row, "overlap_note")
            verification = _first(row, "verification_state") or "unreviewed"
            activity_status = _first(row, "activity_status") or "unknown"
            location_basis = _first(row, "location_basis") or "unknown"
            location_confidence = _numeric(row.get("location_confidence"))
            ai_confidence = _numeric(row.get("ai_confidence"))
            source_url = _safe_url(_first(row, "primary_source_url"))
            platform = ""
            source_mode = "research_observation"
            triage_labels = _json_list(row.get("triage_labels", ""))
        else:
            kind = _first(row, "content_type") or "post"
            platform = _first(row, "platform") or "source"
            native_id = _first(row, "native_id", "tweet_id")
            record_id = _first(row, "record_key") or (f"{platform}:{native_id}" if native_id else f"row-{index}")
            author = _first(row, "author_name", "display_name", "author_handle", "username")
            title = f"{platform.title()} {kind.replace('_', ' ')}"
            if author:
                title += f" — {author}"
            summary = _first(row, "translated_text", "translated_en", "original_text")
            date_value = _first(row, "published_at", "date_iso")
            location = _first(row, "inferred_location", "author_location")
            country = ""
            region = ""
            city = ""
            institution = ""
            program = ""
            actors = [author] if author else []
            audiences = []
            themes = []
            overlap = []
            overlap_note = ""
            verification = "source_record"
            activity_status = "unknown"
            location_basis = _first(row, "location_source") or ("ai_inferred" if _first(row, "inferred_location") else "unknown")
            location_confidence = _numeric(row.get("location_confidence"))
            ai_confidence = None
            source_url = _safe_url(_first(row, "canonical_url", "post_url", "source_url"))
            source_mode = _first(row, "source_mode")
            triage_labels = []

        normalized.append(
            {
                "_record_id": record_id,
                "_dataset_type": dataset_type,
                "_kind": kind.casefold(),
                "_platform": platform.casefold(),
                "_title": title,
                "_summary": summary,
                "_date_raw": date_value,
                "_location": location,
                "_country": country,
                "_region": region,
                "_city": city,
                "_institution": institution,
                "_program": program,
                "_actors": actors,
                "_audiences": audiences,
                "_themes": themes,
                "_us_overlap": overlap,
                "_overlap_note": overlap_note,
                "_verification": verification.casefold(),
                "_activity_status": activity_status.casefold(),
                "_location_basis": location_basis,
                "_location_confidence": location_confidence,
                "_ai_confidence": ai_confidence,
                "_source_url": source_url,
                "_source_mode": source_mode,
                "_triage_labels": triage_labels,
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
            }
        )

    result = pd.DataFrame(normalized)
    result["_date"] = pd.to_datetime(result["_date_raw"], errors="coerce", utc=True)
    return result, dataset_type


def _list_text(values: Iterable[str]) -> str:
    return ", ".join(_clean(value) for value in values if _clean(value))


def _popup_html(row: pd.Series, max_chars: int) -> str:
    def esc(value: Any) -> str:
        return html.escape(_clean(value), quote=True)

    summary = _clean(row.get("_summary"))
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1].rstrip() + "…"

    location_bits = [
        _clean(row.get("_city")),
        _clean(row.get("_region")),
        _clean(row.get("_country")),
    ]
    structured_location = ", ".join(part for part in location_bits if part)
    location = structured_location or _clean(row.get("_location"))
    kind = _clean(row.get("_kind")).replace("_", " ").title()
    verification = _clean(row.get("_verification")).replace("_", " ").title()
    observed = _clean(row.get("_date_raw"))
    institution = _clean(row.get("_institution"))
    program = _clean(row.get("_program"))
    actors = _list_text(row.get("_actors") or [])
    audiences = _list_text(row.get("_audiences") or [])
    themes = _list_text(row.get("_themes") or [])
    overlap = _list_text(row.get("_us_overlap") or [])
    overlap_note = _clean(row.get("_overlap_note"))
    location_basis = _clean(row.get("_location_basis"))
    loc_conf = row.get("_location_confidence")
    ai_conf = row.get("_ai_confidence")
    source_mode = _clean(row.get("_source_mode"))
    platform = _clean(row.get("_platform"))
    triage = _list_text(row.get("_triage_labels") or [])
    source_url = _safe_url(row.get("_source_url"))

    lines = [
        "<div class='sugar-popup'>",
        f"<div class='sugar-popup-title'>{esc(row.get('_title'))}</div>",
        f"<div class='sugar-popup-meta'><b>{esc(kind)}</b> · {esc(verification)}</div>",
    ]
    if location:
        lines.append(f"<div><b>Location:</b> {esc(location)}</div>")
    if observed:
        lines.append(f"<div><b>Observed:</b> {esc(observed)}</div>")
    if institution:
        lines.append(f"<div><b>Institution:</b> {esc(institution)}</div>")
    if program:
        lines.append(f"<div><b>Program:</b> {esc(program)}</div>")
    if actors:
        lines.append(f"<div><b>Actors:</b> {esc(actors)}</div>")
    if audiences:
        lines.append(f"<div><b>Audiences:</b> {esc(audiences)}</div>")
    if themes:
        lines.append(f"<div><b>Themes:</b> {esc(themes)}</div>")
    if triage:
        lines.append(f"<div><b>Triage labels:</b> {esc(triage)}</div>")
    if overlap or overlap_note:
        overlap_text = overlap or overlap_note
        lines.append(f"<div class='sugar-overlap'><b>U.S. overlap:</b> {esc(overlap_text)}</div>")
    if summary:
        lines.append(f"<div class='sugar-popup-summary'>{esc(summary)}</div>")
    provenance: list[str] = []
    if platform:
        provenance.append(f"platform {platform}")
    if source_mode:
        provenance.append(source_mode)
    if location_basis:
        provenance.append(f"location: {location_basis}")
    if loc_conf is not None:
        provenance.append(f"location confidence: {float(loc_conf):.2f}")
    if ai_conf is not None:
        provenance.append(f"AI confidence: {float(ai_conf):.2f}")
    if provenance:
        lines.append(f"<div class='sugar-popup-provenance'>{esc(' · '.join(provenance))}</div>")
    if source_url:
        safe_link = html.escape(source_url, quote=True)
        lines.append(f"<div><a href='{safe_link}' target='_blank' rel='noopener noreferrer'>Open source evidence ↗</a></div>")
    lines.append(f"<div class='sugar-popup-id'>{esc(row.get('_record_id'))}</div>")
    lines.append("</div>")
    return "".join(lines)


def _tooltip(row: pd.Series) -> str:
    title = _clean(row.get("_title")) or _clean(row.get("_record_id"))
    location = _clean(row.get("_location")) or _clean(row.get("_country"))
    return html.escape(f"{title} — {location}" if location else title, quote=True)


def _row_color(row: pd.Series, dataset_type: str) -> str:
    if dataset_type == "research_observations":
        return OBSERVATION_COLORS.get(_clean(row.get("_kind")), OBSERVATION_COLORS["other"])
    label = _clean(row.get("_platform")) or _clean(row.get("_kind")) or "source"
    return _stable_color(label)


def _heat_points(frame: pd.DataFrame, mask: pd.Series | None = None, weight_column: str | None = None) -> list[list[float]]:
    subset = frame if mask is None else frame.loc[mask]
    points: list[list[float]] = []
    for _, row in subset.iterrows():
        point = [float(row["latitude"]), float(row["longitude"])]
        if weight_column:
            weight = row.get(weight_column)
            if weight is None or pd.isna(weight):
                continue
            point.append(max(0.0, min(1.0, float(weight))))
        points.append(point)
    return points


def _summary_stats(frame: pd.DataFrame, dataset_type: str, source_rows: int) -> dict[str, Any]:
    dated = frame["_date"].dropna() if "_date" in frame else pd.Series(dtype="datetime64[ns, UTC]")
    return {
        "dataset_type": dataset_type,
        "source_rows": int(source_rows),
        "mapped_rows": int(len(frame)),
        "unmapped_rows": int(max(0, source_rows - len(frame))),
        "countries": int(frame["_country"].replace("", pd.NA).dropna().nunique()) if "_country" in frame else 0,
        "kinds": int(frame["_kind"].replace("", pd.NA).dropna().nunique()),
        "us_overlap_rows": int(frame["_us_overlap"].map(bool).sum() + frame["_overlap_note"].map(bool).sum()),
        "human_verified_rows": int(frame["_verification"].eq("human_verified").sum()),
        "earliest_date": dated.min().isoformat() if not dated.empty else "",
        "latest_date": dated.max().isoformat() if not dated.empty else "",
    }


def _panel_html(stats: dict[str, Any], title: str, subtitle: str) -> str:
    coverage = 100.0 * stats["mapped_rows"] / max(1, stats["source_rows"])
    dataset_label = "Research observations" if stats["dataset_type"] == "research_observations" else "Source records"
    rows = [
        f"<div><b>{stats['mapped_rows']:,}</b> mapped of {stats['source_rows']:,} rows ({coverage:.1f}%)</div>",
        f"<div><b>{stats['kinds']}</b> mapped record types</div>",
    ]
    if stats["countries"]:
        rows.append(f"<div><b>{stats['countries']}</b> countries represented</div>")
    if stats["human_verified_rows"]:
        rows.append(f"<div><b>{stats['human_verified_rows']}</b> human-verified observations</div>")
    if stats["us_overlap_rows"]:
        rows.append(f"<div><b>{stats['us_overlap_rows']}</b> records tagged for U.S. overlap</div>")
    return f"""
    <div id="sugar-map-panel" class="sugar-map-panel">
      <div class="sugar-panel-title">{html.escape(title)}</div>
      <div class="sugar-panel-subtitle">{html.escape(subtitle)}</div>
      <div class="sugar-panel-type">{html.escape(dataset_label)}</div>
      {''.join(rows)}
      <div class="sugar-panel-note">Heat intensity represents mapped record density, not influence, sentiment, audience size, or causal effect.</div>
    </div>
    """


def _legend_html(frame: pd.DataFrame, dataset_type: str) -> str:
    labels = sorted(value for value in frame["_kind"].dropna().unique() if _clean(value))
    items: list[str] = []
    for label in labels[:12]:
        if dataset_type == "research_observations":
            color = OBSERVATION_COLORS.get(label, OBSERVATION_COLORS["other"])
        else:
            color = _stable_color(label)
        items.append(
            f"<div class='sugar-legend-row'><span class='sugar-dot' style='background:{color}'></span>{html.escape(label.replace('_', ' ').title())}</div>"
        )
    return "<div class='sugar-legend'><b>Record types</b>" + "".join(items) + "</div>"


def _style_html() -> str:
    return """
    <style>
      .sugar-map-panel, .sugar-legend {
        position: fixed; z-index: 9999; background: rgba(255,255,255,.95);
        border: 1px solid #cbd5e1; border-radius: 8px; box-shadow: 0 2px 12px rgba(15,23,42,.16);
        font: 12px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color: #0f172a;
      }
      .sugar-map-panel { top: 12px; right: 12px; width: 285px; padding: 12px 14px; }
      .sugar-legend { bottom: 28px; left: 12px; padding: 9px 11px; max-height: 260px; overflow-y: auto; }
      .sugar-panel-title { font-weight: 700; font-size: 16px; margin-bottom: 2px; }
      .sugar-panel-subtitle { color: #475569; margin-bottom: 7px; }
      .sugar-panel-type { font-weight: 600; margin-bottom: 5px; }
      .sugar-panel-note { color: #64748b; border-top: 1px solid #e2e8f0; margin-top: 7px; padding-top: 7px; }
      .sugar-legend-row { white-space: nowrap; margin-top: 4px; }
      .sugar-dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; border:1px solid rgba(15,23,42,.35); }
      .sugar-popup { min-width: 275px; max-width: 430px; font: 12px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
      .sugar-popup-title { font-size: 15px; font-weight: 700; margin-bottom: 2px; }
      .sugar-popup-meta { color: #475569; margin-bottom: 7px; }
      .sugar-popup-summary { border-top: 1px solid #e2e8f0; margin-top: 7px; padding-top: 7px; }
      .sugar-popup-provenance { color: #64748b; margin-top: 7px; font-size: 11px; }
      .sugar-popup-id { color: #94a3b8; font-size: 10px; margin-top: 5px; word-break: break-all; }
      .sugar-overlap { color: #9f1239; }
      @media (max-width: 700px) {
        .sugar-map-panel { width: 220px; max-height: 190px; overflow-y:auto; }
        .sugar-legend { display:none; }
      }
    </style>
    """


def create_map(
    df: pd.DataFrame,
    output_file: str | Path,
    *,
    options: MapOptions | None = None,
) -> str:
    """Create an analyst-oriented interactive map from SUGAR source or observation data.

    The map deliberately separates record density from claims about influence. It is designed to
    remain useful as the Diplomacy Lab dataset evolves from raw social records toward verified
    institutions, programs, events, narratives, partnerships, and U.S.-overlap observations.
    """
    import folium
    from folium.plugins import Fullscreen, HeatMap, MarkerCluster, MeasureControl, MiniMap, MousePosition

    options = options or MapOptions()
    work, dataset_type = _normalize_rows(df)
    if work.empty:
        raise ValueError("No valid coordinates are available to map.")

    center = [float(work["latitude"].median()), float(work["longitude"].median())]
    m = folium.Map(
        location=center,
        zoom_start=2,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
        world_copy_jump=True,
    )
    folium.TileLayer("CartoDB positron", name="Light basemap", control=True, show=True).add_to(m)
    folium.TileLayer("OpenStreetMap", name="Street basemap", control=True, show=False).add_to(m)
    folium.TileLayer("CartoDB dark_matter", name="Dark basemap", control=True, show=False).add_to(m)

    all_cluster = MarkerCluster(
        name=f"All mapped records ({len(work):,})",
        overlay=True,
        control=True,
        show=True,
        options={"disableClusteringAtZoom": options.cluster_disable_at_zoom, "spiderfyOnMaxZoom": True},
    ).add_to(m)

    for _, row in work.iterrows():
        color = _row_color(row, dataset_type)
        popup = folium.Popup(_popup_html(row, options.max_popup_chars), max_width=470)
        folium.CircleMarker(
            [float(row["latitude"]), float(row["longitude"])],
            radius=6,
            color=color,
            weight=1.5,
            fill=True,
            fill_color=color,
            fill_opacity=0.78,
            popup=popup,
            tooltip=_tooltip(row),
        ).add_to(all_cluster)

    # Type/platform layers let analysts isolate a category without requiring a custom web app.
    for kind in sorted(value for value in work["_kind"].dropna().unique() if _clean(value)):
        subset = work[work["_kind"].eq(kind)]
        group = folium.FeatureGroup(
            name=f"Type — {kind.replace('_', ' ').title()} ({len(subset):,})",
            overlay=True,
            show=False,
        ).add_to(m)
        for _, row in subset.iterrows():
            color = _row_color(row, dataset_type)
            folium.CircleMarker(
                [float(row["latitude"]), float(row["longitude"])],
                radius=7,
                color=color,
                weight=2,
                fill=True,
                fill_color=color,
                fill_opacity=0.68,
                popup=folium.Popup(_popup_html(row, options.max_popup_chars), max_width=470),
                tooltip=_tooltip(row),
            ).add_to(group)

    # Review/quality layers are intentionally explicit rather than folded into one opaque score.
    if dataset_type == "research_observations":
        for state in ("human_verified", "ai_triaged", "needs_followup", "unreviewed"):
            subset = work[work["_verification"].eq(state)]
            if subset.empty:
                continue
            group = folium.FeatureGroup(
                name=f"Verification — {state.replace('_', ' ').title()} ({len(subset):,})",
                overlay=True,
                show=False,
            ).add_to(m)
            color = VERIFICATION_COLORS.get(state, "#64748b")
            for _, row in subset.iterrows():
                folium.CircleMarker(
                    [float(row["latitude"]), float(row["longitude"])],
                    radius=8,
                    color=color,
                    weight=2.5,
                    fill=False,
                    popup=folium.Popup(_popup_html(row, options.max_popup_chars), max_width=470),
                    tooltip=_tooltip(row),
                ).add_to(group)

    overlap_mask = work["_us_overlap"].map(bool) | work["_overlap_note"].map(bool)
    if overlap_mask.any():
        overlap_rows = work.loc[overlap_mask]
        overlap_group = folium.FeatureGroup(
            name=f"U.S. overlap tagged ({len(overlap_rows):,})",
            overlay=True,
            show=False,
        ).add_to(m)
        for _, row in overlap_rows.iterrows():
            folium.CircleMarker(
                [float(row["latitude"]), float(row["longitude"])],
                radius=10,
                color="#be123c",
                weight=3,
                fill=False,
                popup=folium.Popup(_popup_html(row, options.max_popup_chars), max_width=470),
                tooltip=_tooltip(row),
            ).add_to(overlap_group)

    # Heat layers remain descriptive density views; none are labeled as influence.
    all_points = _heat_points(work)
    all_heat = folium.FeatureGroup(name="Density — all mapped records", overlay=True, show=False)
    HeatMap(all_points, radius=24, blur=18, min_opacity=0.25).add_to(all_heat)
    all_heat.add_to(m)

    now = pd.Timestamp.now(tz="UTC")
    if work["_date"].notna().any():
        for days in options.heat_windows:
            mask = work["_date"].ge(now - pd.Timedelta(days=days)) & work["_date"].le(now)
            points = _heat_points(work, mask)
            if not points:
                continue
            layer = folium.FeatureGroup(
                name=f"Density — activity in last {days}d ({int(mask.sum()):,})",
                overlay=True,
                show=(days == options.default_heat_window),
            )
            HeatMap(points, radius=25, blur=19, min_opacity=0.24).add_to(layer)
            layer.add_to(m)

    if overlap_mask.any():
        points = _heat_points(work, overlap_mask)
        layer = folium.FeatureGroup(name="Density — U.S. overlap tagged", overlay=True, show=False)
        HeatMap(points, radius=28, blur=20, min_opacity=0.25).add_to(layer)
        layer.add_to(m)

    verified_mask = work["_verification"].eq("human_verified")
    if verified_mask.any():
        points = _heat_points(work, verified_mask)
        layer = folium.FeatureGroup(name="Density — human-verified only", overlay=True, show=False)
        HeatMap(points, radius=26, blur=18, min_opacity=0.25).add_to(layer)
        layer.add_to(m)

    confidence_mask = work["_location_confidence"].notna()
    if confidence_mask.any():
        points = _heat_points(work, confidence_mask, "_location_confidence")
        if points:
            layer = folium.FeatureGroup(
                name="Density — location-confidence weighted",
                overlay=True,
                show=False,
            )
            HeatMap(points, radius=25, blur=18, min_opacity=0.2).add_to(layer)
            layer.add_to(m)

    Fullscreen(position="topleft", title="Fullscreen", title_cancel="Exit fullscreen").add_to(m)
    if options.show_minimap:
        MiniMap(toggle_display=True, minimized=True).add_to(m)
    if options.show_measure_control:
        MeasureControl(position="topleft", primary_length_unit="kilometers").add_to(m)
    if options.show_mouse_position:
        MousePosition(position="bottomright", separator=" · ", prefix="Lat/Lon:").add_to(m)

    if len(work) == 1:
        m.location = [float(work.iloc[0]["latitude"]), float(work.iloc[0]["longitude"])]
        m.options["zoom"] = 7
    else:
        bounds = [
            [float(work["latitude"].min()), float(work["longitude"].min())],
            [float(work["latitude"].max()), float(work["longitude"].max())],
        ]
        m.fit_bounds(bounds, padding=(28, 28))

    stats = _summary_stats(work, dataset_type, len(df))
    m.get_root().html.add_child(folium.Element(_style_html()))
    m.get_root().html.add_child(folium.Element(_panel_html(stats, options.title, options.subtitle)))
    m.get_root().html.add_child(folium.Element(_legend_html(work, dataset_type)))
    folium.LayerControl(collapsed=False, position="topright").add_to(m)

    output_file = str(Path(output_file).expanduser().resolve())
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    m.save(output_file)
    return output_file
