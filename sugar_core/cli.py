from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path

from . import __version__
from .importers import import_external_dataset, parse_field_mappings
from .handoff import build_handoff_bundle, verify_handoff_bundle
from .lineage import (
    build_lineage_index,
    load_dataset_metadata,
    load_lineage_index,
    provenance_document,
    save_lineage_index,
    validate_lineage_index,
)
from .llm import ARC_BASE_URL, LLMConfig
from .plan_execution import execute_search_plan
from .plan_feedback import apply_triage_feedback, evidence_excerpts_for_branch
from .observation_storage import load_observations
from .research_requirements import (
    ResearchRequirement,
    ResearchTimeframe,
    build_initial_search_plan,
    load_requirement,
    load_search_plan,
    save_requirement,
    save_search_plan,
)
from .requirement_compiler import (
    build_search_plan_from_strategy,
    compile_requirement_deterministically,
    enrich_strategy_with_llm,
    load_research_strategy,
    save_research_strategy,
)
from .search_planner import expand_branch_from_evidence, expand_initial_plan_with_llm
from .service import run_analysis, run_harvest, run_map, run_overlap, run_search
from .source_conflicts import load_source_conflicts
from .state_workflow import load_state_assessments
from .triage import DEFAULT_PROJECT_CONTEXT
from .triage_io import load_post_records, triage_dataset
from .weibo_investigation import investigate_weibo_seed, save_weibo_investigation
from .weibo_qualification import run_weibo_qualification
from .weibo_seed_harvest import SeedHarvestConfig, run_weibo_seed_harvest
from .workspace_runtime import (
    choose_output_directory,
    latest_workspace_artifact_path,
    optional_workspace,
    register_handoff_bundle,
    register_workspace_outputs,
)


def _secret(prompt: str, env: str) -> str:
    return os.environ.get(env, "") or getpass.getpass(prompt).strip()


