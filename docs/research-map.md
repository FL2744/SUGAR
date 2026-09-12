# SUGAR research map

The research map is an interactive analytical surface for SUGAR datasets. It can consume either raw source-record exports (`posts` CSV/XLSX) or the richer `ResearchObservation` dataset (`observations` CSV/XLSX).

The map is intentionally designed around the Diplomacy Lab workflow rather than around a generic social-media heatmap. It should help an analyst distinguish what is present, what kind of activity it is, how recent it is, how strong the geographic evidence is, whether the record has been reviewed, and where a record has been explicitly tagged for U.S. overlap.

## Analytical layers

The default clustered marker layer shows all mappable records. Additional switchable layers provide:

- observation-type views for institutions, programs, events, digital posts, narratives, partnerships, and other observations
- platform/source views when mapping raw source records
- human-verified, AI-triaged, needs-followup, and unreviewed observation layers
- records explicitly tagged for U.S. overlap
- all-record density
- rolling activity-density windows (30/90/365 days by default)
- U.S.-overlap density
- human-verified-only density
- location-confidence-weighted density where explicit confidence values exist

The heat layers represent **mapped record density only**. They must not be interpreted as influence, sentiment, audience size, persuasion, institutional strength, or causal effect. A location with many collected records can appear hotter than a location with fewer records even when the latter is strategically more important.

## Popups and provenance

Observation popups can show:

- observation type and verification state
- structured location
- observation date
- institution and program
- actors
- target audiences
- themes
- triage labels
- explicit U.S.-overlap tags/notes
- summary text
- location basis and location confidence
- AI confidence when present
- source evidence link
- stable observation/record identity

Source-record popups preserve the relevant social-platform/source mode so analysts can distinguish how the item entered SUGAR.

All popup text is HTML-escaped. Evidence links are emitted only for valid `http` or `https` URLs; unsafe URL schemes are not rendered as links.

## Data compatibility

`load_map_frame()` automatically recognizes:

- CSV exports
- SUGAR source-record workbooks using the `posts` sheet
- SUGAR research-observation workbooks using the `observations` sheet

Coordinate values are coerced numerically and must fall inside valid latitude/longitude bounds. Rows without valid coordinates are excluded from the map and counted as unmapped in the map summary panel.

## Map controls

Generated maps include:

- light, street, and dark basemaps
- marker clustering
- layer control
- automatic bounds fitting
- fullscreen mode
- minimap
- distance/area measurement
- live cursor latitude/longitude
- a compact dataset/coverage summary
- a record-type legend

## Configuration

`run_map()` accepts optional settings under a `map` object:

```json
{
  "source_file": "observations.xlsx",
  "output_file": "research_map.html",
  "map": {
    "title": "American Spaces / PRC Activity",
    "subtitle": "Public-source activity and overlap",
    "heat_windows": [30, 90, 180, 365],
    "default_heat_window": 90,
    "max_popup_chars": 2200,
    "cluster_disable_at_zoom": 11,
    "show_minimap": true,
    "show_measure_control": true,
    "show_mouse_position": true
  }
}
```

Defaults remain suitable for ordinary use, so existing map calls do not need configuration changes.

## Future extensions

The architecture intentionally leaves room for later project-level features without requiring another rewrite of the mapper:

- dedicated American Spaces and EducationUSA reference layers
- institution/program relationship lines
- country-level aggregation and comparison
- explicit collection-coverage diagnostics
- longitudinal event playback
- analyst-defined saved views
- audience/reach layers based on verified metrics
- master-dataset joins instead of single-file input

Those features should remain analytically separated from the descriptive density layers rather than being collapsed into one opaque "influence score."