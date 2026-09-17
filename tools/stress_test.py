"""Run deterministic, offline SUGAR scale probes.

The runner exercises storage, tabular export, and map generation with synthetic records. It
never creates collector sessions or makes network requests, so it is safe to use as a local
baseline before any explicitly authorized live integration testing.
"""

from __future__ import annotations

import argparse
import json
import platform
import tempfile
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable

from sugar_core import __version__
from sugar_core.harvest import HarvestStore
from sugar_core.mapping import MapOptions, create_map
from sugar_core.models import PostRecord
from sugar_core.storage import records_to_frame, save_records
from sugar_core.utils import atomic_write_text


def make_records(count: int) -> list[PostRecord]:
    """Create stable, varied records without randomness or external data."""
    return [
        PostRecord(
            platform="bluesky",
            native_id=str(index),
            canonical_url=f"https://example.test/synthetic/{index}",
            query="stress",
            query_matches=["stress", f"term-{index % 11}"],
            published_at="2026-09-10T12:00:00Z",
            author_handle=f"synthetic-{index % 1000}",
            author_name=f"Synthetic Author {index % 1000}",
            original_text=(
                f"Synthetic record {index}; deterministic payload for SUGAR scale testing. "
                f"The record belongs to bucket {index % 37}."
            ),
            latitude=-60.0 + (index % 1200) * 0.1,
            longitude=-170.0 + (index % 3400) * 0.1,
            engagement={"likes": index % 17, "reposts": index % 5},
            raw_stats={"synthetic": True, "bucket": index % 37},
            access_mode="anonymous",
        )
        for index in range(count)
    ]


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def _measure(name: str, operation: Callable[[], Any]) -> tuple[dict[str, Any], Any]:
    started = time.perf_counter()
    value = operation()
    result = {"name": name, "seconds": round(time.perf_counter() - started, 6)}
    return result, value


def run_probes(
    records_count: int,
    map_count: int,
    root: Path,
    *,
    export: bool,
    map_output: bool,
) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    records = make_records(records_count)
    results: list[dict[str, Any]] = []
    artifacts: list[str] = []

    checkpoint_path = root / "harvest.sqlite3"
    with HarvestStore(checkpoint_path) as store:
        measured, _ = _measure("harvest_store_upsert", lambda: store.upsert_records(records))
        measured["records"] = records_count
        results.append(measured)
        measured, restored = _measure("harvest_store_read", store.records)
        measured["records"] = len(restored)
        results.append(measured)
    artifacts.append(str(checkpoint_path.resolve()))

    measured, frame = _measure("records_to_frame", lambda: records_to_frame(records))
    measured.update({"records": len(frame), "columns": len(frame.columns)})
    results.append(measured)

    if export:
        export_path = root / "synthetic.csv"
        measured, _ = _measure("csv_xlsx_export", lambda: save_records(records, export_path))
        measured["records"] = records_count
        results.append(measured)
        artifacts.extend(
            str(path.resolve())
            for path in (
                export_path,
                export_path.with_suffix(".xlsx"),
                export_path.with_suffix(".metadata.json"),
            )
            if path.is_file()
        )

    if map_output:
        actual_map_count = min(records_count, map_count)
        map_path = root / "synthetic-map.html"
        map_frame = frame.iloc[:actual_map_count].copy()
        options = MapOptions(
            heat_windows=(30, 90),
            show_minimap=False,
            show_measure_control=False,
            show_mouse_position=False,
        )
        measured, _ = _measure("interactive_map_export", lambda: create_map(map_frame, map_path, options=options))
        measured.update({"records": actual_map_count, "bytes": map_path.stat().st_size})
        results.append(measured)
        artifacts.append(str(map_path.resolve()))

    return {
        "operation": "offline_stress_probe",
        "sugar_version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "records": records_count,
        "map_records": min(records_count, map_count) if map_output else 0,
        "network": False,
        "results": results,
        "artifacts": artifacts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=_positive, default=5000, help="Synthetic records for storage/export probes.")
    parser.add_argument(
        "--map-records", type=_positive, default=500, help="Synthetic records to embed in the map probe."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Keep generated artifacts in this directory; otherwise use a temporary directory.",
    )
    parser.add_argument("--skip-export", action="store_true", help="Skip CSV/XLSX export.")
    parser.add_argument("--skip-map", action="store_true", help="Skip interactive map export.")
    args = parser.parse_args(argv)

    if args.output_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="sugar-stress-")
        context = temporary
    else:
        context = nullcontext(str(args.output_dir.expanduser().resolve()))

    with context as location:
        root = Path(location)
        report = run_probes(
            args.records,
            args.map_records,
            root,
            export=not args.skip_export,
            map_output=not args.skip_map,
        )
        report_path = root / "stress-report.json"
        report["report"] = str(report_path.resolve())
        atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
