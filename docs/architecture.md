# SUGAR architecture

SUGAR is organized around one shared Python research core with multiple user-facing entry points. The repository should preserve that separation as the project grows.

## Supported architecture

```text
                        ┌──────────────────────┐
                        │   Native macOS UI    │
                        │       SwiftUI        │
                        └──────────┬───────────┘
                                   │
                                   │ line-delimited JSON
                                   │
┌──────────────────────┐   ┌──────▼───────────┐   ┌──────────────────────┐
│  Windows workbench   ├──►│   sugar_bridge   │◄──┤  Future frontends     │
│      PySide6         │   └──────┬───────────┘   │ / automation clients │
└──────────────────────┘          │               └──────────────────────┘
                                  │ typed operations
                                  ▼
                         ┌──────────────────────┐
                         │      sugar_core      │
                         │ collection/evidence │
                         │ analysis/workspaces │
                         └──────────┬───────────┘
                                    │
              ┌─────────────────────┼──────────────────────┐
              ▼                     ▼                      ▼
       source collectors     State workflow        maps/reports/intel
              │                     │                      │
              └─────────────────────┴──────────────────────┘
                                    │
                                    ▼
                           ordinary project files
                         + workspace metadata
```

The desktop applications are clients of the shared core. They may provide platform-native credential storage, settings, file pickers, progress displays, and packaging, but they should not independently implement collection semantics, evidence rules, assessment logic, mapping methodology, or analytic synthesis.

## Core layers

### Collection and normalization

`collector_registry.py`, `collectors.py`, platform-specific collectors, `paged_collectors.py`, and `harvest.py` retrieve public or authorized source material and normalize it into `PostRecord`. New collectors must preserve stable native identifiers, source URLs, query provenance, source-specific metrics, and explicit access failures.

High-volume collection is checkpointed and resumable. It must not become a mechanism for defeating platform controls; rate limits and access gates remain authoritative.

### Evidence layer

`observations.py` and `observation_storage.py` convert normalized source material into `ResearchObservation`, which is the source-grounded evidence layer. This layer should remain independent from sponsor-specific analytical judgments.

### State workflow

`state_schema.py` and the `state_*` modules provide sponsor-oriented assessment, review, auditing, freshness, gap analysis, entity monitoring, overlap, networks, rollups, briefing products, hypotheses, and analytic intelligence. These modules may interpret evidence but must not mutate the underlying source facts to match an assessment.

### Spatial and reporting layer

`spatial.py`, `mapping.py`, `state_map.py`, `reporting.py`, and related modules produce spatial analysis and research outputs. Density, proximity, engagement, and influence are separate concepts; visual products must preserve those distinctions.

### Workspace layer

`workspace.py` defines the persistent project contract. Research data remains in ordinary files while `sugar-project.json` defines portable project identity/layout and `.sugar/workspace.sqlite3` indexes project artifacts. See `project-workspaces.md`.

### Desktop bridge

`sugar_bridge.py` is the supported process boundary for native desktop clients. It exposes only named/typed operations and emits line-delimited JSON events. Frontends should not expose arbitrary shell passthrough. Long operations belong in the child process so the UI can remain responsive and cancel work safely.

## Entry points

- `sugar` — general collection, harvest, triage, map, overlap, and analysis CLI.
- `sugar-project` — project-workspace management.
- `sugar-state` — State assessment/review/package workflow.
- `sugar-intel` — analytic-intelligence workflow.
- `SUGAR-macOS/` — native macOS client.
- `SUGAR-Windows/` — native Windows research workbench.

## Repository history

The pre-package monolithic scripts have been removed from the working tree. Their history remains available in Git, but they are not a compatibility surface and should not be restored for new feature work. New capabilities belong in `sugar_core` and should be exposed through stable services or typed bridge operations when a desktop surface needs them.

## Dependency direction

The intended dependency direction is:

```text
frontends / CLIs
      ↓
service + typed operations
      ↓
domain modules
      ↓
models / storage / utilities
```

Domain modules should not import desktop UI code. The core must remain usable on Linux/ARC without PySide6 or Swift tooling. Platform-specific packaging dependencies therefore remain optional extras.

## Tests and compatibility

CI runs the Python suite on Ubuntu, macOS, and Windows across Python 3.11–3.13, then independently builds and smoke-tests packaged macOS and Windows applications. Live-network checks are bounded and kept separate from deterministic fixtures.

Changes to schemas, collector semantics, workspace layout, bridge protocol, evidence rules, or exported columns require regression tests and documentation in the same pull request.

## Design rules

1. Prefer one shared implementation over frontend-specific copies.
2. Preserve raw evidence and provenance before enrichment or interpretation.
3. Fail explicitly at access/security boundaries.
4. Keep AI-generated judgments distinguishable from human verification.
5. Do not collapse incomparable metrics into opaque universal scores.
6. Keep workflows resumable and outputs reproducible.
7. Treat workspace/project state as metadata around ordinary research files, not as a hidden replacement for them.
8. Keep pull requests focused enough that reviewers can understand the methodological consequences of a change.
