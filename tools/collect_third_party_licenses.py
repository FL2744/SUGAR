from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import re
import shutil
from collections import deque
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement


LEGAL_BASENAME_PREFIXES = ("license", "licence", "copying", "notice", "copyright")


def _normalise_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "unknown"


def _marker_matches(requirement: Requirement, extras: set[str]) -> bool:
    if requirement.marker is None:
        return True
    environments = extras or {""}
    for extra in environments:
        env = default_environment()
        env["extra"] = extra
        if requirement.marker.evaluate(env):
            return True
    return False


def _dependency_closure(roots: list[str], root_extras: set[str]) -> list[metadata.Distribution]:
    queue: deque[tuple[str, set[str]]] = deque()
    for index, root in enumerate(roots):
        queue.append((root, set(root_extras) if index == 0 else set()))

    seen_extras: dict[str, set[str]] = {}
    resolved: dict[str, metadata.Distribution] = {}

    while queue:
        name, extras = queue.popleft()
        key = _normalise_name(name)
        previous = seen_extras.get(key, set())
        if key in resolved and extras.issubset(previous):
            continue

        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError as exc:
            raise SystemExit(f"Required distribution is not installed: {name}") from exc

        resolved[key] = dist
        effective_extras = previous | extras
        seen_extras[key] = effective_extras

        for raw_requirement in dist.requires or []:
            requirement = Requirement(raw_requirement)
            if not _marker_matches(requirement, effective_extras):
                continue
            queue.append((requirement.name, set(requirement.extras)))

    return sorted(resolved.values(), key=lambda item: _normalise_name(item.metadata.get("Name", "")))


def _legal_files(dist: metadata.Distribution) -> list[Path]:
    files: list[Path] = []
    for relative in dist.files or []:
        rendered = str(relative).replace("\\", "/")
        basename = Path(rendered).name.casefold()
        lowered = rendered.casefold()
        in_metadata = ".dist-info/" in lowered or ".egg-info/" in lowered
        in_license_directory = "/licenses/" in lowered or lowered.startswith("licenses/")
        looks_legal = basename.startswith(LEGAL_BASENAME_PREFIXES)
        if not ((in_metadata and looks_legal) or in_license_directory):
            continue
        located = Path(dist.locate_file(relative))
        if located.is_file():
            files.append(located)
    return sorted(set(files))


def collect(output: Path, roots: list[str], extras: set[str]) -> dict[str, object]:
    output = output.expanduser().resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, object]] = []
    for dist in _dependency_closure(roots, extras):
        name = dist.metadata.get("Name") or "unknown"
        version = dist.version
        target = output / f"{_safe_component(name)}-{_safe_component(version)}"
        target.mkdir(parents=True, exist_ok=True)

        copied: list[str] = []
        for index, source in enumerate(_legal_files(dist), start=1):
            destination = target / source.name
            if destination.exists():
                destination = target / f"{index:02d}-{source.name}"
            shutil.copy2(source, destination)
            copied.append(str(destination.relative_to(output)).replace("\\", "/"))

        entries.append(
            {
                "name": name,
                "version": version,
                "license": dist.metadata.get("License") or "",
                "license_expression": dist.metadata.get("License-Expression") or "",
                "license_files": copied,
                "home_page": dist.metadata.get("Home-page") or "",
            }
        )

    manifest = {
        "roots": roots,
        "extras": sorted(extras),
        "packages": entries,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "README.txt").write_text(
        "This directory contains license/notice files discovered from the installed third-party "
        "dependency set used to build this SUGAR distribution. See ../THIRD_PARTY_NOTICES.md for "
        "the project-level summary.\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect third-party license materials for a SUGAR binary release.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--root", action="append", default=["sugar-osint"])
    parser.add_argument("--extra", action="append", default=[])
    args = parser.parse_args()

    roots = list(dict.fromkeys(args.root))
    manifest = collect(args.output, roots, set(args.extra))
    print(f"Collected licensing metadata for {len(manifest['packages'])} installed distributions into {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
