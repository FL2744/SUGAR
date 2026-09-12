from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from .service import run_analysis, run_harvest, run_map, run_search
from .weibo_investigation import investigate_weibo_seed, save_weibo_investigation


def _secret(prompt: str, env: str) -> str:
    return os.environ.get(env, "") or getpass.getpass(prompt).strip()


def _csv(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def _terms_from_files(paths: list[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(path)
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            term = line.strip()
            if not term or term.startswith("#"):
                continue
            key = term.casefold()
            if key not in seen:
                terms.append(term)
                seen.add(key)
    return terms


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sugar", description="SUGAR stable research pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Run a normal bounded collection + optional enrichment.")
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
    harvest.add_argument("--target", type=int, default=5000, help="Stop after at least this many unique records.")
    harvest.add_argument("--posts-per-task", type=int, default=500)
    harvest.add_argument("--pages-per-task", type=int, default=5, help="Durable checkpoint page chunk for numbered-page sources.")
    harvest.add_argument("--max-pages-per-query", type=int, default=100, help="Maximum numbered pages planned for each query.")
    harvest.add_argument("--shard-days", type=int, default=7)
    harvest.add_argument("--max-retries", type=int, default=4)
    harvest.add_argument("--max-inline-wait", type=float, default=900.0)
    harvest.add_argument("--task-delay", type=float, default=1.0)
    harvest.add_argument("--output", default=".")
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
    investigate.add_argument("--output", default=".")
    investigate.add_argument("--name", default="weibo_investigation")

    map_p = sub.add_parser("map")
    map_p.add_argument("source_file")
    map_p.add_argument("--output")

    report = sub.add_parser("analysis")
    report.add_argument("source_file")
    report.add_argument("--output-stem")
    report.add_argument("--format", choices=["docx", "pdf", "both"], default="both")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "map":
        outputs = run_map({"source_file": args.source_file, "output_file": args.output})
        print("\n".join(outputs))
        return 0

    if args.command == "analysis":
        stem = args.output_stem or str(Path(args.source_file).with_suffix("")) + "_analysis"
        outputs = run_analysis(
            {"source_file": args.source_file, "output_stem": stem, "output_format": args.format}
        )
        print("\n".join(outputs))
        return 0

    if args.command == "weibo-investigate":
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
        print("\n".join(save_weibo_investigation(investigation, args.output, name=args.name)))
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
