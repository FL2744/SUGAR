from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .llm import ARC_BASE_URL, LLMConfig
from .observation_storage import load_observations
from .state_aggregate import save_state_rollups
from .state_entities import load_entity_registry, save_query_plan, write_entity_template
from .state_freshness import save_freshness_report
from .state_gaps import save_gap_report
from .state_map import create_state_map
from .state_network import save_state_network
from .state_review import apply_review_workbook_file, export_review_workbook
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
from .workspace_runtime import (
    choose_output_directory,
    optional_workspace,
    register_workspace_outputs,
)


def _workspace_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace",
        help="SUGAR project directory. If omitted, discover sugar-project.json from the current directory upward.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sugar-state",
        description="Evidence-first State Department research workflow for SUGAR observations.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    template = sub.add_parser("template-us-sites", help="Write a CSV template for American Spaces/EducationUSA/U.S. presence data.")
    template.add_argument("output", nargs="?")
    _workspace_arg(template)

    entity_template = sub.add_parser("template-entities", help="Write a monitored-entity/alias registry template.")
    entity_template.add_argument("output", nargs="?")
    _workspace_arg(entity_template)

    query_plan = sub.add_parser("query-plan", help="Create a reproducible watch-query plan from the monitored-entity registry.")
    query_plan.add_argument("entities")
    query_plan.add_argument("--output")
    _workspace_arg(query_plan)

    blank = sub.add_parser("blank", help="Create blank State-assessment JSONL for an observation dataset.")
    blank.add_argument("observations")
    blank.add_argument("--output")
    _workspace_arg(blank)

    triage = sub.add_parser("triage", help="AI-triage observations into State-specific assessment suggestions.")
    triage.add_argument("observations")
    triage.add_argument("--output")
    triage.add_argument("--provider", choices=["openai", "arc", "custom"], default="openai")
    triage.add_argument("--model", default="gpt-5.6-luna")
    triage.add_argument("--base-url", default="")
    triage.add_argument("--cache-dir")
    triage.add_argument("--limit", type=int)
    _workspace_arg(triage)

    review_export = sub.add_parser("review-export", help="Create an analyst Excel workbook for assessment and claim review.")
    review_export.add_argument("observations")
    review_export.add_argument("assessments")
    review_export.add_argument("--output")
    _workspace_arg(review_export)

    review_apply = sub.add_parser("review-apply", help="Apply analyst workbook decisions back into validated State assessments.")
    review_apply.add_argument("assessments")
    review_apply.add_argument("workbook")
    review_apply.add_argument("--output")
    _workspace_arg(review_apply)

    network = sub.add_parser("network", help="Export typed, evidence-backed relationship nodes and edges.")
    network.add_argument("observations")
    network.add_argument("assessments")
    network.add_argument("--us-sites")
    network.add_argument("--output")
    network.add_argument("--name", default="state_network")
    network.add_argument("--include-unverified", action="store_true")
    _workspace_arg(network)

    rollup = sub.add_parser("rollup", help="Export country/city activity and verification rollups (not an influence score).")
    rollup.add_argument("observations")
    rollup.add_argument("assessments")
    rollup.add_argument("--us-sites")
    rollup.add_argument("--output")
    rollup.add_argument("--name", default="state_research")
    _workspace_arg(rollup)

    freshness = sub.add_parser("freshness", help="Report current-period, historical, and stale collection coverage.")
    freshness.add_argument("observations")
    freshness.add_argument("assessments")
    freshness.add_argument("--output")
    freshness.add_argument("--current-start", default="2024-01-01")
    freshness.add_argument("--stale-days", type=int, default=90)
    _workspace_arg(freshness)

    gaps = sub.add_parser("gaps", help="Prioritize verification, stale-data, entity, location, and U.S.-comparison research gaps.")
    gaps.add_argument("observations")
    gaps.add_argument("assessments")
    gaps.add_argument("--entities")
    gaps.add_argument("--us-sites")
    gaps.add_argument("--output")
    gaps.add_argument("--name", default="state_research")
    gaps.add_argument("--current-start", default="2024-01-01")
    gaps.add_argument("--stale-days", type=int, default=90)
    _workspace_arg(gaps)

    map_p = sub.add_parser("map", help="Create a precision-aware layered activity/U.S.-presence HTML map.")
    map_p.add_argument("observations")
    map_p.add_argument("assessments")
    map_p.add_argument("--us-sites")
    map_p.add_argument("--output")
    map_p.add_argument("--include-unverified", action="store_true")
    map_p.add_argument("--no-density", action="store_true")
    map_p.add_argument(
        "--resolve-locations",
        action="store_true",
        help="Resolve missing site/city/region coordinates through the cached public geocoder. Country-only records remain unplotted.",
    )
    map_p.add_argument("--geocode-cache", help="Directory for the State-map geocode cache. Defaults to the project cache when in a workspace.")
    map_p.add_argument("--min-location-confidence", type=float, default=0.45)
    _workspace_arg(map_p)

    package = sub.add_parser(
        "package",
        help="Build the complete State-facing bundle: audit, review, BLUF, map, network, rollups, freshness, and gaps.",
    )
    package.add_argument("observations")
    package.add_argument("--assessments")
    package.add_argument("--us-sites")
    package.add_argument("--entities")
    package.add_argument("--previous-assessments")
    package.add_argument("--output")
    package.add_argument("--name", default="state_research")
    package.add_argument("--title", default="PRC Cultural Influence Network Research Update")
    package.add_argument("--current-start", default="2024-01-01")
    package.add_argument("--stale-days", type=int, default=90)
    package.add_argument("--resolve-locations", action="store_true")
    package.add_argument("--min-location-confidence", type=float, default=0.45)
    _workspace_arg(package)

    audit = sub.add_parser("audit", help="Audit claim/evidence/verification integrity before briefing.")
    audit.add_argument("observations")
    audit.add_argument("assessments")
    audit.add_argument("--output")
    _workspace_arg(audit)

    diff = sub.add_parser("diff", help="Compare two State-assessment snapshots by stable observation ID.")
    diff.add_argument("previous")
    diff.add_argument("current")
    diff.add_argument("--output")
    _workspace_arg(diff)
    return parser


