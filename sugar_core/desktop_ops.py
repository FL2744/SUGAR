from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable

from .llm import ARC_BASE_URL, LLMConfig
from .observation_storage import load_observations
from .state_aggregate import save_state_rollups
from .state_conflict_package import package_from_files_with_conflicts
from .state_conflict_review import (
    apply_source_conflict_review_workbook_file,
    export_review_workbook_with_conflict_file,
    workbook_has_source_conflict_decisions,
)
from .state_entities import load_entity_registry, save_query_plan, write_entity_template
from .state_freshness import save_freshness_report
from .state_gaps import save_gap_report
from .state_hypotheses import save_hypothesis_matrix
from .state_intelligence import save_intelligence_packet
from .state_longitudinal import save_longitudinal_comparison
from .state_map import create_state_map
from .state_network import save_state_network
from .state_review import (
    apply_observation_review_workbook_file,
    apply_review_workbook_file,
)
from .state_agentic import save_iterative_agentic_synthesis
from .state_tradecraft import save_tradecraft_audit
from .state_triage import triage_observations
from .state_workflow import (
    apply_us_overlaps,
    audit_state_records,
    blank_state_assessments,
    compare_state_snapshots,
    load_state_assessments,
    load_us_presence_sites,
    save_state_assessments,
    write_us_presence_template,
)
from .workspace import SugarWorkspace
from .workspace_runtime import (
    latest_workspace_artifact_path,
    register_workspace_outputs,
    workspace_from_config,
)

ProgressCallback = Callable[[str, dict[str, Any]], None]

DESKTOP_STATE_OPERATIONS = {
    "state-package",
    "state-map",
    "state-triage",
    "state-review-export",
    "state-review-apply",
    "state-audit",
    "state-diff",
    "state-template-us-sites",
    "state-template-entities",
    "state-query-plan",
}

DESKTOP_INTEL_OPERATIONS = {
    "intel-packet",
    "intel-tradecraft",
    "intel-synthesize",
    "intel-hypotheses",
    "intel-compare",
}

DESKTOP_ANALYTIC_OPERATIONS = DESKTOP_STATE_OPERATIONS | DESKTOP_INTEL_OPERATIONS


def _notify(progress: ProgressCallback | None, event: str, **values: Any) -> None:
    if progress is not None:
        progress(event, values)


def _optional_input_path(
    config: dict[str, Any],
    key: str,
    workspace: SugarWorkspace | None,
    *,
    workspace_kinds: str | Iterable[str] = (),
) -> Path | None:
    raw = str(config.get(key) or "").strip()
    if raw:
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
    kinds = workspace_kinds if workspace_kinds else []
    return latest_workspace_artifact_path(workspace, kinds) if kinds else None


def _required_path(
    config: dict[str, Any],
    key: str,
    *,
    workspace: SugarWorkspace | None = None,
    workspace_kinds: str | Iterable[str] = (),
    directory: bool = False,
) -> Path:
    raw = str(config.get(key) or "").strip()
    if raw:
        path = Path(raw).expanduser()
        if directory:
            path.mkdir(parents=True, exist_ok=True)
            return path.resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        return path.resolve()
    if not directory and workspace is not None and workspace_kinds:
        candidate = latest_workspace_artifact_path(workspace, workspace_kinds)
        if candidate is not None:
            return candidate
    raise ValueError(f"{key} is required.")


def _output_path(
    config: dict[str, Any],
    key: str,
    default_name: str,
    *,
    workspace: SugarWorkspace | None = None,
    workspace_key: str = "exports",
) -> Path:
    raw = str(config.get(key) or "").strip()
    if raw:
        target = Path(raw).expanduser()
    elif workspace is not None:
        target = workspace.path_for(workspace_key) / default_name
    else:
        directory = Path(str(config.get("output_directory") or Path.cwd())).expanduser()
        target = directory / default_name
    target.parent.mkdir(parents=True, exist_ok=True)
    return target.resolve()


def _output_directory(
    config: dict[str, Any],
    *,
    workspace: SugarWorkspace | None = None,
    workspace_key: str = "exports",
) -> Path:
    raw = str(config.get("output_directory") or "").strip()
    if raw:
        target = Path(raw).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        return target
    if workspace is not None:
        return workspace.path_for(workspace_key)
    raise ValueError("output_directory is required outside a SUGAR workspace.")


