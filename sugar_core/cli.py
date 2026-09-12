from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from .service import run_analysis, run_map, run_overlap, run_search


def _secret(prompt: str, env: str) -> str:
    return os.environ.get(env, "") or getpass.getpass(prompt).strip()


def _csv(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sugar", description="SUGAR stable research pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search")
    search.add_argument("terms", nargs="+")
    search.add_argument("--sources", default="x")
    search.add_argument("--since")
    search.add_argument("--until")
    search.add_argument("--posts", type=int, default=10)
    search.add_argument("--pages", type=int, default=1)
    search.add_argument("--output", default=".")
    search.add_argument("--provider", choices=["openai", "arc", "custom"], default="openai")
    search.add_argument("--model", default="gpt-5.6-luna")
    search.add_argument("--base-url", default="")
    search.add_argument("--no-translate", action="store_true")
    search.add_argument("--no-location", action="store_true")
    search.add_argument("--x-mode", choices=["recent", "all"], default="recent")
    search.add_argument("--x-languages", default="")
    search.add_argument("--mastodon-url", default="https://mastodon.social")
    search.add_argument("--include-reposts", action="store_true")

    map_p = sub.add_parser("map")
    map_p.add_argument("source_file")
    map_p.add_argument("--output")

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
    overlap.add_argument("--bands", default="5,25,100,250", help="Comma-separated distance bands in km.")
    overlap.add_argument("--max-distance", type=float)
    overlap.add_argument("--top-k", type=int, default=5, help="Nearest matches to store inside each observation.")
    overlap.add_argument("--include-rejected", action="store_true")
    overlap.add_argument("--output")
    overlap.add_argument("--map", action="store_true", dest="create_map")
    overlap.add_argument("--map-output")

    report = sub.add_parser("analysis")
    report.add_argument("source_file")
    report.add_argument("--output-stem")
    report.add_argument("--format", choices=["docx", "pdf", "both"], default="both")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "map":
        outputs = run_map({"source_file": args.source_file, "output_file": args.output})
        print("\n".join(outputs))
        return 0
    if args.command == "overlap":
        config = {
            "source_file": args.source_file,
            "output_file": args.output,
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
        stem = args.output_stem or str(Path(args.source_file).with_suffix("")) + "_analysis"
        outputs = run_analysis(
            {"source_file": args.source_file, "output_stem": stem, "output_format": args.format}
        )
        print("\n".join(outputs))
        return 0

    sources = _csv(args.sources)
    secrets = {}
    if "x" in sources:
        secrets["x_bearer_token"] = _secret("X bearer token: ", "SUGAR_X_BEARER_TOKEN")
    if not (args.no_translate and args.no_location):
        secrets["llm_api_key"] = _secret("LLM API key: ", "SUGAR_LLM_API_KEY")
    secrets["bluesky_identifier"] = os.environ.get("SUGAR_BLUESKY_IDENTIFIER", "")
    secrets["bluesky_app_password"] = os.environ.get("SUGAR_BLUESKY_APP_PASSWORD", "")
    secrets["mastodon_token"] = os.environ.get("SUGAR_MASTODON_TOKEN", "")
    config = {
        "sources": sources,
        "terms": args.terms,
        "since": args.since,
        "until": args.until,
        "max_posts_per_query": args.posts,
        "max_pages_per_query": args.pages,
        "output_directory": args.output,
        "translate_posts": not args.no_translate,
        "infer_locations": not args.no_location,
        "include_retweets": args.include_reposts,
        "x_search_mode": args.x_mode,
        "post_languages": _csv(args.x_languages),
        "mastodon_url": args.mastodon_url,
        "llm": {"provider": args.provider, "model": args.model, "base_url": args.base_url},
    }
    print("\n".join(run_search(config, secrets)))
    return 0
