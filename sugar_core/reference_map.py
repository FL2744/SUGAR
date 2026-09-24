from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, Iterable

import folium

from .research_workspace import ENTITY_LIFECYCLE_STATUSES


_NAME_FIELDS = ("canonical_name", "name", "institution", "title", "site_name")
_LAT_FIELDS = ("latitude", "lat", "y")
_LON_FIELDS = ("longitude", "lon", "lng", "x")
_STATUS_FIELDS = ("lifecycle_status", "status", "state")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _first(row: dict[str, Any], candidates: Iterable[str]) -> Any:
    normalized = {str(key).casefold(): value for key, value in row.items()}
    for candidate in candidates:
        value = normalized.get(candidate.casefold())
        if value not in (None, ""):
            return value
    return ""


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


@dataclass
class ReferenceFeature:
    name: str
    latitude: float
    longitude: float
    status: str = "unknown"
    feature_id: str = ""
    layer_name: str = ""
    description: str = ""
    source_refs: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = _clean(self.name) or "Unnamed site"
        self.status = _clean(self.status).casefold() or "unknown"
        if self.status not in ENTITY_LIFECYCLE_STATUSES:
            self.status = "unknown"
        if not -90 <= float(self.latitude) <= 90:
            raise ValueError("Reference feature latitude must be between -90 and 90.")
        if not -180 <= float(self.longitude) <= 180:
            raise ValueError("Reference feature longitude must be between -180 and 180.")
        self.latitude = float(self.latitude)
        self.longitude = float(self.longitude)


def _rows_from_file(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))
    if suffix in {".json", ".geojson"}:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
            rows = []
            for item in payload.get("features") or []:
                if not isinstance(item, dict):
                    continue
                props = dict(item.get("properties") or {})
                geometry = item.get("geometry") or {}
                if geometry.get("type") == "Point":
                    coords = geometry.get("coordinates") or []
                    if len(coords) >= 2:
                        props.setdefault("longitude", coords[0])
                        props.setdefault("latitude", coords[1])
                rows.append(props)
            return rows
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            return [payload]
        raise ValueError("Reference JSON must be an object, array, or GeoJSON FeatureCollection.")
    if suffix == ".jsonl":
        rows = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"Reference JSONL line {line_number} must be an object.")
            rows.append(payload)
        return rows
    if suffix in {".xlsx", ".xls"}:
        import pandas as pd
        frame = pd.read_excel(path)
        return frame.where(frame.notna(), "").to_dict(orient="records")
    raise ValueError("Reference layers must be CSV, XLSX/XLS, JSON, JSONL, or GeoJSON.")


def load_reference_features(
    path: str | Path,
    *,
    layer_name: str = "",
    field_mapping: dict[str, str] | None = None,
) -> list[ReferenceFeature]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    mapping = {str(k): str(v) for k, v in (field_mapping or {}).items()}
    features: list[ReferenceFeature] = []
    for row in _rows_from_file(source):
        name = row.get(mapping.get("name", "")) if mapping.get("name") else _first(row, _NAME_FIELDS)
        lat = row.get(mapping.get("latitude", "")) if mapping.get("latitude") else _first(row, _LAT_FIELDS)
        lon = row.get(mapping.get("longitude", "")) if mapping.get("longitude") else _first(row, _LON_FIELDS)
        latitude = _float(lat)
        longitude = _float(lon)
        if latitude is None or longitude is None:
            continue
        status = row.get(mapping.get("status", "")) if mapping.get("status") else _first(row, _STATUS_FIELDS)
        source_value = row.get(mapping.get("source_refs", "")) if mapping.get("source_refs") else row.get("source_refs", "")
        if isinstance(source_value, list):
            source_refs = [_clean(item) for item in source_value if _clean(item)]
        else:
            source_refs = [_clean(item) for item in str(source_value or "").replace("|", ";").split(";") if _clean(item)]
        features.append(
            ReferenceFeature(
                name=_clean(name),
                latitude=latitude,
                longitude=longitude,
                status=_clean(status) or "unknown",
                feature_id=_clean(row.get("entity_id") or row.get("id")),
                layer_name=_clean(layer_name) or source.stem,
                description=_clean(row.get("description") or row.get("notes")),
                source_refs=source_refs,
                properties=dict(row),
            )
        )
    return features


