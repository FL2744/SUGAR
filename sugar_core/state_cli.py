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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sugar-state",
        description="Evidence-first State Department research workflow for SUGAR observations.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    template = sub.add_parser("template-us-sites", help="Write a CSV template for American Spaces/EducationUSA/U.S. presence data.")
    template.add_argument("output")

    entity_template = sub.add_parser("template-entities", help="Write a monitored-entity/alias registry template.")
    entity_template.add_argument("output")

    query_plan = sub.add_parser("query-plan", help="Create a reproducible watch-query plan from the monitored-entity registry.")
    query_plan.add_argument("entities")
    query_plan.add_argument("--output", required=True)

    blank = sub.add_parser("blank", help="Create blank State-assessment JSONL for an observation dataset.")
    blank.add_argument("observations")
    blank.add_argument("--output", required=True)

    triage = sub.add_parser("triage", help="AI-triage observations into State-specific assessment suggestions.")
    triage.add_argument("observations")
    triage.add_argument("--output", required=True)
    triage.add_argument("--provider", choices=["openai", "arc", "custom"], default="openai")
    triage.add_argument("--model", default="gpt-5.6-luna")
    triage.add_argument("--base-url", default="")
    triage.add_argument("--cache-dir", default=".sugar-cache")
    triage.add_argument("--limit", type=int)

    review_export = sub.add_parser("review-export", help="Create an analyst Excel workbook for assessment and claim review.")
    review_export.add_argument("observations")
    review_export.add_argument("assessments")
    review_export.add_argument("--output", required=True)

    review_apply = sub.add_parser("review-apply", help="Apply analyst workbook decisions back into validated State assessments.")
    review_apply.add_argument("assessments")
    review_apply.add_argument("workbook")
    review_apply.add_argument("--output", required=True)

    network = sub.add_parser("network", help="Export typed, evidence-backed relationship nodes and edges.")
    network.add_argument("observations")
    network.add_argument("assessments")
    network.add_argument("--us-sites")
    network.add_argument("--output", required=True)
    network.add_argument("--name", default="state_network")
    network.add_argument("--include-unverified", action="store_true")

    rollup = sub.add_parser("rollup", help="Export country/city activity and verification rollups (not an influence score).")
    rollup.add_argument("observations")
    rollup.add_argument("assessments")
    rollup.add_argument("--us-sites")
    rollup.add_argument("--output", required=True)
    rollup.add_argument("--name", default="state_research")

    freshness = sub.add_parser("freshness", help="Report current-period, historical, and stale collection coverage.")
    freshness.add_argument("observations")
    freshness.add_argument("assessments")
    freshness.add_argument("--output", required=True)
    freshness.add_argument("--current-start", default="2024-01-01")
    freshness.add_argument("--stale-days", type=int, default=90)

    gaps = sub.add_parser("gaps", help="Prioritize verification, stale-data, entity, location, and U.S.-comparison research gaps.")
    gaps.add_argument("observations")
    gaps.add_argument("assessments")
    gaps.add_argument("--entities")
    gaps.add_argument("--us-sites")
    gaps.add_argument("--output", required=True)
    gaps.add_argument("--name", default="state_research")
    gaps.add_argument("--current-start", default="2024-01-01")
    gaps.add_argument("--stale-days", type=int, default=90)

    map_p = sub.add_parser("map", help="Create a layered verified-activity/U.S.-presence HTML map.")
    map_p.add_argument("observations")
    map_p.add_argument("assessments")
    map_p.add_argument("--us-sites")
    map_p.add_argument("--output", required=True)
    map_p.add_argument("--include-unverified", action="store_true")
    map_p.add_argument("--no-density", action="store_true")

    package = sub.add_parser(
        "package",
        help="Build the complete State-facing bundle: audit, review, BLUF, map, network, rollups, freshness, and gaps.",
    )
    package.add_argument("observations")
    package.add_argument("--assessments")
    package.add_argument("--us-sites")
    package.add_argument("--entities")
    package.add_argument("--previous-assessments")
    package.add_argument("--output", required=True)
    package.add_argument("--name", default="state_research")
    package.add_argument("--title", default="PRC Cultural Influence Network Research Update")
    package.add_argument("--current-start", default="2024-01-01")
    package.add_argument("--stale-days", type=int, default=90)

    audit = sub.add_parser("audit", help="Audit claim/evidence/verification integrity before briefing.")
    audit.add_argument("observations")
    audit.add_argument("assessments")
    audit.add_argument("--output")

    diff = sub.add_parser("diff", help="Compare two State-assessment snapshots by stable observation ID.")
    diff.add_argument("previous")
    diff.add_argument("current")
    diff.add_argument("--output")
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


