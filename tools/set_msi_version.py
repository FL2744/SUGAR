#!/usr/bin/env python3
"""Give the Windows installer a version that lets rolling builds upgrade each other (see release_tools.msi_version)."""
import argparse
import subprocess
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
parser.add_argument("--mode", default="release")
args = parser.parse_args()
commits = 0
try:
    last = subprocess.run(["git", "describe", "--tags", "--abbrev=0", "--match", "v*"], capture_output=True, text=True, check=True).stdout.strip()
    commits = int(subprocess.run(["git", "rev-list", "--count", f"{last}..HEAD"], capture_output=True, text=True, check=True).stdout.strip())
except (OSError, subprocess.CalledProcessError, ValueError):
    pass
print(release_tools.set_msi_version(args.mode, commits=commits))
