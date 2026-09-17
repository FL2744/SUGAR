# Error-handling contract

SUGAR failures follow the contract **what happened → what was preserved → what to do next**.
The CLI and desktop bridge convert uncaught operation failures into structured, redacted error
payloads with stable codes, retryability, remediation text, and a nonzero exit status.

## Catching policy

Broad catches are reserved for boundaries that must fail closed without losing the surrounding
workflow:

- CLI and bridge entry points classify and redact the final failure.
- Per-record AI and State triage failures become explicit `needs_followup`/failed-closed results,
  while the remaining records continue when configured to do so.
- Harvest and seed-harvest failures are checkpointed, classified as retry/deferred/failed, and
  written to durable event history before continuation.
- Diagnostic history is best-effort and cannot replace the operation's original failure.
- Store destructors suppress shutdown-time close errors because raising from `__del__` is unsafe.

Parsing and normalization code catches only the conversion errors it expects. Invalid optional
fields fall back to an explicit unknown/empty value or the documented legacy delimiter form;
they do not silently change a verified value into `false`. Malformed required records raise a
line-specific validation error instead.

## Verification

The deterministic suite covers malformed payloads, provider access failures, retry/defer behavior,
connection reset, timeout classification, workspace corruption, atomic-output failure, and
redacted structured errors. Run the offline gate from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp .\work\pytest-basetemp -m "not live"
```

Live collection is intentionally excluded. The CI live smoke requires an explicit manual
`workflow_dispatch` and a source-specific opt-in variable.
