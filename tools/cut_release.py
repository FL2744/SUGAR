#!/usr/bin/env python3
"""Cut a SUGAR release: bump the version everywhere and roll the changelog.

    python tools/cut_release.py patch        # 1.7.0 -> 1.7.1
    python tools/cut_release.py minor --notes-file RELEASE_NOTES.md

It only edits files. The "Cut release" workflow commits the result and starts the release build.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sugar_core import release_tools  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("part", choices=("patch", "minor", "major"))
    parser.add_argument("--notes-file", default="", help="Write the release notes here.")
    args = parser.parse_args()
    result = release_tools.cut(args.part)
    if args.notes_file:
        Path(args.notes_file).write_text(result["notes"] + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "notes"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
