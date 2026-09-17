# SUGAR quickstart

This walkthrough takes a new operator from an empty checkout to a reviewable, reproducible
research workspace. It uses the checked-in Kyrgyzstan fixture case, so it does not need credentials
or network access.

## Install

Use Python 3.11, 3.12, or 3.13:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

Confirm the installation and runtime without exposing environment values:

```powershell
.\.venv\Scripts\sugar.exe --version
.\.venv\Scripts\sugar.exe diagnostics --json
```

## Produce the first workspace

Run the deterministic example into a new directory:

```powershell
.\.venv\Scripts\python.exe examples\cases\kyrgyzstan_2026\run_case.py `
  --output .\quickstart-workspace `
  --clean
```

The command prints a JSON summary and writes ordinary inspectable files under the portable
workspace layout. The example intentionally keeps all observations `ai_triaged`, so its
verified-only State map is empty until a human reviews the evidence.

Inspect the workspace:

```powershell
.\.venv\Scripts\sugar-project.exe status .\quickstart-workspace --json
.\.venv\Scripts\sugar-project.exe list .\quickstart-workspace --json
```

Useful outputs include the observation CSV, State review queue, audit JSON, analyst and verified
maps, source-conflict records, and the preliminary analyst note. Start with the case README and
the review queue; do not treat the example's descriptive counts as causal influence findings.

## Make a small local map

For a first non-case operation, create a synthetic CSV so the workflow remains offline and uses no
private material:

```powershell
@"
platform,native_id,published_at,author_handle,original_text,latitude,longitude,engagement
bluesky,quick-1,2026-09-10T12:00:00Z,fixture-user,Public fixture record,37.2296,-80.4139,"{""likes"": 1}"
"@ | Set-Content -Encoding UTF8 .\quickstart-records.csv

.\.venv\Scripts\sugar.exe map .\quickstart-records.csv `
  --output .\quickstart-map.html `
  --json
```

Open `quickstart-map.html` in a browser. A map point is a descriptive location, not proof of
overlap, affiliation, coordination, or causation. Keep the synthetic input and generated map
together if you want to reproduce the result later.

## Next steps

- Read [`reproducibility.md`](reproducibility.md) before sharing a result.
- Read [`project-workspaces.md`](project-workspaces.md) before moving or archiving a project.
- Read [`collector-capability-matrix.md`](collector-capability-matrix.md) before enabling live collection.
- Read [`legal-and-data-handling.md`](legal-and-data-handling.md) and [`SECURITY.md`](../SECURITY.md)
  before supplying credentials or processing personal data.
