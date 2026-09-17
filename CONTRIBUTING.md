# Contributing to SUGAR

SUGAR is a research system, so code changes can affect both software behavior and research methodology. Contributions should therefore be reviewable, testable, and explicit about provenance, access boundaries, and analytical assumptions.

## Before you start

Read:

- `README.md` for the supported product surface;
- `docs/architecture.md` for module boundaries and dependency direction;
- `SECURITY.md` for credential/security expectations;
- the relevant methodology/platform document under `docs/`.

New work should target `sugar_core/`. The historical `SUGAR.py` and `sugar_analysis.py` monoliths are retained for compatibility/reference and should not receive new platform or workflow architecture.

## Development setup

Python 3.11–3.14 is supported.

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest
```

Install optional desktop dependencies only when working on that surface:

```bash
python -m pip install -e ".[dev,windows]"
python -m pip install -e ".[dev,macos]"
```

## Pull-request scope

Prefer focused pull requests that a reviewer can understand without reconstructing several unrelated changes. Large features should still preserve clear internal boundaries and should avoid replacing unrelated components merely because they are nearby.

A pull request should explain:

1. the research/user problem it solves;
2. the architectural surface changed;
3. any schema, evidence, access, or methodological consequences;
4. tests added or updated;
5. documentation changed;
6. known limitations or intentionally deferred follow-up.

## Required validation

Run at minimum:

```bash
python -m pytest
```

CI additionally tests the core on Ubuntu, macOS, and Windows across Python 3.11–3.14 and builds/smoke-tests the packaged desktop applications. Windows packaging is validated under Python 3.14; macOS packaging intentionally embeds Python 3.12 to preserve the macOS 13 deployment target.

Changes to the following require regression tests in the same pull request:

- exported columns or schema versions;
- collector pagination/date/access semantics;
- deduplication/query provenance;
- evidence/reference handling;
- State verification or claim rules;
- spatial/map semantics;
- bridge protocol or typed desktop operations;
- workspace manifest/database behavior;
- packaging/launch behavior.

Live-network tests should remain bounded and separate from deterministic mocked/fixture tests.

## Collector contributions

New collectors must use the shared collector architecture and normalize into `PostRecord`. At minimum preserve:

- stable platform-native identity;
- canonical source URL when available;
- author and publication time;
- query/source provenance;
- raw platform metrics in addition to canonical engagement fields;
- explicit source/access mode;
- thread/relationship data where the platform exposes it;
- deterministic test fixtures.

Do not silently turn login gates, verification challenges, rate limiting, unsupported search, or other access failures into empty-result findings.

SUGAR does not accept collector logic that solves CAPTCHAs, manufactures authentication/session state, spoofs device identities, rotates proxies/accounts to evade controls, or otherwise defeats platform access restrictions.

## Evidence and analytical changes

`ResearchObservation` is the evidence layer. State-specific or sponsor-specific judgments belong in sidecar assessment structures rather than rewriting source facts.

High-consequence claims should retain explicit evidence references and review state. AI output must remain distinguishable from human verification. Do not introduce opaque universal influence scores or treat engagement, geographic proximity, or record density as causal influence.

If a code change alters the meaning of a map layer, score, claim state, evidence rule, or generated briefing statement, document that methodological change—not just the implementation.

## Project workspaces

Workspace changes must preserve portability and inspectability:

- `sugar-project.json` contains no secrets;
- in-project artifact paths stay relative where possible;
- external/non-portable paths remain explicit;
- unknown schema versions fail closed;
- migrations are explicit and tested before changing the workspace schema version;
- research files remain ordinary files rather than being silently absorbed into SQLite.

See `docs/project-workspaces.md`.

## Desktop applications

macOS and Windows are clients of the same backend. Native code may own UI, settings, secure credential storage, packaging, and process management, but it should call typed shared-core operations instead of reimplementing collection/evidence/analysis logic.

Do not add arbitrary shell passthrough to a desktop UI. Long-running work should remain cancellable through the backend process boundary.

## Documentation standard

Update documentation in the same pull request when behavior changes. Root documentation should describe current behavior; historical migration notes belong in Git history or clearly labeled historical documents.

Use precise terminology. In particular, distinguish collection coverage from absence, activity from influence, proximity from overlap, and AI triage from human verification.

## Credentials and test data

Never commit real API keys, passwords, session cookies, bearer tokens, private research notes, or other secrets. Fixtures should use synthetic/non-sensitive values. If a secret is accidentally committed, treat it as compromised even if the commit is later reverted; follow `SECURITY.md`.

## Contribution licensing

SUGAR is distributed under the Apache License, Version 2.0. Unless you explicitly state otherwise when submitting a contribution, intentionally submitted code, documentation, tests, or other material is provided under the same Apache-2.0 terms in accordance with Section 5 of the license.

Contributors retain copyright in their original contributions. The project-level notice is `Copyright 2026 Alejandro Grenier and contributors`; it is not an assignment of every contributor's copyright to the maintainer.

Do not contribute material that you do not have the right to license under these terms. Third-party code, data, images, fonts, models, or other assets must have compatible licensing and must carry the required notices or attribution.
