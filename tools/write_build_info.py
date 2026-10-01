#!/usr/bin/env python3
"""Stamp the commit this build is made from (used by the release workflow before packaging)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sugar_core import release_tools  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--commit", required=True)
parser.add_argument("--mode", default="release")
args = parser.parse_args()
print(release_tools.write_build_info(args.commit, args.mode))
