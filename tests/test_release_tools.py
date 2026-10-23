import base64
from pathlib import Path
import shutil

import pytest

from tools import release_tools as release


KEY_ID = b"12345678"
PUBLIC_KEY = base64.b64encode(
    b"untrusted comment: minisign public key\n" + base64.b64encode(b"Ed" + KEY_ID + bytes(32)) + b"\n"
).decode()


def signature(key_id: bytes = KEY_ID, version: str = "1.6.1") -> str:
    return base64.b64encode(b"\n".join([
        b"untrusted comment: signature from minisign secret key",
        base64.b64encode(b"ED" + key_id + bytes(64)),
        b"trusted comment: timestamp:1\tfile:SUGAR\tversion:" + version.encode(),
        base64.b64encode(bytes(64)),
    ]) + b"\n").decode()


def artifacts(path: Path, version: str = "1.6.1") -> Path:
    path.mkdir(parents=True)
    for name in ("SUGAR_1.6.1_x64_en-US.msi", "SUGAR.app.tar.gz"):
        (path / name).write_bytes(b"test installer payload")
        (path / (name + ".sig")).write_text(signature(version=version), encoding="utf-8")
    return path


def test_repository_versions_are_synchronized() -> None:
    version = release.validate_versions()
    assert release.validate_versions(tag="v" + version) == version
    with pytest.raises(ValueError, match="mismatches"):
        release.validate_versions(tag="v" + version + "-rc.1")


