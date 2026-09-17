from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {
    ".py", ".md", ".yml", ".yaml", ".toml", ".txt", ".swift",
    ".ps1", ".sh", ".json", ".html", ".plist", ".ini", ".cfg",
}


def _blocked_terms() -> list[str]:
    # Split strings keep the guard itself target-neutral to ordinary repository search.
    return [
        "P" + "RC",
        "Chi" + "na",
        "Chi" + "nese",
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
    patterns = [re.compile(rf"(?i)(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])") for term in _blocked_terms()]
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if any(pattern.search(line) for pattern in patterns):
                findings.append(f"{path.relative_to(ROOT)}:{line_no}")
    assert not findings, "Target-specific public-repository markers found: " + ", ".join(findings[:30])
