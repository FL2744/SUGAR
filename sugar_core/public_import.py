from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .collector_registry import CollectorRequest, fetch_registered_item, get_collector
from .storage import save_records
from .workspace_runtime import choose_output_directory, register_workspace_outputs, workspace_from_config

ProgressCallback = Callable[[str, dict[str, Any]], None]


def _notify(progress: ProgressCallback | None, event: str, **values: Any) -> None:
    if progress is not None:
        progress(event, values)


def _clean_items(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def run_public_import(
    config: dict[str, Any],
    secrets: dict[str, str] | None = None,
    progress: ProgressCallback | None = None,
) -> list[str]:
    secrets = secrets or {}
    source = str(config.get("source") or "").strip().casefold()
    if not source:
        raise ValueError("source is required for public-item import.")
    spec = get_collector(source)
    if not spec.capabilities.known_item:
        raise ValueError(f"{source} does not currently support known public item import.")
    items = _clean_items(list(config.get("items") or config.get("urls") or []))
    if not items:
        raise ValueError("Enter at least one public URL or supported native item identifier.")

    workspace = workspace_from_config(config)
    out_dir = choose_output_directory(config.get("output_directory"), workspace, "raw", fallback=Path.cwd())
    safe_name = "_".join(str(config.get("name") or f"{source}_public_import").split())
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"{safe_name}_{stamp}.csv"
    request = CollectorRequest(config=config, secrets=secrets)

    records = []
    _notify(progress, "starting", operation="import-public", source=source, total=len(items))
    for index, item in enumerate(items, start=1):
        _notify(progress, "importing_public_item", source=source, current=index, total=len(items), item=item)
        record = fetch_registered_item(source, item, request)
        if not record.query:
            record.query = item
        record.add_query_match(item)
        records.append(record)

    metadata = {
        "source": source,
        "mode": "known_public_item_import",
        "items_requested": len(items),
        "items_collected": len(records),
        "collector_capabilities": spec.capabilities.as_dict(),
        "workspace_project_id": workspace.manifest.project_id if workspace is not None else None,
    }
    _notify(progress, "saving", records=len(records), output=str(csv_path))
    save_records(records, csv_path, metadata=metadata)
    outputs = [str(csv_path), str(csv_path.with_suffix(".xlsx")), str(csv_path.with_suffix(".metadata.json"))]
    register_workspace_outputs(workspace, outputs, operation="import-public", kind="raw_collection")
    _notify(progress, "saved", outputs=outputs)
    return outputs


def _items_file(path: str) -> list[str]:
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    return [
        line.strip()
        for line in source.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sugar-import",
        description="Import known public items through SUGAR's registered source adapters.",
    )
    parser.add_argument("source", help="Registered source, e.g. wechat, zhihu, douyin, bilibili, or weibo.")
    parser.add_argument("items", nargs="*", help="Public URLs or supported native item identifiers.")
    parser.add_argument("--items-file", action="append", default=[], help="UTF-8 file containing one item per line. Repeatable.")
    parser.add_argument("--output", help="Output directory.")
    parser.add_argument("--name", help="Output name prefix.")
    parser.add_argument("--workspace", help="Optional SUGAR project directory.")
    args = parser.parse_args(argv)

    items = list(args.items)
    for path in args.items_file:
        items.extend(_items_file(path))
    secrets = {
        "weibo_cookie": os.environ.get("SUGAR_WEIBO_COOKIE", ""),
        "zhihu_access_secret": os.environ.get("SUGAR_ZHIHU_ACCESS_SECRET", ""),
    }
    outputs = run_public_import(
        {
            "source": args.source,
            "items": items,
            "output_directory": args.output,
            "name": args.name,
            "workspace": args.workspace,
        },
        secrets,
    )
    print("\n".join(outputs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
