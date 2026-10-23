"""Validate release versions and prepare signed Tauri updater configuration/feed.

Only public configuration is written to disk. Tauri reads its private signing key
directly from the environment; this module never prints or persists that value.
"""

from __future__ import annotations

import argparse
import ast
import base64
import binascii
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tomllib
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def release_version(tag: str) -> str:
    version = tag.removeprefix("v")
    match = SEMVER.fullmatch(version)
    if not match:
        raise ValueError("Release tags must use vMAJOR.MINOR.PATCH or vMAJOR.MINOR.PATCH-prerelease.")
    if match[4]:
        for part in match[4].split("."):
            if not part or (part.isdigit() and len(part) > 1 and part.startswith("0")):
                raise ValueError("Prerelease identifiers must follow semantic versioning.")
    return version


def repository_name(value: str) -> str:
    if not REPOSITORY.fullmatch(value) or any(part in {".", ".."} for part in value.split("/")):
        raise ValueError("The release repository must be owner/repository on github.com.")
    return value


def validate_versions(root: Path = ROOT, tag: str | None = None) -> str:
    desktop = root / "SUGAR-Desktop"
    package = json.loads((desktop / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((desktop / "package-lock.json").read_text(encoding="utf-8"))
    cargo_lock = tomllib.loads((desktop / "src-tauri/Cargo.lock").read_text(encoding="utf-8"))
    cargo_app = next(item for item in cargo_lock["package"] if item["name"] == "sugar-desktop")
    tree = ast.parse((root / "sugar_core/__init__.py").read_text(encoding="utf-8"))
    core_version = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign) and any(isinstance(name, ast.Name) and name.id == "__version__" for name in node.targets)
    )
    versions = {
        "pyproject.toml": tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"],
        "sugar_core.__version__": core_version,
        "package.json": package["version"],
        "package-lock.json": lock["version"],
        "package-lock.json root package": lock["packages"][""]["version"],
        "Cargo.toml": tomllib.loads((desktop / "src-tauri/Cargo.toml").read_text(encoding="utf-8"))["package"]["version"],
        "Cargo.lock": cargo_app["version"],
        "tauri.conf.json": json.loads((desktop / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))["version"],
    }
    expected = release_version(tag or str(versions["pyproject.toml"]))
    mismatches = [f"{name}: {value}" for name, value in versions.items() if value != expected]
    if mismatches:
        raise ValueError(f"Release version must be {expected} everywhere; mismatches: " + "; ".join(mismatches))
    return expected


def changelog_notes(tag: str, root: Path = ROOT) -> str:
    version = release_version(tag)
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.search(r"^## " + re.escape(version) + r"(?:[ \t]+[^\n]*)?$", changelog, re.MULTILINE)
    if not heading:
        raise ValueError(f"Add a versioned CHANGELOG.md section for {version} before publishing.")
    body = changelog[heading.end():]
    next_section = re.search(r"^## ", body, re.MULTILINE)
    if next_section:
        body = body[:next_section.start()]
    if not body.strip():
        raise ValueError(f"The changelog for {version} is empty.")
    return f"SUGAR {version}\n\n{body.strip()}\n"


def public_key_id(public_key: str) -> bytes:
    try:
        lines = base64.b64decode(public_key, validate=True).decode("ascii").splitlines()
        key = base64.b64decode(lines[1], validate=True)
        if not lines[0].startswith("untrusted comment:") or len(key) != 42 or key[:2] != b"Ed":
            raise ValueError
        return key[2:10]
    except (binascii.Error, UnicodeError, IndexError, ValueError) as issue:
        raise ValueError("SUGAR_UPDATER_PUBLIC_KEY must contain the complete Tauri .pub file contents.") from issue


def updater_config(environ: dict[str, str]) -> dict:
    public_key = environ.get("SUGAR_UPDATER_PUBLIC_KEY", "").strip()
    private_key_present = bool(environ.get("TAURI_SIGNING_PRIVATE_KEY", "").strip())
    required = environ.get("SUGAR_REQUIRE_UPDATER", "") == "1"
    if not public_key and not private_key_present and not required:
        return {"bundle": {"createUpdaterArtifacts": False}}
    if not public_key or not private_key_present:
        raise ValueError("Signed updater builds require SUGAR_UPDATER_PUBLIC_KEY and TAURI_SIGNING_PRIVATE_KEY.")
    public_key_id(public_key)
    repository = repository_name(environ.get("GITHUB_REPOSITORY", "FL2744/SUGAR"))
    return {
        "bundle": {"createUpdaterArtifacts": True},
        "plugins": {"updater": {
            "pubkey": public_key,
            "requireSignedVersion": True,
            "endpoints": [f"https://github.com/{repository}/releases/latest/download/latest.json"],
            "windows": {"installMode": "passive"},
        }},
    }


