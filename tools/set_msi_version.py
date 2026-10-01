#!/usr/bin/env python3
"""Give the Windows installer a version that lets rolling builds upgrade each other (see release_tools.msi_version)."""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sugar_core import release_tools  # noqa: E402

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
