from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .workspace import ArtifactRecord, SugarWorkspace


HANDOFF_ROLE_KINDS = {
    "research_requirement": "research_requirement",
    "search_plan": "search_plan",
    "normalized_records": "evidence",
    "research_observations": "observations",
    "evidence_lineage": "lineage",
    "human_review_state": "state_assessments",
    "source_conflicts": "source_conflicts",
    "coverage_and_limitations": "limitations",
    "provenance": "provenance",
    "analytic_output": "analytic_output",
}


def optional_workspace(
    path: str | Path | None = None,
    *,
    discover_from: str | Path = ".",
) -> SugarWorkspace | None:
    """Open an explicit workspace or discover one from the current working tree.

    Absence of a workspace is not an error: legacy standalone workflows continue to work.
    An explicit path, however, is strict and must point to a valid SUGAR workspace.
    """
    if path is not None and str(path).strip():
        return SugarWorkspace.open(path)
    try:
        return SugarWorkspace.discover(discover_from)
    except FileNotFoundError:
        return None


def workspace_from_config(config: dict[str, Any], *, discover_from: str | Path = ".") -> SugarWorkspace | None:
    return optional_workspace(config.get("workspace"), discover_from=discover_from)


def choose_output_directory(
    explicit: str | Path | None,
    workspace: SugarWorkspace | None,
    workspace_key: str,
    *,
    fallback: str | Path = ".",
) -> Path:
    if explicit is not None and str(explicit).strip():
        target = Path(explicit).expanduser().resolve()
    elif workspace is not None:
        target = workspace.path_for(workspace_key)
    else:
        target = Path(fallback).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def latest_workspace_artifact_path(
    workspace: SugarWorkspace | None,
    kinds: str | Iterable[str],
    *,
    require_exists: bool = True,
) -> Path | None:
    if workspace is None:
        return None
    if isinstance(kinds, str):
        kinds = [kinds]
    for kind in kinds:
        for artifact in workspace.list_artifacts(kind):
            path = workspace.artifact_absolute_path(artifact)
            if not require_exists or path.exists():
                return path
    return None


def classify_workspace_output(path: str | Path, *, operation: str = "") -> str:
    value = Path(path)
    name = value.name.casefold()
    suffix = value.suffix.casefold()
    operation = operation.casefold()

    if operation == "external-import":
        if name.endswith(".import.json"):
            return "import_manifest"
        if name.endswith(".rejected.jsonl"):
            return "import_rejections"
        if suffix == ".jsonl":
            return "import"
        if suffix in {".csv", ".xlsx"}:
            return "import_view"
        return "import_artifact"
    if operation in {"search", "weibo-investigate", "weibo-qualify"}:
        return "raw_collection"
    if operation in {"harvest", "weibo-seed-harvest"}:
        return "harvest"
    if suffix == ".html" and "map" in name:
        return "map"
    if name.endswith(".lineage.json") or operation in {"lineage", "verify-lineage"}:
        return "lineage"
    if suffix in {".pdf", ".docx"}:
        return "report"
    if "observation" in name or operation == "triage":
        return "observations"
    if "harvest" in name:
        return "harvest"
    if name.startswith("social_search_posts_"):
        return "raw_collection"
    if operation.startswith("intel-") or "intelligence" in name or "hypoth" in name or "tradecraft" in name:
        return "intelligence"
    if operation.startswith("state-") or operation == "state-package":
        return "state"
    if "reference" in name or "us_presence" in name or "entities" in name:
        return "reference"
    return "export"


def register_workspace_outputs(
    workspace: SugarWorkspace | None,
    outputs: Iterable[str | Path],
    *,
    operation: str,
    kind: str | None = None,
    inputs: Iterable[str | Path] = (),
    parameters: dict[str, Any] | None = None,
) -> list[ArtifactRecord]:
    if workspace is None:
        return []
    records: list[ArtifactRecord] = []
    for output in outputs:
        path = Path(output).expanduser().resolve()
        if not path.exists():
            continue
        artifact_kind = kind or classify_workspace_output(path, operation=operation)
        metadata: dict[str, Any] = {"operation": operation}
        input_paths = [Path(value).expanduser().resolve() for value in inputs]
        if input_paths:
            from .workspace_pipeline import derivation_metadata

            metadata["pipeline"] = derivation_metadata(
                workspace,
                path,
                input_paths,
                operation=operation,
                parameters=parameters,
            )
        records.append(
            workspace.register_artifact(
                artifact_kind,
                path,
                metadata=metadata,
            )
        )
    return records


def register_handoff_bundle(
    workspace: SugarWorkspace | None,
    manifest_file: str | Path,
    *,
    archive_file: str | Path | None = None,
) -> list[ArtifactRecord]:
    """Register a handoff manifest and each manifest-listed component in the project catalog."""
    if workspace is None:
        return []
    manifest_path = Path(manifest_file).expanduser().resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Handoff manifest must contain a JSON object.")
    artifacts = payload.get("artifacts") or []
    if not isinstance(artifacts, list):
        raise ValueError("Handoff manifest artifacts must be a JSON array.")

    metadata_base = {
        "operation": "handoff",
        "requirement_id": str(payload.get("requirement_id") or ""),
        "handoff_schema_version": str(payload.get("handoff_schema_version") or ""),
    }
    records = [
        workspace.register_artifact(
            "handoff_manifest",
            manifest_path,
            metadata=metadata_base,
        )
    ]
    bundle_root = manifest_path.parent.resolve()
    for raw in artifacts:
        if not isinstance(raw, dict):
            raise ValueError("Handoff manifest artifact entries must be JSON objects.")
        role = str(raw.get("role") or "").strip()
        relative = Path(str(raw.get("path") or ""))
        if not role or not str(relative):
            raise ValueError("Handoff manifest artifacts require role and path.")
        if relative.is_absolute():
            raise ValueError(f"Handoff artifact path must be relative: {relative}")
        resolved = (bundle_root / relative).resolve()
        try:
            resolved.relative_to(bundle_root)
        except ValueError as exc:
            raise ValueError(f"Handoff artifact path escapes bundle root: {relative}") from exc
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        kind = HANDOFF_ROLE_KINDS.get(role, "handoff_artifact")
        records.append(
            workspace.register_artifact(
                kind,
                resolved,
                metadata={**metadata_base, "handoff_role": role},
            )
        )

    if archive_file:
        archive = Path(archive_file).expanduser().resolve()
        if archive.is_file():
            records.append(workspace.register_artifact("export", archive, metadata=metadata_base))
    return records
