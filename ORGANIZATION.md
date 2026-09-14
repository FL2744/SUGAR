# SUGAR repository guide

This file describes the current repository layout. Historical cleanup notes have been removed from the root documentation; Git history remains the source of truth for prior migrations.

## Supported source

- `sugar_core/` — supported Python research core. New collection, evidence, State, spatial, reporting, intelligence, and workspace work belongs here.
- `sugar_bridge.py` — typed line-delimited JSON backend used by native desktop clients.
- `SUGAR-macOS/` — SwiftUI macOS client and packaging scripts.
- `SUGAR-Windows/` — PySide6 Windows client and packaging scripts.
- `tests/` — deterministic Python regression suite plus bounded live-network tests.
- `docs/` — methodology, architecture, collector, workflow, and platform documentation.
- `examples/` — sample research outputs retained for demonstration/regression context.

## Command-line entry points

- `sugar` — general collection, harvest, triage, mapping, overlap, and reporting.
- `sugar-project` — persistent project workspace creation and artifact management.
- `sugar-state` — State/Diplomacy Lab evidence-to-brief workflow.
- `sugar-intel` — structured analytic-intelligence workflow.

## Legacy compatibility

`SUGAR.py` and `sugar_analysis.py` are historical monoliths retained for compatibility/reference. They are not the target for new features. Do not add new collectors, State logic, workspace behavior, or frontend-specific branches to those files.

## Local/generated state

The following are intentionally local or generated and ignored by Git:

- `.venv/`, Python caches, build outputs;
- `.sugar/` workspace registry/cache state;
- `.sugar-cache/` legacy/general cache state;
- `outputs/`, `scratch/`, `archive/`, and `private-notes/`;
- native macOS/Windows build directories;
- credential/token files matched by `.gitignore`.

A workspace's portable `sugar-project.json` manifest is not ignored by default. It contains project identity/layout metadata only and must never contain secrets.

## Engineering rule

The repository has one research core and multiple clients. Desktop applications may own native UI, credential storage, packaging, and process management, but they should call shared `sugar_core` logic through typed operations rather than reimplementing methodology.

See `docs/architecture.md` for dependency direction and design rules, and `CONTRIBUTING.md` for the pull-request/test standard.