def test_release_notes_include_only_the_requested_version(tmp_path: Path) -> None:
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n\nFuture work\n\n## 1.7.0 — 2026-10-15\n\n- Verified updates\n\n## 1.6.1\n\nOlder work\n", encoding="utf-8")
    assert release.changelog_notes("v1.7.0", tmp_path) == "SUGAR 1.7.0\n\n- Verified updates\n"
    with pytest.raises(ValueError, match="versioned"):
        release.changelog_notes("v1.8.0", tmp_path)
    (tmp_path / "CHANGELOG.md").write_text("## 1.7.0\n\n## 1.6.1\nOld work", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        release.changelog_notes("v1.7.0", tmp_path)


@pytest.mark.parametrize("name", ["package.json", "package-lock.json", "src-tauri/Cargo.toml", "src-tauri/Cargo.lock", "src-tauri/tauri.conf.json"])
def test_version_validation_rejects_desktop_drift(tmp_path: Path, name: str) -> None:
    root = tmp_path / "repo"
    files = ["pyproject.toml", "sugar_core/__init__.py"] + ["SUGAR-Desktop/" + file for file in (
        "package.json", "package-lock.json", "src-tauri/Cargo.toml", "src-tauri/Cargo.lock", "src-tauri/tauri.conf.json",
    )]
    for file in files:
        target = root / file
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(release.ROOT / file, target)
    path = root / "SUGAR-Desktop" / name
    version = release.validate_versions(root)
    path.write_text(path.read_text(encoding="utf-8").replace(version, "9.9.9"), encoding="utf-8")
    with pytest.raises(ValueError, match="mismatches"):
        release.validate_versions(root)


@pytest.mark.parametrize("tag", ["v1.2", "v01.2.3", "v1.2.3-rc..1", "v1.2.3-01", "v1.2.3;touch", "v1.2.3+build"])
def test_malformed_release_tags_are_rejected(tag: str) -> None:
    with pytest.raises(ValueError):
        release.release_version(tag)


def test_unsigned_local_build_is_explicit_and_release_requires_keys() -> None:
    assert release.updater_config({}) == {"bundle": {"createUpdaterArtifacts": False}}
    for env in ({"SUGAR_REQUIRE_UPDATER": "1"}, {"SUGAR_UPDATER_PUBLIC_KEY": PUBLIC_KEY}, {"TAURI_SIGNING_PRIVATE_KEY": "sensitive-key"}):
        with pytest.raises(ValueError, match="require") as error:
            release.updater_config(env)
        assert "sensitive-key" not in str(error.value)


def test_signed_config_contains_only_public_material() -> None:
    config = release.updater_config({
        "SUGAR_REQUIRE_UPDATER": "1", "SUGAR_UPDATER_PUBLIC_KEY": PUBLIC_KEY,
        "TAURI_SIGNING_PRIVATE_KEY": "sensitive-key", "GITHUB_REPOSITORY": "Example/SUGAR",
    })
    assert config["bundle"]["createUpdaterArtifacts"] is True
    assert config["plugins"]["updater"]["endpoints"] == ["https://github.com/Example/SUGAR/releases/latest/download/latest.json"]
    assert "sensitive-key" not in str(config)
    with pytest.raises(ValueError, match="complete Tauri"):
        release.updater_config({"SUGAR_UPDATER_PUBLIC_KEY": "path/to/file.pub", "TAURI_SIGNING_PRIVATE_KEY": "secret"})


def test_manifest_has_signed_architecture_specific_downloads(tmp_path: Path) -> None:
    result = release.create_manifest(artifacts(tmp_path / "assets", "1.6.1-rc.1"), "v1.6.1-rc.1", "Example/SUGAR", PUBLIC_KEY, "  Release notes  ", "2026-10-15T12:00:00Z")
    assert result["version"] == "1.6.1-rc.1"
    assert result["notes"] == "Release notes"
    assert set(result["platforms"]) == {"windows-x86_64", "darwin-aarch64"}
    windows = result["platforms"]["windows-x86_64"]
    assert windows["url"] == "https://github.com/Example/SUGAR/releases/download/v1.6.1-rc.1/SUGAR_1.6.1_x64_en-US.msi"
    assert windows["signature"] == signature(version="1.6.1-rc.1")


@pytest.mark.parametrize("problem", ["missing-mac", "missing-signature", "invalid-signature", "wrong-key", "wrong-version", "empty-installer", "duplicate-installer"])
def test_manifest_rejects_incomplete_or_untrusted_payloads(tmp_path: Path, problem: str) -> None:
    assets = artifacts(tmp_path / "assets")
    if problem == "missing-mac":
        (assets / "SUGAR.app.tar.gz").unlink()
    elif problem == "missing-signature":
        (assets / "SUGAR.app.tar.gz.sig").unlink()
    elif problem == "invalid-signature":
        (assets / "SUGAR.app.tar.gz.sig").write_text("not a signature", encoding="utf-8")
    elif problem == "wrong-key":
        (assets / "SUGAR.app.tar.gz.sig").write_text(signature(b"87654321"), encoding="utf-8")
    elif problem == "wrong-version":
        (assets / "SUGAR.app.tar.gz.sig").write_text(signature(version="1.0.0"), encoding="utf-8")
    elif problem == "empty-installer":
        (assets / "SUGAR.app.tar.gz").write_bytes(b"")
    else:
        (assets / "other.msi").write_bytes(b"extra installer")
    with pytest.raises(ValueError):
        release.create_manifest(assets, "v1.6.1", "Example/SUGAR", PUBLIC_KEY)


def test_asset_collection_preserves_every_file_and_refuses_collisions(tmp_path: Path) -> None:
    source = tmp_path / "downloaded"
    assets = artifacts(source / "native" / "bundle")
    output = tmp_path / "assets"
    release.collect_assets(source, output)
    assert {item.name for item in output.iterdir()} == {item.name for item in assets.iterdir()}
    with pytest.raises(ValueError, match="empty"):
        release.collect_assets(source, output)
    (source / "duplicate").mkdir()
    shutil.copy2(assets / "SUGAR.app.tar.gz", source / "duplicate/SUGAR.app.tar.gz")
    with pytest.raises(ValueError, match="collide"):
        release.collect_assets(source, tmp_path / "other-output")


def test_release_cli_reports_configuration_errors_without_a_traceback(capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SUGAR_REQUIRE_UPDATER", "1")
    monkeypatch.delenv("SUGAR_UPDATER_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("TAURI_SIGNING_PRIVATE_KEY", raising=False)
    assert release.main(["updater-config", "--output", str(tmp_path / "config.json")]) == 2
    assert "Traceback" not in capsys.readouterr().err
    assert not (tmp_path / "config.json").exists()
