import json
from datetime import date

import pytest

from sugar_core import release_tools as rt


def make_root(tmp_path, version="1.7.0"):
    (tmp_path / "sugar_core").mkdir()
    (tmp_path / "sugar_core" / "__init__.py").write_text(f'x = 1\n__version__ = "{version}"\n')
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "s"\nversion = "{version}"\n')
    d = tmp_path / "SUGAR-Desktop"
    (d / "src-tauri").mkdir(parents=True)
    (d / "package.json").write_text(f'{{\n  "name": "s",\n  "version": "{version}"\n}}\n')
    (d / "package-lock.json").write_text(f'{{\n  "version": "{version}",\n  "packages": {{"": {{\n      "version": "{version}"}},\n "node_modules/x": {{"version": "4.13.0"}}}}}}\n')
    (d / "src-tauri" / "tauri.conf.json").write_text(f'{{\n  "version": "{version}"\n}}\n')
    (d / "src-tauri" / "Cargo.toml").write_text(f'[package]\nname = "sugar-desktop"\nversion = "{version}"\n')
    (d / "src-tauri" / "Cargo.lock").write_text(f'[[package]]\nname = "sugar-desktop"\nversion = "{version}"\n\n[[package]]\nname = "other"\nversion = "{version}"\n')
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\nIntro.\n\n## Unreleased\n\n### Added\n\n- a thing\n\n## 1.7.0 - 2026-10-01\n\n- old\n")
    return tmp_path


def test_bump_rules():
    assert rt.bump("1.7.0", "patch") == "1.7.1" and rt.bump("1.7.9", "minor") == "1.8.0" and rt.bump("1.7.9", "major") == "2.0.0"
    with pytest.raises(ValueError):
        rt.bump("1.7.0-rc.1", "patch")


def test_cut_updates_every_file_and_rolls_the_changelog(tmp_path):
    root = make_root(tmp_path)
    result = rt.cut("minor", root, today=date(2026, 11, 2))
    assert result["new"] == "1.8.0" and result["tag"] == "v1.8.0" and "a thing" in result["notes"]
    assert rt.current_version(root) == "1.8.0"
    assert 'version = "1.8.0"' in (root / "pyproject.toml").read_text()
    assert json.loads((root / "SUGAR-Desktop" / "package.json").read_text())["version"] == "1.8.0"
    lock = json.loads((root / "SUGAR-Desktop" / "package-lock.json").read_text())
    assert lock["version"] == "1.8.0" and lock["packages"][""]["version"] == "1.8.0" and lock["packages"]["node_modules/x"]["version"] == "4.13.0"
    cargo_lock = (root / "SUGAR-Desktop" / "src-tauri" / "Cargo.lock").read_text()
    assert 'name = "sugar-desktop"\nversion = "1.8.0"' in cargo_lock and 'name = "other"\nversion = "1.7.0"' in cargo_lock
    changelog = (root / "CHANGELOG.md").read_text()
    assert "## 1.8.0 - 2026-11-02" in changelog and "## Unreleased" not in changelog and changelog.index("1.8.0") < changelog.index("## 1.7.0")


def test_empty_unreleased_falls_back_to_commit_headlines(tmp_path):
    root = make_root(tmp_path)
    (root / "CHANGELOG.md").write_text("# C\n\n## Unreleased\n\n## 1.7.0 - x\n")
    notes = rt.roll_changelog("1.7.1", root, today=date(2026, 1, 1), commits=["Fix map", "Add updates"])
    assert "- Fix map" in notes and "- Add updates" in notes


def test_build_info_is_importable(tmp_path):
    root = make_root(tmp_path)
    path = rt.write_build_info("abc123", "rolling", root)
    ns: dict = {}
    exec(path.read_text(), ns)
    assert ns["BUILD"]["commit"] == "abc123" and ns["BUILD"]["mode"] == "rolling" and ns["BUILD"]["version"] == "1.7.0"
