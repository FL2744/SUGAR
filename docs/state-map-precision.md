# State map geographic precision

SUGAR's State research map treats geographic location as an evidence claim. A latitude/longitude pair is not automatically an exact event location, and a successful geocoder response is not automatically a site-level match.

The precision-aware resolver exists to make the map more useful without making it look more certain than the underlying research supports.

## Precision tiers

Every mapped observation is assigned one of these tiers:

| Tier | Meaning | Typical use |
| --- | --- | --- |
| `exact` | Native/exact coordinates are explicitly supported by the record | Native geotag or explicitly reviewed coordinates |
| `site` | A venue, campus, facility, or address-level location is supported | Named event venue or institution site |
| `locality` | Sub-city locality/neighborhood precision | District, neighborhood, borough, locality |
| `city` | City-level location only | Report says an activity occurred in Bishkek but not where |
| `region` | Province/state/oblast-level location only | Activity known only at the regional level |
| `country` | Country-level evidence only | Existing recorded coordinate with country-level basis; never density-eligible |
| `unknown` | Coordinate exists but its precision cannot be responsibly classified | Legacy/unclassified records |

The map exposes the tier in the layer name, marker popup, legend, and metadata sidecar.

## Resolution order

When an eligible observation already has both latitude and longitude, SUGAR keeps those coordinates but classifies their precision from `location_basis`, `location_label`, city/region/country fields, and location confidence. Existing coordinates are not silently upgraded to site-level precision.

When coordinates are missing and location resolution is enabled, SUGAR tries defensible public queries in descending precision:

1. an explicit `location_label` only when `location_basis` itself says the location is a venue/site/address/campus or similarly precise feature;
2. city + region + country;
3. region + country.

SUGAR does **not** use an institution name as an event venue merely because that institution appears in the observation. An organization may sponsor or participate in an event somewhere else.

Country-only observations are deliberately left unresolved rather than plotted at a national centroid. A dot at the middle of a country would look locally precise while encoding no local knowledge.

## Geocoder result validation

The resolver preserves the public geocoder's returned feature metadata and bounding box. The requested query precision and the returned feature precision are compared conservatively.

For example:

- a venue query that resolves to a building remains site-level;
- a venue query that resolves only to a city is downgraded to city-level;
- a city query that resolves only to a region is downgraded to region-level;
- a site/city/region query that resolves only to a country is rejected rather than plotted.

Unknown provider feature types do not automatically upgrade precision.

Geocoder results are cached so repeated map generation is deterministic with respect to prior successful lookups and does not needlessly repeat public-service requests.

## Uncertainty envelopes

A centroid is not an exact venue. City-, locality-, and region-level points can therefore be displayed with a translucent uncertainty envelope. When the geocoder provides a bounding box, SUGAR derives an approximate radius from that extent; otherwise it uses a conservative tier-specific default.

The exact uncertainty footprint is an aid to interpretation, not a statistical confidence interval.

## Density layer

The optional density layer is deliberately stricter than the marker layer. An observation is density-eligible only when:

- its resolved precision is `exact`, `site`, `locality`, or `city`; and
- its location confidence meets the configured threshold.

Region, country, unknown, and low-confidence points do not contribute to density. This prevents several broad or uncertain centroids from manufacturing a visually persuasive hotspot.

All retained observations receive equal weight. Likes, views, attendance, followers, and other heterogeneous reach metrics are not converted into an influence score.

## Uncertainty-aware U.S. proximity

A single center-to-center distance can overstate what the research actually knows. An observation localized only to a city may have a centroid 45 km from an American Space, for example, while the plausible activity location extends to either side of a 50 km analytic reference threshold.

For every mapped observation with at least one active, geocoded U.S. public-diplomacy site, SUGAR therefore computes:

- the physically nearest mapped U.S. site, regardless of national border;
- the center-to-center distance;
- a conservative minimum and maximum separation using the observation's precision envelope plus a small default site-location envelope;
- whether the entire range is within the 50 km reference threshold, the range intersects the threshold, or the entire range is outside it;
- same-city and same-country flags as descriptive context rather than ranking constraints.

The physically nearest site is used instead of a same-country-first rule because border geography can make a site in a neighboring country much closer than one elsewhere in the observation's country.

Two optional map layers visualize only the cases that are fully within the threshold or whose uncertainty range intersects it. They are hidden by default to avoid clutter. Solid lines represent ranges fully within the reference threshold; dashed lines represent threshold-intersecting uncertainty. Outside-threshold cases remain in the metadata ledger but are not connected on the map.

These ranges are **not statistical confidence intervals**. They are conservative interpretation aids derived from map precision. Likewise, proximity to an American Space, EducationUSA site, embassy, or other U.S. presence is not itself evidence of competition, displacement, coordination, persuasion, or influence.

## CLI use

Strict mode uses only coordinates already present in the observation dataset:

```bash
sugar-state map observations.csv assessments.jsonl
```

Inside a SUGAR project, the output automatically goes to `outputs/maps` and is registered in the project workspace.

To resolve missing site/city/region locations through the cached public geocoder:

```bash
sugar-state map observations.csv assessments.jsonl --resolve-locations
```

A minimum confidence can be raised for more conservative density/mapping behavior:

```bash
sugar-state map observations.csv assessments.jsonl \
  --resolve-locations \
  --min-location-confidence 0.70
```

The full State package supports the same resolution option:

```bash
sugar-state package observations.csv --resolve-locations
```

## Metadata and auditability

Every State map writes `<map>.metadata.json`. The sidecar records:

- whether location resolution was enabled;
- the minimum confidence threshold;
- counts by precision tier;
- how many mapped points were derived/geocoded;
- a complete `resolved_locations` ledger for every plotted observation, including coordinates, precision, confidence, basis, original/derived status, resolution query, provider feature type, uncertainty radius, and density eligibility;
- how many eligible observations remained unresolved;
- a structured list of unresolved observation IDs and reasons;
- whether activity density was requested and actually rendered;
- how many observations were density-eligible or excluded for precision;
- the U.S.-proximity threshold, site uncertainty assumption, relation counts, and a per-observation `us_proximity` ledger with center/min/max distances and relation classification;
- the density, proximity, and precision semantics used to generate the map.

Analysts should inspect this sidecar when using the map in a brief. A map with excellent visual coverage but mostly city/region-derived points communicates something materially different from a map dominated by reviewed site-level coordinates. The same applies to proximity: a center distance inside a threshold is weaker evidence than an uncertainty range entirely inside it.
