# Research observations and human verification

SUGAR collects source material as platform-native records such as `PostRecord`. A research project usually needs a second layer above those records: a structured statement about something observed in the world, supported by evidence and reviewed by a human.

`ResearchObservation` provides that layer without replacing or weakening the collector schema.

## Why this exists

A social-media post, an official program page, an institutional announcement, and a news report can all support the same research finding. Treating every finding as a social-media post makes downstream analysis brittle and forces Teams 1, 2, and 4 into incompatible spreadsheets.

The intended workflow is:

**Collect -> Normalize -> AI triage -> Human verify -> Code -> Dataset -> Map -> Update**

The observation layer begins after normalization. Raw/source-specific records remain available for audit and reprocessing.

## Observation types

The initial schema supports:

- `institution`
- `program`
- `event`
- `digital_post`
- `narrative`
- `partnership`
- `other`

These are deliberately broad. New types should be added only when they represent a recurring research object rather than a one-off label.

## Core fields

Each observation has a stable `observation_id`, type, short title/summary, observed date, activity status, geographic fields, institution/program fields, actors, audiences, themes, U.S.-overlap tags, evidence references, AI-triage metadata, and verification metadata.

Location is explicitly epistemic rather than just geographic. `location_basis` records whether a location came from a profile, AI inference, human verification, or another method; `location_confidence` records uncertainty separately from coordinates.

Evidence references preserve the source URL when available and can also preserve a platform/native-ID identity for social-media material. An observation may carry multiple evidence references.

## Verification states

Observations use a small state machine:

- `unreviewed`: created but not triaged or reviewed
- `ai_triaged`: AI labels or preliminary classification have been attached
- `human_verified`: a named reviewer confirmed the observation against the evidence
- `rejected`: a named reviewer determined that the observation should not be treated as supported
- `needs_followup`: evidence is incomplete, contradictory, stale, or otherwise requires another pass

`human_verified` and `rejected` require a reviewer. Verified or rejected observations can be reopened as `needs_followup` when new evidence appears.

AI triage is therefore visible and reversible. It is not equivalent to human verification.

## What is intentionally not in this schema

There is no single "China influence score" in the observation model. Presence, activity, reach, audience relevance, persistence, engagement, overlap with U.S. efforts, and source confidence are analytically different concepts. They should not be collapsed into one number until the project agrees on a defensible methodology and tests it against real cases.

The schema does preserve the evidence needed to add such dimensions later without rebuilding collection from scratch.

## Converting collected posts

A normalized `PostRecord` can be converted into a `digital_post` observation with `observation_from_post(record)`. The conversion preserves:

- platform/native-ID identity
- canonical source URL
- publication and collection timestamps
- author identity
- inferred/profile location provenance
- coordinates and location confidence when present

This conversion does not claim that the post proves a broader program, institution, or influence finding. Analysts can create those higher-level observations separately and attach the relevant evidence.

## Dataset output

`save_observations()` writes a CSV, an XLSX workbook with an `observations` sheet, and a sidecar metadata JSON file. Nested evidence, actor, audience, theme, overlap, and triage fields are serialized as JSON inside flat-file cells so the files remain usable in Excel while preserving structure.

Numeric coordinates and confidence fields remain numeric. Text cells use the same spreadsheet formula-injection guard as the existing post export.

## Team use

A practical division of labor is:

- Team 1 creates institution/program/event observations from verified open sources.
- Team 2 creates or derives digital-post/narrative observations from collected material.
- Team 3 owns the schema, AI-triage rules, verification workflow, provenance requirements, and update procedure.
- Team 4 consumes human-verified or explicitly confidence-filtered observations for geospatial products.

The observation layer is meant to make those handoffs explicit rather than requiring each team to invent its own spreadsheet semantics.
