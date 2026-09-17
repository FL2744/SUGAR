# Portable research handoff bundles

SUGAR handoff bundles are application-independent interchange artifacts for moving a research run between teams, machines, or downstream systems without requiring Virginia Tech infrastructure or a running SUGAR installation to inspect the evidence.

They complement, rather than replace, sponsor-specific products such as `sugar-state package`. Existing State briefs, audits, maps, assessment files, and intelligence outputs can be included as analytic outputs inside the handoff.

## Create a bundle

```bash
sugar handoff \
  research-requirement.json \
  search-plan.json \
  collected-records.csv \
  observations.jsonl \
  --output ./handoffs \
  --name reporting-period-a \
  --assessments state_research.state.jsonl \
  --include-output state_research.brief.md \
  --include-output state_research.audit.json
```

The default output is both a directory and a ZIP archive. `--no-zip` leaves only the inspectable directory.

## Bundle layout

```text
reporting-period-a/
|-- manifest.json
|-- limitations.json
|-- context/
|   |-- research-requirement.json
|   `-- search-plan.json
|-- evidence/
|   |-- records.jsonl
|   `-- observations.jsonl
|-- review/
|   `-- state-assessments.jsonl       # when supplied
|-- provenance/
|   `-- ...                            # import/collection manifests
`-- outputs/
    `-- ...                            # existing briefs, audits, maps, etc.
```

`manifest.json` records the SUGAR version, schema versions, requirement ID, counts, relative paths, byte sizes, and SHA-256 for every packaged artifact. Relative paths let the directory move without rewriting links.

Canonical source records and research observations are always emitted as JSONL even if the original input was CSV or XLSX. This keeps the evidentiary core machine-readable without proprietary serialization.

## Coverage and limitations

When the analyst does not supply a dedicated limitations JSON file, SUGAR generates one from the stored requirement, search plan, records, and observations. When a collection-coverage sidecar or embedded coverage metadata is available, those source outcomes are incorporated directly instead of inferring access from record counts. It reports corpus counts by platform/language/geography where available, observed time bounds, branch status counts, and preferred sources with no observed records.

The generated limitations explicitly state that a source with no records is not evidence of zero real-world activity. It may be unrun, unavailable, filtered, or outside the effective collection plan.

This generated file is a minimum disclosure layer, not a substitute for analyst-authored methodological caveats when a finished brief requires more context.

## Integrity verification

```bash
sugar verify-handoff ./handoffs/reporting-period-a
```

Verification checks every manifest-listed relative path, byte length, and SHA-256. A missing, modified, or path-escaping artifact fails verification. The ZIP is a transport convenience; the manifest inside the unpacked directory is the integrity contract.
