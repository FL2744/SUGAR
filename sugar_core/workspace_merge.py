from __future__ import annotations

import hashlib
import json
import shutil
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlsplit

from .models import PostRecord, merge_record
from .state_workflow import load_state_assessments, save_state_assessments
from .storage import save_records
from .triage_io import load_post_records
from .workspace import SugarWorkspace


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_host(record: PostRecord) -> str:
    if record.source_host:
        return record.source_host.strip().casefold()
    try:
        return (urlsplit(record.canonical_url or record.source_url).hostname or "").casefold()
    except ValueError:
        return ""


def _assessment_conflicts(items: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for contributor, assessment in items:
        grouped[assessment.observation_id].append({
            "contributor": contributor,
            "assessment": asdict(assessment),
        })
    conflicts = []
    for observation_id, entries in sorted(grouped.items()):
        if len(entries) < 2:
            continue
        semantic = {
            json.dumps(entry["assessment"], sort_keys=True, ensure_ascii=False, default=str)
            for entry in entries
        }
        if len(semantic) > 1:
            conflicts.append({"observation_id": observation_id, "assessments": entries})
    return conflicts


def merge_workspaces(
    destination: str | Path,
    sources: Iterable[str | Path],
    *,
    name: str = "Merged SUGAR Research",
) -> dict[str, Any]:
    """Merge project artifacts, canonical evidence, and review records with provenance."""
    target_path = Path(destination).expanduser().resolve()
    source_workspaces = [SugarWorkspace.open(path) for path in sources]
    if not source_workspaces:
        raise ValueError("Provide at least one source SUGAR project.")
    source_ids = [workspace.manifest.project_id for workspace in source_workspaces]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("The same SUGAR project was supplied more than once.")
    if any(workspace.root == target_path for workspace in source_workspaces):
        raise ValueError("The destination project cannot also be a merge source.")

    destination_workspace = SugarWorkspace.create(target_path, name=name, exist_ok=True)
    import_root = destination_workspace.root / "data" / "merged"
    import_root.mkdir(parents=True, exist_ok=True)
    deduplicated: dict[str, Path] = {}
    dedup_sources: dict[str, list[dict[str, str]]] = defaultdict(list)
    imported: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    schema_versions: set[str] = set()
    software_versions: set[str] = set()
    records_by_key: dict[str, PostRecord] = {}
    record_contributors: dict[str, set[str]] = defaultdict(set)
    assessment_inputs: list[tuple[str, Any]] = []
    search_branch_rows: list[dict[str, Any]] = []
    record_schema_versions: set[str] = set()
    assessment_schema_versions: set[str] = set()
    source_statuses = []

    for source in source_workspaces:
        contributor = source.manifest.name
        status = source.status()
        source_statuses.append({
            "project_id": source.manifest.project_id,
            "name": contributor,
            "workspace_schema_version": source.manifest.schema_version,
            "software_version": status.get("software_version", "unknown"),
        })
        software_versions.add(str(status.get("software_version") or "unknown"))
        schema_versions.add(str(source.manifest.schema_version))
        for artifact in source.list_artifacts():
            source_path = source.artifact_absolute_path(artifact)
            source_hash = _sha256(source_path) if source_path.is_file() else ""
            row = {
                "contributor": contributor,
                "project_id": source.manifest.project_id,
                "kind": artifact.kind,
                "source_path": artifact.path,
                "sha256": source_hash,
                "status": "missing" if not source_hash else "copied",
            }
            if not source_path.is_file():
                missing.append(row)
                imported.append(row)
                continue

            for key in ("schema_version", "software_version"):
                value = artifact.metadata.get(key)
                if value:
                    (schema_versions if key == "schema_version" else software_versions).add(str(value))
            if artifact.kind in {"evidence", "raw_collection", "import"} and source_path.suffix.casefold() in {".csv", ".jsonl"}:
                try:
                    for record in load_post_records(source_path):
                        record_schema_versions.add(str(record.schema_version or "unknown"))
                        key = record.record_key
                        if not key:
                            continue
                        record_contributors[key].add(contributor)
                        if key in records_by_key:
                            merge_record(records_by_key[key], record)
                        else:
                            records_by_key[key] = record
                except (ValueError, OSError, KeyError):
                    pass
            if artifact.kind == "state_assessments" and source_path.suffix.casefold() in {".jsonl", ".csv"}:
                try:
                    loaded_assessments = load_state_assessments(source_path)
                    assessment_schema_versions.update(str(item.schema_version or "unknown") for item in loaded_assessments)
                    assessment_inputs.extend((contributor, item) for item in loaded_assessments)
                except (ValueError, OSError, KeyError):
                    pass
            if artifact.kind == "search_plan" and source_path.suffix.casefold() == ".json":
                try:
                    plan_payload = json.loads(source_path.read_text(encoding="utf-8-sig"))
                    for branch in plan_payload.get("branches") or []:
                        query = str(branch.get("query") or "").strip()
                        if query:
                            search_branch_rows.append({
                                "contributor": contributor,
                                "project_id": source.manifest.project_id,
                                "branch_id": str(branch.get("branch_id") or ""),
                                "query": query,
                                "status": str(branch.get("status") or ""),
                                "metrics": branch.get("metrics"),
                            })
                except (ValueError, OSError, AttributeError):
                    pass

            if source_hash in deduplicated:
                merged_path = deduplicated[source_hash]
                row["status"] = "deduplicated_identical_bytes"
            else:
                relative = PurePosixPath(artifact.path)
                if artifact.external or relative.is_absolute() or ".." in relative.parts or "\\" in artifact.path:
                    relative = PurePosixPath(source_path.name)
                merged_path = (import_root / source.manifest.project_id / Path(*relative.parts)).resolve()
                merged_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, merged_path)
                if _sha256(merged_path) != source_hash:
                    raise IOError(f"Hash verification failed after copying {source_path}.")
                deduplicated[source_hash] = merged_path
            row["merged_path"] = merged_path.relative_to(destination_workspace.root).as_posix()
            metadata = dict(artifact.metadata)
            dedup_sources[source_hash].append({
                "contributor": contributor,
                "source_project_id": source.manifest.project_id,
                "source_artifact_path": artifact.path,
                "sha256": source_hash,
            })
            metadata["merge_provenance"] = dedup_sources[source_hash]
            destination_workspace.register_artifact(
                artifact.kind,
                merged_path,
                label=artifact.label or f"Merged from {contributor}",
                metadata=metadata,
            )
            imported.append(row)

    merged_records_path = destination_workspace.path_for("raw") / "merged_evidence.csv"
    if records_by_key:
        for key, record in records_by_key.items():
            stats = dict(record.raw_stats)
            stats["project_merge"] = {
                "contributors": sorted(record_contributors[key]),
                "canonical_record_key": key,
            }
            record.raw_stats = stats
        save_records(list(records_by_key.values()), merged_records_path)
        destination_workspace.register_artifact(
            "evidence", merged_records_path,
            label="Deduplicated canonical evidence from merged projects",
            metadata={"operation": "project-merge", "record_count": len(records_by_key)},
        )

    distribution: dict[str, dict[str, int]] = {
        "records_by_platform": {}, "records_by_language": {}, "records_by_contributor": {},
    }
    hosts: set[str] = set()
    dates: list[str] = []
    for key, record in records_by_key.items():
        for dimension, value in (
            ("records_by_platform", record.platform.casefold()),
            ("records_by_language", (record.detected_language or record.platform_language or "unknown").casefold()),
        ):
            distribution[dimension][value] = distribution[dimension].get(value, 0) + 1
        for contributor in record_contributors[key]:
            distribution["records_by_contributor"][contributor] = distribution["records_by_contributor"].get(contributor, 0) + 1
        host = _record_host(record)
        if host:
            hosts.add(host)
        if record.published_at:
            dates.append(record.published_at)
    branch_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in search_branch_rows:
        branch_groups[" ".join(row["query"].casefold().split())].append(row)
    duplicate_query_groups = [
        rows for rows in branch_groups.values()
        if len({row["project_id"] for row in rows}) > 1
    ]

    unique_assessments: dict[tuple[str, str], Any] = {}
    for contributor, assessment in assessment_inputs:
        # Keep all versions in separate contributor artifacts. This combined view includes only
        # unambiguous identical assessments; conflicts remain in the report for human resolution.
        identity = (assessment.observation_id, json.dumps(asdict(assessment), sort_keys=True, ensure_ascii=False, default=str))
        unique_assessments.setdefault(identity, assessment)
    conflicts = _assessment_conflicts(assessment_inputs)
    conflict_ids = {item["observation_id"] for item in conflicts}
    safe_assessments = [item for (obs_id, _), item in unique_assessments.items() if obs_id not in conflict_ids]
    if safe_assessments:
        merged_assessments_path = destination_workspace.path_for("state") / "merged_assessments.jsonl"
        save_state_assessments(safe_assessments, merged_assessments_path)
        destination_workspace.register_artifact(
            "state_assessments", merged_assessments_path,
            label="Merged identical, non-conflicting human review assessments",
            metadata={"operation": "project-merge", "omitted_conflicting_observation_ids": sorted(conflict_ids)},
        )

    report = {
        "schema_version": "1.0",
        "operation": "sugar-project-merge",
        "destination": str(destination_workspace.root),
        "contributors": [
            {"project_id": workspace.manifest.project_id, "name": workspace.manifest.name, "root": str(workspace.root)}
            for workspace in source_workspaces
        ],
        "artifacts": {"imported": len(imported) - len(missing), "identical_byte_deduplications": sum(row["status"] == "deduplicated_identical_bytes" for row in imported), "missing": len(missing)},
        "canonical_evidence": {"unique_record_keys": len(records_by_key), "source_contributors": len(source_workspaces)},
        "human_review_conflicts": conflicts,
        "schema_versions": sorted(schema_versions),
        "software_versions": sorted(software_versions),
        "record_schema_versions": sorted(record_schema_versions),
        "assessment_schema_versions": sorted(assessment_schema_versions),
        "source_project_status": source_statuses,
        "combined_corpus_coverage": {
            "record_distributions": {key: dict(sorted(value.items())) for key, value in distribution.items()},
            "distinct_source_hosts": len(hosts),
            "published_at_min": min(dates) if dates else "",
            "published_at_max": max(dates) if dates else "",
            "search_branches_preserved": len(search_branch_rows),
            "duplicate_query_groups_across_sources": duplicate_query_groups,
            "scope": "Corpus distribution and reused query candidates only; this does not aggregate complete/partial/unavailable collection attempts or establish requirement coverage.",
        },
        "compatibility": "review_required" if len(schema_versions) > 1 or conflicts else "no_detected_conflict",
        "artifact_manifest": imported,
        "guardrails": [
            "Original contributor artifacts are preserved as separate imported files with source IDs and hashes.",
            "Canonical records with the same platform/native ID are combined; every merged row lists contributing projects.",
            "Conflicting analyst assessments are excluded from the combined assessment view and preserved per contributor for review.",
            "No entity aliases or conflicting judgments are silently resolved.",
        ],
    }
    report_path = destination_workspace.path_for("exports") / "research_merge_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    destination_workspace.register_artifact("merge_report", report_path, metadata={"operation": "project-merge"})
    return report
