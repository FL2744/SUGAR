from pathlib import Path

import pytest

from sugar_core.utils import safe_artifact_stem


@pytest.mark.parametrize("value", ["../escape", r"..\escape", "C:/escape", "nested/name", "bad\x00name"])
def test_safe_artifact_stem_rejects_path_syntax(value: str):
    with pytest.raises(ValueError, match="single file name"):
        safe_artifact_stem(value)


def test_safe_artifact_stem_normalizes_hostile_filename_characters():
    assert safe_artifact_stem("Quarter 1 analyst? notes", "fallback") == "Quarter_1_analyst_notes"
    assert safe_artifact_stem("..", "fallback") == "fallback"
    assert "/" not in safe_artifact_stem(Path("report"), "fallback")


def test_safe_artifact_stem_bounds_length():
    result = safe_artifact_stem("a" * 200, "fallback", max_length=32)
    assert result == "a" * 32
