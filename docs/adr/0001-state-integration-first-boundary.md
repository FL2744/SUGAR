# ADR 0001: State integration-first product boundary

- **Status:** Accepted for implementation planning
- **Date:** 2026-09-17
- **Decision scope:** State/Diplomacy Lab delivery profile

## Context

SUGAR is being developed in an academic environment where Virginia Tech ARC and project-owned public-source collectors are convenient. The eventual Department user environment is different and cannot be inferred to expose the same services.

Public Department documentation also shows that State already operates enterprise capabilities relevant to the problem, including Northstar for digital/news/social-media analytics, StateChat for generative AI, a Department Enterprise Data Catalog, and enterprise analytics/data-management functions. Rebuilding those systems would create duplication and make SUGAR harder to adopt.

## Decision

SUGAR will be designed as an **integration-first, evidence-centric research workbench**.

1. Virginia Tech services are optional development integrations, never State delivery dependencies.
2. Existing and future collectors are adapters into a canonical evidence pipeline.
3. Externally collected records must be able to enter the same pipeline through documented import adapters.
4. LLM services are replaceable providers. No internal Department AI API is assumed.
5. Evidence, review state, provenance, limitations, and outputs must be exportable in application-independent formats.
6. State-facing workflows begin from a research requirement and maintain an auditable search/collection plan.
7. SUGAR must complement rather than duplicate incumbent Department capabilities when those capabilities are available.

## Consequences

### Positive

- The State handoff is not blocked by loss of Virginia Tech access.
- Northstar or other Department data can become inputs if an export/API is made available later.
- StateChat or another approved model can become an AI provider without changing evidence semantics.
- SUGAR remains independently useful for research environments where those enterprise systems are absent.
- The codebase has a clearer maintenance boundary for future teams.

### Costs

- We must build and test import/export schemas, not only collectors.
- Search planning needs its own persisted state and audit model.
- UI work must support multiple deployment profiles without forking the core.
- Some desired integrations cannot be completed until the sponsor exposes a supported interface.

## Rejected alternatives

### Make ARC the default operational backend

Rejected because Virginia Tech access is not a reasonable Department deployment assumption.

### Rebuild a complete media-monitoring platform

Rejected because State already publicly describes Northstar and related digital-media analytics capabilities. SUGAR should add transparent research orchestration, evidence lineage, extensibility, and portable handoff instead of duplicating a broad incumbent system.

### Hard-code a Northstar or StateChat connector now

Rejected because no supported public integration contract has been identified. The correct near-term boundary is a generic importer/exporter and replaceable model-provider interface.

