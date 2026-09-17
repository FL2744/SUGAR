# State Department research workflow

This workflow turns SUGAR collection output into an auditable, updateable research product for the Diplomacy Lab project on sponsor-supported global cultural/public-engagement networks and their overlap with U.S. public diplomacy.

It is a research methodology, not a Department of State certification, security authorization, intelligence product, or automated determination of influence.

## Why there are two data layers

`ResearchObservation` remains the source-normalized evidence layer. It answers: what did the source actually show, where/when did it occur, and what source proves it?

`StateAssessment` is a sidecar analytic layer. It answers sponsor-specific questions: what audience/program/narrative is relevant, what evidence supports sponsoring state involvement, how much observable reach or engagement exists, where does it overlap American Spaces/EducationUSA/U.S. public diplomacy, and what still requires human verification?

Keeping these layers separate prevents a later analytic judgment from silently rewriting raw source evidence.

## Collection coverage and absence claims

State package briefs preserve bounded-search coverage metadata when it is available. Successful zero-result searches are distinguished from unavailable, failed, partial, and not-run sources. Unavailable or failed surfaces are reported as collection limitations and must not be interpreted as evidence that no activity occurred. See [`collection-coverage.md`](collection-coverage.md).

## Core concepts

Do not collapse these into one score:

1. **Presence** — an institution, program, account, partnership, or event exists.
2. **Activity** — programming/content actually occurred.
3. **Reach** — observable exposure such as attendance or views.
4. **Engagement** — observable interaction such as comments, likes, shares, or participation.
5. **Outcome evidence** — evidence of a changed knowledge, behavior, relationship, or other result.
6. **Causal influence evidence** — evidence sufficient to support an analytic claim that the activity caused a relevant change.

SUGAR deliberately does not create a universal "influence score." Cross-platform engagement units are not equivalent, and reach/engagement are not causal evidence.

## State-specific coding

### Strategic audiences

The controlled taxonomy includes students, prospective students, youth, emerging leaders, entrepreneurs, technical professionals, educators, researchers/academics, journalists/media, civil society, government officials, exchange alumni, general public, and `other`.

### Program domains

The controlled taxonomy includes higher education, English language, entrepreneurship, STEM/technology, media/information literacy, civic engagement, culture/arts, economic/commercial programming, professional skills, exchange/alumni, digital connectivity, and `other`.

### Narratives

Narrative tags include education opportunity, technology/innovation, development/modernization, culture/civilization, economic opportunity, sponsoring state model, sponsoring state-U.S. comparison, anti-U.S., multipolarity, Global South solidarity, shared future, cross-state coordination, third-party coordination, local partnership, commercial branding, and `other`.

`anti_us`, `cross_state_coordination`, and `third_party_coordination` are high-consequence labels. They should not enter a State-facing brief without a source-backed, human-verified claim.

## sponsor-support methodology

sponsor support is not inferred from sponsoring-state identity, sponsoring-state language, sponsoring-state culture, commercial sponsoring-state ownership, geographic origin, or sponsoring state-friendly messaging alone.

The support assessment records both a level and basis:

- `not_assessed`
- `unsupported`
- `possible`
- `probable`
- `confirmed`

Possible bases include official sponsoring state or host-government sources, funding, personnel, governance, branding, co-sponsorship, facility/material support, program delivery, or credible secondary reporting.

`probable` and `confirmed` support require explicit evidence references. `confirmed` also requires a named human reviewer and `human_verified` support state. AI triage can never confirm sponsor support.

## Claim-level evidence

High-consequence claims—support relationships, coordination, and influence—require explicit evidence references. Evidence IDs must point to evidence attached to the underlying `ResearchObservation`.

Claims also distinguish:

- `observed_fact`
- `analytic_assessment`
- `hypothesis`

An influence claim cannot be stored as a simple observed fact. AI-generated influence language is automatically converted to a follow-up hypothesis, and AI cannot assign `causal_influence_evidence`.

## End-to-end workflow

### 1. Collect and normalize

Use the ordinary SUGAR collection/harvest tools. Collection output becomes normalized `PostRecord` rows and then `ResearchObservation` records. Program/event observations are preferred when the research question is about public diplomacy activity rather than merely institutional presence.

### 2. Maintain a monitored-entity registry

Create a template:

```bash
sugar-state template-entities entities.csv
```

The registry stores stable entity IDs, canonical names, aliases/native names, country/city, official/social URLs, languages, watch-query terms, priority, and status.

Generate a reproducible watch plan:

```bash
sugar-state query-plan entities.csv --output query_plan.csv
```

Aliases improve discovery and entity resolution; they do **not** transfer or prove a sponsor-support assessment.

### 3. Create or AI-triage State assessments

Create blank assessment rows for manual coding:

```bash
sugar-state blank observations.xlsx --output state.jsonl
```

Or use AI for first-pass triage:

```bash
export SUGAR_LLM_API_KEY="..."
sugar-state triage observations.xlsx \
  --provider arc \
  --output state.ai.jsonl
```

AI output is only triage. SUGAR strips unknown taxonomy values and invented evidence IDs, downgrades AI `confirmed` support to `probable`, downgrades evidence-free probable support, and converts proposed causal influence into follow-up work.

