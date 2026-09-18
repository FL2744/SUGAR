from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import PostRecord
from .observations import EvidenceReference, ResearchObservation
from .source_conflicts import SourceConflict
from .state_schema import StateAssessment

LINEAGE_SCHEMA_VERSION = "1.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _record_aliases(record: PostRecord) -> set[str]:
    aliases = {record.record_key, record.canonical_url}
    if record.platform and record.native_id:
        aliases.add(f"{record.platform}:{record.native_id}")
    return {_clean(value) for value in aliases if _clean(value)}


def _evidence_aliases(evidence: EvidenceReference) -> set[str]:
    aliases = {evidence.url}
    if evidence.platform and evidence.native_id:
        aliases.add(f"{evidence.platform}:{evidence.native_id}")
    return {_clean(value) for value in aliases if _clean(value)}


def _observation_aliases(observation: ResearchObservation) -> set[str]:
    aliases = set(observation.source_record_keys)
    for evidence in observation.evidence:
        aliases.update(_evidence_aliases(evidence))
    return {_clean(value) for value in aliases if _clean(value)}


def _record_payload(record: PostRecord) -> dict[str, Any]:
    return {
        "record_key": record.record_key,
        "platform": record.platform,
        "native_id": record.native_id,
        "canonical_url": record.canonical_url,
        "published_at": record.published_at,
        "collected_at": record.collected_at,
        "source_mode": record.source_mode,
        "source_host": record.source_host,
        "source_url": record.source_url,
        "collector_version": record.collector_version,
        "schema_version": record.schema_version,
        "original_text_sha256": _sha256_text(record.original_text) if record.original_text else "",
        "has_original_text": bool(record.original_text),
    }


def _external_reference_aliases(reference: dict[str, Any]) -> set[str]:
    aliases = {
        _clean(reference.get("evidence_id")),
        _clean(reference.get("url")),
        _clean(reference.get("native_id")),
    }
    platform = _clean(reference.get("platform"))
    native_id = _clean(reference.get("native_id"))
    if platform and native_id:
        aliases.add(f"{platform}:{native_id}")
    return {value for value in aliases if value}


def _overlap_external_references(assessment: StateAssessment) -> list[dict[str, Any]]:
    overlap = assessment.us_overlap
    references: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(reference: dict[str, Any]) -> None:
        key = _clean(reference.get("evidence_id"))
        if key and key not in seen:
            references.append(reference)
            seen.add(key)

    for source in overlap.service_sources:
        evidence_id = source.source_url or f"us-site:{source.site_id}"
        add({
            "evidence_id": evidence_id,
            "url": source.source_url,
            "native_id": source.site_id,
            "platform": "us_public_diplomacy",
            "source_type": "us_public_diplomacy_service_source",
            "title": source.name,
            "network": source.network,
            "delivery_mode": source.delivery_mode,
            "coverage_scope": source.coverage_scope,
            "program_service_matches": list(source.program_service_matches),
            "audience_service_matches": list(source.audience_service_matches),
        })
    if overlap.nearest_site_id:
        add({
            "evidence_id": f"us-site:{overlap.nearest_site_id}",
            "url": "",
            "native_id": overlap.nearest_site_id,
            "platform": "us_public_diplomacy",
            "source_type": "us_public_diplomacy_site_reference",
            "title": overlap.nearest_site_name,
            "network": overlap.nearest_network,
        })
    return references


