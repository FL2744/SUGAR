# Evidence lineage

SUGAR keeps analytic findings separate from the source evidence and collection/import context that produced them. State-facing packages and portable handoffs materialize this relationship in a machine-readable lineage index rather than requiring a reviewer to reconstruct it manually from several files.

## Lineage model

`*.lineage.json` / `evidence/lineage.json` links:

```text
analytic finding
    -> State assessment
    -> ResearchObservation
    -> evidence identity (URL and/or platform:native_id)
    -> canonical PostRecord when present
    -> record collection/import fields
    -> dataset/provenance documents
```

Each finding records `supporting_evidence_ids` explicitly. When a structured `SourceConflict` applies to one of those exact supporting references, the other source-claim IDs are recorded separately as `contradicting_evidence_ids`. SUGAR does not attach a conflict to a finding merely because the topics look similar.

The lineage index includes source URL/native identity, publication and collection timestamps where available, source mode/host/request URL, collector/schema versions, and a SHA-256 of stored original source text. The actual original text remains in the canonical record dataset; the hash and record key make the relationship inspectable without turning an AI-generated summary into the source of record.

The index also materializes the assessment layer itself. Each finding points to a real `assessment_id` and `observation_id`; the assessment index preserves review state, reviewer, review note, analytic priority, schema version, and claim IDs. Claim findings additionally preserve claim type, epistemic status, confidence, reviewer, review note, and exact supporting evidence IDs.

Support resolution is observation-scoped. A citation does **not** become valid merely because the same URL or record exists elsewhere in the corpus. The cited identity must be attached to the finding's `ResearchObservation`, or be an explicitly structured external analytic reference such as a U.S. public-diplomacy service source.

## State package behavior

`sugar-state package` emits a `<name>.lineage.json` alongside the State assessment dataset, audit, review queue, brief, map, and snapshot. The snapshot names the lineage file. If the input observation dataset has a metadata sidecar, that dataset provenance is included in the lineage index.

Triage carries the raw dataset's metadata forward under `source_dataset_provenance`. For an external import this can include source-system name, source-file SHA-256, importer version, and import time; for a native collection it can retain query/source/coverage metadata. API keys, cookies, and other runtime secrets are not written to ordinary dataset metadata.

## Portable handoff behavior

`sugar handoff` emits `evidence/lineage.json` with the canonical source records available, producing the deepest lineage chain. When `--assessments` is supplied, State analytic claims and sponsor-support findings are indexed. `--source-conflicts` can add structured contradictory evidence.

The handoff verifier checks both artifact hashes and lineage consistency: finding observation IDs must exist, each supporting ID must have a corresponding chain entry, referenced canonical record keys must exist in the lineage record index, and contradicting source-claim IDs must exist in the packaged conflict evidence.

Semantic verification is intentionally stronger than checksum verification. `sugar verify-handoff` fails even if someone edits a lineage file *and updates its manifest hash* when the edit leaves a dangling observation, assessment, evidence, record, contradiction, or conflict reference.

## Standalone lineage commands

Lineage can be generated and audited independently of a State package or handoff:

```text
sugar lineage observations.csv \
  --assessments state-assessments.jsonl \
  --records records.csv \
  --source-conflicts source-conflicts.json \
  --provenance records.metadata.json \
  --output evidence.lineage.json

sugar verify-lineage evidence.lineage.json
```

`--records` is optional. Without canonical records, SUGAR can still resolve claim support through `ResearchObservation.evidence` identities and preserve dataset provenance from the observation metadata sidecar. Supplying canonical records adds the deepest chain, including source identity, collection/import context, and original-text SHA-256.

The validator rejects duplicate IDs, missing assessment/observation links, undeclared or missing support-chain entries, unresolved supporting evidence, cross-observation record leakage, missing canonical records, tampered embedded record payloads, detached source-conflict claims, missing contradictions, conflict-ID mismatches, and declared-count inconsistencies.

## Epistemic rule

Lineage is a reference structure, not a confidence or influence score. It does not make a claim true because it has citations. Human verification state, source quality, contradictory evidence, collection coverage, and analytic tradecraft remain separate judgments.

Generated summaries never replace the stored original evidence. Removing the canonical record or source reference breaks the lineage rather than silently promoting the summary into evidence.
