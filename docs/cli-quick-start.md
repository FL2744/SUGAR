# CLI quick start

The CLI uses the same research engine and workspace format as the browser and desktop app. Python 3.11–3.14 is supported. Run installation commands from the repository root.

## Install

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
sugar --version
```

macOS/Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
sugar --version
```

If activation is restricted on Windows, use `.\.venv\Scripts\python.exe` and `.\.venv\Scripts\sugar.exe` directly. Re-run installation after changes to console entry points.

Every command supports `--help`; all five launchers support `--version`:

| Launcher | Module alternative | Purpose |
| --- | --- | --- |
| `sugar` | `python -m sugar_core` | Import, requirements, plans, collection, maps, reports |
| `sugar-project` | `python -m sugar_core.workspace_cli` | Project folders, registry, history, project exchange |
| `sugar-state` | `python -m sugar_core.state_cli` | Assessment drafts, human review, State exports |
| `sugar-intel` | `python -m sugar_core.state_intel_cli` | Intelligence, evidence analysis, calibration |
| `sugar-api` | `python -m sugar_api` | HTTP service for the browser UI |

For command-specific options, use e.g. `sugar import --help`, `sugar strategy approve --help`, or `sugar-project registry-import --help`.

## Complete an offline workflow

No provider credentials or network connection are required for these steps. Save the following synthetic data as `sample.csv` in your current directory:

```csv
platform,native_id,published_at,author_handle,original_text,latitude,longitude
external,demo-1,2026-09-01T12:00:00Z,demo,Public education workshop,5.6037,-0.1870
```

Create a project and normalize the evidence. The quoted paths work in both PowerShell and POSIX shells:

```sh
sugar-project init "./my research" --name "Offline example"
sugar import sample.csv --output "./my research/data/raw/imported" --workspace "./my research"
sugar-project status "./my research"
```

The import writes canonical CSV, XLSX, and JSONL plus an import manifest. Input rows need a platform and either a native ID or canonical URL. See [importer-interface.md](importer-interface.md) for mappings and rejected rows.

Save a requirement, compile a strategy, review it, and approve it before generating a plan:

```sh
sugar requirement create --question "Which public education programs are documented?" --source bluesky --workspace "./my research"
sugar strategy compile "./my research/state/research-requirement.json" --workspace "./my research"
sugar strategy show "./my research/state/research-strategy.json"
sugar strategy approve "./my research/state/research-strategy.json" --reviewer "Example analyst" --workspace "./my research"
sugar plan "./my research/state/research-requirement.json" --workspace "./my research"
```

Approval records a human decision. Inspect the generated concepts and scope before approving a real project. This sequence saves a plan without collecting anything. See [research-requirement-compiler.md](research-requirement-compiler.md) for editing a strategy.

Export a map and a PDF report from the imported evidence, then inspect the portable project catalog:

```sh
sugar map "./my research/data/raw/imported.csv" --workspace "./my research"
sugar analysis "./my research/data/raw/imported.csv" --format pdf --workspace "./my research"
sugar-project list "./my research" --json
sugar-project export-project "./my research" "./offline-project.zip"
```

Map generation runs offline; viewing the basemap requires network access. Project outputs are registered under `outputs/maps` and `outputs/reports`. `export-project` preserves the project for continuation on another machine. A research evidence handoff is a separate export with observations and verification; see [handoff-bundles.md](handoff-bundles.md).

Pass `--workspace` to workflow commands to select a project explicitly. When omitted, supported research commands discover `sugar-project.json` from the current directory upward. Outside a project, outputs use the command's file/directory defaults. Workspace-management commands take an explicit project path.

## Collect and use optional AI

Bounded raw collection without translation or location inference:

```sh
sugar search "public education" --sources bluesky --posts 10 --pages 1 --no-translate --no-location --workspace "./my research"
```

Network access and provider availability are required. Search defaults to X and enables translation/location inference; explicitly choose sources and turn off both AI options when you want raw collection without an LLM key. Dates use `--since YYYY-MM-DD --until YYYY-MM-DD`; the start must precede or equal the end. Source names are case-insensitive and deduplicated. Counts must be positive.

| Environment variable | Needed for |
| --- | --- |
| `SUGAR_X_BEARER_TOKEN` | X collection |
| `SUGAR_LLM_API_KEY` | AI translation, inference, triage, or synthesis |
| `SUGAR_BLUESKY_IDENTIFIER`, `SUGAR_BLUESKY_APP_PASSWORD` | Optional authenticated Bluesky access |
| `SUGAR_MASTODON_TOKEN` | Authorized Mastodon keyword search; explicit public hashtags can use anonymous access |
| `SUGAR_WEIBO_COOKIE` | Optional authorized Weibo access; provider restrictions can still apply |

Set variables in the shell before running the command. Interactive `sugar` commands can prompt for required keys; scripts and redirected input fail promptly with the missing variable's name. `sugar-state` and `sugar-intel` AI commands require the environment variable. Keep credentials out of command arguments, project files, and shared bundles.

For resumable collection and file-based term lists, use `sugar harvest --help` and [high-volume-harvest.md](high-volume-harvest.md). For browser API hosting and its separate operator token, see [SUGAR-Desktop/README.md](../SUGAR-Desktop/README.md).

## Errors and troubleshooting

| Result | Exit code |
| --- | --- |
| Successful operation, help, version, or successful verification | `0` |
| Failed intelligence calibration | `1` |
| Invalid arguments, expected file/access errors, missing credentials, or failed handoff/lineage verification | `2` |
| Interrupted CLI operation | `130` |

The API closes cleanly on Ctrl+C. Verification and calibration commands print structured results; check their exit status in scripts. Unexpected programming errors retain a traceback. Set `SUGAR_DEBUG=1` to also show tracebacks for expected errors when troubleshooting.

- **Command not found:** activate the environment used for installation, or use the module alternative above with that environment's Python. `python -m pip show sugar-osint` identifies the installation.
- **Missing workspace/file:** check the current directory, quote paths containing spaces, and use an explicit `--workspace` path. File arguments are relative to the current directory unless a command documents workspace-relative resolution (for example, `sugar-project register`).
- **Windows JSON files:** requirements, strategies, plans, strategy edits, and threshold configuration accept UTF-8 with or without a BOM. CSV imports accept UTF-8 BOMs too. Use UTF-8 when saving files.
- **Unapproved strategy:** review and approve the strategy before generating a plan from it. Edits require a fresh approval.
- **No collection results:** inspect coverage and access errors before interpreting a zero count. Provider login, rate limits, and unavailable sources are distinct from successful zero-result searches; see [collection-coverage.md](collection-coverage.md).
- **API startup:** `sugar-api --host 127.0.0.1 --port 8765` starts the local service. Ports must be 1–65535. An explicit `--port` overrides `SUGAR_API_PORT`. Binding beyond loopback requires `SUGAR_API_TOKEN`.
