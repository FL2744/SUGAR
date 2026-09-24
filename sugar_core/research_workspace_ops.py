from __future__ import annotations

from typing import Any, Callable

from .research_workspace import (
    ResearchWorkspaceManager,
    import_project_bundle,
    user_support_payload,
)
from .workspace import SugarWorkspace

ProgressCallback = Callable[[str, dict[str, Any]], None]

RESEARCH_WORKSPACE_OPERATIONS = {
    "workspace-research-status",
    "workspace-subproject-add",
    "workspace-collaborator-add",
    "workspace-institutions-import",
    "workspace-layer-add",
    "workspace-listening-add",
    "workspace-listening-run",
    "workspace-map",
    "workspace-conversations",
    "workspace-share",
    "workspace-share-import",
    "workspace-history",
    "workspace-help",
}


def _notify(progress: ProgressCallback | None, event: str, **values: Any) -> None:
    if progress is not None:
        progress(event, values)


def _workspace_path(config: dict[str, Any]) -> str:
    value = str(config.get("workspace") or config.get("path") or "").strip()
    if not value:
        raise ValueError("workspace is required.")
    return value


def _manager(config: dict[str, Any]) -> ResearchWorkspaceManager:
    return ResearchWorkspaceManager(SugarWorkspace.open(_workspace_path(config)))


def run_research_workspace_operation(
    operation: str,
    config: dict[str, Any],
    secrets: dict[str, str] | None = None,
    progress: ProgressCallback | None = None,
) -> list[str]:
    if operation not in RESEARCH_WORKSPACE_OPERATIONS:
        raise ValueError(f"Unsupported research workspace operation: {operation}")
    secrets = secrets or {}

    if operation == "workspace-share-import":
        bundle = str(config.get("bundle") or config.get("input_file") or "").strip()
        destination = str(config.get("destination") or config.get("workspace") or "").strip()
        if not bundle or not destination:
            raise ValueError("bundle and destination are required.")
        workspace = import_project_bundle(
            bundle,
            destination,
            overwrite=bool(config.get("overwrite", False)),
        )
        manager = ResearchWorkspaceManager(workspace)
        _notify(progress, "workspace_research_status", **manager.status())
        return [str(workspace.manifest_path), str(manager.state_path)]

    if operation == "workspace-help":
        _notify(progress, "workspace_help", **user_support_payload())
        return []

    manager = _manager(config)

    if operation == "workspace-research-status":
        _notify(progress, "workspace_research_status", **manager.status())
        return [str(manager.state_path)]

    if operation == "workspace-subproject-add":
        item = manager.add_subproject(
            str(config.get("name") or ""),
            description=str(config.get("description") or ""),
            parent_id=str(config.get("parent_id") or ""),
            status=str(config.get("status") or "active"),
            tags=config.get("tags") or [],
        )
        _notify(progress, "workspace_subproject", subproject=item.__dict__)
        _notify(progress, "workspace_research_status", **manager.status())
        return [str(manager.state_path)]

    if operation == "workspace-collaborator-add":
        item = manager.add_collaborator(
            str(config.get("name") or ""),
            email=str(config.get("email") or ""),
            role=str(config.get("role") or "viewer"),
        )
        _notify(progress, "workspace_collaborator", collaborator=item.__dict__)
        _notify(progress, "workspace_research_status", **manager.status())
        return [str(manager.state_path)]

    if operation == "workspace-institutions-import":
        source = str(config.get("input_file") or config.get("source") or "").strip()
        if not source:
            raise ValueError("input_file is required.")
        result = manager.import_institutions(
            source,
            subproject_id=str(config.get("subproject_id") or ""),
            replace_existing=not bool(config.get("keep_existing", False)),
        )
        _notify(progress, "workspace_institutions", **result)
        _notify(progress, "workspace_research_status", **manager.status())
        return [str(manager.state_path)]

    if operation == "workspace-layer-add":
        source = str(config.get("input_file") or config.get("source") or "").strip()
        if not source:
            raise ValueError("input_file is required.")
        layer = manager.add_reference_layer(
            source,
            name=str(config.get("name") or ""),
            subproject_id=str(config.get("subproject_id") or ""),
            kind=str(config.get("kind") or "reference"),
            visible=not bool(config.get("hidden", False)),
            copy_into_workspace=not bool(config.get("external", False)),
        )
        _notify(progress, "workspace_reference_layer", layer=layer.__dict__)
        _notify(progress, "workspace_research_status", **manager.status())
        return [str(manager._resolve_layer_path(layer.__dict__)), str(manager.state_path)]

    if operation == "workspace-listening-add":
        post = manager.add_listening_post(
            str(config.get("name") or ""),
            subproject_id=str(config.get("subproject_id") or ""),
            entity_ids=config.get("entity_ids") or [],
            handles=config.get("handles") or [],
            query_terms=config.get("query_terms") or config.get("terms") or [],
            sources=config.get("sources") or ["bilibili"],
            cadence=str(config.get("cadence") or "manual"),
            enabled=not bool(config.get("disabled", False)),
        )
        _notify(progress, "workspace_listening_post", listening_post=post.__dict__)
        _notify(progress, "workspace_research_status", **manager.status())
        return [str(manager.state_path)]

    if operation == "workspace-listening-run":
        listening_post_id = str(config.get("listening_post_id") or "").strip()
        if not listening_post_id:
            raise ValueError("listening_post_id is required.")
        reserved = {
            "workspace",
            "path",
            "listening_post_id",
            "command",
        }
        overrides = {key: value for key, value in config.items() if key not in reserved}
        result = manager.run_listening_post(
            listening_post_id,
            secrets=secrets,
            overrides=overrides,
            progress=progress,
        )
        _notify(progress, "workspace_listening_result", **result)
        _notify(progress, "workspace_research_status", **manager.status())
        return [*result["outputs"], result["delta"], str(manager.state_path)]

    if operation == "workspace-map":
        output = str(config.get("output_file") or "").strip() or None
        outputs = manager.create_map(
            output,
            subproject_id=str(config.get("subproject_id") or ""),
            include_closed=not bool(config.get("exclude_closed", False)),
        )
        _notify(progress, "workspace_map", outputs=outputs)
        return outputs

    if operation == "workspace-conversations":
        records = str(config.get("records") or config.get("input_file") or "").strip()
        if not records:
            raise ValueError("records is required.")
        output = str(config.get("output_file") or "").strip() or None
        outputs = manager.build_conversation_view(
            records,
            output_file=output,
            subproject_id=str(config.get("subproject_id") or ""),
        )
        _notify(progress, "workspace_conversations", outputs=outputs)
        return outputs

    if operation == "workspace-share":
        output = str(config.get("output_file") or "").strip() or None
        bundle = manager.export_share_bundle(output)
        _notify(progress, "workspace_share", output=bundle)
        return [bundle]

    if operation == "workspace-history":
        rows = manager.search_history(
            str(config.get("query") or ""),
            subproject_id=str(config.get("subproject_id") or ""),
        )
        _notify(progress, "workspace_history", history=rows)
        return [str(manager.state_path)]

    raise AssertionError(operation)
