from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from .llm import ARC_BASE_URL, LLMConfig
from .observation_storage import load_observations
from .state_aggregate import save_state_rollups
from .state_entities import load_entity_registry, save_query_plan, write_entity_template
from .state_freshness import save_freshness_report
from .state_gaps import save_gap_report
from .state_hypotheses import save_hypothesis_matrix
from .state_intelligence import save_intelligence_packet
from .state_longitudinal import save_longitudinal_comparison
from .state_map import create_state_map
from .state_network import save_state_network
from .state_review import apply_review_workbook_file, export_review_workbook
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
    package_from_files,
    save_state_assessments,
    write_us_presence_template,
)

ProgressCallback = Callable[[str, dict[str, Any]], None]

DESKTOP_STATE_OPERATIONS = {
    "state-package",
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


def _required_path(config: dict[str, Any], key: str, *, directory: bool = False) -> Path:
    raw = str(config.get(key) or "").strip()
    if not raw:
        raise ValueError(f"{key} is required.")
    path = Path(raw).expanduser()
    if directory:
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.resolve()


def _output_path(config: dict[str, Any], key: str, default_name: str) -> Path:
    raw = str(config.get(key) or "").strip()
    if raw:
        target = Path(raw).expanduser()
    else:
        directory = Path(str(config.get("output_directory") or Path.cwd())).expanduser()
        target = directory / default_name
    target.parent.mkdir(parents=True, exist_ok=True)
    return target.resolve()


def _output_directory(config: dict[str, Any]) -> Path:
    raw = str(config.get("output_directory") or "").strip()
    if not raw:
        raise ValueError("output_directory is required.")
    target = Path(raw).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


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


def _loaded_state_inputs(config: dict[str, Any]):
    observations_path = _required_path(config, "observations")
    observations = load_observations(observations_path)
    assessment_path = str(config.get("assessments") or "").strip()
    assessments = load_state_assessments(assessment_path) if assessment_path else blank_state_assessments(observations)
    sites_path = str(config.get("us_sites") or "").strip()
    sites = load_us_presence_sites(sites_path) if sites_path else []
    if sites:
        assessments = apply_us_overlaps(observations, assessments, sites)
    return observations, assessments, sites


def _run_state_package(config: dict[str, Any], progress: ProgressCallback | None) -> list[str]:
    observations_file = _required_path(config, "observations")
    out_dir = _output_directory(config)
    assessment_file = str(config.get("assessments") or "").strip() or None
    us_sites_file = str(config.get("us_sites") or "").strip() or None
    entities_file = str(config.get("entities") or "").strip() or None
    previous_file = str(config.get("previous_assessments") or "").strip() or None
    name = str(config.get("name") or "state_research").strip() or "state_research"
    title = str(config.get("title") or "PRC Cultural Influence Network Research Update").strip()
    current_start = str(config.get("current_start") or "2024-01-01").strip()
    stale_days = int(config.get("stale_days", 90))

    _notify(progress, "state_package_stage", stage="core_package")
    outputs = package_from_files(
        observations_file,
        out_dir,
        assessments_file=assessment_file,
        us_sites_file=us_sites_file,
        previous_assessments_file=previous_file,
        name=name,
        title=title,
    )
    observations, assessments, sites = _loaded_state_inputs(
        {
            "observations": str(observations_file),
            "assessments": assessment_file or "",
            "us_sites": us_sites_file or "",
        }
    )
    registry = load_entity_registry(entities_file) if entities_file else None
    stem = "_".join(name.split())

    _notify(progress, "state_package_stage", stage="assessed_snapshot")
    assessed_snapshot = out_dir / f"{stem}.assessed.jsonl"
    outputs.append(save_state_assessments(assessments, assessed_snapshot))

    _notify(progress, "state_package_stage", stage="rollups_network")
    outputs.extend(save_state_rollups(observations, assessments, out_dir, name=name))
    outputs.extend(save_state_network(observations, assessments, out_dir, us_sites=sites, name=name, verified_only=True))

    _notify(progress, "state_package_stage", stage="review_freshness_gaps")
    outputs.append(export_review_workbook(observations, assessments, out_dir / f"{stem}.review.xlsx"))
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
    map_path = out_dir / f"{stem}.interactive_map.html"
    outputs.append(
        create_state_map(
            observations,
            assessments,
            map_path,
            us_sites=sites,
            verified_only=True,
            include_activity_density=True,
        )
    )
    metadata_path = map_path.with_suffix(map_path.suffix + ".metadata.json")
    if metadata_path.is_file():
        outputs.append(str(metadata_path.resolve()))
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

    _notify(progress, "starting", operation=operation)

    if operation == "state-package":
        return _run_state_package(config, progress)

    if operation == "state-triage":
        observations = load_observations(_required_path(config, "observations"))
        target = _output_path(config, "output_file", "state_triage.jsonl")
        assessments = triage_observations(
            observations,
            llm=_llm_config(config, secrets),
            cache_dir=str(config.get("cache_dir") or ".sugar-cache"),
            limit=int(config["limit"]) if config.get("limit") not in (None, "") else None,
            progress=progress,
        )
        return [save_state_assessments(assessments, target)]

    if operation == "state-review-export":
        observations = load_observations(_required_path(config, "observations"))
        assessments = load_state_assessments(_required_path(config, "assessments"))
        target = _output_path(config, "output_file", "state_review.xlsx")
        return [export_review_workbook(observations, assessments, target)]

    if operation == "state-review-apply":
        assessments = _required_path(config, "assessments")
        workbook = _required_path(config, "workbook")
        target = _output_path(config, "output_file", "state_reviewed.jsonl")
        return [apply_review_workbook_file(assessments, workbook, target)]

    if operation == "state-audit":
        observations = load_observations(_required_path(config, "observations"))
        assessments = load_state_assessments(_required_path(config, "assessments"))
        target = _output_path(config, "output_file", "state_audit.json")
        return [_write_json(target, audit_state_records(observations, assessments))]

    if operation == "state-diff":
        previous = load_state_assessments(_required_path(config, "previous"))
        current = load_state_assessments(_required_path(config, "current"))
        target = _output_path(config, "output_file", "state_diff.json")
        return [_write_json(target, compare_state_snapshots(previous, current))]

    if operation == "state-template-us-sites":
        return [write_us_presence_template(_output_path(config, "output_file", "us_presence.csv"))]

    if operation == "state-template-entities":
        return [write_entity_template(_output_path(config, "output_file", "monitored_entities.csv"))]

    if operation == "state-query-plan":
        registry = load_entity_registry(_required_path(config, "entities"))
        return [save_query_plan(registry, _output_path(config, "output_file", "query_plan.txt"))]

    if operation == "intel-packet":
        observations = load_observations(_required_path(config, "observations"))
        assessments = load_state_assessments(_required_path(config, "assessments"))
        target = _output_path(config, "output_file", "intelligence_packet.json")
        return [
            save_intelligence_packet(
                observations,
                assessments,
                target,
                country=str(config.get("country") or ""),
                observation_id=str(config.get("observation_id") or ""),
                representative_case_limit=max(1, int(config.get("case_limit", 20))),
            )
        ]

    if operation == "intel-tradecraft":
        observations = load_observations(_required_path(config, "observations"))
        assessments = load_state_assessments(_required_path(config, "assessments"))
        target = _output_path(config, "output_file", "tradecraft_audit.json")
        return [save_tradecraft_audit(observations, assessments, target)]

    if operation == "intel-synthesize":
        observations = load_observations(_required_path(config, "observations"))
        assessments = load_state_assessments(_required_path(config, "assessments"))
        out_dir = _output_directory(config)
        return save_iterative_agentic_synthesis(
            observations,
            assessments,
            out_dir,
            llm=_llm_config(config, secrets),
            country=str(config.get("country") or ""),
            observation_id=str(config.get("observation_id") or ""),
            depth=str(config.get("depth") or "standard"),
            cache_dir=str(config.get("cache_dir") or ".sugar-cache"),
            max_workers=max(1, int(config.get("workers", 4))),
            name=str(config.get("name") or "analytic_intelligence"),
        )

    if operation == "intel-hypotheses":
        synthesis = _required_path(config, "synthesis")
        out_dir = _output_directory(config)
        return save_hypothesis_matrix(
            synthesis,
            out_dir,
            name=str(config.get("name") or "analytic_intelligence"),
        )

    previous = _required_path(config, "previous")
    current = _required_path(config, "current")
    target = _output_path(config, "output_file", "intelligence_comparison.json")
    return [
        save_longitudinal_comparison(
            previous,
            current,
            target,
            kind=str(config.get("kind") or "synthesis"),
        )
    ]