def _resolve_support(
    reference: str,
    observation: ResearchObservation,
    records_by_alias: dict[str, PostRecord],
    *,
    external_references: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    reference = _clean(reference)
    observation_aliases = _observation_aliases(observation)
    evidence_matches = [
        evidence
        for evidence in observation.evidence
        if reference in _evidence_aliases(evidence)
    ]
    external_matches = [
        dict(item)
        for item in external_references
        if reference in _external_reference_aliases(item)
    ]
    record_keys: set[str] = set()
    if reference in observation.source_record_keys:
        record = records_by_alias.get(reference)
        if record is not None and record.record_key:
            record_keys.add(record.record_key)
    for evidence in evidence_matches:
        for alias in _evidence_aliases(evidence):
            record = records_by_alias.get(alias)
            if record is not None and record.record_key:
                record_keys.add(record.record_key)
    direct_record = records_by_alias.get(reference)
    # A record elsewhere in the corpus must not silently become support for this
    # observation. It resolves only when the observation itself points to it.
    if (
        direct_record is not None
        and direct_record.record_key
        and (
            reference in observation_aliases
            or direct_record.record_key in observation.source_record_keys
        )
    ):
        record_keys.add(direct_record.record_key)
    unlinked_record_keys: list[str] = []
    if direct_record is not None and direct_record.record_key and direct_record.record_key not in record_keys:
        unlinked_record_keys.append(direct_record.record_key)
    resolved_records = sorted(
        {
            record.record_key: record
            for key in record_keys
            if (record := records_by_alias.get(key)) is not None
        }.values(),
        key=lambda record: record.record_key,
    )
    resolution_kinds: list[str] = []
    if evidence_matches:
        resolution_kinds.append("observation_evidence")
    if resolved_records:
        resolution_kinds.append("canonical_record")
    if external_matches:
        resolution_kinds.append("external_reference")
    resolved = bool(evidence_matches or resolved_records or external_matches or reference in observation_aliases)
    return {
        "evidence_id": reference,
        "resolved": resolved,
        "resolution_kinds": resolution_kinds,
        "observation_id": observation.observation_id,
        "evidence_references": [asdict(item) for item in evidence_matches],
        "external_evidence_references": external_matches,
        "source_record_keys": [record.record_key for record in resolved_records],
        "source_records": [_record_payload(record) for record in resolved_records],
        "unlinked_candidate_record_keys": unlinked_record_keys,
    }


def _contradictions(
    supporting_refs: Iterable[str],
    conflicts: Iterable[SourceConflict],
) -> tuple[list[str], list[str]]:
    refs = {_clean(value) for value in supporting_refs if _clean(value)}
    contradiction_ids: set[str] = set()
    conflict_ids: set[str] = set()
    for conflict in conflicts:
        matched = [
            claim for claim in conflict.claims
            if claim.claim_id in refs or claim.source_url in refs
        ]
        if not matched:
            continue
        matched_ids = {claim.claim_id for claim in matched}
        conflict_ids.add(conflict.conflict_id)
        contradiction_ids.update(
            claim.claim_id for claim in conflict.claims if claim.claim_id not in matched_ids
        )
    return sorted(contradiction_ids), sorted(conflict_ids)


def build_lineage_index(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment] = (),
    *,
    records: Iterable[PostRecord] = (),
    source_conflicts: Iterable[SourceConflict] = (),
    dataset_provenance: dict[str, Any] | None = None,
    provenance_documents: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    observations = list(observations)
    assessments = list(assessments)
    records = list(records)
    conflicts = list(source_conflicts)
    observation_map = {item.observation_id: item for item in observations}
    records_by_alias: dict[str, PostRecord] = {}
    for record in records:
        for alias in _record_aliases(record):
            records_by_alias[alias] = record

    source_claims = {
        claim.claim_id: {
            **asdict(claim),
            "conflict_ids": sorted(
                conflict.conflict_id for conflict in conflicts if claim.claim_id in {row.claim_id for row in conflict.claims}
            ),
        }
        for conflict in conflicts
        for claim in conflict.claims
    }
    findings: list[dict[str, Any]] = []

    def add_finding(
        *,
        finding_id: str,
        finding_type: str,
        statement: str,
        assessment: StateAssessment,
        supporting_refs: Iterable[str],
        review_state: str,
        epistemic_status: str = "",
        claim_type: str = "",
        confidence: float | None = None,
        reviewer: str = "",
        review_note: str = "",
        support_bases: Iterable[str] = (),
        external_references: Iterable[dict[str, Any]] = (),
    ) -> None:
        observation = observation_map.get(assessment.observation_id)
        refs = list(dict.fromkeys(_clean(value) for value in supporting_refs if _clean(value)))
        external_references = [dict(item) for item in external_references]
        contradiction_ids, conflict_ids = _contradictions(refs, conflicts)
        support_chain = [
            _resolve_support(
                reference,
                observation,
                records_by_alias,
                external_references=external_references,
            )
            for reference in refs
        ] if observation is not None else []
        findings.append({
            "finding_id": finding_id,
            "finding_type": finding_type,
            "statement": _clean(statement),
            "claim_type": _clean(claim_type),
            "assessment_id": assessment.assessment_id,
            "observation_id": assessment.observation_id,
            "review_state": _clean(review_state),
            "reviewer": _clean(reviewer),
            "review_note": _clean(review_note),
            "epistemic_status": _clean(epistemic_status),
            "confidence": confidence,
            "support_bases": [_clean(value) for value in support_bases if _clean(value)],
            "supporting_evidence_ids": refs,
            "contradicting_evidence_ids": contradiction_ids,
            "source_conflict_ids": conflict_ids,
            "supporting_evidence": support_chain,
            "unresolved_supporting_evidence_ids": [
                item["evidence_id"] for item in support_chain if not item["resolved"]
            ],
        })

    for assessment in assessments:
        if assessment.sponsor_support.level != "not_assessed" or assessment.sponsor_support.evidence_refs:
            add_finding(
                finding_id=f"support:{assessment.assessment_id}",
                finding_type="sponsor_support",
                statement=assessment.sponsor_support.rationale or f"Sponsor support assessed as {assessment.sponsor_support.level}.",
                assessment=assessment,
                supporting_refs=assessment.sponsor_support.evidence_refs,
                review_state=assessment.sponsor_support.review_state,
                epistemic_status=assessment.sponsor_support.level,
                claim_type="sponsor_support",
                confidence=assessment.sponsor_support.confidence,
                reviewer=assessment.sponsor_support.reviewer,
                support_bases=assessment.sponsor_support.bases,
            )
        for claim in assessment.claims:
            add_finding(
                finding_id=claim.claim_id,
                finding_type="analytic_claim",
                statement=claim.statement,
                assessment=assessment,
                supporting_refs=claim.evidence_refs,
                review_state=claim.review_state,
                epistemic_status=claim.epistemic_status,
                claim_type=claim.claim_type,
                confidence=claim.confidence,
                reviewer=claim.reviewer,
                review_note=claim.review_note,
            )
        if assessment.us_overlap.material:
            observation = observation_map.get(assessment.observation_id)
            refs = list(_observation_aliases(observation)) if observation is not None else []
            overlap_refs = _overlap_external_references(assessment)
            refs.extend(
                str(item["evidence_id"])
                for item in overlap_refs
                if item.get("evidence_id")
            )
            add_finding(
                finding_id=f"overlap:{assessment.assessment_id}",
                finding_type="us_public_diplomacy_overlap",
                statement=assessment.us_overlap.note or "Material U.S. public-diplomacy overlap is recorded.",
                assessment=assessment,
                supporting_refs=refs,
                review_state=assessment.review_state,
                epistemic_status="analytic_assessment",
                claim_type="comparative_overlap",
                reviewer=assessment.reviewer,
                review_note=assessment.review_note,
                external_references=overlap_refs,
            )

    return {
        "schema_version": LINEAGE_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "counts": {
            "records": len(records),
            "observations": len(observations),
            "assessments": len(assessments),
            "findings": len(findings),
            "source_conflicts": len(conflicts),
        },
        "findings": findings,
        "assessments": [
            {
                "assessment_id": assessment.assessment_id,
                "observation_id": assessment.observation_id,
                "review_state": assessment.review_state,
                "reviewer": assessment.reviewer,
                "review_note": assessment.review_note,
                "analytic_priority": assessment.analytic_priority,
                "ai_provider": assessment.ai_provider,
                "ai_model": assessment.ai_model,
                "ai_workflow": assessment.ai_workflow,
                "schema_version": assessment.schema_version,
                "claim_ids": [claim.claim_id for claim in assessment.claims],
            }
            for assessment in assessments
        ],
        "observations": [
            {
                "observation_id": observation.observation_id,
                "verification_state": observation.verification_state,
                "reviewer": observation.reviewer,
                "reviewed_at": observation.reviewed_at,
                "verification_notes": observation.verification_notes,
                "ai_provider": observation.ai_provider,
                "ai_model": observation.ai_model,
                "ai_workflow": observation.ai_workflow,
                "source_record_keys": observation.source_record_keys,
                "evidence": [asdict(item) for item in observation.evidence],
            }
            for observation in observations
        ],
        "records": [_record_payload(record) for record in records],
        "source_claims": source_claims,
        "source_conflicts": [asdict(conflict) for conflict in conflicts],
        "dataset_provenance": dataset_provenance or {},
        "provenance_documents": list(provenance_documents),
        "guardrail": "Lineage points to stored original evidence. Summaries and analytic findings do not replace canonical source records or evidence references.",
    }


def validate_lineage_index(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate semantic integrity of a lineage index.

    This is deliberately stricter than JSON/schema shape checking. A lineage file
    is useful only when its graph actually closes: findings must point to a real
    assessment/observation, every declared support ID must have one support-chain
    node, resolved record keys must exist in the canonical record index, and
    contradiction/conflict IDs must resolve to the packaged source-conflict data.
    """

    issues: list[dict[str, Any]] = []

    def issue(code: str, **detail: Any) -> None:
        issues.append({"code": code, **detail})

    if not isinstance(payload, dict):
        return {
            "status": "fail",
            "schema_version": "",
            "issues": [{"code": "lineage_not_object"}],
        }
    if payload.get("schema_version") != LINEAGE_SCHEMA_VERSION:
        issue(
            "unsupported_lineage_schema",
            expected=LINEAGE_SCHEMA_VERSION,
            actual=payload.get("schema_version"),
        )

    findings = payload.get("findings") or []
    assessments = payload.get("assessments") or []
    observations = payload.get("observations") or []
    records = payload.get("records") or []
    source_claims = payload.get("source_claims") or {}
    source_conflicts = payload.get("source_conflicts") or []

    for name, value, expected_type in (
        ("findings", findings, list),
        ("assessments", assessments, list),
        ("observations", observations, list),
        ("records", records, list),
        ("source_claims", source_claims, dict),
        ("source_conflicts", source_conflicts, list),
    ):
        if not isinstance(value, expected_type):
            issue("invalid_lineage_collection", field=name, expected=expected_type.__name__)

    if issues and any(item["code"] == "invalid_lineage_collection" for item in issues):
        return {
            "status": "fail",
            "schema_version": str(payload.get("schema_version") or ""),
            "issues": issues,
        }

    def index_unique(rows: list[Any], field: str, kind: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for raw in rows:
            if not isinstance(raw, dict):
                issue("invalid_lineage_row", kind=kind)
                continue
            value = _clean(raw.get(field))
            if not value:
                issue("missing_lineage_id", kind=kind, field=field)
                continue
            if value in result:
                issue("duplicate_lineage_id", kind=kind, field=field, value=value)
                continue
            result[value] = raw
        return result

    finding_index = index_unique(findings, "finding_id", "finding")
    assessment_index = index_unique(assessments, "assessment_id", "assessment")
    observation_index = index_unique(observations, "observation_id", "observation")
    record_index = index_unique(records, "record_key", "record")
    conflict_index = index_unique(source_conflicts, "conflict_id", "source_conflict")
    source_claim_ids = {_clean(value) for value in source_claims if _clean(value)}

    for assessment_id, assessment in assessment_index.items():
        observation_id = _clean(assessment.get("observation_id"))
        if observation_id not in observation_index:
            issue(
                "assessment_observation_missing",
                assessment_id=assessment_id,
                observation_id=observation_id,
            )

    # Source-conflict rows and the source_claims lookup must agree in both
    # directions so contradiction IDs cannot point to detached synthetic claims.
    claims_in_conflicts: set[str] = set()
    for conflict_id, conflict in conflict_index.items():
        claims = conflict.get("claims") or []
        if not isinstance(claims, list):
            issue("invalid_source_conflict_claims", conflict_id=conflict_id)
            continue
        for raw_claim in claims:
            if not isinstance(raw_claim, dict):
                issue("invalid_source_conflict_claim", conflict_id=conflict_id)
                continue
            claim_id = _clean(raw_claim.get("claim_id"))
            if not claim_id:
                issue("missing_source_claim_id", conflict_id=conflict_id)
                continue
            claims_in_conflicts.add(claim_id)
            if claim_id not in source_claim_ids:
                issue(
                    "source_conflict_claim_missing_from_index",
                    conflict_id=conflict_id,
                    claim_id=claim_id,
                )
    for claim_id in sorted(source_claim_ids - claims_in_conflicts):
        issue("source_claim_detached_from_conflict", claim_id=claim_id)

    for finding_id, finding in finding_index.items():
        assessment_id = _clean(finding.get("assessment_id"))
        observation_id = _clean(finding.get("observation_id"))
        assessment = assessment_index.get(assessment_id)
        if assessment is None:
            issue(
                "finding_assessment_missing",
                finding_id=finding_id,
                assessment_id=assessment_id,
            )
        elif _clean(assessment.get("observation_id")) != observation_id:
            issue(
                "finding_assessment_observation_mismatch",
                finding_id=finding_id,
                assessment_id=assessment_id,
                observation_id=observation_id,
                assessment_observation_id=_clean(assessment.get("observation_id")),
            )
        if observation_id not in observation_index:
            issue(
                "finding_observation_missing",
                finding_id=finding_id,
                observation_id=observation_id,
            )

        support_ids = [
            _clean(value)
            for value in (finding.get("supporting_evidence_ids") or [])
            if _clean(value)
        ]
        if not support_ids:
            issue("finding_without_supporting_evidence", finding_id=finding_id)
        support_chain = finding.get("supporting_evidence") or []
        if not isinstance(support_chain, list):
            issue("invalid_support_chain", finding_id=finding_id)
            support_chain = []
        chain_index: dict[str, dict[str, Any]] = {}
        for raw_chain in support_chain:
            if not isinstance(raw_chain, dict):
                issue("invalid_support_chain_entry", finding_id=finding_id)
                continue
            evidence_id = _clean(raw_chain.get("evidence_id"))
            if not evidence_id:
                issue("missing_support_chain_id", finding_id=finding_id)
                continue
            if evidence_id in chain_index:
                issue(
                    "duplicate_support_chain_id",
                    finding_id=finding_id,
                    evidence_id=evidence_id,
                )
            chain_index[evidence_id] = raw_chain
            if _clean(raw_chain.get("observation_id")) != observation_id:
                issue(
                    "support_chain_observation_mismatch",
                    finding_id=finding_id,
                    evidence_id=evidence_id,
                )
            if not bool(raw_chain.get("resolved")):
                issue(
                    "unresolved_supporting_evidence",
                    finding_id=finding_id,
                    evidence_id=evidence_id,
                )
            for record_key in raw_chain.get("source_record_keys") or []:
                key = _clean(record_key)
                if key not in record_index:
                    issue(
                        "support_record_missing",
                        finding_id=finding_id,
                        evidence_id=evidence_id,
                        record_key=key,
                    )
            embedded_records = raw_chain.get("source_records") or []
            if not isinstance(embedded_records, list):
                issue(
                    "invalid_embedded_source_records",
                    finding_id=finding_id,
                    evidence_id=evidence_id,
                )
                embedded_records = []
            embedded_keys = {
                _clean(item.get("record_key"))
                for item in embedded_records
                if isinstance(item, dict) and _clean(item.get("record_key"))
            }
            declared_keys = {
                _clean(value)
                for value in raw_chain.get("source_record_keys") or []
                if _clean(value)
            }
            if embedded_keys != declared_keys:
                issue(
                    "embedded_record_keys_mismatch",
                    finding_id=finding_id,
                    evidence_id=evidence_id,
                    declared=sorted(declared_keys),
                    embedded=sorted(embedded_keys),
                )
            for key in embedded_keys & set(record_index):
                canonical = record_index[key]
                embedded = next(
                    item for item in embedded_records
                    if isinstance(item, dict) and _clean(item.get("record_key")) == key
                )
                for field in (
                    "platform",
                    "native_id",
                    "canonical_url",
                    "original_text_sha256",
                    "schema_version",
                ):
                    if embedded.get(field) != canonical.get(field):
                        issue(
                            "embedded_record_payload_mismatch",
                            finding_id=finding_id,
                            evidence_id=evidence_id,
                            record_key=key,
                            field=field,
                        )

        missing_chain = sorted(set(support_ids) - set(chain_index))
        extra_chain = sorted(set(chain_index) - set(support_ids))
        if missing_chain:
            issue(
                "missing_support_chain_entries",
                finding_id=finding_id,
                evidence_ids=missing_chain,
            )
        if extra_chain:
            issue(
                "undeclared_support_chain_entries",
                finding_id=finding_id,
                evidence_ids=extra_chain,
            )
        declared_unresolved = {
            _clean(value)
            for value in finding.get("unresolved_supporting_evidence_ids") or []
            if _clean(value)
        }
        actual_unresolved = {
            evidence_id
            for evidence_id, chain in chain_index.items()
            if not bool(chain.get("resolved"))
        }
        if declared_unresolved != actual_unresolved:
            issue(
                "unresolved_support_index_mismatch",
                finding_id=finding_id,
                declared=sorted(declared_unresolved),
                actual=sorted(actual_unresolved),
            )

        contradiction_ids = {
            _clean(value)
            for value in finding.get("contradicting_evidence_ids") or []
            if _clean(value)
        }
        missing_contradictions = sorted(contradiction_ids - source_claim_ids)
        if missing_contradictions:
            issue(
                "contradicting_source_claim_missing",
                finding_id=finding_id,
                claim_ids=missing_contradictions,
            )
        conflict_ids = {
            _clean(value)
            for value in finding.get("source_conflict_ids") or []
            if _clean(value)
        }
        missing_conflicts = sorted(conflict_ids - set(conflict_index))
        if missing_conflicts:
            issue(
                "source_conflict_missing",
                finding_id=finding_id,
                conflict_ids=missing_conflicts,
            )
        if contradiction_ids and not conflict_ids:
            issue("contradictions_without_conflict", finding_id=finding_id)
        if contradiction_ids and conflict_ids:
            claims_for_conflicts = {
                _clean(claim.get("claim_id"))
                for conflict_id in conflict_ids
                if conflict_id in conflict_index
                for claim in (conflict_index[conflict_id].get("claims") or [])
                if isinstance(claim, dict)
            }
            detached = sorted(contradiction_ids - claims_for_conflicts)
            if detached:
                issue(
                    "contradiction_not_in_finding_conflict",
                    finding_id=finding_id,
                    claim_ids=detached,
                )

    counts = payload.get("counts") or {}
    if isinstance(counts, dict):
        expected_counts = {
            "records": len(record_index),
            "observations": len(observation_index),
            "assessments": len(assessment_index),
            "findings": len(finding_index),
            "source_conflicts": len(conflict_index),
        }
        for key, expected in expected_counts.items():
            if int(counts.get(key, -1)) != expected:
                issue(
                    "lineage_count_mismatch",
                    field=key,
                    declared=counts.get(key),
                    actual=expected,
                )
    else:
        issue("invalid_lineage_counts")

    return {
        "status": "pass" if not issues else "fail",
        "schema_version": str(payload.get("schema_version") or ""),
        "counts": {
            "findings": len(finding_index),
            "assessments": len(assessment_index),
            "observations": len(observation_index),
            "records": len(record_index),
            "source_conflicts": len(conflict_index),
        },
        "issues": issues,
    }


def load_lineage_index(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Evidence lineage must contain a JSON object.")
    return payload


def save_lineage_index(payload: dict[str, Any], path: str | Path) -> str:
    validation = validate_lineage_index(payload)
    if validation["status"] != "pass":
        codes = ", ".join(item["code"] for item in validation["issues"][:8])
        raise ValueError(f"Evidence lineage is internally inconsistent: {codes}")
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(target)


def load_dataset_metadata(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    metadata = source.with_suffix(".metadata.json")
    if not metadata.is_file():
        return {}
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def provenance_document(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    kind = "provenance"
    if source.name.endswith(".import.json"):
        kind = "import_manifest"
    elif source.name.endswith(".coverage.json"):
        kind = "collection_coverage"
    elif source.name.endswith(".metadata.json"):
        kind = "dataset_metadata"
    return {"name": source.name, "kind": kind, "sha256": digest}
