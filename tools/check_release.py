"""Validate that a release tag, package version, and changelog entry agree."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from sugar_core import __version__


def validate(tag: str, *, version: str = __version__, changelog: str | None = None) -> None:
    match = re.fullmatch(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag.strip())
    if not match:
        raise ValueError(f"Release tag must use vMAJOR.MINOR.PATCH, got {tag!r}.")
    tag_version = tag[1:]
    if tag_version != version:
        raise ValueError(f"Release tag {tag!r} does not match package version {version!r}.")
    contents = changelog if changelog is not None else Path("CHANGELOG.md").read_text(encoding="utf-8")
    if f"## {version} —" not in contents and f"## {version} " not in contents:
        raise ValueError(f"CHANGELOG.md has no release heading for {version}.")


def main(argv: list[str] | None = None) -> int:
    values = argv if argv is not None else sys.argv[1:]
    if len(values) != 1:
        print("usage: check_release.py vMAJOR.MINOR.PATCH", file=sys.stderr)
        return 2
    try:
        validate(values[0])
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"validated {values[0]} for sugar-osint {__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
