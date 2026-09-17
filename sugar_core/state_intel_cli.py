from __future__ import annotations

import argparse
import os

from . import __version__
from .llm import ARC_BASE_URL, LLMConfig
from .observation_storage import load_observations
from .state_agentic import save_iterative_agentic_synthesis
from .state_hypotheses import save_hypothesis_matrix
from .state_intelligence import save_intelligence_packet
from .state_longitudinal import save_longitudinal_comparison
from .state_tradecraft import save_tradecraft_audit
from .state_workflow import load_state_assessments


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
        print(save_tradecraft_audit(observations, assessments, args.output))
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

    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