def _marker_html(feature: ReferenceFeature, *, closed_symbol: str = "☠") -> str:
    if feature.status == "closed":
        return (
            '<div style="font-size:22px;line-height:22px;'
            'filter:grayscale(1);text-shadow:0 1px 2px white;">'
            f'{escape(closed_symbol)}</div>'
        )
    symbol = {
        "active": "●",
        "renamed": "◆",
        "relocated": "↪",
        "planned": "◇",
        "unknown": "○",
    }.get(feature.status, "○")
    return (
        '<div style="font-size:20px;line-height:20px;color:#245ea8;'
        'text-shadow:0 1px 2px white;">'
        f'{escape(symbol)}</div>'
    )


def _popup(feature: ReferenceFeature) -> str:
    parts = [
        f"<b>{escape(feature.name)}</b>",
        f"Status: {escape(feature.status.title())}",
    ]
    if feature.description:
        parts.append(escape(feature.description))
    if feature.source_refs:
        links = []
        for ref in feature.source_refs:
            safe = escape(ref, quote=True)
            if ref.startswith(("http://", "https://")):
                links.append(f'<a href="{safe}" target="_blank" rel="noopener noreferrer">source</a>')
            else:
                links.append(safe)
        parts.append("Sources: " + ", ".join(links))
    return "<br>".join(parts)


def create_reference_workspace_map(
    layers: Iterable[tuple[str, str | Path, dict[str, str] | None]],
    output_file: str | Path,
    *,
    title: str = "SUGAR Reference Workspace",
    closed_symbol: str = "☠",
) -> str:
    loaded: list[tuple[str, list[ReferenceFeature]]] = []
    all_features: list[ReferenceFeature] = []
    for name, path, mapping in layers:
        features = load_reference_features(path, layer_name=name, field_mapping=mapping)
        loaded.append((name, features))
        all_features.extend(features)

    center = [20.0, 0.0]
    zoom = 2
    if all_features:
        center = [
            sum(item.latitude for item in all_features) / len(all_features),
            sum(item.longitude for item in all_features) / len(all_features),
        ]
        zoom = 4 if len(all_features) < 30 else 2

    research_map = folium.Map(location=center, zoom_start=zoom, control_scale=True, tiles="OpenStreetMap")
    title_html = f'<h3 style="position:fixed;top:10px;left:55px;z-index:9999;background:white;padding:6px 10px;border:1px solid #bbb;">{escape(title)}</h3>'
    research_map.get_root().html.add_child(folium.Element(title_html))

    for layer_name, features in loaded:
        group = folium.FeatureGroup(name=layer_name, show=True)
        for feature in features:
            icon = folium.DivIcon(html=_marker_html(feature, closed_symbol=closed_symbol))
            folium.Marker(
                location=[feature.latitude, feature.longitude],
                tooltip=f"{feature.name} — {feature.status}",
                popup=folium.Popup(_popup(feature), max_width=420),
                icon=icon,
            ).add_to(group)
        group.add_to(research_map)

    folium.LayerControl(collapsed=False).add_to(research_map)
    target = Path(output_file).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    research_map.save(str(target))

    metadata = {
        "schema_version": "1.0",
        "title": title,
        "feature_count": len(all_features),
        "layers": [
            {
                "name": name,
                "feature_count": len(features),
                "status_counts": {
                    status: sum(1 for feature in features if feature.status == status)
                    for status in sorted({feature.status for feature in features})
                },
            }
            for name, features in loaded
        ],
        "closed_symbol": closed_symbol,
        "semantics": {
            "closed": "Historical/closed institution retained as a reference feature; closure does not imply absence of residual activity.",
            "map_points": "Reference-location points are descriptive and do not themselves establish influence, coordination, or causality.",
        },
    }
    target.with_suffix(target.suffix + ".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(target)
