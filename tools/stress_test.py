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
import tracemalloc
from contextlib import nullcontext
from itertools import islice
from math import isfinite
from pathlib import Path
from typing import Any, Callable

from sugar_core import __version__
from sugar_core.harvest import HarvestStore
from sugar_core.mapping import MapOptions, create_map
from sugar_core.models import PostRecord
from sugar_core.storage import records_to_frame, save_records

try:
    from .benchmark_utils import atomic_write_text
except ImportError:  # Direct ``python tools/stress_test.py`` execution.
    from benchmark_utils import atomic_write_text

DEFAULT_IN_MEMORY_SAMPLE = 100_000


def make_record(index: int) -> PostRecord:
    """Create one stable, varied record without randomness or external data."""
    return PostRecord(
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
    )


def iter_records(count: int):
    """Yield deterministic records lazily so high-scale storage probes stay bounded."""
    for index in range(count):
        yield make_record(index)


def make_records(count: int) -> list[PostRecord]:
    """Create deterministic records as a list for small tests and callers that need one."""
    return list(iter_records(count))


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


def _nonnegative_float(value: str) -> float:
    parsed = float(value)
    if not isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("value must be a finite number at least 0")
    return parsed


def evaluate_budgets(
    report: dict[str, Any],
    *,
    max_seconds: float | None = None,
    max_disk_bytes: int | None = None,
    max_peak_python_bytes: int | None = None,
) -> list[str]:
    """Return stable budget-failure descriptions for a completed stress report."""
    failures: list[str] = []
    if max_seconds is not None:
        for result in report.get("results", []):
            elapsed = float(result.get("seconds", 0.0))
            if elapsed > max_seconds:
                failures.append(f"{result.get('name', 'operation')} exceeded {max_seconds:g}s ({elapsed:.6f}s)")
    if max_disk_bytes is not None and int(report.get("disk_bytes", 0)) > max_disk_bytes:
        failures.append(f"disk usage exceeded {max_disk_bytes} bytes ({report.get('disk_bytes', 0)} bytes)")
    peak = report.get("peak_python_bytes")
    if max_peak_python_bytes is not None and peak is not None and int(peak) > max_peak_python_bytes:
        failures.append(f"peak Python allocation exceeded {max_peak_python_bytes} bytes ({peak} bytes)")
    return failures


def run_probes(
    records_count: int,
    map_count: int,
    root: Path,
    *,
    export: bool,
    map_output: bool,
    in_memory_sample: int = DEFAULT_IN_MEMORY_SAMPLE,
) -> dict[str, Any]:
    if records_count < 1:
        raise ValueError("records_count must be at least 1")
    if in_memory_sample < 1:
        raise ValueError("in_memory_sample must be at least 1")
    root.mkdir(parents=True, exist_ok=True)
    sample_count = min(records_count, in_memory_sample)
    sample_records = list(islice(iter_records(records_count), sample_count))
    results: list[dict[str, Any]] = []
    artifacts: list[str] = []

    checkpoint_path = root / "harvest.sqlite3"
    with HarvestStore(checkpoint_path) as store:
        measured, _ = _measure("harvest_store_upsert", lambda: store.upsert_records(iter_records(records_count)))
        measured["records"] = records_count
        results.append(measured)
        measured, restored = _measure("harvest_store_read", lambda: store.records(limit=sample_count))
        measured["records"] = store.count_records()
        measured["sample_records"] = len(restored)
        results.append(measured)
    artifacts.append(str(checkpoint_path.resolve()))

    measured, frame = _measure("records_to_frame", lambda: records_to_frame(sample_records))
    measured.update({"records": len(frame), "source_records": records_count, "columns": len(frame.columns)})
    results.append(measured)

    if export:
        export_path = root / "synthetic.csv"
        measured, _ = _measure("csv_xlsx_export", lambda: save_records(sample_records, export_path))
        measured["records"] = len(sample_records)
        measured["source_records"] = records_count
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
        actual_map_count = min(records_count, map_count, len(frame))
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

    artifact_sizes = {artifact: Path(artifact).stat().st_size for artifact in artifacts if Path(artifact).is_file()}

    return {
        "operation": "offline_stress_probe",
        "sugar_version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "records": records_count,
        "materialized_records": sample_count,
        "in_memory_sample_limit": in_memory_sample,
        "map_records": min(records_count, map_count, len(frame)) if map_output else 0,
        "network": False,
        "results": results,
        "artifacts": artifacts,
        "artifact_sizes_bytes": artifact_sizes,
        "disk_bytes": sum(artifact_sizes.values()),
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
    parser.add_argument(
        "--in-memory-sample",
        type=_positive,
        default=DEFAULT_IN_MEMORY_SAMPLE,
        help="Maximum records materialized for frame/export/map probes; storage still processes all records.",
    )
    parser.add_argument(
        "--max-seconds",
        type=_nonnegative_float,
        help="Fail with exit code 2 when any measured operation exceeds this wall-time budget.",
    )
    parser.add_argument(
        "--max-disk-mb",
        type=_nonnegative_float,
        help="Fail with exit code 2 when generated artifacts exceed this total disk budget.",
    )
    parser.add_argument(
        "--max-peak-python-mb",
        type=_nonnegative_float,
        help="Fail with exit code 2 when a measured peak Python allocation exceeds this budget.",
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
        trace_memory = args.max_peak_python_mb is not None
        if trace_memory:
            tracemalloc.start()
        try:
            report = run_probes(
                args.records,
                args.map_records,
                root,
                export=not args.skip_export,
                map_output=not args.skip_map,
                in_memory_sample=args.in_memory_sample,
            )
            if trace_memory:
                _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
                report["peak_python_bytes"] = peak_bytes
        finally:
            if trace_memory:
                tracemalloc.stop()
        limits = {
            "max_seconds": args.max_seconds,
            "max_disk_bytes": round(args.max_disk_mb * 1024 * 1024) if args.max_disk_mb is not None else None,
            "max_peak_python_bytes": (
                round(args.max_peak_python_mb * 1024 * 1024) if args.max_peak_python_mb is not None else None
            ),
        }
        report["budget_limits"] = limits
        report["budget_failures"] = evaluate_budgets(report, **limits)
        report_path = root / "stress-report.json"
        report["report"] = str(report_path.resolve())
        atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if report["budget_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
