"""Run bounded, offline repetition tests for memory and checkpoint stability.

The soak runner repeats the existing synthetic stress probe in isolated temporary directories.
It never creates collector sessions, reads credentials, or makes network requests. Use a finite
iteration count for a quick regression check, or a duration with a large/no iteration cap for an
extended reliability run.
"""

from __future__ import annotations

import argparse
import json
import platform
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any

if __package__:
    from .stress_test import run_probes
else:  # Direct ``python tools/soak_test.py`` execution.
    from stress_test import run_probes

from sugar_core import __version__
try:
    from .benchmark_utils import atomic_write_text
except ImportError:  # Direct ``python tools/soak_test.py`` execution.
    from benchmark_utils import atomic_write_text


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def _nonnegative(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must not be negative")
    return parsed


def run_soak(
    records_count: int,
    *,
    iterations: int,
    duration_seconds: int,
    max_samples: int,
) -> dict[str, Any]:
    """Run synthetic probes until the iteration or duration budget is exhausted."""
    started = time.perf_counter()
    deadline = started + duration_seconds if duration_seconds else None
    samples: list[dict[str, Any]] = []
    completed = 0
    interrupted = False
    tracemalloc.start()
    try:
        while (iterations == 0 or completed < iterations) and (deadline is None or time.perf_counter() < deadline):
            iteration_started = time.perf_counter()
            with tempfile.TemporaryDirectory(prefix="sugar-soak-") as location:
                probe = run_probes(records_count, 0, Path(location), export=False, map_output=False)
            _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
            completed += 1
            sample = {
                "iteration": completed,
                "seconds": round(time.perf_counter() - iteration_started, 6),
                "records": records_count,
                "peak_python_bytes": peak_bytes,
                "disk_bytes": probe["disk_bytes"],
                "probe_results": probe["results"],
            }
            if len(samples) < max_samples:
                samples.append(sample)
            else:
                samples[(completed - 1) % max_samples] = sample
    except KeyboardInterrupt:
        interrupted = True
    finally:
        tracemalloc.stop()

    elapsed = time.perf_counter() - started
    return {
        "operation": "offline_soak",
        "sugar_version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "network": False,
        "records_per_iteration": records_count,
        "iterations_requested": iterations,
        "duration_seconds_requested": duration_seconds,
        "iterations_completed": completed,
        "elapsed_seconds": round(elapsed, 6),
        "interrupted": interrupted,
        "samples": samples,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=_positive, default=1000, help="Synthetic records per iteration.")
    parser.add_argument(
        "--iterations",
        type=_nonnegative,
        default=0,
        help="Maximum iterations; use 0 when the duration budget should control the run.",
    )
    parser.add_argument(
        "--duration-seconds",
        type=_nonnegative,
        default=0,
        help="Maximum runtime; use 0 when the iteration budget should control the run.",
    )
    parser.add_argument("--max-samples", type=_positive, default=1000, help="Bound report sample history.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for the JSON report.")
    args = parser.parse_args(argv)
    if args.iterations == 0 and args.duration_seconds == 0:
        parser.error("provide --iterations or --duration-seconds")

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_soak(
        args.records,
        iterations=args.iterations,
        duration_seconds=args.duration_seconds,
        max_samples=args.max_samples,
    )
    report_path = output_dir / "soak-report.json"
    report["report"] = str(report_path)
    atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 130 if report["interrupted"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
