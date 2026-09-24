from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from . import __version__
from .analyst_capture import capture_saved_page
from .calibration import run_calibration_suite
from .columnar import build_parquet_dataset, query_parquet_dataset, save_query_result
from .llm import ARC_BASE_URL, LLMConfig, create_client
from .media_artifacts import attach_media_citation, build_media_citation, ingest_media
from .observation_storage import load_observations
from .research_intelligence import (
    build_content_lineage,
    load_entity_aliases,
    build_next_evidence_recommendation,
    apply_next_evidence_recommendation,
    build_robustness_report,
    build_temporal_evidence_graph,
    save_research_intelligence,
)
from .research_requirements import load_requirement, load_search_plan, save_search_plan
from .semantic_search import (
    build_semantic_index,
    load_semantic_index,
    refresh_semantic_index,
    save_semantic_index,
    search_lexical,
    search_semantic_index,
)
from .state_agentic import save_iterative_agentic_synthesis
from .state_hypotheses import build_hypothesis_matrix, save_hypothesis_matrix
from .state_intelligence import save_intelligence_packet
from .state_longitudinal import save_longitudinal_comparison
from .state_tradecraft import save_tradecraft_audit
from .state_workflow import load_state_assessments
from .triage_io import load_post_records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sugar-intel",
        description="Macro/micro analytic intelligence and evidence-constrained agentic synthesis for SUGAR State research.",
    )
    parser.add_argument("--version", action="version", version=f"sugar-intel {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    packet = sub.add_parser("packet", help="Build deterministic macro/micro intelligence features without an LLM.")
    packet.add_argument("observations")
    packet.add_argument("assessments")
    packet.add_argument("--output", required=True)
    packet.add_argument("--country", default="")
    packet.add_argument("--observation-id", default="")
    packet.add_argument("--case-limit", type=int, default=20)

    tradecraft = sub.add_parser("tradecraft", help="Audit source adequacy, analytic tensions, and epistemic debt without an LLM.")
    tradecraft.add_argument("observations")
    tradecraft.add_argument("assessments")
    tradecraft.add_argument("--records", help="Optional canonical records CSV/JSONL for content-lineage candidates.")
    tradecraft.add_argument("--output", required=True)

    synthesize = sub.add_parser("synthesize", help="Run specialist agents, optional evidence-neighborhood refinement, integration, red-team critique, and revision.")
    synthesize.add_argument("observations")
    synthesize.add_argument("assessments")
    synthesize.add_argument("--output", required=True)
    synthesize.add_argument("--name", default="analytic_intelligence")
    synthesize.add_argument("--country", default="")
    synthesize.add_argument("--observation-id", default="")
    synthesize.add_argument("--depth", choices=["quick", "standard", "deep"], default="standard")
    synthesize.add_argument("--provider", choices=["openai", "arc", "custom"], default="openai")
    synthesize.add_argument("--model", default="gpt-5.6-luna")
    synthesize.add_argument("--base-url", default="")
    synthesize.add_argument("--cache-dir", default=".sugar-cache")
    synthesize.add_argument("--workers", type=int, default=4)

    hypotheses = sub.add_parser("hypotheses", help="Turn synthesis alternatives into a competing-hypothesis evidence matrix.")
    hypotheses.add_argument("synthesis")
    hypotheses.add_argument("--output", required=True)
    hypotheses.add_argument("--name", default="analytic_intelligence")

    compare = sub.add_parser("compare", help="Compare two intelligence packets or two agentic syntheses over time.")
    compare.add_argument("previous")
    compare.add_argument("current")
    compare.add_argument("--kind", choices=["synthesis", "packet"], default="synthesis")
    compare.add_argument("--output", required=True)

    recommend = sub.add_parser(
        "next-evidence",
        help="Rank bounded collection actions from plan metrics, requirement gaps, and hypothesis collection needs.",
    )
    recommend.add_argument("requirement")
    recommend.add_argument("plan")
    recommend.add_argument("--hypotheses", help="Competing-hypothesis matrix or synthesis JSON.")
    recommend.add_argument("--output", required=True)
    recommend.add_argument("--max-queries", type=int, default=10)
    recommend.add_argument("--max-records-per-query", type=int, default=300)

    content_lineage = sub.add_parser(
        "content-lineage",
        help="Find exact and near-duplicate text candidates in normalized records.",
    )
    content_lineage.add_argument("records")
    content_lineage.add_argument("--output", required=True)
    content_lineage.add_argument("--similarity-threshold", type=float, default=0.82)

    graph = sub.add_parser(
        "graph",
        help="Build a temporal entity-to-observation graph with evidence and review state.",
    )
    graph.add_argument("observations")
    graph.add_argument("--assessments")
    graph.add_argument("--entity-aliases", help="Optional human-reviewed canonical-name to aliases JSON registry.")
    graph.add_argument("--output", required=True)

    robustness = sub.add_parser(
        "robustness",
        help="Run leave-one-source/factor-out sensitivity checks on verified evidence.",
    )
    robustness.add_argument("observations")
    robustness.add_argument("assessments")
    robustness.add_argument("--output", required=True)

    columnar_build = sub.add_parser(
        "columnar-build",
        help="Stream a canonical CSV or JSONL dataset into an optional DuckDB/Parquet analytical store.",
    )
    columnar_build.add_argument("source")
    columnar_build.add_argument("--output-dir", required=True)

    columnar_query = sub.add_parser(
        "columnar-query",
        help="Run one analyst-supplied SELECT query against a Parquet dataset using the evidence view.",
    )
    columnar_query.add_argument("dataset")
    columnar_query.add_argument("--sql", required=True)
    columnar_query.add_argument("--max-rows", type=int, default=1000)
    columnar_query.add_argument("--output")

    semantic_index = sub.add_parser(
        "semantic-index",
        help="Build a cross-lingual retrieval index using a configured embedding endpoint.",
    )
    semantic_index.add_argument("records")
    semantic_index.add_argument("--output", required=True)
    semantic_index.add_argument("--provider", choices=["openai", "arc", "custom"], default="openai")
    semantic_index.add_argument("--model", default="text-embedding-3-small")
    semantic_index.add_argument("--base-url", default="")
    semantic_index.add_argument("--allow-remote-content", action="store_true", required=True)

    semantic_search = sub.add_parser(
        "semantic-search",
        help="Search evidence locally by words or cross-lingually with an explicit embedding index.",
    )
    semantic_search.add_argument("records")
    semantic_search.add_argument("--query", required=True)
    semantic_search.add_argument("--top-k", type=int, default=20)
    semantic_search.add_argument("--index", help="Existing compressed semantic index to refresh and search.")
    semantic_search.add_argument("--output")
    semantic_search.add_argument("--provider", choices=["openai", "arc", "custom"], default="openai")
    semantic_search.add_argument("--model", default="text-embedding-3-small")
    semantic_search.add_argument("--base-url", default="")
    semantic_search.add_argument("--allow-remote-content", action="store_true")

    calibrate = sub.add_parser(
        "calibrate",
        help="Run the fixed offline gold-case suite for SUGAR research-intelligence components.",
    )
    calibrate.add_argument("--output")

    media_ingest = sub.add_parser(
        "media-ingest",
        help="Preserve an analyst-supplied media file and optional transcript/OCR derivatives in a project.",
    )
    media_ingest.add_argument("media_file")
    media_destination = media_ingest.add_mutually_exclusive_group(required=True)
    media_destination.add_argument("--workspace")
    media_destination.add_argument("--output-dir")
    media_ingest.add_argument("--source-url", default="")
    media_ingest.add_argument("--parent-record-id", default="")
    media_ingest.add_argument("--language", default="")
    media_ingest.add_argument("--transcript")
    media_ingest.add_argument("--ocr")

    media_cite = sub.add_parser(
        "media-cite",
        help="Create a timestamped, reviewable citation locator for a preserved media artifact.",
    )
    media_cite.add_argument("manifest")
    media_cite.add_argument("--start", required=True)
    media_cite.add_argument("--end", required=True)
    media_cite.add_argument("--quote", default="")
    media_cite.add_argument("--output")

    media_attach = sub.add_parser(
        "media-attach",
        help="Attach a timestamped media locator to an observation in a new saved observations file.",
    )
    media_attach.add_argument("manifest")
    media_attach.add_argument("observations")
    media_attach.add_argument("--observation-id", required=True)
    media_attach.add_argument("--start", required=True)
    media_attach.add_argument("--end", required=True)
    media_attach.add_argument("--quote", default="")
    media_attach.add_argument("--output", required=True)

    capture = sub.add_parser(
        "capture-page",
        help="Import sanitized visible text from a locally saved public or authorized HTML page.",
    )
    capture.add_argument("html_file")
    capture.add_argument("--source-url", required=True)
    capture.add_argument("--workspace", required=True)
    return parser


def _llm(args) -> LLMConfig:
    api_key = os.environ.get("SUGAR_LLM_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Set SUGAR_LLM_API_KEY before running agentic synthesis.")
    base_url = args.base_url
    if args.provider == "arc" and not base_url:
        base_url = ARC_BASE_URL
    if args.provider == "custom" and not base_url:
        raise ValueError("--base-url is required for provider=custom")
    return LLMConfig(provider=args.provider, model=args.model, api_key=api_key, base_url=base_url)


def _embedding_client(args):
    if not args.allow_remote_content:
        raise ValueError("Pass --allow-remote-content to send the query and any changed records to the embedding service.")
    api_key = os.environ.get("SUGAR_LLM_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Set SUGAR_LLM_API_KEY before using remote embeddings.")
    base_url = args.base_url.strip()
    if args.provider == "arc" and not base_url:
        base_url = ARC_BASE_URL
    if args.provider == "custom" and not base_url:
        raise ValueError("--base-url is required for provider=custom")
    return create_client(LLMConfig(provider=args.provider, model=args.model, api_key=api_key, base_url=base_url))


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "packet":
        observations = load_observations(args.observations)
        assessments = load_state_assessments(args.assessments)
        print(save_intelligence_packet(
            observations, assessments, args.output,
            country=args.country, observation_id=args.observation_id,
            representative_case_limit=args.case_limit,
        ))
        return 0

    if args.command == "tradecraft":
        observations = load_observations(args.observations)
        assessments = load_state_assessments(args.assessments)
        records = load_post_records(args.records) if args.records else None
        print(save_tradecraft_audit(observations, assessments, args.output, records=records))
        return 0

    if args.command == "synthesize":
        observations = load_observations(args.observations)
        assessments = load_state_assessments(args.assessments)
        outputs = save_iterative_agentic_synthesis(
            observations, assessments, args.output,
            llm=_llm(args), country=args.country, observation_id=args.observation_id,
            depth=args.depth, cache_dir=args.cache_dir, max_workers=args.workers, name=args.name,
        )
        print("\n".join(outputs))
        return 0

    if args.command == "hypotheses":
        print("\n".join(save_hypothesis_matrix(args.synthesis, args.output, name=args.name)))
        return 0

    if args.command == "compare":
        print(save_longitudinal_comparison(
            args.previous, args.current, args.output, kind=args.kind,
        ))
        return 0

    if args.command == "next-evidence":
        hypothesis_payload = None
        if args.hypotheses:
            raw = json.loads(Path(args.hypotheses).expanduser().read_text(encoding="utf-8-sig"))
            if not isinstance(raw, dict):
                raise ValueError("Hypotheses input must contain a JSON object.")
            hypothesis_payload = raw if "hypotheses" in raw else build_hypothesis_matrix(raw)
        plan = load_search_plan(args.plan)
        report = build_next_evidence_recommendation(
            load_requirement(args.requirement),
            plan,
            hypotheses=hypothesis_payload,
            max_queries=args.max_queries,
            max_records_per_query=args.max_records_per_query,
        )
        branch_id = apply_next_evidence_recommendation(plan, report)
        saved_plan = save_search_plan(plan, args.plan)
        saved_report = save_research_intelligence(report, args.output)
        print(json.dumps({"report": saved_report, "plan": saved_plan, "proposed_branch_id": branch_id}, indent=2))
        return 0

    if args.command == "content-lineage":
        report = build_content_lineage(
            load_post_records(args.records),
            similarity_threshold=args.similarity_threshold,
        )
        print(save_research_intelligence(report, args.output))
        return 0

    if args.command == "graph":
        observations = load_observations(args.observations)
        assessments = load_state_assessments(args.assessments) if args.assessments else []
        aliases = load_entity_aliases(args.entity_aliases) if args.entity_aliases else None
        report = build_temporal_evidence_graph(observations, assessments, entity_aliases=aliases)
        print(save_research_intelligence(report, args.output))
        return 0

    if args.command == "robustness":
        report = build_robustness_report(
            load_observations(args.observations),
            load_state_assessments(args.assessments),
        )
        print(save_research_intelligence(report, args.output))
        return 0

    if args.command == "columnar-build":
        print(json.dumps(build_parquet_dataset(args.source, args.output_dir), ensure_ascii=False, indent=2))
        return 0

    if args.command == "columnar-query":
        result = query_parquet_dataset(args.dataset, args.sql, max_rows=args.max_rows)
        if args.output:
            print(save_query_result(result, args.output))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "semantic-index":
        index = build_semantic_index(
            load_post_records(args.records), _embedding_client(args), model=args.model,
            provider=args.provider, base_url=args.base_url,
        )
        print(save_semantic_index(index, args.output))
        return 0

    if args.command == "semantic-search":
        records = load_post_records(args.records)
        if args.index:
            client = _embedding_client(args)
            index = refresh_semantic_index(
                load_semantic_index(args.index), records, client, model=args.model,
                provider=args.provider, base_url=args.base_url,
            )
            save_semantic_index(index, args.index)
            report = search_semantic_index(
                index, args.query, client, model=args.model, top_k=args.top_k,
                provider=args.provider, base_url=args.base_url,
            )
        else:
            report = search_lexical(records, args.query, top_k=args.top_k)
        if args.output:
            print(save_research_intelligence(report, args.output))
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "calibrate":
        report = run_calibration_suite()
        if args.output:
            print(save_research_intelligence(report, args.output))
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "pass" else 1

    if args.command == "media-ingest":
        destination = args.workspace or args.output_dir
        report = ingest_media(
            args.media_file, destination,
            source_url=args.source_url,
            parent_record_id=args.parent_record_id,
            language=args.language,
            transcript_file=args.transcript,
            ocr_file=args.ocr,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "media-cite":
        citation = build_media_citation(
            args.manifest, start=args.start, end=args.end, quote=args.quote,
        )
        if args.output:
            output = Path(args.output).expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(citation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(output)
        else:
            print(json.dumps(citation, ensure_ascii=False, indent=2))
        return 0

    if args.command == "media-attach":
        citation = build_media_citation(args.manifest, start=args.start, end=args.end, quote=args.quote)
        print(attach_media_citation(
            args.observations,
            args.output,
            observation_id=args.observation_id,
            citation=citation,
            quote=args.quote,
        ))
        return 0

    if args.command == "capture-page":
        report = capture_saved_page(args.html_file, source_url=args.source_url, workspace_path=args.workspace)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
