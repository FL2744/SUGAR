## Problem

<!-- What user/research/engineering problem does this change solve? -->

## Changes

<!-- Describe the implementation at the architectural level. -->

## Research / methodology impact

<!-- Note any changes to evidence semantics, schemas, access behavior, map meaning, review rules, or analytical outputs. Write "None" when genuinely none. -->

## Validation

- [ ] `python -m pytest`
- [ ] New/changed behavior has regression coverage
- [ ] Desktop/package smoke tests considered when relevant
- [ ] Live-network behavior remains bounded/fail-closed when relevant

## Documentation

- [ ] README/docs updated for behavior changes
- [ ] `CHANGELOG.md` updated when the change is release-notable
- [ ] Schema/bridge/workspace version changes are documented

## Security / provenance

- [ ] No credentials, session cookies, private research data, or secrets are included
- [ ] Source/query provenance is preserved
- [ ] Access-control failures are not converted into zero-activity findings
- [ ] AI-generated judgments remain distinguishable from human verification
