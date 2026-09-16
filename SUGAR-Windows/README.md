# SUGAR for Windows

SUGAR for Windows is the desktop research workbench for the SUGAR Diplomacy Lab workflow. It is a thin PySide6 application over the same `sugar_core` research logic and JSON bridge used by the rest of the project; collection, evidence rules, State assessment logic, and analytic intelligence are not reimplemented in the GUI.

## Classroom users: download one file

The classroom Windows build is a single downloadable file:

```text
SUGAR.exe
```

Download it and run it. **You do not need to install Python, extract a ZIP, clone GitHub, or keep support files beside the executable.**

The executable contains the frozen SUGAR backend worker and classroom resources internally. Long-running collection and analysis still run in a separate cancellable child process, but that implementation detail is packaged inside `SUGAR.exe` rather than exposed to the user as a second executable.

Windows SmartScreen may warn about unsigned classroom builds downloaded from the internet. Do not disable SmartScreen or endpoint protection as a workaround; verify that the file came from the project’s canonical GitHub build/release location.

Python 3.11–3.13 is required only when running SUGAR from source or using the developer CLI.

## What the application exposes

The Windows workbench has seven primary areas:

- **Home** — backend diagnostics, collector capability summary, research-pipeline guardrails, and quick navigation.
- **Collect** — bounded multi-source search and resumable/checkpointed high-volume harvesting.
- **Weibo** — real public-post investigation and explicit qualification campaigns.
- **State Workflow** — State-specific AI triage, analyst review workbook round-trip, American Spaces/EducationUSA comparison package, source-conflict review, evidence audit, snapshot diff, and monitoring templates.
- **Intelligence** — deterministic macro/micro packet, source/tradecraft audit, bounded synthesis, competing-hypothesis matrix, and longitudinal judgment comparison.
- **Maps & Reports** — maps plus Word/PDF reports from existing normalized results.
- **Settings** — LLM and source credentials, output defaults, and backend diagnostics.

A persistent Activity & Outputs panel shows structured progress events, provides child-process cancellation, keeps a bounded support log, and links to generated output folders.

The shared backend additionally exposes the `import-public` operation for known public WeChat, Zhihu, Douyin, Bilibili, and Weibo items. The Windows UI can continue to evolve independently while using that same typed backend operation; developers should not reimplement those collectors in the GUI.

## Research and access boundaries

The Windows application does not solve CAPTCHAs, automate login, manufacture cookies/device identities, rotate proxies/accounts, reproduce anti-bot signatures to defeat access controls, or bypass platform restrictions. High-volume harvesting scales through durable tasks, checkpoint/resume, deduplication, bounded plans, and rate-limit-aware waiting/defer behavior.

AI output remains analytically useful but unverified until human review. Presence, activity, reach, engagement, outcomes, and causal influence remain separate concepts. Geographic proximity, recurring actors, clusters, or engagement do not automatically become an influence finding.

The generated State workflow is a research product for the Diplomacy Lab project. It is not an official Department of State security authorization, ATO, records determination, procurement approval, or AI certification.

## Credentials

Secrets entered in the Windows Settings page are held in memory for the app session and passed only to the bundled backend child process through its environment. They are not written into desktop settings or JSON config files by the GUI.

Supported backend environment-variable fallbacks include:

```text
SUGAR_LLM_API_KEY
SUGAR_X_BEARER_TOKEN
SUGAR_BLUESKY_IDENTIFIER
SUGAR_BLUESKY_APP_PASSWORD
SUGAR_MASTODON_TOKEN
SUGAR_WEIBO_COOKIE
SUGAR_ZHIHU_ACCESS_SECRET
```

A Weibo cookie is optional and should only be an existing legitimate session the analyst is authorized to use. A Zhihu Access Secret is required only for official Zhihu keyword search; known public Zhihu URL import is separate.

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

## Build the single Windows executable

```powershell
python -m pip install -e ".[windows]"
.\SUGAR-Windows\scripts\build.ps1
```

The script creates:

```text
SUGAR-Windows\dist\SUGAR.exe
```

Internally the build is two-stage: PyInstaller first freezes the command bridge, then embeds that worker plus required resources inside the final one-file GUI executable. At runtime the GUI starts the embedded worker through `QProcess`, preserving real cancellation and keeping backend failures from freezing the event loop while ordinary users still manage only one file.

## Windows security / distribution note

Development and CI builds are unsigned. Windows SmartScreen may therefore warn when a build is downloaded from the internet. A public production release should be Authenticode-signed with an organization-controlled code-signing certificate and the signed artifact should be distributed through an approved release process.

The project repository still needs a formal license/distribution decision before presenting a classroom build as a general public software release.

## Troubleshooting

Use **Settings → Run backend diagnostics** first. The Home page reports the backend version, architecture, runtime type, bridge protocol, and current collector capabilities.

If the packaged UI reports that the backend cannot start, re-download the current `SUGAR.exe` from the canonical GitHub build/release location. Developers can override the worker path with `SUGAR_BRIDGE` for debugging.

For support, use **Copy log** in the Activity & Outputs panel and include the SUGAR version/build shown by diagnostics. Check the log before posting it and remove any sensitive data.