def read_signature(path: Path, expected_key: bytes, version: str) -> str:
    encoded = path.read_text(encoding="utf-8").strip()
    try:
        lines = base64.b64decode(encoded, validate=True).decode("ascii").splitlines()
        signature = base64.b64decode(lines[1], validate=True)
        global_signature = base64.b64decode(lines[3], validate=True)
        if (len(lines) != 4 or not lines[0].startswith("untrusted comment:")
                or not lines[2].startswith("trusted comment:") or len(signature) != 74
                or signature[:2] not in {b"Ed", b"ED"} or len(global_signature) != 64):
            raise ValueError
        if signature[2:10] != expected_key:
            raise ValueError("Signature was produced by a different updater signing key.")
        signed_version = next((field.removeprefix("version:") for field in lines[2].split("\t") if field.startswith("version:")), None)
        if signed_version != version:
            raise ValueError("Signature must be bound to the release version. Build with Tauri CLI 2.12 or newer.")
    except (binascii.Error, UnicodeError, IndexError, ValueError) as issue:
        raise ValueError(f"Invalid updater signature {path.name}: {issue}") from issue
    return encoded


def create_manifest(assets: Path, tag: str, repository: str, public_key: str, notes: str = "", published: str | None = None) -> dict:
    version = release_version(tag)
    repository = repository_name(repository)
    expected_key = public_key_id(public_key.strip())
    platforms = {}
    # Only the architectures actually built and smoke-tested by release.yml.
    for target, pattern in (("windows-x86_64", "*.msi"), ("darwin-aarch64", "*.app.tar.gz")):
        matches = sorted(assets.rglob(pattern))
        if len(matches) != 1 or matches[0].stat().st_size == 0:
            raise ValueError(f"Expected exactly one nonempty {target} updater artifact ({pattern}).")
        artifact = matches[0]
        signature = artifact.with_name(artifact.name + ".sig")
        if not signature.is_file():
            raise ValueError(f"Missing signature for {artifact.name}.")
        platforms[target] = {
            "url": f"https://github.com/{repository}/releases/download/{quote('v' + version, safe='')}/{quote(artifact.name, safe='')}",
            "signature": read_signature(signature, expected_key, version),
        }
    published = published or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    date = datetime.fromisoformat(published.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("The publication date must include a timezone.")
    return {"version": version, "notes": notes.strip(), "pub_date": published, "platforms": platforms}


def collect_assets(source: Path, destination: Path) -> None:
    files = sorted(item for item in source.rglob("*") if item.is_file())
    if not files:
        raise ValueError("No release artifacts were downloaded.")
    names = [item.name for item in files]
    if len(names) != len(set(names)):
        raise ValueError("Release artifact filenames collide; refusing to overwrite an asset.")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("The release asset directory must be empty.")
    if destination.resolve().is_relative_to(source.resolve()):
        raise ValueError("The release asset directory must be outside the downloaded artifact directory.")
    destination.mkdir(parents=True, exist_ok=True)
    for item in files:
        shutil.copy2(item, destination / item.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    versions = commands.add_parser("versions", help="Check every package/desktop version, optionally against a release tag")
    versions.add_argument("--tag")
    notes = commands.add_parser("notes", help="Extract the versioned changelog section for release and updater notes")
    notes.add_argument("--tag", required=True)
    notes.add_argument("--output", type=Path, required=True)
    config = commands.add_parser("updater-config", help="Write a public build override; require signing credentials in release CI")
    config.add_argument("--output", type=Path, required=True)
    collect = commands.add_parser("collect-assets", help="Flatten downloaded artifacts without overwriting filenames")
    collect.add_argument("--source", type=Path, required=True)
    collect.add_argument("--output", type=Path, required=True)
    manifest = commands.add_parser("manifest", help="Build the updater feed from signed Windows and macOS artifacts")
    manifest.add_argument("--assets", type=Path, required=True)
    manifest.add_argument("--tag", required=True)
    manifest.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "FL2744/SUGAR"))
    manifest.add_argument("--notes", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "versions":
            print(f"Release versions agree: {validate_versions(tag=args.tag)}")
            return 0
        if args.command == "collect-assets":
            collect_assets(args.source, args.output)
            print(f"Collected release assets in {args.output}")
            return 0
        if args.command == "notes":
            content = changelog_notes(args.tag)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
            print(f"Wrote {args.output}")
            return 0
        if args.command == "updater-config":
            output, payload = args.output, updater_config(dict(os.environ))
        else:
            output = args.assets / "latest.json"
            notes = args.notes.read_text(encoding="utf-8") if args.notes else ""
            payload = create_manifest(args.assets, args.tag, args.repository, os.environ.get("SUGAR_UPDATER_PUBLIC_KEY", ""), notes)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {output}")
        return 0
    except (ValueError, OSError, KeyError, StopIteration) as issue:
        print(f"Release validation failed: {issue}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
