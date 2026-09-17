# Product contracts

This directory contains machine-readable product requirements that are treated as repository contracts rather than informal roadmap notes.

The current State/Diplomacy Lab contract is [`requirements/state_product.v1.json`](requirements/state_product.v1.json). Requirements are intentionally separated from implementation details so the project can change collectors, desktop frameworks, LLM providers, or deployment environments without silently changing the product promise.

Changes to a P0 requirement must update its acceptance criteria and the corresponding design or methodology documentation in the same pull request.