def _csv(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def _lines_from_files(paths: list[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(path)
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            key = value.casefold()
            if key not in seen:
                values.append(value)
                seen.add(key)
    return values


def _terms_from_files(paths: list[str]) -> list[str]:
    return _lines_from_files(paths)


def _merge_terms(inline: list[str], files: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for term in [*inline, *_terms_from_files(files)]:
        term = term.strip()
        key = term.casefold()
        if term and key not in seen:
            result.append(term)
            seen.add(key)
    return result


def _collection_secrets(sources: list[str]) -> dict[str, str]:
    secrets: dict[str, str] = {
        "bluesky_identifier": os.environ.get("SUGAR_BLUESKY_IDENTIFIER", ""),
        "bluesky_app_password": os.environ.get("SUGAR_BLUESKY_APP_PASSWORD", ""),
        "mastodon_token": os.environ.get("SUGAR_MASTODON_TOKEN", ""),
        "weibo_cookie": os.environ.get("SUGAR_WEIBO_COOKIE", ""),
    }
    if "x" in sources:
        secrets["x_bearer_token"] = _secret("X bearer token: ", "SUGAR_X_BEARER_TOKEN")
    return secrets


def _json_mapping(path: str | None) -> dict:
    if not path:
        return {}
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{source} must contain a JSON object.")
    return data


def _reference_spec(value: str) -> dict[str, str]:
    text = str(value).strip()
    if not text:
        raise argparse.ArgumentTypeError("Reference layer cannot be empty.")
    if "=" in text:
        name, path = text.split("=", 1)
        name = name.strip()
        path = path.strip()
        if not name or not path:
            raise argparse.ArgumentTypeError("Use --reference 'Layer name=path/to/file.csv'.")
        return {"name": name, "file": path}
    path = Path(text)
    return {"name": path.stem.replace("_", " ").replace("-", " ").title(), "file": text}


def _workspace_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace",
        help="SUGAR project directory. If omitted, discover sugar-project.json from the current directory upward.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sugar", description="SUGAR stable research pipeline")
    parser.add_argument("--version", action="version", version=f"sugar {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Run a normal bounded collection + optional enrichment.")
    search.add_argument("terms", nargs="+")
    search.add_argument("--sources", default="x")
    search.add_argument("--since")
    search.add_argument("--until")
    search.add_argument("--posts", type=int, default=10)
    search.add_argument("--pages", type=int, default=1)
    search.add_argument("--output")
    search.add_argument("--provider", choices=["openai", "arc", "custom"], default="openai")
    search.add_argument("--model", default="gpt-5.6-luna")
    search.add_argument("--base-url", default="")
    search.add_argument("--no-translate", action="store_true")
    search.add_argument("--no-location", action="store_true")
    search.add_argument("--x-mode", choices=["recent", "all"], default="recent")
    search.add_argument("--x-languages", default="")
    search.add_argument("--mastodon-url", default="https://mastodon.social")
    search.add_argument("--include-reposts", action="store_true")
    search.add_argument(
        "--continue-on-source-error",
        action="store_true",
        help="Preserve successful sources and record failed/unavailable sources instead of aborting the whole search.",
    )
    _workspace_arg(search)

    import_p = sub.add_parser(
        "import",
        help="Normalize an external CSV/JSONL dataset into SUGAR records without recollection.",
    )
    import_p.add_argument("source_file")
    import_p.add_argument("--output")
    import_p.add_argument("--source-system", default="external")
    import_p.add_argument("--platform", default="")
    import_p.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="CANONICAL=SOURCE_COLUMN",
        help="Explicit column mapping. Repeatable.",
    )
    import_p.add_argument("--strict", action="store_true")
    import_p.add_argument("--drop-unmapped", action="store_true")
    _workspace_arg(import_p)

    requirement = sub.add_parser("requirement", help="Create or validate a versioned research requirement.")
    requirement_sub = requirement.add_subparsers(dest="requirement_command", required=True)
    requirement_create = requirement_sub.add_parser("create")
    requirement_create.add_argument("--question", required=True)
    requirement_create.add_argument("--geography", action="append", default=[])
    requirement_create.add_argument("--since", default="")
    requirement_create.add_argument("--until", default="")
    requirement_create.add_argument("--audience", action="append", default=[])
    requirement_create.add_argument("--language", action="append", default=[])
    requirement_create.add_argument("--known-entity", action="append", default=[])
    requirement_create.add_argument("--exclude", action="append", default=[])
    requirement_create.add_argument("--source", action="append", default=[])
    requirement_create.add_argument("--mode", choices=["quick", "standard", "deep"], default="standard")
    requirement_create.add_argument("--notes", default="")
    requirement_create.add_argument("--output")
    _workspace_arg(requirement_create)
    requirement_validate = requirement_sub.add_parser("validate")
    requirement_validate.add_argument("requirement_file")

    strategy = sub.add_parser(
        "strategy",
        help="Compile, inspect, edit, and approve a structured research strategy from a requirement.",
    )
    strategy_sub = strategy.add_subparsers(dest="strategy_command", required=True)
    strategy_compile = strategy_sub.add_parser("compile")
    strategy_compile.add_argument("requirement_file")
    strategy_compile.add_argument("--output")
    strategy_compile.add_argument("--ai-expand", action="store_true")
    strategy_compile.add_argument("--provider", choices=["openai", "arc", "custom"], default="openai")
    strategy_compile.add_argument("--model", default="gpt-5.6-luna")
    strategy_compile.add_argument("--base-url", default="")
    _workspace_arg(strategy_compile)
    strategy_show = strategy_sub.add_parser("show")
    strategy_show.add_argument("strategy_file")
    strategy_update = strategy_sub.add_parser(
        "update",
        help="Apply structured JSON edits to a compiled strategy.",
    )
    strategy_update.add_argument("strategy_file")
    strategy_update.add_argument(
        "--edits",
        required=True,
        help="JSON file containing concept_updates, add_concepts, and/or analytic_task.",
    )
    strategy_update.add_argument("--output")
    strategy_update.add_argument("--actor", default="cli analyst")
    _workspace_arg(strategy_update)
    strategy_approve = strategy_sub.add_parser("approve")
    strategy_approve.add_argument("strategy_file")
    strategy_approve.add_argument("--reviewer", required=True)
    strategy_approve.add_argument("--note", default="")
    strategy_approve.add_argument("--output")
    _workspace_arg(strategy_approve)

    plan = sub.add_parser("plan", help="Create an inspectable bounded initial search plan from a requirement.")
    plan.add_argument("requirement_file")
    plan.add_argument("--strategy", help="Approved compiled research strategy. Workspace plans auto-discover one when present.")
    plan.add_argument("--output")
    plan.add_argument("--ai-expand", action="store_true", help="Ask the configured LLM for additional bounded query branches.")
    plan.add_argument("--provider", choices=["openai", "arc", "custom"], default="openai")
    plan.add_argument("--model", default="gpt-5.6-luna")
    plan.add_argument("--base-url", default="")
    plan.add_argument("--max-ai-queries", type=int, default=24)
    _workspace_arg(plan)

    collect_plan = sub.add_parser("collect-plan", help="Execute runnable branches from a saved search plan.")
    collect_plan.add_argument("requirement_file")
    collect_plan.add_argument("plan_file")
    collect_plan.add_argument("--sources", default="")
    collect_plan.add_argument("--posts", type=int, default=20)
    collect_plan.add_argument("--pages", type=int, default=1)
    collect_plan.add_argument("--output")
    collect_plan.add_argument("--x-mode", choices=["recent", "all"], default="recent")
    collect_plan.add_argument("--mastodon-url", default="https://mastodon.social")
    collect_plan.add_argument("--include-reposts", action="store_true")
    _workspace_arg(collect_plan)

    feedback_plan = sub.add_parser(
        "plan-feedback",
        help="Update branch relevance metrics and bounded continue/retire/review decisions from triaged observations.",
    )
    feedback_plan.add_argument("plan_file")
    feedback_plan.add_argument("records_file")
    feedback_plan.add_argument("observations_file")
    _workspace_arg(feedback_plan)

    expand_plan = sub.add_parser(
        "expand-plan",
        help="Propose evidence-grounded follow-up queries for one search branch using original source text.",
    )
    expand_plan.add_argument("requirement_file")
    expand_plan.add_argument("plan_file")
    expand_plan.add_argument("records_file")
    expand_plan.add_argument("observations_file")
    expand_plan.add_argument("--branch", required=True, dest="branch_id")
    expand_plan.add_argument("--provider", choices=["openai", "arc", "custom"], default="openai")
    expand_plan.add_argument("--model", default="gpt-5.6-luna")
    expand_plan.add_argument("--base-url", default="")
    expand_plan.add_argument("--max-ai-queries", type=int, default=8)
    expand_plan.add_argument("--max-evidence", type=int, default=24)
    _workspace_arg(expand_plan)

    handoff = sub.add_parser(
        "handoff",
        help="Build a portable, hash-verified research handoff directory/ZIP independent of SUGAR runtime infrastructure.",
    )
    handoff.add_argument("requirement_file")
    handoff.add_argument("plan_file")
    handoff.add_argument("records_file")
    handoff.add_argument("observations_file")
    handoff.add_argument("--strategy")
    handoff.add_argument("--output", required=True, help="Parent directory for the portable handoff.")
    handoff.add_argument("--name", default="sugar-handoff")
    handoff.add_argument("--assessments")
    handoff.add_argument("--source-conflicts")
    handoff.add_argument("--limitations")
    handoff.add_argument("--include-output", action="append", default=[])
    handoff.add_argument("--provenance", action="append", default=[])
    handoff.add_argument("--no-zip", action="store_true")
    _workspace_arg(handoff)

    verify_handoff = sub.add_parser("verify-handoff", help="Verify all files in a SUGAR handoff against manifest hashes and sizes.")
    verify_handoff.add_argument("bundle_directory")

    lineage = sub.add_parser(
        "lineage",
        help="Build a standalone claim/evidence lineage index from research artifacts.",
    )
    lineage.add_argument("observations_file")
    lineage.add_argument("--assessments")
    lineage.add_argument("--records")
    lineage.add_argument("--source-conflicts")
    lineage.add_argument("--provenance", action="append", default=[])
    lineage.add_argument("--output")
    _workspace_arg(lineage)

    verify_lineage = sub.add_parser(
        "verify-lineage",
        help="Validate semantic claim/evidence lineage integrity.",
    )
    verify_lineage.add_argument("lineage_file")

    harvest = sub.add_parser(
        "harvest",
        help="Run resumable high-volume raw collection while honoring platform limits.",
    )
    harvest.add_argument("terms", nargs="*", help="Inline search terms. Can be combined with --terms-file.")
    harvest.add_argument(
        "--terms-file",
        action="append",
        default=[],
        help="UTF-8 query-plan file: one term per line; blank lines/# comments ignored. Repeatable.",
    )
    harvest.add_argument("--sources", default="bilibili,weibo")
    harvest.add_argument("--since")
    harvest.add_argument("--until")
    harvest.add_argument("--target", type=int, default=5000)
    harvest.add_argument("--posts-per-task", type=int, default=500)
    harvest.add_argument("--pages-per-task", type=int, default=5)
    harvest.add_argument("--max-pages-per-query", type=int, default=100)
    harvest.add_argument("--shard-days", type=int, default=7)
    harvest.add_argument("--max-retries", type=int, default=4)
    harvest.add_argument("--max-inline-wait", type=float, default=900.0)
    harvest.add_argument("--task-delay", type=float, default=1.0)
    harvest.add_argument("--output")
    harvest.add_argument("--name", default="sugar_harvest")
    harvest.add_argument("--time-shard-sources", default="x,bluesky")
    harvest.add_argument("--fail-fast", action="store_true")
    harvest.add_argument("--x-mode", choices=["recent", "all"], default="recent")
    harvest.add_argument("--x-languages", default="")
    harvest.add_argument("--mastodon-url", default="https://mastodon.social")
    harvest.add_argument("--include-reposts", action="store_true")
    harvest.add_argument("--bilibili-order", default="pubdate")
    harvest.add_argument("--no-bilibili-hydrate", action="store_true")
    harvest.add_argument("--no-weibo-hydrate", action="store_true")
    _workspace_arg(harvest)

    investigate = sub.add_parser(
        "weibo-investigate",
        help="Expand one real public Weibo post into comments/reposts/account context and a research brief.",
    )
    investigate.add_argument("seed", help="Weibo status URL, mobile detail/status URL, numeric mid, or bid.")
    investigate.add_argument("--comments", type=int, default=100)
    investigate.add_argument("--comment-pages", type=int, default=5)
    investigate.add_argument("--reposts", type=int, default=100)
    investigate.add_argument("--repost-pages", type=int, default=5)
    investigate.add_argument("--author-posts", type=int, default=40)
    investigate.add_argument("--author-pages", type=int, default=2)
    investigate.add_argument("--output")
    investigate.add_argument("--name", default="weibo_investigation")
    _workspace_arg(investigate)

    seed_harvest = sub.add_parser(
        "weibo-seed-harvest",
        help="Durably expand hundreds/thousands of known public Weibo post URLs or IDs without relying on keyword search.",
    )
    seed_harvest.add_argument("seeds", nargs="*", help="Inline public Weibo URLs/IDs. Can be combined with --seeds-file.")
    seed_harvest.add_argument("--seeds-file", action="append", default=[], help="UTF-8 file with one public Weibo URL/ID per line. Repeatable.")
    seed_harvest.add_argument("--comments", type=int, default=20)
    seed_harvest.add_argument("--comment-pages", type=int, default=1)
    seed_harvest.add_argument("--reposts", type=int, default=0)
    seed_harvest.add_argument("--repost-pages", type=int, default=1)
    seed_harvest.add_argument("--author-posts", type=int, default=0)
    seed_harvest.add_argument("--author-pages", type=int, default=1)
    seed_harvest.add_argument("--max-retries", type=int, default=2)
    seed_harvest.add_argument("--base-backoff", type=float, default=5.0)
    seed_harvest.add_argument("--max-inline-wait", type=float, default=120.0)
    seed_harvest.add_argument("--seed-delay", type=float, default=1.0)
    seed_harvest.add_argument("--fail-fast", action="store_true")
    seed_harvest.add_argument("--output")
    seed_harvest.add_argument("--name", default="weibo_seed_harvest")
    _workspace_arg(seed_harvest)

    qualify = sub.add_parser(
        "weibo-qualify",
        help="Run a reproducible Weibo collection/investigation acceptance campaign for State-facing research.",
    )
    qualify.add_argument("terms", nargs="*", help="Inline query-plan terms. Can be combined with --terms-file.")
    qualify.add_argument("--terms-file", action="append", default=[])
    qualify.add_argument("--seed", action="append", default=[], help="Real public Weibo post URL/ID. Repeatable.")
    qualify.add_argument("--seeds-file", action="append", default=[], help="UTF-8 seed file, one post URL/ID per line.")
    qualify.add_argument("--replicates", type=int, default=2, help="Independent fresh harvest snapshots for stability measurement.")
    qualify.add_argument("--target", type=int, default=1000, help="Minimum unique-record acceptance floor per fresh replicate; does not stop the query plan early.")
    qualify.add_argument("--posts-per-task", type=int, default=250)
    qualify.add_argument("--pages-per-task", type=int, default=2)
    qualify.add_argument("--max-pages-per-query", type=int, default=25)
    qualify.add_argument("--max-retries", type=int, default=3)
    qualify.add_argument("--max-inline-wait", type=float, default=300.0)
    qualify.add_argument("--task-delay", type=float, default=2.0)
    qualify.add_argument("--comments", type=int, default=50)
    qualify.add_argument("--comment-pages", type=int, default=3)
    qualify.add_argument("--reposts", type=int, default=25)
    qualify.add_argument("--repost-pages", type=int, default=2)
    qualify.add_argument("--author-posts", type=int, default=20)
    qualify.add_argument("--author-pages", type=int, default=1)
    qualify.add_argument("--audit-size", type=int, default=100)
    qualify.add_argument("--audit-file", help="Completed human-audit CSV from a prior qualification run.")
    qualify.add_argument("--thresholds", help="Optional JSON object overriding project acceptance thresholds.")
    qualify.add_argument("--output")
    qualify.add_argument("--name", default="weibo_qualification")
    qualify.add_argument("--no-weibo-hydrate", action="store_true")
    _workspace_arg(qualify)

    triage = sub.add_parser(
        "triage",
        help="AI-triage an existing SUGAR post dataset into a human-review observation dataset",
    )
    triage.add_argument("source_file")
    triage.add_argument("--output")
    triage.add_argument("--provider", choices=["openai", "arc", "custom"], default="openai")
    triage.add_argument("--model", default="gpt-5.6-luna")
    triage.add_argument("--base-url", default="")
    triage.add_argument("--project-context-file")
    triage.add_argument("--fail-fast", action="store_true")
    _workspace_arg(triage)

    map_p = sub.add_parser("map")
    map_p.add_argument("source_file")
    map_p.add_argument("--output")
    _workspace_arg(map_p)

    overlap = sub.add_parser(
        "overlap",
        help="Compute geographic proximity between research observations and reference networks.",
    )
    overlap.add_argument("source_file")
    overlap.add_argument(
        "--reference",
        action="append",
        type=_reference_spec,
        required=True,
        help="Reference file, optionally named as 'American Spaces=american_spaces.csv'. Repeat as needed.",
    )
    overlap.add_argument("--bands", default="5,25,100,250")
    overlap.add_argument("--max-distance", type=float)
    overlap.add_argument("--top-k", type=int, default=5)
    overlap.add_argument("--include-rejected", action="store_true")
    overlap.add_argument("--output")
    overlap.add_argument("--map", action="store_true", dest="create_map")
    overlap.add_argument("--map-output")
    _workspace_arg(overlap)

    report = sub.add_parser("analysis")
    report.add_argument("source_file")
    report.add_argument("--output-stem")
    report.add_argument("--format", choices=["docx", "pdf", "both"], default="both")
    _workspace_arg(report)
    return parser


def _llm_from_cli(provider: str, model: str, base_url: str, api_key: str) -> LLMConfig:
    base = base_url.strip()
    if provider == "arc" and not base:
        base = ARC_BASE_URL
    if provider == "custom" and not base:
        raise ValueError("--base-url is required when --provider custom is used.")
    return LLMConfig(provider=provider, model=model, api_key=api_key, base_url=base)


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "import":
        workspace = optional_workspace(args.workspace)
        source = Path(args.source_file).expanduser().resolve()
        output = (
            Path(args.output).expanduser()
            if args.output
            else (
                workspace.path_for("raw") / f"{source.stem}.import"
                if workspace is not None
                else source.with_name(source.stem + ".sugar-import")
            )
        )
        outputs = import_external_dataset(
            source,
            output,
            source_system=args.source_system,
            platform=args.platform,
            field_map=parse_field_mappings(args.map),
            strict=args.strict,
            preserve_unmapped_fields=not args.drop_unmapped,
        )
        register_workspace_outputs(workspace, outputs, operation="external-import")
        print("\n".join(outputs))
        return 0

    if args.command == "requirement":
        if args.requirement_command == "validate":
            requirement = load_requirement(args.requirement_file)
            print(json.dumps({
                "requirement_id": requirement.requirement_id,
                "schema_version": requirement.schema_version,
                "question": requirement.question,
                "collection_mode": requirement.collection_mode,
                "geographies": requirement.geographies,
                "languages": requirement.languages,
                "known_entities": requirement.known_entities,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        workspace = optional_workspace(args.workspace)
        target = (
            Path(args.output).expanduser()
            if args.output
            else (
                workspace.path_for("state") / "research-requirement.json"
                if workspace is not None
                else Path("research-requirement.json")
            )
        )
        requirement = ResearchRequirement(
            question=args.question,
            geographies=args.geography,
            timeframe=ResearchTimeframe(start=args.since, end=args.until),
            target_audiences=args.audience,
            languages=args.language or ["auto"],
            known_entities=args.known_entity,
            excluded_topics=args.exclude,
            preferred_sources=args.source,
            collection_mode=args.mode,
            notes=args.notes,
        )
        output = save_requirement(requirement, target)
        if workspace is not None:
            workspace.register_artifact(
                "research_requirement",
                output,
                label=requirement.question,
                metadata={"requirement_id": requirement.requirement_id, "schema_version": requirement.schema_version},
            )
        print(output)
        return 0

    if args.command == "strategy":
        if args.strategy_command == "show":
            strategy = load_research_strategy(args.strategy_file)
            print(json.dumps(strategy.export_dict(), ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        workspace = optional_workspace(getattr(args, "workspace", None))
        if args.strategy_command == "compile":
            requirement = load_requirement(args.requirement_file)
            target = (
                Path(args.output).expanduser()
                if args.output
                else (
                    workspace.path_for("state") / "research-strategy.json"
                    if workspace is not None
                    else Path(args.requirement_file).expanduser().with_name("research-strategy.json")
                )
            )
            strategy = compile_requirement_deterministically(requirement)
            if args.ai_expand:
                api_key = _secret("LLM API key: ", "SUGAR_LLM_API_KEY")
                llm = _llm_from_cli(args.provider, args.model, args.base_url, api_key)
                cache_dir = workspace.path_for("cache") if workspace is not None else target.parent / ".sugar-cache"
                strategy = enrich_strategy_with_llm(
                    requirement,
                    strategy,
                    llm=llm,
                    cache_dir=cache_dir,
                )
            output = save_research_strategy(strategy, target)
            if workspace is not None:
                workspace.register_artifact(
                    "research_strategy",
                    output,
                    label=f"Compiled strategy for {requirement.requirement_id}",
                    metadata={
                        "strategy_id": strategy.strategy_id,
                        "requirement_id": requirement.requirement_id,
                        "review_state": strategy.review_state,
                        "ai_provider": strategy.ai_provider,
                        "ai_model": strategy.ai_model,
                    },
                )
            print(output)
            return 0

        strategy = load_research_strategy(args.strategy_file)
        target = (
            Path(args.output).expanduser()
            if getattr(args, "output", None)
            else Path(args.strategy_file).expanduser()
        )
        if args.strategy_command == "update":
            edits_path = Path(args.edits).expanduser()
            payload = json.loads(edits_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Strategy edits file must contain a JSON object.")
            for raw in payload.get("concept_updates") or []:
                if not isinstance(raw, dict) or not str(raw.get("concept_id") or "").strip():
                    continue
                strategy.update_concept(
                    str(raw["concept_id"]),
                    value=str(raw["value"]) if "value" in raw else None,
                    included=bool(raw["included"]) if "included" in raw else None,
                    rationale=str(raw["rationale"]) if "rationale" in raw else None,
                    analyst_note=str(raw["analyst_note"]) if "analyst_note" in raw else None,
                    actor=args.actor,
                )
            for raw in payload.get("add_concepts") or []:
                if not isinstance(raw, dict):
                    continue
                strategy.add_analyst_concept(
                    kind=str(raw.get("kind") or ""),
                    value=str(raw.get("value") or ""),
                    origin=str(raw.get("origin") or "interpreted"),
                    rationale=str(raw.get("rationale") or ""),
                    actor=args.actor,
                )
            for raw in payload.get("dimension_updates") or []:
                if not isinstance(raw, dict) or not str(raw.get("dimension_id") or "").strip():
                    continue
                strategy.update_dimension(
                    str(raw["dimension_id"]),
                    question=str(raw["question"]) if "question" in raw else None,
                    indicators=raw.get("indicators") if "indicators" in raw else None,
                    source_families=raw.get("source_families") if "source_families" in raw else None,
                    rationale=str(raw["rationale"]) if "rationale" in raw else None,
                    included=bool(raw["included"]) if "included" in raw else None,
                    analyst_note=str(raw["analyst_note"]) if "analyst_note" in raw else None,
                    actor=args.actor,
                )
            if str(payload.get("analytic_task") or "").strip():
                strategy.update_analytic_task(
                    str(payload["analytic_task"]),
                    actor=args.actor,
                )
        elif args.strategy_command == "approve":
            strategy.approve(reviewer=args.reviewer, note=args.note)
        output = save_research_strategy(strategy, target)
        if workspace is not None:
            workspace.register_artifact(
                "research_strategy",
                output,
                label=f"Reviewed strategy for {strategy.requirement_id}",
                metadata={
                    "strategy_id": strategy.strategy_id,
                    "requirement_id": strategy.requirement_id,
                    "review_state": strategy.review_state,
                    "reviewer": strategy.reviewer,
                },
            )
        print(output)
        return 0

    if args.command == "plan":
        workspace = optional_workspace(args.workspace)
        requirement = load_requirement(args.requirement_file)
        target = (
            Path(args.output).expanduser()
            if args.output
            else (
                workspace.path_for("state") / "search-plan.json"
                if workspace is not None
                else Path(args.requirement_file).expanduser().with_name("search-plan.json")
            )
        )
        strategy_path = (
            Path(args.strategy).expanduser().resolve()
            if args.strategy
            else latest_workspace_artifact_path(workspace, "research_strategy")
        )
        strategy = None
        if strategy_path is not None and strategy_path.is_file():
            strategy = load_research_strategy(strategy_path)
            if strategy.requirement_id != requirement.requirement_id:
                raise ValueError(
                    "The compiled research strategy belongs to a different research requirement."
                )
            plan = build_search_plan_from_strategy(requirement, strategy)
        else:
            plan = build_initial_search_plan(requirement)
        if args.ai_expand:
            api_key = _secret("LLM API key: ", "SUGAR_LLM_API_KEY")
            llm = _llm_from_cli(args.provider, args.model, args.base_url, api_key)
            cache_dir = workspace.path_for("cache") if workspace is not None else target.parent / ".sugar-cache"
            plan = expand_initial_plan_with_llm(
                requirement,
                plan,
                llm=llm,
                cache_dir=cache_dir,
                max_candidates=args.max_ai_queries,
            )
        output = save_search_plan(plan, target)
        if workspace is not None:
            workspace.register_artifact(
                "search_plan",
                output,
                label=f"Search plan for {requirement.requirement_id}",
                metadata={
                    "requirement_id": requirement.requirement_id,
                    "schema_version": plan.schema_version,
                    "branch_count": len(plan.branches),
                    "strategy_id": strategy.strategy_id if strategy is not None else "",
                },
            )
        print(output)
        return 0

    if args.command == "collect-plan":
        workspace = optional_workspace(args.workspace)
        requirement = load_requirement(args.requirement_file)
        plan = load_search_plan(args.plan_file)
        sources = _csv(args.sources) or requirement.preferred_sources
        if not sources:
            parser.error("collect-plan requires --sources or preferred_sources in the research requirement")
        secrets = _collection_secrets(sources)
        result = execute_search_plan(
            requirement,
            plan,
            config={
                "sources": sources,
                "max_posts_per_query": args.posts,
                "max_pages_per_query": args.pages,
                "output_directory": args.output,
                "workspace": args.workspace,
                "translate_posts": False,
                "infer_locations": False,
                "include_retweets": args.include_reposts,
                "x_search_mode": args.x_mode,
                "mastodon_url": args.mastodon_url,
            },
            secrets=secrets,
        )
        save_search_plan(plan, args.plan_file)
        if workspace is not None:
            workspace.register_artifact(
                "search_plan",
                args.plan_file,
                label=f"Executed search plan for {requirement.requirement_id}",
                metadata={
                    "requirement_id": requirement.requirement_id,
                    "executed_branches": len(result.executed_branch_ids),
                    "records": result.records,
                },
            )
        print("\n".join([*result.outputs, str(Path(args.plan_file).expanduser().resolve())]))
        return 0

    if args.command == "plan-feedback":
        workspace = optional_workspace(args.workspace)
        plan = load_search_plan(args.plan_file)
        records = load_post_records(args.records_file)
        observations = load_observations(args.observations_file)
        feedback = apply_triage_feedback(plan, records, observations)
        output = save_search_plan(plan, args.plan_file)
        if workspace is not None:
            workspace.register_artifact(
                "search_plan",
                output,
                label=f"Evaluated search plan {plan.requirement_id}",
                metadata={
                    "requirement_id": plan.requirement_id,
                    "evaluated_branches": len(feedback),
                    "retired": sum(item.decision.action == "retire" for item in feedback),
                    "review": sum(item.decision.action == "review" for item in feedback),
                },
            )
        print(json.dumps({
            "plan": output,
            "branches": [
                {
                    "branch_id": item.branch_id,
                    "decision": item.decision.action,
                    "reasons": item.decision.reasons,
                    "matched_records": item.matched_records,
                    "matched_observations": item.matched_observations,
                }
                for item in feedback
            ],
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "expand-plan":
        workspace = optional_workspace(args.workspace)
        requirement = load_requirement(args.requirement_file)
        plan = load_search_plan(args.plan_file)
        records = load_post_records(args.records_file)
        observations = load_observations(args.observations_file)
        excerpts = evidence_excerpts_for_branch(
            plan,
            args.branch_id,
            records,
            observations,
            max_excerpts=args.max_evidence,
        )
        if not excerpts:
            raise ValueError(
                "No relevant/uncertain source-grounded observations are available for this branch."
            )
        api_key = _secret("LLM API key: ", "SUGAR_LLM_API_KEY")
        llm = _llm_from_cli(args.provider, args.model, args.base_url, api_key)
        cache_dir = workspace.path_for("cache") if workspace is not None else Path(args.plan_file).expanduser().resolve().parent / ".sugar-cache"
        plan = expand_branch_from_evidence(
            requirement,
            plan,
            parent_branch_id=args.branch_id,
            evidence=excerpts,
            llm=llm,
            cache_dir=cache_dir,
            max_candidates=args.max_ai_queries,
        )
        output = save_search_plan(plan, args.plan_file)
        if workspace is not None:
            workspace.register_artifact(
                "search_plan",
                output,
                label=f"Expanded search plan {plan.requirement_id}",
                metadata={
                    "requirement_id": plan.requirement_id,
                    "expanded_parent_branch": args.branch_id,
                    "evidence_count": len(excerpts),
                    "provider": llm.provider,
                    "model": llm.model,
                },
            )
        print(output)
        return 0

    if args.command == "handoff":
        workspace = optional_workspace(args.workspace)
        strategy_path = (
            Path(args.strategy).expanduser().resolve()
            if args.strategy
            else latest_workspace_artifact_path(workspace, "research_strategy")
        )
        result = build_handoff_bundle(
            args.requirement_file,
            args.plan_file,
            args.records_file,
            args.observations_file,
            args.output,
            name=args.name,
            strategy_file=strategy_path,
            assessments_file=args.assessments,
            source_conflicts_file=args.source_conflicts,
            limitations_file=args.limitations,
            analytic_outputs=args.include_output,
            provenance_files=args.provenance,
            create_zip=not args.no_zip,
        )
        if workspace is not None:
            register_handoff_bundle(workspace, result.manifest, archive_file=result.archive)
        print(json.dumps({
            "directory": result.directory,
            "manifest": result.manifest,
            "archive": result.archive,
            "artifacts": result.artifacts,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "verify-handoff":
        result = verify_handoff_bundle(args.bundle_directory)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["status"] == "pass" else 2

    if args.command == "lineage":
        workspace = optional_workspace(args.workspace)
        observations_path = Path(args.observations_file).expanduser().resolve()
        observations = load_observations(observations_path)
        assessments = load_state_assessments(args.assessments) if args.assessments else []
        records = load_post_records(args.records) if args.records else []
        conflicts = load_source_conflicts(args.source_conflicts) if args.source_conflicts else []
        provenance_paths = [Path(value).expanduser().resolve() for value in args.provenance]
        provenance_source = (
            Path(args.records).expanduser().resolve()
            if args.records
            else observations_path
        )
        lineage = build_lineage_index(
            observations,
            assessments,
            records=records,
            source_conflicts=conflicts,
            dataset_provenance=load_dataset_metadata(provenance_source),
            provenance_documents=[
                provenance_document(path)
                for path in provenance_paths
            ],
        )
        target = (
            Path(args.output).expanduser().resolve()
            if args.output
            else (
                workspace.path_for("state") / "evidence.lineage.json"
                if workspace is not None
                else observations_path.with_name(
                    f"{observations_path.stem}.lineage.json"
                )
            )
        )
        output = save_lineage_index(lineage, target)
        register_workspace_outputs(
            workspace,
            [output],
            operation="lineage",
            kind="lineage",
        )
        print(output)
        return 0

    if args.command == "verify-lineage":
        result = validate_lineage_index(load_lineage_index(args.lineage_file))
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["status"] == "pass" else 2

    if args.command == "map":
        outputs = run_map({"source_file": args.source_file, "output_file": args.output, "workspace": args.workspace})
        print("\n".join(outputs))
        return 0

    if args.command == "overlap":
        config = {
            "source_file": args.source_file,
            "output_file": args.output,
            "workspace": args.workspace,
            "spatial": {
                "reference_layers": args.reference,
                "distance_bands_km": [float(value) for value in _csv(args.bands)],
                "max_distance_km": args.max_distance,
                "stored_matches_per_observation": args.top_k,
                "include_rejected": args.include_rejected,
                "create_map": args.create_map,
                "map_output": args.map_output,
            },
        }
        print("\n".join(run_overlap(config)))
        return 0

    if args.command == "analysis":
        print(
            "\n".join(
                run_analysis(
                    {
                        "source_file": args.source_file,
                        "output_stem": args.output_stem,
                        "output_format": args.format,
                        "workspace": args.workspace,
                    }
                )
            )
        )
        return 0

    if args.command == "weibo-investigate":
        workspace = optional_workspace(args.workspace)
        out_dir = choose_output_directory(args.output, workspace, "raw")
        cookie = os.environ.get("SUGAR_WEIBO_COOKIE", "")
        investigation = investigate_weibo_seed(
            args.seed,
            max_comments=args.comments,
            comment_pages=args.comment_pages,
            max_reposts=args.reposts,
            repost_pages=args.repost_pages,
            author_posts=args.author_posts,
            author_pages=args.author_pages,
            cookie=cookie,
        )
        outputs = save_weibo_investigation(investigation, out_dir, name=args.name)
        register_workspace_outputs(workspace, outputs, operation="weibo-investigate")
        print("\n".join(outputs))
        return 0

    if args.command == "weibo-seed-harvest":
        workspace = optional_workspace(args.workspace)
        out_dir = choose_output_directory(args.output, workspace, "raw")
        seeds = _merge_terms(args.seeds, args.seeds_file)
        if not seeds:
            parser.error("weibo-seed-harvest requires at least one inline seed or --seeds-file entry")
        config = SeedHarvestConfig(
            seeds=tuple(seeds),
            name=args.name,
            max_comments=args.comments,
            comment_pages=args.comment_pages,
            max_reposts=args.reposts,
            repost_pages=args.repost_pages,
            author_posts=args.author_posts,
            author_pages=args.author_pages,
            max_retries=args.max_retries,
            base_backoff_seconds=args.base_backoff,
            max_inline_wait_seconds=args.max_inline_wait,
            inter_seed_delay_seconds=args.seed_delay,
            continue_on_error=not args.fail_fast,
        )
        outputs = run_weibo_seed_harvest(
            config,
            out_dir,
            cookie=os.environ.get("SUGAR_WEIBO_COOKIE", ""),
        )
        register_workspace_outputs(workspace, outputs, operation="weibo-seed-harvest", kind="harvest")
        print("\n".join(outputs))
        return 0

    if args.command == "weibo-qualify":
        workspace = optional_workspace(args.workspace)
        out_dir = choose_output_directory(args.output, workspace, "raw")
        terms = _merge_terms(args.terms, args.terms_file)
        seeds = _merge_terms(args.seed, args.seeds_file)
        if not terms:
            parser.error("weibo-qualify requires at least one inline term or --terms-file entry")
        if not seeds:
            parser.error("weibo-qualify requires at least one --seed or --seeds-file entry for real-post validation")
        thresholds = _json_mapping(args.thresholds)
        thresholds.setdefault("minimum_unique_records", args.target)
        config = {
            "sources": ["weibo"],
            "terms": terms,
            "output_directory": str(out_dir),
            "weibo_hydrate_details": not args.no_weibo_hydrate,
            "harvest": {
                "target_records": None,
                "posts_per_task": args.posts_per_task,
                "pages_per_task": args.pages_per_task,
                "max_pages_per_query": args.max_pages_per_query,
                "max_retries": args.max_retries,
                "max_inline_wait_seconds": args.max_inline_wait,
                "inter_task_delay_seconds": args.task_delay,
                "continue_on_error": True,
            },
            "qualification": {
                "name": args.name,
                "replicates": args.replicates,
                "seeds": seeds,
                "max_comments": args.comments,
                "comment_pages": args.comment_pages,
                "max_reposts": args.reposts,
                "repost_pages": args.repost_pages,
                "author_posts": args.author_posts,
                "author_pages": args.author_pages,
                "audit_sample_size": args.audit_size,
                "audit_file": args.audit_file,
                "thresholds": thresholds,
            },
        }
        secrets = {"weibo_cookie": os.environ.get("SUGAR_WEIBO_COOKIE", "")}
        outputs = run_weibo_qualification(config, secrets)
        register_workspace_outputs(workspace, outputs, operation="weibo-qualify")
        print("\n".join(outputs))
        return 0

    if args.command == "triage":
        workspace = optional_workspace(args.workspace)
        source = Path(args.source_file).expanduser()
        output = (
            Path(args.output).expanduser()
            if args.output
            else (
                workspace.path_for("observations") / f"{source.stem}_observations.csv"
                if workspace is not None
                else source.with_name(source.stem + "_observations.csv")
            )
        )
        project_context = DEFAULT_PROJECT_CONTEXT
        if args.project_context_file:
            project_context = Path(args.project_context_file).expanduser().read_text(encoding="utf-8").strip()
            if not project_context:
                raise ValueError("The project context file is empty.")
        api_key = _secret("LLM API key: ", "SUGAR_LLM_API_KEY")
        llm = _llm_from_cli(args.provider, args.model, args.base_url, api_key)
        outputs = triage_dataset(
            source,
            output,
            llm=llm,
            project_context=project_context,
            continue_on_error=not args.fail_fast,
        )
        register_workspace_outputs(workspace, outputs, operation="triage", kind="observations")
        print("\n".join(outputs))
        return 0

    sources = _csv(args.sources)
    secrets = _collection_secrets(sources)

    if args.command == "harvest":
        terms = _merge_terms(args.terms, args.terms_file)
        if not terms:
            parser.error("harvest requires at least one inline term or --terms-file entry")
        config = {
            "sources": sources,
            "terms": terms,
            "since": args.since,
            "until": args.until,
            "output_directory": args.output,
            "workspace": args.workspace,
            "x_search_mode": args.x_mode,
            "post_languages": _csv(args.x_languages),
            "mastodon_url": args.mastodon_url,
            "include_retweets": args.include_reposts,
            "bilibili_order": args.bilibili_order,
            "bilibili_hydrate_details": not args.no_bilibili_hydrate,
            "weibo_hydrate_details": not args.no_weibo_hydrate,
            "harvest": {
                "name": args.name,
                "target_records": args.target,
                "posts_per_task": args.posts_per_task,
                "pages_per_task": args.pages_per_task,
                "max_pages_per_query": args.max_pages_per_query,
                "shard_days": args.shard_days,
                "max_retries": args.max_retries,
                "max_inline_wait_seconds": args.max_inline_wait,
                "inter_task_delay_seconds": args.task_delay,
                "time_shard_sources": _csv(args.time_shard_sources),
                "continue_on_error": not args.fail_fast,
            },
        }
        print("\n".join(run_harvest(config, secrets)))
        return 0

    if not (args.no_translate and args.no_location):
        secrets["llm_api_key"] = _secret("LLM API key: ", "SUGAR_LLM_API_KEY")
    config = {
        "sources": sources,
        "terms": args.terms,
        "since": args.since,
        "until": args.until,
        "max_posts_per_query": args.posts,
        "max_pages_per_query": args.pages,
        "output_directory": args.output,
        "workspace": args.workspace,
        "translate_posts": not args.no_translate,
        "infer_locations": not args.no_location,
        "include_retweets": args.include_reposts,
        "x_search_mode": args.x_mode,
        "post_languages": _csv(args.x_languages),
        "mastodon_url": args.mastodon_url,
        "continue_on_source_error": args.continue_on_source_error,
        "llm": {"provider": args.provider, "model": args.model, "base_url": args.base_url},
    }
    print("\n".join(run_search(config, secrets)))
    return 0
