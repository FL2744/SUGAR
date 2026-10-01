# Using SUGAR in a State Department or similar office

A short guide for the people who will install, run and review SUGAR. It collects what is already true of the software and marks what the office must decide.

## Getting it running

| Need | How |
| --- | --- |
| A workstation app | Install the Windows `.msi` or unzip `SUGAR-macOS.zip` from the project's GitHub release page. Everything runs on that computer; there is no SUGAR cloud. |
| A shared service for a team | Run `sugar serve` (or `sugar-api`) on one machine, give each person a member address and role (viewer, reviewer, analyst, owner). See `docs/operations-runbook.md`. |
| Offline or restricted network | Collection needs the open internet, but reading, reviewing, mapping and exporting existing projects does not. Choose "No AI" and nothing is sent to a model provider. |
| Staying current | Settings → Updates. **Stable** (formal releases) is the right channel for an office that wants change control; **Latest** follows every tested change. `sugar update` checks from the command line. An office that cannot reach GitHub can mirror the release files and install them by hand. |

## What an office should check first

1. **Network allow-list:** `api.github.com` and `github.com` (updates), the platforms in use, `tiles.openfreemap.org` (and `*.tile.opentopomap.org` for Terrain), `nominatim.openstreetmap.org` (place lookup), and the AI provider if one is chosen. Each can be blocked without breaking the rest; the related feature simply turns off.
2. **Unsigned installers:** current builds are ad-hoc signed classroom builds. A government deployment needs the organization's own code signing (Authenticode on Windows, signing and notarization on macOS). `docs/release-process.md` lists the steps.
3. **Credentials:** AI and platform keys go in the OS vault or environment variables. Decide who holds them and how they rotate. They never enter projects or exports.
4. **Data handling:** `docs/privacy.md` states what stays local and what leaves. Retention, records rules, and handling of personal information in public posts are the office's decisions; projects are plain folders and can be stored, encrypted or deleted like any other.
5. **Licensing:** SUGAR is Apache License 2.0 (`LICENSE`, `NOTICE`); dependency and font licenses are in `THIRD_PARTY_NOTICES.md`. Map data is © OpenStreetMap contributors and the tile providers, shown on the map.
6. **Evidence standards:** every institution claim carries a quoted source and a reviewer; confidence and distances are computed facts, not findings of influence. A person verifies before anything is reported.

## What SUGAR does not do

It does not bypass logins or access controls, collect private messages, or score influence or intent. Country-level places are approximate. A post's origin is shown only when the platform supplied coordinates or the post is linked to a located institution.

## Before relying on it

The software has been tested in a development environment and against recorded responses. Live platform behavior changes; run a small known collection, check the results against what you can see by hand, and use **Accuracy check** on a labeled sample before trusting outputs for a decision.