def _llm_config(config: dict[str, Any], secrets: dict[str, str]) -> LLMConfig:
    raw = config.get("llm") or {}
    provider = str(raw.get("provider") or "openai").strip().casefold()
    model = str(raw.get("model") or "gpt-5.6-luna").strip()
    base_url = str(raw.get("base_url") or "").strip()
    api_key = str(secrets.get("llm_api_key") or "").strip()
    if not api_key:
        raise ValueError("An LLM API key is required for this operation.")
    if provider == "arc" and not base_url:
        base_url = ARC_BASE_URL
    if provider == "custom" and not base_url:
        raise ValueError("A base URL is required for a custom LLM endpoint.")
    if provider not in {"openai", "arc", "custom"}:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    return LLMConfig(provider=provider, model=model, api_key=api_key, base_url=base_url)


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return str(path.resolve())


def _loaded_state_inputs(config: dict[str, Any], workspace: SugarWorkspace | None):
    observations_path = _required_path(
        config,
        "observations",
        workspace=workspace,
        workspace_kinds=("observations",),
    )
    observations = load_observations(observations_path)
    assessment_path = _optional_input_path(
        config,
        "assessments",
        workspace,
        workspace_kinds=("state_assessments",),
    )
    assessments = load_state_assessments(assessment_path) if assessment_path else blank_state_assessments(observations)
    sites_path = _optional_input_path(config, "us_sites", workspace)
    sites = load_us_presence_sites(sites_path) if sites_path else []
    if sites:
        assessments = apply_us_overlaps(observations, assessments, sites)
    return observations, assessments, sites


def _register(
    workspace: SugarWorkspace | None,
    outputs: Iterable[str | Path],
    *,
    operation: str,
    kind: str | None = None,
) -> list[str]:
    values = [str(Path(value).expanduser().resolve()) for value in outputs]
    register_workspace_outputs(workspace, values, operation=operation, kind=kind)
    return values


