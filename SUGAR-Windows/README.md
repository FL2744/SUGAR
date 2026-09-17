# SUGAR for Windows

SUGAR for Windows is the desktop research workbench for the SUGAR OSINT and State Department Diplomacy Lab workflow. It is a thin PySide6 application over the same `sugar_core` research logic and JSON bridge used by the rest of the project; collection, evidence rules, State assessment logic, and analytic intelligence are not reimplemented in the GUI.

SUGAR itself is licensed under Apache License 2.0. The portable bundle includes `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`, and a generated `licenses/` inventory for the exact third-party packages included in the build. Qt/PySide6 remains subject to its own applicable licensing terms.

## What the application exposes

The Windows workbench has seven primary areas:

- **Home** — backend diagnostics, collector capability summary, research-pipeline guardrails, and quick navigation.
- **Collect** — bounded multi-source search and resumable/checkpointed high-volume harvesting.
- **Weibo** — real public-post investigation and explicit industrial qualification campaigns.
- **State Workflow** — State-specific AI triage, analyst review workbook round-trip, American Spaces/EducationUSA comparison package, evidence audit, snapshot diff, and monitoring templates.
- **Intelligence** — deterministic macro/micro packet, source/tradecraft audit, quick/standard/deep agentic synthesis, competing-hypothesis matrix, and longitudinal judgment comparison.
- **Maps & Reports** — maps plus Word/PDF reports from existing normalized results.
- **Settings** — LLM and source credentials, output defaults, and backend diagnostics.

A persistent Activity & Outputs panel shows structured progress events, provides real child-process cancellation, keeps a bounded support log, and links to generated output folders.

## Research and access boundaries

The Windows application does not change SUGAR's collection policy. It does not solve CAPTCHAs, automate login, manufacture cookies or device identities, rotate proxies/accounts, or bypass platform access controls. High-volume harvesting scales through durable tasks, checkpoint/resume, deduplication, bounded plans, and rate-limit-aware waiting/defer behavior.

The State and intelligence surfaces also keep SUGAR's evidence guardrails. AI output remains analytically useful but unverified until human review. Presence, activity, reach, engagement, outcomes, and causal influence remain separate concepts. Geographic proximity, recurring actors, clusters, or engagement do not automatically become an influence finding.

The generated State workflow is a research product for the Diplomacy Lab project. It is not an official Department of State security authorization, ATO, records determination, procurement approval, or AI certification.

## Credentials

Secrets entered in the Windows Settings page are held in memory for the app session and passed only to the backend child process through its environment. They are not written into desktop settings or JSON config files by the GUI.

Supported environment-variable fallbacks are:

```text
SUGAR_LLM_API_KEY
SUGAR_X_BEARER_TOKEN
SUGAR_BLUESKY_IDENTIFIER
SUGAR_BLUESKY_APP_PASSWORD
SUGAR_MASTODON_TOKEN
SUGAR_WEIBO_COOKIE
```

A Weibo cookie is optional and should only be an existing legitimate session the analyst is authorized to use. Anonymous public surfaces remain the default when it is blank.

## Development run

From PowerShell in the repository root:

```powershell
python -m pip install -e ".[dev,windows]"
.\SUGAR-Windows\run_dev.ps1
```

The application can be instantiated without opening a window for CI:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python .\SUGAR-Windows\app.py --smoke-test
```

## Build the portable Windows bundle

Install the Windows optional dependencies and run:

```powershell
python -m pip install -e ".[windows]"
.\SUGAR-Windows\scripts\build.ps1
```

The script creates:

```text
SUGAR-Windows\dist\SUGAR\SUGAR.exe
SUGAR-Windows\dist\SUGAR\sugar-bridge.exe
SUGAR-Windows\dist\SUGAR-Windows-x64.zip
```

`SUGAR.exe` is the windowed PySide6 application. `sugar-bridge.exe` is the console backend used as a child process. Keeping them separate gives the UI real cancellation and keeps backend failures from freezing the event loop.

## Windows security / distribution note

Development and CI builds are unsigned. Windows SmartScreen may therefore warn when a portable build is downloaded from the internet. A public production release should be Authenticode-signed with an organization-controlled code-signing certificate and the signed artifacts should be distributed through an approved release process. Do not weaken SmartScreen or tell users to disable endpoint protections as a workaround.

## Troubleshooting

Use **Settings → Run backend diagnostics** first. The Home page reports the backend version, architecture, runtime type, bridge protocol, and current collector capabilities.

If the packaged UI reports that the backend cannot start, verify `sugar-bridge.exe` is next to `SUGAR.exe`. Developers can override the bridge path with `SUGAR_BRIDGE` for debugging.

If ARC calls fail on campus, verify normal Virginia Tech ARC network prerequisites such as an appropriate campus network/VPN configuration. The Windows app does not modify network policy or tunnel around blocked access.

For support, use **Copy log** in the Activity & Outputs panel. The support log contains structured operation/progress messages; the GUI does not deliberately print entered secret values.
