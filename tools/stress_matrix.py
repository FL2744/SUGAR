"""Run a deterministic offline stress matrix across multiple synthetic scales."""

from __future__ import annotations

import argparse
import json
import platform
import tracemalloc
from pathlib import Path
from typing import Any, Iterable

try:
    from .stress_test import run_probes
except ImportError:  # Direct ``python tools/stress_matrix.py`` execution.
    from stress_test import run_probes

from sugar_core import __version__
from sugar_core.utils import atomic_write_text


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("scale must be at least 1")
    return parsed


def parse_scales(value: str) -> list[int]:
    """Parse a comma-separated list of unique positive scales in execution order."""

    scales = [_positive(part.strip()) for part in value.split(",") if part.strip()]
    if not scales:
        raise argparse.ArgumentTypeError("provide at least one comma-separated scale")
    return list(dict.fromkeys(scales))


def run_matrix(
    scales: Iterable[int],
    output_dir: str | Path,
    *,
    export: bool = False,
    map_output: bool = False,
    map_records: int = 500,
    in_memory_sample: int = 100_000,
) -> dict[str, Any]:
    """Run one isolated stress probe per scale and persist each scale report."""

    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    normalized_scales = list(dict.fromkeys(_positive(str(scale)) for scale in scales))
    if not normalized_scales:
        raise ValueError("provide at least one scale")

    runs: list[dict[str, Any]] = []
    for records in normalized_scales:
        scale_root = root / f"records-{records}"
        tracemalloc.start()
        try:
            report = run_probes(
                records,
                map_records,
                scale_root,
                export=export,
                map_output=map_output,
                in_memory_sample=in_memory_sample,
            )
            _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        report["peak_python_bytes"] = peak_bytes
        report_path = scale_root / "stress-report.json"
        report["report"] = str(report_path.resolve())
        atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        runs.append(
            {
                "records": records,
                "map_records": report["map_records"],
                "peak_python_bytes": report["peak_python_bytes"],
                "results": report["results"],
                "artifacts": report["artifacts"],
                "artifact_sizes_bytes": report["artifact_sizes_bytes"],
                "disk_bytes": report["disk_bytes"],
                "report": str(report_path.resolve()),
            }
        )

    return {
        "operation": "offline_stress_matrix",
        "sugar_version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "network": False,
        "export": export,
        "map_output": map_output,
        "map_records_requested": map_records,
        "runs": runs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scales",
        type=parse_scales,
        default=[1000, 10000, 100000, 1000000],
        help="Comma-separated synthetic record counts (default: 1000,10000,100000,1000000).",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for per-scale and matrix reports.")
    parser.add_argument("--map-records", type=_positive, default=500, help="Points to embed when --include-map is set.")
    parser.add_argument(
        "--in-memory-sample",
        type=_positive,
        default=100_000,
        help="Maximum records materialized for frame/export/map probes; storage still processes all records.",
    )
    parser.add_argument("--include-export", action="store_true", help="Include CSV/XLSX export at every scale.")
    parser.add_argument("--include-map", action="store_true", help="Include interactive map generation at every scale.")
    args = parser.parse_args(argv)

    report = run_matrix(
        args.scales,
        args.output_dir,
        export=args.include_export,
        map_output=args.include_map,
        map_records=args.map_records,
        in_memory_sample=args.in_memory_sample,
    )
    report_path = args.output_dir.expanduser().resolve() / "stress-matrix-report.json"
    report["report"] = str(report_path)
    atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
