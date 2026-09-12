# SUGAR spatial overlap analysis

SUGAR's spatial overlap workflow computes reproducible geographic proximity between geocoded research observations and one or more external reference networks, such as American Spaces or EducationUSA locations.

The central methodological rule is simple: **proximity is a computed geographic fact, not a finding of influence, competition, coordination, displacement, exposure, or causation.** SUGAR therefore stores computed proximity separately from the analyst-controlled `us_overlap` field.

## Why this exists

A visual map can make two nearby markers look meaningfully related even when the relationship is only apparent. The spatial workflow makes that comparison explicit and auditable by calculating distances with one documented method, retaining the underlying pair matches, and recording which observations were unmapped or excluded.

This supports questions such as:

- Which PRC-linked observations are physically near an American Space or EducationUSA location?
- How many observations fall within 5 km, 25 km, 100 km, or 250 km of a reference network?
- What is the nearest reference point to each observation?
- Is the nearest point in the same city or country?
- Which apparent map overlaps disappear when distance is calculated consistently?

It does **not** answer whether two institutions target the same audience, compete for the same participants, coordinate programming, or exert measurable influence. Those require additional evidence.

## Calculation

Distances use the haversine great-circle formula with the IUGG mean Earth radius of 6,371.0088 km. This produces deterministic straight-line surface distance between latitude/longitude coordinates and avoids requiring a GIS database or paid routing service.

Default distance bands are:

- 0–5 km
- 5–25 km
- 25–100 km
- 100–250 km

The upper boundary is inclusive. Bands and the maximum retained distance are configurable.

Same-city and same-country flags are also descriptive fields. They are set only when both the observation and reference point provide matching non-empty normalized city/country strings.

## Observation schema 1.1

`ResearchObservation` adds `spatial_matches`, a list of structured derived matches. Each match records:

- reference layer
- stable reference ID
- reference name and category
- distance in km
- distance band
- same-city and same-country flags
- reference coordinates
- reference source URL when available

Only the nearest configurable number of matches are embedded in each observation to keep the master dataset portable. The separate match table preserves **every** observation/reference pair inside the configured maximum radius.

The existing `us_overlap` and `overlap_note` fields are not changed by the spatial engine. Those remain analyst judgments.

## Command line

```bash
sugar overlap observations.xlsx \
  --reference "American Spaces=american_spaces.csv" \
  --reference "EducationUSA=educationusa.xlsx" \
  --bands 5,25,100,250 \
  --max-distance 250 \
  --top-k 5 \
  --map
```

`--reference` can be repeated. If the `Layer name=` prefix is omitted, SUGAR derives a display name from the filename.

Rejected observations are excluded by default. `--include-rejected` is available for audit work but should not normally be used for analytical summaries.

## Outputs

For an input named `observations.csv`, a typical spatial run produces:

- `observations_spatial.csv` — enriched observation master data
- `observations_spatial.xlsx` — same data in workbook form
- `observations_spatial.metadata.json` — observation export metadata including the spatial summary
- `observations_spatial_matches.csv` — complete retained observation/reference pair table
- `observations_spatial_matches.xlsx` — pair table in workbook form
- `observations_spatial_summary.json` — compact audit/coverage summary
- `observations_spatial_map.html` — optional map when `--map` is requested

The summary reports total/analyzed/matched/unmapped observations, rejected records skipped, reference counts by layer, retained pair count, configured bands/radius, nearest-distance band counts, and median nearest-reference distance.

## Reference dataset requirements

A reference file must be CSV or XLSX and must contain valid `latitude` and `longitude` columns. SUGAR accepts common identity fields including `id`, `reference_id`, `observation_id`, or `native_id`, and common name/category/location/source fields such as:

```text
id,name,category,city,country,latitude,longitude,url
```

Rows without valid coordinates are ignored. Duplicate reference rows with the same normalized reference ID and coordinates are removed before analysis.

## Analytical interpretation

A useful workflow is:

1. Compute spatial proximity.
2. Inspect the full match table and unmapped coverage.
3. Use proximity to prioritize human review, not to generate a conclusion.
4. Compare program type, audience, date, institution, narrative, and verified reach.
5. Record true strategic overlap separately in `us_overlap` only when the evidence supports it.

For example, a Confucius Institute program 2 km from an American Space is a valid **geographic proximity** finding. It becomes a stronger overlap finding only if evidence shows shared audiences, similar programming, temporal competition, deliberate targeting, participant crossover, or another substantive relationship.

## Reproducibility and limits

The engine requires no external geospatial API and makes no network calls. Results are deterministic for the same coordinates, configuration, and reference data.

Straight-line distance does not represent travel time, transportation access, administrative boundaries, online reach, participant catchment areas, or cultural/geographic barriers. Coordinate quality remains important: a city-centroid coordinate should not be interpreted with the same precision as a source-stated street location. Analysts should consider `location_basis` and `location_confidence` alongside distance.
