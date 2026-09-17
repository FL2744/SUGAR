import re
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from sugar_core import __version__
from tools.check_release import validate


def test_release_check_requires_exact_package_version():
    validate(f"v{__version__}", changelog=f"## {__version__} — release")


@pytest.mark.parametrize("tag", ["1.2.0", "v1.2", "v1.2.0-rc1", "v01.2.0"])
def test_release_check_rejects_non_release_tags(tag):
    with pytest.raises(ValueError):
        validate(tag, changelog=f"## {__version__} — release")


def test_release_check_rejects_version_mismatch():
    with pytest.raises(ValueError, match="does not match"):
        validate("v9.9.9", version=__version__, changelog=f"## {__version__} — release")


def test_native_package_metadata_tracks_canonical_version_and_protocol():
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    plist = ET.parse(root / "SUGAR-macOS" / "Resources" / "Info.plist")
    values = [element.text for element in plist.getroot().iter() if element.text]
    assert version in values

    bridge = (root / "sugar_bridge.py").read_text(encoding="utf-8")
    protocol = re.search(r"^BRIDGE_PROTOCOL_VERSION = (\d+)$", bridge, re.MULTILINE)
    assert protocol
    build_script = (root / "SUGAR-Windows" / "scripts" / "build.ps1").read_text(encoding="utf-8")
    assert "bridge_protocol = [int]$BridgeProtocol" in build_script
    assert "version = $Version" in build_script