def _write_or_print(payload: dict, output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if output:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(str(target.resolve()))
    else:
        print(text)


def _loaded_state_inputs(args):
    observations = load_observations(args.observations)
    assessments = load_state_assessments(args.assessments) if getattr(args, "assessments", None) else blank_state_assessments(observations)
    sites = load_us_presence_sites(args.us_sites) if getattr(args, "us_sites", None) else []
    if sites:
        assessments = apply_us_overlaps(observations, assessments, sites)
    return observations, assessments, sites


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "template-us-sites":
        print(write_us_presence_template(args.output))
        return 0

    if args.command == "template-entities":
        print(write_entity_template(args.output))
        return 0

    if args.command == "query-plan":
        print(save_query_plan(load_entity_registry(args.entities), args.output))
        return 0

    if args.command == "blank":
        observations = load_observations(args.observations)
        print(save_state_assessments(blank_state_assessments(observations), args.output))
        return 0

    if args.command == "triage":
        observations = load_observations(args.observations)
        assessments = triage_observations(
            observations,
            llm=_llm_config(args),
            cache_dir=args.cache_dir,
            limit=args.limit,
        )
        print(save_state_assessments(assessments, args.output))
        return 0

    if args.command == "review-export":
        observations = load_observations(args.observations)
        assessments = load_state_assessments(args.assessments)
        print(export_review_workbook(observations, assessments, args.output))
        return 0

    if args.command == "review-apply":
        print(apply_review_workbook_file(args.assessments, args.workbook, args.output))
        return 0

    if args.command == "network":
        observations, assessments, sites = _loaded_state_inputs(args)
        print("\n".join(save_state_network(observations, assessments, args.output, us_sites=sites, name=args.name, verified_only=not args.include_unverified)))
        return 0

    if args.command == "rollup":
        observations, assessments, _ = _loaded_state_inputs(args)
        print("\n".join(save_state_rollups(observations, assessments, args.output, name=args.name)))
        return 0

    if args.command == "freshness":
        observations, assessments, _ = _loaded_state_inputs(args)
        print(save_freshness_report(observations, assessments, args.output, current_activity_start=args.current_start, collection_stale_days=args.stale_days))
        return 0

    if args.command == "gaps":
        observations, assessments, sites = _loaded_state_inputs(args)
        registry = load_entity_registry(args.entities) if args.entities else None
        print("\n".join(save_gap_report(observations, assessments, args.output, entities=registry, us_sites=sites, name=args.name, current_activity_start=args.current_start, collection_stale_days=args.stale_days)))
        return 0

    if args.command == "map":
        observations, assessments, sites = _loaded_state_inputs(args)
        print(create_state_map(observations, assessments, args.output, us_sites=sites, verified_only=not args.include_unverified, include_activity_density=not args.no_density))
        return 0

    if args.command == "package":
        outputs = package_from_files(
            args.observations,
            args.output,
            assessments_file=args.assessments,
            us_sites_file=args.us_sites,
            previous_assessments_file=args.previous_assessments,
            name=args.name,
            title=args.title,
        )
        observations, assessments, sites = _loaded_state_inputs(args)
        registry = load_entity_registry(args.entities) if args.entities else None
        stem = "_".join(args.name.split())
        out_dir = Path(args.output).expanduser().resolve()
        assessed_snapshot = out_dir / f"{stem}.assessed.jsonl"
        outputs.append(save_state_assessments(assessments, assessed_snapshot))
        outputs.extend(save_state_rollups(observations, assessments, out_dir, name=args.name))
        outputs.extend(save_state_network(observations, assessments, out_dir, us_sites=sites, name=args.name, verified_only=True))
        review_path = out_dir / f"{stem}.review.xlsx"
        outputs.append(export_review_workbook(observations, assessments, review_path))
        freshness_path = out_dir / f"{stem}.freshness.json"
        outputs.append(save_freshness_report(observations, assessments, freshness_path, current_activity_start=args.current_start, collection_stale_days=args.stale_days))
        outputs.extend(save_gap_report(observations, assessments, out_dir, entities=registry, us_sites=sites, name=args.name, current_activity_start=args.current_start, collection_stale_days=args.stale_days))
        map_path = out_dir / f"{stem}.interactive_map.html"
        outputs.append(create_state_map(observations, assessments, map_path, us_sites=sites, verified_only=True, include_activity_density=True))
        outputs.append(str(map_path.with_suffix(map_path.suffix + ".metadata.json")))
        print("\n".join(dict.fromkeys(outputs)))
        return 0

    if args.command == "audit":
        observations = load_observations(args.observations)
        assessments = load_state_assessments(args.assessments)
        _write_or_print(audit_state_records(observations, assessments), args.output)
        return 0

    if args.command == "diff":
        previous = load_state_assessments(args.previous)
        current = load_state_assessments(args.current)
        _write_or_print(compare_state_snapshots(previous, current), args.output)
        return 0

    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
