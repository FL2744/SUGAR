from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .models import SCHEMA_VERSION as POST_SCHEMA_VERSION, PostRecord
from .observation_storage import load_observations
from .observations import OBSERVATION_SCHEMA_VERSION, ResearchObservation
from .research_requirements import (
    REQUIREMENT_SCHEMA_VERSION,
    SEARCH_PLAN_SCHEMA_VERSION,
    ResearchRequirement,
    SearchPlan,
    load_requirement,
    load_search_plan,
)
from .triage_io import load_post_records

HANDOFF_SCHEMA_VERSION = "1.0"
LIMITATIONS_SCHEMA_VERSION = "1.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip(".-")
    return cleaned or "sugar-handoff"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _record_payload(record: PostRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["record_key"] = record.record_key
    return payload


@dataclass(frozen=True)
class HandoffArtifact:
    role: str
    path: str
    sha256: str
    bytes: int


@dataclass(frozen=True)
class HandoffResult:
    directory: str
    manifest: str
    archive: str | None
    artifacts: int


def build_coverage_limitations(
    requirement: ResearchRequirement,
    plan: SearchPlan,
    records: Iterable[PostRecord],
    observations: Iterable[ResearchObservation],
) -> dict[str, Any]:
    records = list(records)
    observations = list(observations)
    platform_counts = Counter(record.platform or "unknown" for record in records)
    platform_counts_folded = Counter((record.platform or "unknown").casefold() for record in records)
    language_counts = Counter(
        (record.detected_language or record.platform_language or "unknown") for record in records
    )
    geography_counts = Counter(
        (observation.country or observation.region or observation.city or "unresolved")
        for observation in observations
    )
    branch_statuses = Counter(branch.status for branch in plan.branches)
    published = sorted(record.published_at for record in records if record.published_at)
    collected = sorted(record.collected_at for record in records if record.collected_at)
    observed_platforms = {key.casefold() for key in platform_counts if key != "unknown"}
    preferred = [source for source in requirement.preferred_sources if source]
    source_coverage = {
        source: {
            "status": "observed" if source.casefold() in observed_platforms else "no_records_or_not_run",
            "records": platform_counts_folded.get(source.casefold(), 0),
        }
        for source in preferred
    }
    limitations = [
        "Counts describe the collected corpus, not the full population of online discussion.",
        "A source with no records is not evidence of zero real-world activity; it may be unrun, unavailable, filtered, or outside the query plan.",
        "Language, geography, and audience attributes are only as complete as the stored evidence and review state.",
    ]
    if any(value["status"] != "observed" for value in source_coverage.values()):
        limitations.append("One or more preferred sources have no observed records in this package; inspect collection events before drawing absence claims.")
    if language_counts.get("unknown", 0):
        limitations.append("Some records have no stored language identification.")
    if geography_counts.get("unresolved", 0):
        limitations.append("Some observations have unresolved geography and must not be treated as geographically absent.")
    return {
        "schema_version": LIMITATIONS_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "requirement_id": requirement.requirement_id,
        "corpus": {
            "records": len(records),
            "observations": len(observations),
            "platform_counts": dict(sorted(platform_counts.items())),
            "language_counts": dict(sorted(language_counts.items())),
            "geography_counts": dict(sorted(geography_counts.items())),
            "published_time_range": [published[0], published[-1]] if published else [],
            "collected_time_range": [collected[0], collected[-1]] if collected else [],
        },
        "search_plan": {
            "branches": len(plan.branches),
            "branch_status_counts": dict(sorted(branch_statuses.items())),
            "collection_runs": sum(event.get("type") == "collection_run" for event in plan.events),
            "branch_evaluations": sum(event.get("type") == "branch_evaluation" for event in plan.events),
        },
        "source_coverage": source_coverage,
        "limitations": limitations,
    }


def _copy_named(source: str | Path, destination_directory: Path, *, preferred_name: str | None = None) -> Path:
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    destination_directory.mkdir(parents=True, exist_ok=True)
    name = _safe_name(preferred_name or source.name)
    target = destination_directory / name
    if target.exists():
        stem, suffix = target.stem, target.suffix
        index = 2
        while target.exists():
            target = destination_directory / f"{stem}-{index}{suffix}"
            index += 1
    shutil.copy2(source, target)
    return target


def _artifact(root: Path, path: Path, role: str) -> HandoffArtifact:
    return HandoffArtifact(
        role=role,
        path=path.relative_to(root).as_posix(),
        sha256=_sha256(path),
        bytes=path.stat().st_size,
    )


def build_handoff_bundle(
    requirement_file: str | Path,
    plan_file: str | Path,
    records_file: str | Path,
    observations_file: str | Path,
    output_directory: str | Path,
    *,
    name: str = "sugar-handoff",
    assessments_file: str | Path | None = None,
    limitations_file: str | Path | None = None,
    analytic_outputs: Iterable[str | Path] = (),
    provenance_files: Iterable[str | Path] = (),
    create_zip: bool = True,
) -> HandoffResult:
    requirement = load_requirement(requirement_file)
    plan = load_search_plan(plan_file)
    if requirement.requirement_id != plan.requirement_id:
        raise ValueError("Research requirement and search plan IDs do not match.")
    records = load_post_records(records_file)
    observations = load_observations(observations_file)
    if not records:
        raise ValueError("Handoff bundle requires at least one canonical source record.")
    if not observations:
        raise ValueError("Handoff bundle requires at least one research observation.")

    output_root = Path(output_directory).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    bundle_name = _safe_name(name)
    final_root = output_root / bundle_name
    archive_path = output_root / f"{bundle_name}.zip"
    if final_root.exists() or (create_zip and archive_path.exists()):
        raise FileExistsError(f"Handoff output already exists for {bundle_name!r} in {output_root}.")

    staging_parent = Path(tempfile.mkdtemp(prefix=f".{bundle_name}-", dir=output_root))
    staging_root = staging_parent / bundle_name
    staging_root.mkdir(parents=True)
    try:
        context = staging_root / "context"
        evidence = staging_root / "evidence"
        review = staging_root / "review"
        provenance = staging_root / "provenance"
        outputs = staging_root / "outputs"

        requirement_path = context / "research-requirement.json"
        plan_path = context / "search-plan.json"
        _write_json(requirement_path, requirement.export_dict())
        _write_json(plan_path, plan.export_dict())
        records_path = evidence / "records.jsonl"
        observations_path = evidence / "observations.jsonl"
        _write_jsonl(records_path, (_record_payload(record) for record in records))
        _write_jsonl(observations_path, (observation.export_dict() for observation in observations))

        artifacts = [
            _artifact(staging_root, requirement_path, "research_requirement"),
            _artifact(staging_root, plan_path, "search_plan"),
            _artifact(staging_root, records_path, "normalized_records"),
            _artifact(staging_root, observations_path, "research_observations"),
        ]

        if assessments_file:
            copied = _copy_named(assessments_file, review, preferred_name="state-assessments" + Path(assessments_file).suffix)
            artifacts.append(_artifact(staging_root, copied, "human_review_state"))

        limitations_path = staging_root / "limitations.json"
        if limitations_file:
            supplied = json.loads(Path(limitations_file).expanduser().resolve().read_text(encoding="utf-8"))
            _write_json(limitations_path, supplied)
        else:
            _write_json(limitations_path, build_coverage_limitations(requirement, plan, records, observations))
        artifacts.append(_artifact(staging_root, limitations_path, "coverage_and_limitations"))

        auto_provenance: list[Path] = []
        records_source = Path(records_file).expanduser().resolve()
        for candidate in (
            Path(f"{records_source.with_suffix('')}.import.json"),
            records_source.with_suffix(".metadata.json"),
        ):
            if candidate.is_file():
                auto_provenance.append(candidate)
        seen_provenance: set[Path] = set()
        for source in [*auto_provenance, *(Path(value).expanduser().resolve() for value in provenance_files)]:
            if source in seen_provenance:
                continue
            seen_provenance.add(source)
            copied = _copy_named(source, provenance)
            artifacts.append(_artifact(staging_root, copied, "provenance"))

        for source in analytic_outputs:
            copied = _copy_named(source, outputs)
            artifacts.append(_artifact(staging_root, copied, "analytic_output"))

        manifest_path = staging_root / "manifest.json"
        manifest = {
            "handoff_schema_version": HANDOFF_SCHEMA_VERSION,
            "generated_at": _utc_now(),
            "software": {"name": "SUGAR", "version": __version__},
            "requirement_id": requirement.requirement_id,
            "schemas": {
                "post_record": POST_SCHEMA_VERSION,
                "research_observation": OBSERVATION_SCHEMA_VERSION,
                "research_requirement": REQUIREMENT_SCHEMA_VERSION,
                "search_plan": SEARCH_PLAN_SCHEMA_VERSION,
                "limitations": LIMITATIONS_SCHEMA_VERSION,
            },
            "counts": {
                "records": len(records),
                "observations": len(observations),
                "analytic_outputs": sum(item.role == "analytic_output" for item in artifacts),
                "provenance_files": sum(item.role == "provenance" for item in artifacts),
            },
            "artifacts": [asdict(item) for item in sorted(artifacts, key=lambda item: item.path)],
            "portability": {
                "paths_relative_to_bundle_root": True,
                "requires_virginia_tech_infrastructure": False,
                "verification": "Verify artifact byte lengths and SHA-256 values against this manifest.",
            },
        }
        _write_json(manifest_path, manifest)

        staged_archive = staging_parent / f"{bundle_name}.zip"
        archive: str | None = None
        if create_zip:
            with zipfile.ZipFile(staged_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive_file:
                for path in sorted(staging_root.rglob("*")):
                    if path.is_file():
                        archive_file.write(path, arcname=(Path(bundle_name) / path.relative_to(staging_root)).as_posix())
        staging_root.replace(final_root)
        if create_zip:
            staged_archive.replace(archive_path)
            archive = str(archive_path)
        staging_parent.rmdir()
        return HandoffResult(
            directory=str(final_root),
            manifest=str(final_root / "manifest.json"),
            archive=archive,
            artifacts=len(artifacts),
        )
    except Exception:
        shutil.rmtree(staging_parent, ignore_errors=True)
        raise


def verify_handoff_bundle(bundle_directory: str | Path) -> dict[str, Any]:
    root = Path(bundle_directory).expanduser().resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("handoff_schema_version") != HANDOFF_SCHEMA_VERSION:
        raise ValueError(f"Unsupported handoff schema: {manifest.get('handoff_schema_version')!r}")
    findings: list[dict[str, Any]] = []
    for artifact in manifest.get("artifacts") or []:
        relative = Path(str(artifact.get("path") or ""))
        if relative.is_absolute() or ".." in relative.parts:
            findings.append({"path": str(relative), "status": "invalid_path"})
            continue
        path = root / relative
        if not path.is_file():
            findings.append({"path": relative.as_posix(), "status": "missing"})
            continue
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            findings.append({"path": relative.as_posix(), "status": "unresolvable"})
            continue
        if not resolved.is_relative_to(root):
            findings.append({"path": relative.as_posix(), "status": "path_escape"})
            continue
        expected_hash = str(artifact.get("sha256") or "")
        expected_bytes = int(artifact.get("bytes") or 0)
        actual_hash = _sha256(path)
        actual_bytes = path.stat().st_size
        status = "ok" if actual_hash == expected_hash and actual_bytes == expected_bytes else "mismatch"
        findings.append({
            "path": relative.as_posix(),
            "status": status,
            "sha256_match": actual_hash == expected_hash,
            "bytes_match": actual_bytes == expected_bytes,
        })
    return {
        "status": "pass" if findings and all(item["status"] == "ok" for item in findings) else "fail",
        "bundle": str(root),
        "artifacts": len(findings),
        "findings": findings,
    }
