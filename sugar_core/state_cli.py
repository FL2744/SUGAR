from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .llm import ARC_BASE_URL, LLMConfig
from .observation_storage import load_observations
from .state_network import save_state_network
from .state_review import apply_review_workbook_file, export_review_workbook
from .state_triage import triage_observations
from .state_workflow import (
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

    package = sub.add_parser("package", help="Build the State-facing research package, audit, review queue, BLUF, and GeoJSON.")
    package.add_argument("observations")
    package.add_argument("--assessments")
    package.add_argument("--us-sites")
    package.add_argument("--previous-assessments")
    package.add_argument("--output", required=True)
    package.add_argument("--name", default="state_research")
    package.add_argument("--title", default="PRC Cultural Influence Network Research Update")

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


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "template-us-sites":
        print(write_us_presence_template(args.output))
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
        observations = load_observations(args.observations)
        assessments = load_state_assessments(args.assessments)
        sites = load_us_presence_sites(args.us_sites) if args.us_sites else []
        print(
            "\n".join(
                save_state_network(
                    observations,
                    assessments,
                    args.output,
                    us_sites=sites,
                    name=args.name,
                    verified_only=not args.include_unverified,
                )
            )
        )
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
        print("\n".join(outputs))
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
