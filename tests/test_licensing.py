from pathlib import Path
import tomllib

from tools.collect_third_party_licenses import _normalise_name


ROOT = Path(__file__).resolve().parents[1]


def test_apache_license_contract_is_declared_consistently():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["license"] == "Apache-2.0"
    assert set(project["license-files"]) == {"LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"}
    assert {author["name"] for author in project["authors"]} == {"Alejandro Grenier"}

    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text

    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "Copyright 2026 Alejandro Grenier and contributors." in notice
    assert "Virginia Tech" in notice
    assert "U.S. Department of State" in notice


def test_third_party_notice_covers_packaged_and_optional_license_boundaries():
    text = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for expected in (
        "PySide6",
        "LGPLv3",
        "PyInstaller",
        "certifi",
        "Mozilla Public License 2.0",
        "python-bidi",
    ):
        assert expected in text

    qt_notice = (ROOT / "third_party_licenses" / "qt" / "README.md").read_text(encoding="utf-8")
    assert "LGPLv3 option" in qt_notice
    assert "Corresponding source offer" in qt_notice
    assert "at least three years" in qt_notice

    assert "GNU LESSER GENERAL PUBLIC LICENSE" in (
        ROOT / "third_party_licenses" / "qt" / "LGPL-3.0.txt"
    ).read_text(encoding="utf-8")
    assert "GNU GENERAL PUBLIC LICENSE" in (
        ROOT / "third_party_licenses" / "qt" / "GPL-3.0.txt"
    ).read_text(encoding="utf-8")


def test_license_inventory_name_normalisation_is_stable():
    assert _normalise_name("PySide6_Essentials") == "pyside6-essentials"
    assert _normalise_name("python_bidi") == "python-bidi"


def test_windows_gui_qt_surface_stays_within_reviewed_modules():
    allowed = {"QtCore", "QtGui", "QtWidgets"}
    imported: set[str] = set()
    for source in (ROOT / "SUGAR-Windows").glob("*.py"):
        for line in source.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("from PySide6."):
                imported.add(stripped.split("from PySide6.", 1)[1].split(" import ", 1)[0])
            elif stripped.startswith("import PySide6."):
                imported.add(stripped.split("import PySide6.", 1)[1].split()[0].split(",", 1)[0])

    assert imported
    assert imported <= allowed, f"Qt module import requires licensing review: {sorted(imported - allowed)}"
