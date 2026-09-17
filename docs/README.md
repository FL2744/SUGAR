# SUGAR documentation

Use this index to find the current design or methodology document for the part of SUGAR you are changing or using.

## Architecture and development

- [`architecture.md`](architecture.md) — system boundaries, dependency direction, desktop/core separation, and engineering rules.
- [`project-workspaces.md`](project-workspaces.md) — persistent project manifest/artifact-registry contract and automatic workflow routing.
- [`release-process.md`](release-process.md) — versioning, CI, packaged-app inspection, research-integrity review, and release checklist.
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — contribution/test expectations.
- [`../SECURITY.md`](../SECURITY.md) — security, credential, workspace, and packaging policy.

## Collection

- [`collector-interface.md`](collector-interface.md) — shared collector capability/normalization contract.
- [`high-volume-harvest.md`](high-volume-harvest.md) — durable, resumable collection at research scale.
- [`bilibili-public.md`](bilibili-public.md) — Bilibili public collector behavior and boundaries.
- [`weibo-public.md`](weibo-public.md) — Weibo public/authorized collection behavior.
- [`wechat-public.md`](wechat-public.md) — public WeChat Official Account article ingestion and access boundaries.
- [`weibo-investigation.md`](weibo-investigation.md) — known-public-post expansion and context workflow.
- [`weibo-qualification.md`](weibo-qualification.md) — reproducible Weibo collection/investigation acceptance campaign.

## Evidence, AI, and spatial analysis

- [`research-observations.md`](research-observations.md) — source-grounded `ResearchObservation` evidence layer.
- [`ai-triage.md`](ai-triage.md) — grounded AI triage and review boundaries.
- [`research-map.md`](research-map.md) — general map layers, density semantics, provenance, and reference overlays.
- [`state-map-precision.md`](state-map-precision.md) — State-map location resolution, precision tiers, uncertainty envelopes, and false-precision guardrails.
- [`spatial-overlap.md`](spatial-overlap.md) — reproducible geographic proximity/reference analysis.

## State / Diplomacy Lab workflow

- [`state-department-workflow.md`](state-department-workflow.md) — end-to-end State evidence-to-brief methodology and integrity rules.
- [`state-analytic-intelligence.md`](state-analytic-intelligence.md) — deterministic and structured analytic-intelligence products.
- [`state-agentic-deep-mode.md`](state-agentic-deep-mode.md) — iterative LLM-assisted synthesis mode and its safeguards.

## Historical context

- [`../STABILIZATION.md`](../STABILIZATION.md) — v1.1 stabilization baseline. This is historical and should not be used as the current feature roadmap.
- [`../CHANGELOG.md`](../CHANGELOG.md) — release/integration history.

When documentation and code disagree, treat that as a defect: behavior changes should update the relevant methodology/design document in the same pull request.
