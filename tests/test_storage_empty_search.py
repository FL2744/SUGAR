import json
from pathlib import Path

import pandas as pd

from sugar_core.storage import PREFERRED_COLUMNS, save_records


def test_empty_collection_is_saved_as_valid_research_result(tmp_path: Path) -> None:
    target = tmp_path / "empty.csv"
    frame = save_records([], target, metadata={"sources": ["mastodon"], "terms": ["example"]})

    assert frame.empty
    assert list(frame.columns) == PREFERRED_COLUMNS
    assert target.is_file()
    assert target.with_suffix(".xlsx").is_file()
    metadata = json.loads(target.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    assert metadata["records"] == 0
    assert metadata["sources"] == ["mastodon"]
    assert pd.read_csv(target).empty
