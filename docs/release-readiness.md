# Release-readiness ledger

This ledger turns the 25-section hardening specification into an auditable work queue. It is not a
release approval. `[x]` means the repository has a checked-in implementation or deterministic test;
`[~]` means the technical foundation exists but an environment, human review, or release-owner
decision remains; `[ ]` means work remains.

1. `[~]` Legal and ownership: access/data-handling policy and disclaimers are documented; license,
   copyright owner, institutional affiliation approval, project-name review, third-party notices,
   and a confirmed private vulnerability route still require the release owner.
2. `[~]` Releases: tagged wheel/sdist, exact version/changelog validation, checksums, and SBOM
   automation are present; Windows Authenticode and macOS signing/notarization identities are not
   configured.
3. `[x]` CI quality: Ruff, formatting, focused mypy, coverage, pip-audit, package installation,
   deterministic stress smoke, CodeQL, Gitleaks, Dependabot, and dependency review are configured.
   Branch protection and required-review settings remain repository-admin work.
4. `[~]` Dependencies: supported Python bounds and declared ranges are explicit, universal newest and
   Python 3.11 lowest-direct hash-pinned runtime locks are checked in, and CI exercises both tracks;
   a formally approved update policy remains to be selected.
5. `[~]` Collectors: capability/access matrix, malformed-payload guards, pagination/duplicate
   coverage, and bounded live separation are present; full per-platform adversarial and authorized
   live qualification still needs execution.
6. `[x]` Provenance: records and derived observations preserve identity, URLs, timestamps, method,
   query matches, collector/access mode, raw/normalized metrics, confidence, evidence, review, AI,
   and round-trip provenance fields.
7. `[~]` Evidence: grounded evidence and unknown/uncertain review semantics exist; a larger fixture
   corpus of deleted/edited/reposted/contradictory/archived-source cases remains.
8. `[~]` Scientific semantics: deterministic State, overlap, freshness, network, longitudinal,
   conflict, and review tests exist; golden corpus fixtures and expert sign-off remain.
9. `[~]` Spatial: coordinate/precision/proximity safeguards and map marker budgets exist; large
   browser-load and 100k/1M aggregation policy tests remain.
10. `[x]` AI safety: source text is untrusted, prompt-injection behavior is tested, output is
    evidence-grounded, AI provenance is retained, and credentials are runtime-only.
11. `[~]` Workspaces: portable manifests, relative-path checks, missing-artifact health, migration
    guards, and atomic manifest writes exist; interruption/concurrency/OneDrive/migration recovery
    testing remains.
12. `[x]` Security: formula-safe spreadsheets, escaped map HTML, typed bridge operations, bounded
    bridge config, secret redaction, fail-closed access behavior, and security scans are present.
13. `[x]` Structured errors: the desktop bridge emits stable error codes, retryability, remediation,
    and redacted messages with nonzero failure exit status.
14. `[x]` Diagnostics: bridge diagnostics report protocol/runtime/capabilities and credential
    presence booleans without including credential values, config contents, or research data.
15. `[~]` CLI: public entry points expose `--help`/`--version`, live tests are separately marked,
    major exports are atomic, cancellation has a stable exit/event contract, and JSON mode works
    before or after subcommands; config precedence, full output-manifest semantics, and a product
    usability pass remain.
16. `[~]` Desktop UX: backend protocol and packaged smoke tests exist; interactive usability,
    accessibility, long-run cancellation, and signed-install testing require Windows/macOS hosts.
17. `[~]` Exports: CSV/XLSX/JSONL plus PDF/DOCX/HTML paths and formula/HTML safety exist; exhaustive
    Unicode/RTL/emoji/long-field workbook and document rendering QA remains.
18. `[x]` Performance harness: deterministic storage/export/map probes and a CI 5k smoke are
    checked in; 1k/10k/100k/1M targets still need measured budgets on representative hardware.
19. `[~]` Long-running reliability: a bounded offline repetition/memory harness is checked in;
    six-hour/24-hour collector, retry, checkpoint, and network-reset qualification runs have not
    been completed.
20. `[~]` Documentation: architecture, collector, workspace, access, stress, and release docs are
    present; final operator runbooks and deployment-specific data-retention guidance remain.
21. `[~]` Canonical demo: the deterministic Kyrgyzstan case is in CI; a polished clean-room demo
    package and expected-output review remain.
22. `[ ]` External reproducibility: an independent operator has not yet completed a clean-machine
    install, fixture run, and artifact verification.
23. `[ ]` Analyst usability: task-based evaluation with representative analysts has not yet run.
24. `[ ]` Domain review: methodology, legal/privacy, and platform-access review has not yet been
    recorded by the responsible experts.
25. `[~]` Professional gate: the repository has a technical candidate gate, but production release
    approval must wait for the unresolved owner, signing, governance, soak, and review items above.

## Local candidate gate

From the repository root, the current deterministic gate is:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,security]"
.\.venv\Scripts\python.exe -m pytest --basetemp ..\pytest-basetemp -m "not live"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pip_audit --format columns
.\.venv\Scripts\python.exe tools\stress_test.py --records 5000 --skip-map --output-dir .\stress-output
.\.venv\Scripts\python.exe -m build --sdist --wheel
```

Live collection is never part of this offline gate. It requires explicit authorization, a bounded
test plan, and the source-specific environment variable documented by the live test.
