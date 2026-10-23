from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {
    ".py", ".md", ".yml", ".yaml", ".toml", ".txt", ".swift",
    ".ps1", ".sh", ".json", ".html", ".plist", ".ini", ".cfg",
}

# Public directory integration names are part of the supported adapter contract.
# This exception permits only that name in the adapter, its entry points, tests,
# and release documentation; the rest of the mission-marker guard still applies.
PUBLIC_BASELINE_FILES = {
    "README.md", "CHANGELOG.md", "docs/public-repository-boundaries.md",
    "sugar_core/official_baselines.py", "sugar_core/workspace_cli.py",
    "sugar_core/workspace_hub.py", "tests/test_official_baselines.py",
}


def _patterns_for(relative: str) -> list[re.Pattern]:
    return [
        re.compile(rf"(?i)(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])")
        for term in _blocked_terms()
        if not (term == "Con" + "fucius" and relative in PUBLIC_BASELINE_FILES)
    ]


def _blocked_terms() -> list[str]:
    # Split strings keep the guard itself target-neutral to ordinary repository search.
    return [
        "P" + "RC",
        "Chi" + "na",
        "Bei" + "jing",
        "C" + "CP",
        "C" + "PC",
        "Con" + "fucius",
        "Lu" + "ban",
        "Xi " + "Jinping",
        "Kyrgyz" + "stan",
        "孔" + "子学院",
        "鲁" + "班工坊",
    ]


def test_public_tree_has_no_target_specific_mission_markers():
    findings: list[str] = []
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        pytest.skip("git is required to identify the public repository tree")
    if tracked.returncode != 0:
        pytest.skip("could not enumerate Git-tracked public repository files")

    for relative in tracked.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        if not relative:
            continue
        path = ROOT / relative
        patterns = _patterns_for(relative)
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if any(pattern.search(line) for pattern in patterns):
                findings.append(f"{path.relative_to(ROOT)}:{line_no}")
    assert not findings, "Target-specific public-repository markers found: " + ", ".join(findings[:30])


def test_public_baseline_exception_is_limited_to_its_name_and_files():
    public_name = "Con" + "fucius"
    mission_marker = "Bei" + "jing"
    assert not any(pattern.search(public_name) for pattern in _patterns_for("sugar_core/official_baselines.py"))
    assert any(pattern.search(mission_marker) for pattern in _patterns_for("sugar_core/official_baselines.py"))
    assert any(pattern.search(public_name) for pattern in _patterns_for("project/watchlist.json"))
