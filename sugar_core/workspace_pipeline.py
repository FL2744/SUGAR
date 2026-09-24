from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .workspace import SugarWorkspace


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_reference(workspace: SugarWorkspace, path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    try:
        relative = resolved.relative_to(workspace.root)
    except ValueError:
        return {"path": str(resolved), "external": True}
    return {"path": relative.as_posix(), "external": False}


def derivation_metadata(
    workspace: SugarWorkspace,
    output: str | Path,
    inputs: Iterable[str | Path],
    *,
    operation: str,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = Path(output).expanduser().resolve(strict=True)
    input_rows = []
    seen: set[Path] = set()
    for raw in inputs:
        source = Path(raw).expanduser().resolve()
        if source == target or source in seen or not source.is_file():
            continue
        seen.add(source)
        input_rows.append({**_portable_reference(workspace, source), "sha256": _sha256(source), "bytes": source.stat().st_size})
    return {
        "operation": operation,
        "software_version": __version__,
        "output_sha256": _sha256(target),
        "inputs": input_rows,
        "parameters": parameters or {},
    }


def _reference_path(workspace: SugarWorkspace, reference: dict[str, Any]) -> Path:
    raw = Path(str(reference.get("path") or ""))
    if reference.get("external"):
        return raw.expanduser().resolve()
    return (workspace.root / raw).resolve()


def pipeline_report(workspace: SugarWorkspace) -> dict[str, Any]:
    """Inspect recorded artifact derivations and return a downstream rebuild order."""
    artifacts = workspace.list_artifacts()
    nodes: dict[str, dict[str, Any]] = {}
    by_path: dict[str, list[str]] = {}
    for artifact in artifacts:
        pipeline = artifact.metadata.get("pipeline") if isinstance(artifact.metadata, dict) else None
        if not isinstance(pipeline, dict):
            continue
        node_id = f"{artifact.kind}:{artifact.path}"
        path = workspace.artifact_absolute_path(artifact)
        inputs = pipeline.get("inputs") or []
        input_statuses = []
        for reference in inputs:
            source = _reference_path(workspace, reference)
            if not source.is_file():
                state = "missing"
            else:
                state = "same" if _sha256(source) == str(reference.get("sha256") or "") else "changed"
            input_statuses.append({"path": reference.get("path", ""), "status": state})
        if not path.is_file():
            state = "missing_output"
        elif _sha256(path) != str(pipeline.get("output_sha256") or ""):
            state = "modified_output"
        elif any(item["status"] == "missing" for item in input_statuses):
            state = "missing_input"
        elif any(item["status"] == "changed" for item in input_statuses):
            state = "stale"
        else:
            state = "fresh"
        nodes[node_id] = {
            "node_id": node_id,
            "kind": artifact.kind,
            "path": artifact.path,
            "absolute_path": str(path),
            "operation": str(pipeline.get("operation") or ""),
            "software_version": str(pipeline.get("software_version") or ""),
            "parameters": pipeline.get("parameters") or {},
            "state": state,
            "input_statuses": input_statuses,
            "inputs": inputs,
            "artifact_id": artifact.id,
        }
        by_path.setdefault(str(path), []).append(node_id)

    edges: list[dict[str, str]] = []
    dependents: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for node_id, node in nodes.items():
        for reference in node["inputs"]:
            path = str(_reference_path(workspace, reference))
            for upstream in by_path.get(path, []):
                if upstream == node_id:
                    continue
                edges.append({"source": upstream, "target": node_id})
                dependents.setdefault(upstream, set()).add(node_id)

    stale_states = {"stale", "missing_input", "missing_output", "modified_output"}
    queue = [node_id for node_id, node in nodes.items() if node["state"] in stale_states]
    stale = set(queue)
    while queue:
        current = queue.pop(0)
        for downstream in dependents.get(current, set()):
            if downstream not in stale:
                stale.add(downstream)
                nodes[downstream]["state"] = "stale_upstream"
                queue.append(downstream)

    # Dependency depth gives a stable upstream-first rebuild sequence.
    adjacency = {node_id: set() for node_id in nodes}
    indegree = {node_id: 0 for node_id in nodes}
    for edge in edges:
        adjacency[edge["source"]].add(edge["target"])
        indegree[edge["target"]] += 1
    ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for downstream in sorted(adjacency[current]):
            indegree[downstream] -= 1
            if indegree[downstream] == 0:
                ready.append(downstream)
                ready.sort()
    rebuild_order = [node_id for node_id in order if node_id in stale]
    return {
        "workspace": str(workspace.root),
        "tracked_derivations": len(nodes),
        "edges": edges,
        "nodes": [nodes[node_id] for node_id in sorted(nodes)],
        "stale_count": len(stale),
        "incremental_rebuild_order": rebuild_order,
        "guardrails": [
            "Only operations that recorded inputs and output hashes participate in this graph.",
            "SUGAR reports the affected upstream-first order; it does not replay an operation without an explicit user review/action.",
            "External input paths must remain available on this machine to verify their hashes.",
        ],
    }