### 4. Load the U.S. public-diplomacy comparison layer

Create the American Spaces/EducationUSA/U.S. presence template:

```bash
sugar-state template-us-sites us_presence.csv
```

Populate it from current, attributable sources. Supported network categories are American Spaces, EducationUSA, U.S. embassies/consulates, Binational Centers, and other USG public-diplomacy presences.

Service tags should represent actual services/programming at the site, such as `educationusa`, `english_language`, `entrepreneurship`, `stem`, `technology`, `media_literacy`, `civic_engagement`, `leadership`, `alumni`, or similar documented services.

SUGAR then calculates geographic, audience, thematic, and service overlap. Overlap identifies potential competitive or complementary engagement space. It does not itself prove displacement, preference change, or persuasion.

### 5. Export the human-review workbook

```bash
sugar-state review-export observations.xlsx state.ai.jsonl \
  --output review.xlsx
```

The workbook contains separate assessment and claim sheets, source links, current AI states, human decision cells, reviewer fields, support decisions, and instructions.

Apply reviewed decisions:

```bash
sugar-state review-apply state.ai.jsonl review.xlsx \
  --output state.reviewed.jsonl
```

The importer re-validates the entire State schema. It rejects nameless human verification, unknown taxonomy entries, invalid confirmed-support decisions, and human verification of an influence claim without causal-influence evidence.

### 6. Audit before briefing

```bash
sugar-state audit observations.xlsx state.reviewed.jsonl \
  --output audit.json
```

The audit checks evidence chains, observation/assessment linkage, support claims, influence claims, coordination/narrative claims, reach/engagement metrics, and briefing eligibility.

`fail` means a required integrity rule failed. `conditional` means a warning or verification issue remains. `pass` means the encoded evidence/verification rules were satisfied; it does not certify complete collection or true causal influence.

### 7. Build the State-facing package

```bash
sugar-state package observations.xlsx \
  --assessments state.reviewed.jsonl \
  --us-sites us_presence.csv \
  --previous-assessments prior_state.jsonl \
  --output ./state_package \
  --name quarterly_update
```

The complete command produces:

- State assessment JSONL/CSV/XLSX
- the exact overlap-assessed snapshot used by supplemental exports
- evidence-integrity audit JSON
- human review-priority CSV
- analyst review workbook
- verified-only BLUF Markdown
- verified-only sponsoring state-observation + U.S.-presence GeoJSON
- typed evidence-backed network nodes/edges and JSON
- country/city rollup JSON/CSV
- evidence-freshness report
- stable assessment snapshot/change-detection report

### 8. Monitor freshness and change

The project primarily emphasizes recent activity. By default, the freshness report treats 2024-01-01 as the current-activity boundary and flags evidence collections older than 90 days for refresh:

```bash
sugar-state freshness observations.xlsx state.reviewed.jsonl \
  --current-start 2024-01-01 \
  --stale-days 90 \
  --output freshness.json
```

Historical evidence remains valid background; it is not deleted merely because it predates the current monitoring window.

Snapshot comparison uses stable observation IDs and reports additions, removals, and changes to sponsor support, review state, observability, U.S. overlap, audiences, program domains, narratives, and claims.

## Network output

```bash
sugar-state network observations.xlsx state.reviewed.jsonl \
  --us-sites us_presence.csv \
  --output ./network
```

The default network includes verified material only. Edge types include:

- `sponsors`
- `hosts`
- `partners`
- `participates_in`
- `targets_audience`
- `program_domain`
- `expresses_or_advances`
- `overlaps_us_public_diplomacy`

Every edge carries the source observation/assessment, verification state, and evidence references. A graph edge is a typed relationship, **not** an influence edge.

Use `--include-unverified` only for analyst working views; those outputs should not be treated as verified briefing material.

## Rollups and heatmap/dashboard data

```bash
sugar-state rollup observations.xlsx state.reviewed.jsonl \
  --us-sites us_presence.csv \
  --output ./rollups
```

Country and city rollups separate total observations from verified observations and report U.S. overlap, support status, program domains, audiences, narratives, observation types, and individual reach/engagement metrics.

A dashboard may visualize these fields as activity density, verified program footprint, observed reach, or U.S.-overlap layers. It should not label a density heatmap as an influence map.

## Briefing standard

The generated BLUF uses only:

1. an underlying `ResearchObservation` with `human_verified` verification state; and
2. a `StateAssessment` that is itself briefing-eligible.

Unverified material can remain in the research database and review queue without appearing as a State-facing judgment.

## Research-integrity rules

- Preserve raw source and collection provenance.
- Keep source facts separate from AI/human analysis.
- Never treat search-access failure as zero activity.
- Never interpret aliases as proof of affiliation.
- Never infer government support solely from nationality, language, culture, or branding.
- Never collapse likes, comments, views, attendance, reposts, and followers into one influence score.
- Never treat comments as a representative public-opinion sample.
- Require explicit evidence for support, coordination, anti-U.S., and influence claims.
- Default maps, networks, and briefs to verified-only content.
- Preserve historical evidence while clearly identifying current-monitoring freshness gaps.