def _run_state_package(
    config: dict[str, Any],
    progress: ProgressCallback | None,
    workspace: SugarWorkspace | None,
) -> list[str]:
    observations_file = _required_path(
        config,
        "observations",
        workspace=workspace,
        workspace_kinds=("observations",),
    )
    out_dir = _output_directory(config, workspace=workspace, workspace_key="state")
    assessment_path = _optional_input_path(config, "assessments", workspace, workspace_kinds=("state_assessments",))
    us_sites_path = _optional_input_path(config, "us_sites", workspace)
    source_conflicts_path = _optional_input_path(config, "source_conflicts", workspace)
    entities_path = _optional_input_path(config, "entities", workspace)
    previous_path = _optional_input_path(config, "previous_assessments", workspace)
    name = str(config.get("name") or "state_research").strip() or "state_research"
    title = str(config.get("title") or "State-Supported Public Engagement Research Update").strip()
    current_start = str(config.get("current_start") or "2024-01-01").strip()
    stale_days = int(config.get("stale_days", 90))

    _notify(progress, "state_package_stage", stage="core_package")
    outputs = package_from_files_with_conflicts(
        observations_file,
        out_dir,
        assessments_file=assessment_path,
        us_sites_file=us_sites_path,
        previous_assessments_file=previous_path,
        source_conflicts_file=source_conflicts_path,
        name=name,
        title=title,
    )
    observations, assessments, sites = _loaded_state_inputs(
        {
            "observations": str(observations_file),
            "assessments": str(assessment_path) if assessment_path else "",
            "us_sites": str(us_sites_path) if us_sites_path else "",
        },
        workspace,
    )
    registry = load_entity_registry(entities_path) if entities_path else None
    stem = "_".join(name.split())

    _notify(progress, "state_package_stage", stage="assessed_snapshot")
    assessed_snapshot = out_dir / f"{stem}.assessed.jsonl"
    assessed_output = save_state_assessments(assessments, assessed_snapshot)
    outputs.append(assessed_output)

    _notify(progress, "state_package_stage", stage="rollups_network")
    outputs.extend(save_state_rollups(observations, assessments, out_dir, name=name))
    outputs.extend(save_state_network(observations, assessments, out_dir, us_sites=sites, name=name, verified_only=True))

    _notify(progress, "state_package_stage", stage="review_freshness_gaps")
    outputs.append(
        export_review_workbook_with_conflict_file(
            observations,
            assessments,
            out_dir / f"{stem}.review.xlsx",
            source_conflicts_file=source_conflicts_path,
        )
    )
    outputs.append(
        save_freshness_report(
            observations,
            assessments,
            out_dir / f"{stem}.freshness.json",
            current_activity_start=current_start,
            collection_stale_days=stale_days,
        )
    )
    outputs.extend(
        save_gap_report(
            observations,
            assessments,
            out_dir,
            entities=registry,
            us_sites=sites,
            name=name,
            current_activity_start=current_start,
            collection_stale_days=stale_days,
        )
    )

    _notify(progress, "state_package_stage", stage="interactive_map")
    map_dir = workspace.path_for("maps") if workspace is not None else out_dir
    map_path = map_dir / f"{stem}.interactive_map.html"
    map_output = create_state_map(
        observations,
        assessments,
        map_path,
        us_sites=sites,
        verified_only=True,
        include_activity_density=True,
        resolve_missing_locations=bool(config.get("resolve_locations", False)),
        geocode_cache=str(workspace.path_for("cache")) if workspace is not None else config.get("geocode_cache"),
        minimum_location_confidence=float(config.get("min_location_confidence", 0.45)),
    )
    outputs.append(map_output)
    metadata_path = map_path.with_suffix(map_path.suffix + ".metadata.json")
    if metadata_path.is_file():
        outputs.append(str(metadata_path.resolve()))

    lineage_outputs = [value for value in outputs if str(value).endswith(".lineage.json")]
    _register(workspace, [assessed_output], operation="state-package", kind="state_assessments")
    _register(workspace, [map_output, metadata_path], operation="state-package", kind="map")
    _register(workspace, lineage_outputs, operation="state-package", kind="lineage")
    excluded = {
        str(Path(assessed_output).resolve()),
        str(Path(map_output).resolve()),
        str(metadata_path.resolve()),
        *(str(Path(value).resolve()) for value in lineage_outputs),
    }
    other = [value for value in outputs if str(Path(value).resolve()) not in excluded]
    _register(workspace, other, operation="state-package", kind="state")
    return list(dict.fromkeys(str(Path(value).resolve()) for value in outputs))


