from pathlib import Path
import tomllib

from packaging.specifiers import SpecifierSet
from packaging.version import Version


ROOT = Path(__file__).resolve().parents[1]


def test_declared_python_support_covers_311_through_314_only():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    supported = SpecifierSet(project["requires-python"])

    for version in ("3.11", "3.12", "3.13", "3.14"):
        assert Version(version) in supported

    assert Version("3.10") not in supported
    assert Version("3.15") not in supported

    classifiers = set(project["classifiers"])
    for version in ("3.11", "3.12", "3.13", "3.14"):
        assert f"Programming Language :: Python :: {version}" in classifiers


def test_ci_matrix_exercises_python_314_cross_platform():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    # Branch development gets one fast Linux 3.14 gate, while the compatibility
    # matrix keeps 3.14 coverage on both native desktop operating systems. This
    # preserves the cross-platform support contract without restoring the old
    # 3 OS x 4 Python Cartesian matrix.
    assert 'fast-test:' in workflow
    assert 'runs-on: ubuntu-latest' in workflow
    assert 'python-version: "3.14"' in workflow
    assert '- os: macos-latest\n            python-version: "3.14"' in workflow
    assert '- os: windows-latest\n            python-version: "3.14"' in workflow
    for version in ("3.11", "3.12", "3.13"):
        assert f'python-version: "{version}"' in workflow


def test_python_314_dependency_floors_are_explicit():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    dependencies = set(project["dependencies"])
    assert "pandas>=2.3.3,<3; python_version >= '3.14'" in dependencies
    assert "pandas>=2.2,<3; python_version < '3.14'" in dependencies
    assert "pyinstaller>=6.15,<7" in project["optional-dependencies"]["macos"]
    assert "pyinstaller>=6.15,<7" in project["optional-dependencies"]["windows"]