def _llm_config(args) -> LLMConfig:
    api_key = os.environ.get("SUGAR_LLM_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Set SUGAR_LLM_API_KEY before running AI triage.")
    base_url = args.base_url
    if args.provider == "arc" and not base_url:
        base_url = ARC_BASE_URL
    if args.provider == "custom" and not base_url:
        raise ValueError("--base-url is required for provider=custom")
    return LLMConfig(provider=args.provider, model=args.model, api_key=api_key, base_url=base_url)


def _write_or_print(payload: dict, output: str | Path | None) -> str | None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if output:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(str(target.resolve()))
        return str(target.resolve())
    print(text)
    return None


def _loaded_state_inputs(args):
    observations = load_observations(args.observations)
    assessments = load_state_assessments(args.assessments) if getattr(args, "assessments", None) else blank_state_assessments(observations)
    sites = load_us_presence_sites(args.us_sites) if getattr(args, "us_sites", None) else []
    if sites:
        assessments = apply_us_overlaps(observations, assessments, sites)
    return observations, assessments, sites


def _file_output(args, workspace, key: str, default_name: str) -> Path:
    raw = getattr(args, "output", None)
    if raw:
        target = Path(raw).expanduser().resolve()
    elif workspace is not None:
        target = workspace.path_for(key) / default_name
    else:
        raise ValueError("--output is required when the command is not running inside a SUGAR workspace.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _directory_output(args, workspace, key: str) -> Path:
    return choose_output_directory(getattr(args, "output", None), workspace, key)


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace = optional_workspace(getattr(args, "workspace", None))

    if args.command == "template-us-sites":
        target = Path(args.output).expanduser().resolve() if args.output else _file_output(args, workspace, "references", "us_presence.csv")
        output = write_us_presence_template(target)
        register_workspace_outputs(workspace, [output], operation="state-template-us-sites", kind="reference")
        print(output)
        return 0

    if args.command == "template-entities":
        target = Path(args.output).expanduser().resolve() if args.output else _file_output(args, workspace, "references", "monitored_entities.csv")
        output = write_entity_template(target)
        register_workspace_outputs(workspace, [output], operation="state-template-entities", kind="reference")
        print(output)
        return 0

    if args.command == "query-plan":
        target = _file_output(args, workspace, "state", "query_plan.txt")
        output = save_query_plan(load_entity_registry(args.entities), target)
        register_workspace_outputs(workspace, [output], operation="state-query-plan", kind="state")
        print(output)
        return 0

    if args.command == "blank":
        target = _file_output(args, workspace, "state", "state_blank.jsonl")
        observations = load_observations(args.observations)
        output = save_state_assessments(blank_state_assessments(observations), target)
        register_workspace_outputs(workspace, [output], operation="state-blank", kind="state_assessments")
        print(output)
        return 0

    if args.command == "triage":
        target = _file_output(args, workspace, "state", "state_triage.jsonl")
        observations = load_observations(args.observations)
        assessments = triage_observations(
            observations,
            llm=_llm_config(args),
            cache_dir=args.cache_dir or (str(workspace.path_for("cache")) if workspace is not None else ".sugar-cache"),
            limit=args.limit,
        )
        output = save_state_assessments(assessments, target)
        register_workspace_outputs(workspace, [output], operation="state-triage", kind="state_assessments")
        print(output)
        return 0

    if args.command == "review-export":
        target = _file_output(args, workspace, "state", "state_review.xlsx")
        observations = load_observations(args.observations)
        assessments = load_state_assessments(args.assessments)
        output = export_review_workbook(observations, assessments, target)
        register_workspace_outputs(workspace, [output], operation="state-review-export", kind="state_review")
        print(output)
        return 0

    if args.command == "review-apply":
        target = _file_output(args, workspace, "state", "state_reviewed.jsonl")
        output = apply_review_workbook_file(args.assessments, args.workbook, target)
        register_workspace_outputs(workspace, [output], operation="state-review-apply", kind="state_assessments")
        print(output)
        return 0

    if args.command == "network":
        out_dir = _directory_output(args, workspace, "state")
        observations, assessments, sites = _loaded_state_inputs(args)
        outputs = save_state_network(observations, assessments, out_dir, us_sites=sites, name=args.name, verified_only=not args.include_unverified)
        register_workspace_outputs(workspace, outputs, operation="state-network", kind="state")
        print("\n".join(outputs))
        return 0

    if args.command == "rollup":
        out_dir = _directory_output(args, workspace, "state")
        observations, assessments, _ = _loaded_state_inputs(args)
        outputs = save_state_rollups(observations, assessments, out_dir, name=args.name)
        register_workspace_outputs(workspace, outputs, operation="state-rollup", kind="state")
        print("\n".join(outputs))
        return 0

    if args.command == "freshness":
        target = _file_output(args, workspace, "state", "state_freshness.json")
        observations, assessments, _ = _loaded_state_inputs(args)
        output = save_freshness_report(observations, assessments, target, current_activity_start=args.current_start, collection_stale_days=args.stale_days)
        register_workspace_outputs(workspace, [output], operation="state-freshness", kind="state")
        print(output)
        return 0

    if args.command == "gaps":
        out_dir = _directory_output(args, workspace, "state")
        observations, assessments, sites = _loaded_state_inputs(args)
        registry = load_entity_registry(args.entities) if args.entities else None
        outputs = save_gap_report(observations, assessments, out_dir, entities=registry, us_sites=sites, name=args.name, current_activity_start=args.current_start, collection_stale_days=args.stale_days)
        register_workspace_outputs(workspace, outputs, operation="state-gaps", kind="state")
        print("\n".join(outputs))
        return 0

    if args.command == "map":
        observations, assessments, sites = _loaded_state_inputs(args)
        target = _file_output(args, workspace, "maps", "state_research.interactive_map.html")
        cache_dir = args.geocode_cache or (str(workspace.path_for("cache")) if workspace is not None else None)
        output = create_state_map(
            observations,
            assessments,
            target,
            us_sites=sites,
            verified_only=not args.include_unverified,
            include_activity_density=not args.no_density,
            resolve_missing_locations=args.resolve_locations,
            geocode_cache=cache_dir,
            minimum_location_confidence=args.min_location_confidence,
        )
        outputs = [output, str(Path(output).with_suffix(Path(output).suffix + ".metadata.json"))]
        register_workspace_outputs(workspace, outputs, operation="state-map", kind="map")
        print(output)
        return 0

    if args.command == "package":
        out_dir = _directory_output(args, workspace, "state")
        outputs = package_from_files(
            args.observations,
            out_dir,
            assessments_file=args.assessments,
            us_sites_file=args.us_sites,
            previous_assessments_file=args.previous_assessments,
            name=args.name,
            title=args.title,
        )
        observations, assessments, sites = _loaded_state_inputs(args)
        registry = load_entity_registry(args.entities) if args.entities else None
        stem = "_".join(args.name.split())
        assessed_snapshot = out_dir / f"{stem}.assessed.jsonl"
        assessed_output = save_state_assessments(assessments, assessed_snapshot)
        outputs.append(assessed_output)
        outputs.extend(save_state_rollups(observations, assessments, out_dir, name=args.name))
        outputs.extend(save_state_network(observations, assessments, out_dir, us_sites=sites, name=args.name, verified_only=True))
        review_path = out_dir / f"{stem}.review.xlsx"
        outputs.append(export_review_workbook(observations, assessments, review_path))
        freshness_path = out_dir / f"{stem}.freshness.json"
        outputs.append(save_freshness_report(observations, assessments, freshness_path, current_activity_start=args.current_start, collection_stale_days=args.stale_days))
        outputs.extend(save_gap_report(observations, assessments, out_dir, entities=registry, us_sites=sites, name=args.name, current_activity_start=args.current_start, collection_stale_days=args.stale_days))
        map_dir = workspace.path_for("maps") if workspace is not None else out_dir
        map_path = map_dir / f"{stem}.interactive_map.html"
        map_output = create_state_map(
            observations,
            assessments,
            map_path,
            us_sites=sites,
            verified_only=True,
            include_activity_density=True,
            resolve_missing_locations=args.resolve_locations,
            geocode_cache=str(workspace.path_for("cache")) if workspace is not None else None,
            minimum_location_confidence=args.min_location_confidence,
        )
        outputs.append(map_output)
        outputs.append(str(map_path.with_suffix(map_path.suffix + ".metadata.json")))
        register_workspace_outputs(workspace, [assessed_output], operation="state-package", kind="state_assessments")
        register_workspace_outputs(workspace, [map_output, str(map_path.with_suffix(map_path.suffix + ".metadata.json"))], operation="state-package", kind="map")
        other_outputs = [value for value in outputs if value not in {assessed_output, map_output, str(map_path.with_suffix(map_path.suffix + ".metadata.json"))}]
        register_workspace_outputs(workspace, other_outputs, operation="state-package", kind="state")
        print("\n".join(dict.fromkeys(outputs)))
        return 0

    if args.command == "audit":
        observations = load_observations(args.observations)
        assessments = load_state_assessments(args.assessments)
        target = Path(args.output).expanduser().resolve() if args.output else (workspace.path_for("state") / "state_audit.json" if workspace is not None else None)
        output = _write_or_print(audit_state_records(observations, assessments), target)
        if output:
            register_workspace_outputs(workspace, [output], operation="state-audit", kind="state")
        return 0

    if args.command == "diff":
        previous = load_state_assessments(args.previous)
        current = load_state_assessments(args.current)
        target = Path(args.output).expanduser().resolve() if args.output else (workspace.path_for("state") / "state_diff.json" if workspace is not None else None)
        output = _write_or_print(compare_state_snapshots(previous, current), target)
        if output:
            register_workspace_outputs(workspace, [output], operation="state-diff", kind="state")
        return 0

    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
