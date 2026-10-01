"""Release automation: bump the version everywhere, roll the changelog, and write build information.

Used by ``tools/cut_release.py`` (and the "Cut release" GitHub workflow) so a release is one action, not a checklist.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def bump(version: str, part: str) -> str:
    match = _SEMVER.match(version)
    if not match:
        raise ValueError(f"{version!r} is not a plain MAJOR.MINOR.PATCH version.")
    major, minor, patch = (int(g) for g in match.groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError("bump is major, minor or patch.")


def current_version(root: Path = ROOT) -> str:
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', (root / "sugar_core" / "__init__.py").read_text(encoding="utf-8"), re.M)
    if not match:
        raise ValueError("Could not find __version__.")
    return match.group(1)


def _sub(path: Path, pattern: str, repl: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(pattern, repl, text, count=count, flags=re.M)
    if n == 0:
        raise ValueError(f"No version found in {path.name}.")
    path.write_text(new, encoding="utf-8", newline="\n")


def set_version(new: str, root: Path = ROOT) -> list[str]:
    """Write ``new`` to every file that carries the package version. Returns the files changed."""
    old = current_version(root)
    changed = []
    _sub(root / "sugar_core" / "__init__.py", r'^__version__\s*=\s*"[^"]+"', f'__version__ = "{new}"')
    _sub(root / "pyproject.toml", r'^version\s*=\s*"[^"]+"', f'version = "{new}"')
    desktop = root / "SUGAR-Desktop"
    _sub(desktop / "package.json", r'^(\s*"version":\s*)"[^"]+"', rf'\g<1>"{new}"')
    _sub(desktop / "src-tauri" / "tauri.conf.json", r'^(\s*"version":\s*)"[^"]+"', rf'\g<1>"{new}"')
    _sub(desktop / "src-tauri" / "Cargo.toml", r'^version\s*=\s*"[^"]+"', f'version = "{new}"')
    lock = desktop / "package-lock.json"
    if lock.exists():
        text = lock.read_text(encoding="utf-8")
        text = text.replace(f'"version": "{old}"', f'"version": "{new}"', 2)     # the root entry and packages[""] only
        lock.write_text(text, encoding="utf-8", newline="\n")
    cargo_lock = desktop / "src-tauri" / "Cargo.lock"
    if cargo_lock.exists():
        _sub(cargo_lock, rf'(name = "sugar-desktop"\nversion = )"{re.escape(old)}"', rf'\g<1>"{new}"')
    changed = ["sugar_core/__init__.py", "pyproject.toml", "SUGAR-Desktop/package.json", "SUGAR-Desktop/package-lock.json", "SUGAR-Desktop/src-tauri/tauri.conf.json",
               "SUGAR-Desktop/src-tauri/Cargo.toml", "SUGAR-Desktop/src-tauri/Cargo.lock"]
    return changed


def roll_changelog(new: str, root: Path = ROOT, *, today: date | None = None, commits: list[str] | None = None) -> str:
    """Turn the ``## Unreleased`` section into ``## <new> - <date>`` and return that section's text (the release notes).

    With nothing under Unreleased, the commit headlines since the last release are used so a release is never empty.
    """
    path = root / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    stamp = (today or date.today()).isoformat()
    match = re.search(r"^## Unreleased[ \t]*\n(.*?)(?=^## )", text, re.M | re.S)
    body = (match.group(1).strip() if match else "")
    if not body and commits:
        body = "### Changes\n\n" + "\n".join(f"- {c}" for c in commits)
    section = f"## {new} - {stamp}\n\n{body}\n\n" if body else f"## {new} - {stamp}\n\nMaintenance release.\n\n"
    if match:
        text = text[:match.start()] + section + text[match.end():]
    else:
        first = re.search(r"^## ", text, re.M)
        text = text[:first.start()] + section + text[first.start():] if first else text + "\n" + section
    path.write_text(text, encoding="utf-8", newline="\n")
    return section.split("\n", 2)[2].strip()


def commits_since_last_release(root: Path = ROOT) -> list[str]:
    try:
        last = subprocess.run(["git", "describe", "--tags", "--abbrev=0", "--match", "v*"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        log = subprocess.run(["git", "log", f"{last}..HEAD", "--no-merges", "--pretty=%s"], cwd=root, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line.strip() for line in log.splitlines() if line.strip() and not line.startswith(("Trigger SUGAR", "Retry SUGAR"))][:40]


def cut(part: str, root: Path = ROOT, *, today: date | None = None) -> dict[str, Any]:
    old = current_version(root)
    new = bump(old, part)
    commits = commits_since_last_release(root)
    set_version(new, root)
    notes = roll_changelog(new, root, today=today, commits=commits)
    return {"old": old, "new": new, "tag": f"v{new}", "notes": notes}


def write_build_info(commit: str, mode: str, root: Path = ROOT, *, version: str = "") -> Path:
    """Record which commit a build was made from, so the app can tell whether a newer one exists."""
    path = root / "sugar_core" / "_build_info.py"
    info = {"commit": commit, "mode": mode, "version": version or current_version(root), "built_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
    path.write_text("# Generated at build time; not committed.\nBUILD = " + json.dumps(info, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path