def run_desktop_analytic_operation(
    operation: str,
    config: dict[str, Any],
    secrets: dict[str, str] | None = None,
    progress: ProgressCallback | None = None,
) -> list[str]:
    """Run a whitelisted State/intelligence desktop operation with typed inputs."""
    secrets = secrets or {}
    if operation not in DESKTOP_ANALYTIC_OPERATIONS:
        raise ValueError(f"Unsupported desktop analytic operation: {operation}")

    workspace = workspace_from_config(config)
    _notify(progress, "starting", operation=operation)

    if operation == "state-package":
        return _run_state_package(config, progress, workspace)

    if operation == "state-map":
        observations, assessments, sites = _loaded_state_inputs(config, workspace)
        target = _output_path(
            config,
            "output_file",
            "state_research.interactive_map.html",
            workspace=workspace,
            workspace_key="maps",
        )
        output = create_state_map(
            observations,
            assessments,
            target,
            us_sites=sites,
            verified_only=not bool(config.get("include_unverified", False)),
            include_activity_density=not bool(config.get("no_density", False)),
            resolve_missing_locations=bool(config.get("resolve_locations", False)),
            geocode_cache=str(workspace.path_for("cache")) if workspace is not None else config.get("geocode_cache"),
            minimum_location_confidence=float(config.get("min_location_confidence", 0.45)),
        )
        metadata = Path(output).with_suffix(Path(output).suffix + ".metadata.json")
        return _register(workspace, [output, metadata], operation=operation, kind="map")

    if operation == "state-triage":
        observations = load_observations(
            _required_path(config, "observations", workspace=workspace, workspace_kinds=("observations",))
        )
        target = _output_path(config, "output_file", "state_triage.jsonl", workspace=workspace, workspace_key="state")
        assessments = triage_observations(
            observations,
            llm=_llm_config(config, secrets),
            cache_dir=str(config.get("cache_dir") or (workspace.path_for("cache") if workspace is not None else ".sugar-cache")),
            limit=int(config["limit"]) if config.get("limit") not in (None, "") else None,
            progress=progress,
        )
        return _register(workspace, [save_state_assessments(assessments, target)], operation=operation, kind="state_assessments")

    if operation == "state-review-export":
        observations = load_observations(_required_path(config, "observations", workspace=workspace, workspace_kinds=("observations",)))
        assessments = load_state_assessments(_required_path(config, "assessments", workspace=workspace, workspace_kinds=("state_assessments",)))
        source_conflicts = _optional_input_path(
            config,
            "source_conflicts",
            workspace,
            workspace_kinds=("source_conflicts",),
        )
        target = _output_path(config, "output_file", "state_review.xlsx", workspace=workspace, workspace_key="state")
        output = export_review_workbook_with_conflict_file(
            observations,
            assessments,
            target,
            source_conflicts_file=source_conflicts,
        )
        return _register(workspace, [output], operation=operation, kind="state_review")

    if operation == "state-review-apply":
        assessments = _required_path(config, "assessments", workspace=workspace, workspace_kinds=("state_assessments",))
        workbook = _required_path(config, "workbook", workspace=workspace, workspace_kinds=("state_review",))
        observations = _optional_input_path(
            config,
            "observations",
            workspace,
            workspace_kinds=("observations",),
        )
        source_conflicts = _optional_input_path(
            config,
            "source_conflicts",
            workspace,
            workspace_kinds=("source_conflicts",),
        )
        has_conflict_decisions = workbook_has_source_conflict_decisions(workbook)
        if has_conflict_decisions and source_conflicts is None:
            raise ValueError(
                "Review workbook contains source-conflict decisions. Provide source_conflicts so they can be validated and applied."
            )

        target = _output_path(config, "output_file", "state_reviewed.jsonl", workspace=workspace, workspace_key="state")
        assessment_output = apply_review_workbook_file(assessments, workbook, target)
        outputs = _register(workspace, [assessment_output], operation=operation, kind="state_assessments")

        if observations is not None:
            observation_target = _output_path(
                config,
                "observations_output_file",
                "observations_reviewed.csv",
                workspace=workspace,
                workspace_key="state",
            )
            observation_outputs = apply_observation_review_workbook_file(
                observations,
                workbook,
                observation_target,
            )
            outputs.extend(
                _register(
                    workspace,
                    observation_outputs,
                    operation=operation,
                    kind="observations",
                )
            )

        if source_conflicts is not None:
            raw_conflict_output = str(config.get("source_conflicts_output_file") or "").strip()
            if raw_conflict_output:
                conflict_target = Path(raw_conflict_output).expanduser().resolve()
            else:
                conflict_target = target.with_name(f"{target.stem}.source_conflicts.json")
            conflict_target.parent.mkdir(parents=True, exist_ok=True)
            conflict_output = apply_source_conflict_review_workbook_file(
                source_conflicts,
                workbook,
                conflict_target,
            )
            outputs.extend(
                _register(
                    workspace,
                    [conflict_output],
                    operation=operation,
                    kind="source_conflicts",
                )
            )

        return list(dict.fromkeys(outputs))

    if operation == "state-audit":
        observations = load_observations(_required_path(config, "observations", workspace=workspace, workspace_kinds=("observations",)))
        assessments = load_state_assessments(_required_path(config, "assessments", workspace=workspace, workspace_kinds=("state_assessments",)))
        target = _output_path(config, "output_file", "state_audit.json", workspace=workspace, workspace_key="state")
        return _register(workspace, [_write_json(target, audit_state_records(observations, assessments))], operation=operation, kind="state")

    if operation == "state-diff":
        previous = load_state_assessments(_required_path(config, "previous", workspace=workspace))
        current = load_state_assessments(_required_path(config, "current", workspace=workspace, workspace_kinds=("state_assessments",)))
        target = _output_path(config, "output_file", "state_diff.json", workspace=workspace, workspace_key="state")
        return _register(workspace, [_write_json(target, compare_state_snapshots(previous, current))], operation=operation, kind="state")

    if operation == "state-template-us-sites":
        target = _output_path(config, "output_file", "us_presence.csv", workspace=workspace, workspace_key="references")
        return _register(workspace, [write_us_presence_template(target)], operation=operation, kind="reference")

    if operation == "state-template-entities":
        target = _output_path(config, "output_file", "monitored_entities.csv", workspace=workspace, workspace_key="references")
        return _register(workspace, [write_entity_template(target)], operation=operation, kind="reference")

    if operation == "state-query-plan":
        registry = load_entity_registry(_required_path(config, "entities", workspace=workspace))
        target = _output_path(config, "output_file", "query_plan.txt", workspace=workspace, workspace_key="state")
        return _register(workspace, [save_query_plan(registry, target)], operation=operation, kind="state")

    if operation == "intel-packet":
        observations = load_observations(_required_path(config, "observations", workspace=workspace, workspace_kinds=("observations",)))
        assessments = load_state_assessments(_required_path(config, "assessments", workspace=workspace, workspace_kinds=("state_assessments",)))
        target = _output_path(config, "output_file", "intelligence_packet.json", workspace=workspace, workspace_key="intelligence")
        output = save_intelligence_packet(
            observations,
            assessments,
            target,
            country=str(config.get("country") or ""),
            observation_id=str(config.get("observation_id") or ""),
            representative_case_limit=max(1, int(config.get("case_limit", 20))),
        )
        return _register(workspace, [output], operation=operation, kind="intelligence")

    if operation == "intel-tradecraft":
        observations = load_observations(_required_path(config, "observations", workspace=workspace, workspace_kinds=("observations",)))
        assessments = load_state_assessments(_required_path(config, "assessments", workspace=workspace, workspace_kinds=("state_assessments",)))
        target = _output_path(config, "output_file", "tradecraft_audit.json", workspace=workspace, workspace_key="intelligence")
        return _register(workspace, [save_tradecraft_audit(observations, assessments, target)], operation=operation, kind="intelligence")

    if operation == "intel-synthesize":
        observations = load_observations(_required_path(config, "observations", workspace=workspace, workspace_kinds=("observations",)))
        assessments = load_state_assessments(_required_path(config, "assessments", workspace=workspace, workspace_kinds=("state_assessments",)))
        out_dir = _output_directory(config, workspace=workspace, workspace_key="intelligence")
        outputs = save_iterative_agentic_synthesis(
            observations,
            assessments,
            out_dir,
            llm=_llm_config(config, secrets),
            country=str(config.get("country") or ""),
            observation_id=str(config.get("observation_id") or ""),
            depth=str(config.get("depth") or "standard"),
            cache_dir=str(config.get("cache_dir") or (workspace.path_for("cache") if workspace is not None else ".sugar-cache")),
            max_workers=max(1, int(config.get("workers", 4))),
            name=str(config.get("name") or "analytic_intelligence"),
        )
        return _register(workspace, outputs, operation=operation, kind="intelligence")

    if operation == "intel-hypotheses":
        synthesis = _required_path(config, "synthesis", workspace=workspace, workspace_kinds=("intelligence",))
        out_dir = _output_directory(config, workspace=workspace, workspace_key="intelligence")
        outputs = save_hypothesis_matrix(
            synthesis,
            out_dir,
            name=str(config.get("name") or "analytic_intelligence"),
        )
        return _register(workspace, outputs, operation=operation, kind="intelligence")

    previous = _required_path(config, "previous", workspace=workspace)
    current = _required_path(config, "current", workspace=workspace, workspace_kinds=("intelligence",))
    target = _output_path(config, "output_file", "intelligence_comparison.json", workspace=workspace, workspace_key="intelligence")
    output = save_longitudinal_comparison(
        previous,
        current,
        target,
        kind=str(config.get("kind") or "synthesis"),
    )
    return _register(workspace, [output], operation=operation, kind="intelligence")
