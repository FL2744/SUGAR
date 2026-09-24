# Product contracts

This directory contains machine-readable product requirements that are treated as repository contracts rather than informal roadmap notes.

The current State/Diplomacy Lab contract is [`requirements/state_product.v1.json`](requirements/state_product.v1.json). Requirements are intentionally separated from implementation details so the project can change collectors, desktop frameworks, LLM providers, or deployment environments without silently changing the product promise.

The persistent external-environment workspace implementation and its boundaries are documented in [`backlog.md`](backlog.md) and [`../docs/research-workspace.md`](../docs/research-workspace.md). It records the delivered implementation baseline for registry, project memory, data inspection, maps, listening posts, conversation context, and portable exchange. A blank schema is not an institution inventory; no authoritative global inventory is bundled.

Changes to a P0 requirement must update its acceptance criteria and the corresponding design or methodology documentation in the same pull request.
