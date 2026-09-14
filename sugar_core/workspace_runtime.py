from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .workspace import ArtifactRecord, SugarWorkspace


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
        artifact = workspace.latest_artifact(kind)
        if artifact is None:
            continue
        path = workspace.artifact_absolute_path(artifact)
        if not require_exists or path.exists():
            return path
    return None


def classify_workspace_output(path: str | Path, *, operation: str = "") -> str:
    value = Path(path)
    name = value.name.casefold()
    suffix = value.suffix.casefold()
    operation = operation.casefold()

    if suffix == ".html" and "map" in name:
        return "map"
    if suffix in {".pdf", ".docx"}:
        return "report"
    if "observation" in name or operation == "triage":
        return "observations"
    if "harvest" in name or operation in {"harvest", "weibo-seed-harvest"}:
        return "harvest"
    if operation == "search" or name.startswith("social_search_posts_"):
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
) -> list[ArtifactRecord]:
    if workspace is None:
        return []
    records: list[ArtifactRecord] = []
    for output in outputs:
        path = Path(output).expanduser().resolve()
        if not path.exists():
            continue
        artifact_kind = kind or classify_workspace_output(path, operation=operation)
        records.append(
            workspace.register_artifact(
                artifact_kind,
                path,
                metadata={"operation": operation},
            )
        )
    return records
