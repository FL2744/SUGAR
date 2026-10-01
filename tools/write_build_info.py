#!/usr/bin/env python3
"""Stamp the commit this build is made from (used by the release workflow before packaging)."""
import argparse
import importlib.util
import sys
from pathlib import Path

# Load release_tools straight from its file: importing the sugar_core package would need every runtime dependency installed.
_path = Path(__file__).resolve().parents[1] / "sugar_core" / "release_tools.py"
_spec = importlib.util.spec_from_file_location("release_tools", _path)
release_tools = importlib.util.module_from_spec(_spec)
sys.modules["release_tools"] = release_tools
_spec.loader.exec_module(release_tools)

parser = argparse.ArgumentParser()
parser.add_argument("--commit", required=True)
parser.add_argument("--mode", default="release")
args = parser.parse_args()
print(release_tools.write_build_info(args.commit, args.mode))
