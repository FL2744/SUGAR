# SUGAR research map

The research map is an interactive analytical surface for SUGAR datasets. It can consume either raw source-record exports (`posts` CSV/XLSX) or the richer `ResearchObservation` dataset (`observations` CSV/XLSX).

The map is intentionally designed around the Diplomacy Lab workflow rather than around a generic social-media heatmap. It should help an analyst distinguish what is present, what kind of activity it is, how recent it is, how strong the geographic evidence is, whether the record has been reviewed, where a record has been explicitly tagged for U.S. overlap, and where reproducible reference-network proximity has been computed.

## Analytical layers

Primary records are clustered once by their most useful filtering dimension: observation type for `ResearchObservation` data and platform for raw source records. Additional switchable layers provide:

- observation-type views for institutions, programs, events, digital posts, narratives, partnerships, and other observations
- platform views for raw source records such as Weibo, Bilibili, X, Bluesky, and Mastodon
- human-verified, AI-triaged, needs-followup, and unreviewed observation layers
- a separate rejected-observation layer for auditability
- records explicitly tagged for U.S. overlap
- a computed-proximity layer connecting each enriched observation to its nearest stored reference point with a dashed line
- all-record analytical density
- rolling activity-density windows (30/90/365 days by default)
- U.S.-overlap density
- human-verified-only density
- location-confidence-weighted density where explicit confidence values exist
- a distinct-institutions/programs footprint layer that reduces distortion from many records produced by one entity

Rejected observations remain inspectable but are excluded from the normal analytical marker groups and from every density layer.

The heat layers represent **mapped record density only**. They must not be interpreted as influence, sentiment, audience size, persuasion, institutional strength, or causal effect. A location with many collected records can appear hotter than a location with fewer records even when the latter is strategically more important.

Computed proximity is also deliberately narrow: a dashed relationship line means SUGAR calculated the displayed geographic distance to the nearest stored reference point. It does **not** mean the two entities compete, coordinate, target the same audience, or influence one another. Human-reviewed strategic overlap remains in the separate `us_overlap`/`overlap_note` fields.

## Reference overlays

The map can load one or more external reference datasets independently of the SUGAR research observations. This is intended for Team 4 products such as American Spaces, EducationUSA centers, or other comparison networks.

Reference CSV/XLSX files require `latitude` and `longitude`. They can additionally provide common fields such as:

- `name` or `title`
- `category`, `type`, or `space_type`
- `city`, `country`, or `location_label`
- `summary`, `description`, `note`, or `notes`
- `url`, `source_url`, `primary_source_url`, or `website`

Reference records receive their own cluster, legend entry, popup style, source link, and map-bounds contribution. They are **not** mixed into PRC activity heat density merely because they appear on the same map.

When an observation has schema 1.1 `spatial_matches`, the map can also render its nearest computed reference relationship even when the reference dataset is not separately loaded for display. Loading the corresponding reference layer remains preferable because it provides richer reference popups and context.

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
- explicit analyst-reviewed U.S.-overlap tags/notes
- nearest computed reference proximity, distance band, and same-city/same-country flags
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
- generic reference CSV/XLSX files supplied as reference layers

Coordinate values are coerced numerically and must fall inside valid latitude/longitude bounds. Rows without valid coordinates are excluded from the map and counted as unmapped in the map summary panel.

Schema 1.1 research observations may contain JSON-serialized `spatial_matches`. Those are parsed and sorted by distance before popup or relationship rendering.

## Map controls

Generated maps include:

- standard OpenStreetMap and Humanitarian OpenStreetMap basemaps, with no map-provider API key required
- marker clustering
- layer control
- automatic bounds fitting across analytical records, external references, and stored proximity endpoints
- fullscreen mode
- minimap
- distance/area measurement
- live cursor latitude/longitude
- a compact dataset/coverage summary
- an observation-type or source-platform legend

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
    "show_mouse_position": true,
    "reference_layers": [
      {
        "name": "American Spaces",
        "file": "american_spaces.csv",
        "show": true
      },
      {
        "name": "EducationUSA",
        "file": "educationusa.xlsx",
        "show": true
      }
    ]
  }
}
```

Reference layers may also be supplied as plain file paths if custom names or visibility are unnecessary. Defaults remain suitable for ordinary use, so existing map calls do not need configuration changes.

For reproducible proximity analysis before mapping, use `sugar overlap` or `run_overlap()`; see `docs/spatial-overlap.md`.

## Future extensions

The architecture intentionally leaves room for later project-level features without requiring another rewrite of the mapper:

- evidence-supported institution/program relationship networks beyond simple proximity
- country-level aggregation and comparison
- explicit collection-coverage diagnostics
- longitudinal event playback
- analyst-defined saved views
- audience/reach layers based on verified metrics
- master-dataset joins instead of single-file input

Those features should remain analytically separated from the descriptive density and computed-proximity layers rather than being collapsed into one opaque "influence score."