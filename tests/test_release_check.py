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
