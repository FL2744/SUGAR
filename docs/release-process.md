# SUGAR release process

This document describes the repository-level release checklist. It does not replace Virginia Tech, Apple, Microsoft, State Department, or other institutional distribution/security requirements.

## 1. Define the release scope

Before changing the version, identify:

- user-visible capabilities included;
- schema/bridge/workspace version changes;
- collector access-semantic changes;
- methodology/evidence-rule changes;
- desktop compatibility changes;
- intentionally deferred items.

Update `CHANGELOG.md` as part of the implementation rather than reconstructing release history afterward.

## 2. Keep version metadata synchronized

The package version appears in:

- `pyproject.toml` under `[project].version`;
- `sugar_core.__version__`.
- `SUGAR-Desktop/package.json` and both root-version entries in `package-lock.json`;
- `SUGAR-Desktop/src-tauri/tauri.conf.json`;
- the app package entries in `SUGAR-Desktop/src-tauri/Cargo.toml` and `Cargo.lock`.

Run `python tools/release_tools.py versions --tag vVERSION` to check every value. Release tags must match exactly, including prerelease identifiers. The release workflow enforces this before building.

Schema and protocol versions are independent of the package version and should only move when their respective contracts change:

- `PostRecord` / observation schema versions;
- workspace manifest/database schema versions;
- desktop bridge protocol version.

Do not bump a schema/protocol solely because the package version changed.

## 3. Run deterministic validation

At minimum:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

A release candidate should have a fully green GitHub Actions matrix. The matrix covers supported Python versions, native platform checks, browser workflows/accessibility, and packaged desktop builds. Bounded live-source checks run separately through the explicitly authorized manual workflow.

A live-source failure should be interpreted carefully: distinguish an actual collector regression from an external platform access/rate-limit change. Never relax access controls simply to make CI green.

## 4. Inspect packaged desktop artifacts

### macOS

Verify:

- application launches on the intended minimum macOS version/architecture set;
- bundled `sugar-bridge` diagnostics report the expected package/protocol version;
- representative packaged analysis succeeds;
- code signing verifies;
- public distribution uses the intended signing/notarization process.

### Windows

Verify:

- the canonical Tauri application installs and launches from the MSI;
- the bundled `sugar-bridge` diagnostics report expected operations/protocol;
- packaged analysis, State, and workspace smoke tests succeed;
- the MSI and its updater signature are present, and the installer includes the Python bridge and dependency licenses;
- production distribution uses an organization-controlled Authenticode signing process if/when releases are distributed outside development channels.

Do not disable Gatekeeper, SmartScreen, antivirus, or endpoint protections to make a release appear functional.

## 5. Review research-integrity changes

For any release touching analysis or collection, verify that documentation still matches code regarding:

- public/authorized access boundaries;
- source provenance and query provenance;
- access failure vs zero activity;
- AI triage vs human verification;
- support/coordination/influence evidence requirements;
- map-density/proximity semantics;
- cross-platform metric comparability.

The release should not silently change the interpretation of previously generated products.

## 6. Review project-workspace compatibility

If workspace behavior changed:

- test opening an existing supported manifest/database;
- test workspace discovery and canonical paths;
- test internal relative and external artifact paths;
- document any schema migration;
- fail closed on unsupported future schema versions.

Never place credentials in workspace migrations or metadata.

## 7. Documentation pass

Check at least:

- `README.md`;
- `CHANGELOG.md`;
- `docs/architecture.md`;
- relevant collector/workflow docs;
- native app READMEs when packaging behavior changed;
- `CONTRIBUTING.md`/`SECURITY.md` when project policy changed.

Historical docs should be clearly labeled historical rather than left looking current.

## 8. Tagging and publication

Only tag a commit after required CI/review is complete. A release tag should point to the exact reviewed commit used for packaged artifacts.

Pushing a `v*` tag invokes the cross-platform release workflow. The workflow first verifies every package version and requires updater signing configuration, then builds and validates Windows x64, macOS Apple Silicon, and Python distribution artifacts from that same tagged commit. Intel Mac desktop builds are not a supported distribution target. It validates the signed update feed, stages all assets in a draft, and publishes only after every platform job succeeds. Prereleases never become the latest stable release. `SHA256SUMS` covers the complete published payload.

Configure the keys, test the updater, and review client behavior using [Software updates](software-updates.md). Updater signatures do not replace Apple notarization or Authenticode. Verify an actual update/restart between disposable signed installations on both platforms before production rollout.

SUGAR is licensed under the Apache License, Version 2.0. Before publication, verify that:

- root `LICENSE`, `NOTICE`, and `THIRD_PARTY_NOTICES.md` are present and current;
- package metadata declares `Apache-2.0` and includes the legal files in the built distribution;
- packaged Windows/macOS artifacts include SUGAR's legal files;
- packaged Windows/macOS artifacts include a generated `licenses/manifest.json` and discovered dependency license files from the exact installed build environment;
- third-party dependency licenses are reviewed against the exact versions resolved for that release;
- Windows community builds using PySide6/Qt preserve the applicable Qt/PySide6 LGPL/GPL license materials and replacement/relinking rights required by those licenses;
- every distributed Windows binary release retains or can supply the corresponding source for the exact LGPL-covered Qt/PySide6 version it ships, consistent with `third_party_licenses/qt/README.md`;
- GPL-only Qt modules are not introduced into an Apache-2.0 SUGAR binary without a separate compatibility review;
- any third-party datasets, platform content, logos, fonts, or other non-SUGAR assets are distributed only when their terms permit it;
- the release does not describe SUGAR as an official Virginia Tech or U.S. Department of State product merely because it was developed in the Diplomacy Lab context.
