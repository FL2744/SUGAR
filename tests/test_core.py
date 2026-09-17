import json

import pandas as pd

from sugar_core import __version__
from sugar_core.collectors import normalize_engagement
from sugar_core.models import PostRecord, merge_record
from sugar_core.reporting import _prepare
from sugar_core.storage import load_results, records_to_frame, save_records
from sugar_core.utils import in_inclusive_date_range, safe_cell


def test_mastodon_engagement_normalization():
    raw = {"favourite_count": 7, "reply_count": 2, "reblog_count": 3}
    result = normalize_engagement("mastodon", raw)
    assert result["likes"] == 7
    assert result["replies"] == 2
    assert result["reposts"] == 3


def test_query_matches_are_preserved_when_deduping():
    a = PostRecord(platform="x", native_id="1", canonical_url="u", query="alpha", query_matches=["alpha"])
    b = PostRecord(platform="x", native_id="1", canonical_url="u", query="beta", query_matches=["beta"])
    merge_record(a, b)
    assert a.query_matches == ["alpha", "beta"]


def test_until_date_is_inclusive():
    assert in_inclusive_date_range("2026-09-10T23:59:59Z", "2026-09-01", "2026-09-10")
    assert not in_inclusive_date_range("2026-09-11T00:00:00Z", "2026-09-01", "2026-09-10")


def test_formula_injection_guard_does_not_corrupt_numbers():
    assert safe_cell("=2+2") == "'=2+2"
    assert safe_cell(-77.4) == -77.4


def test_export_has_stable_and_legacy_fields():
    record = PostRecord(
        platform="bluesky",
        native_id="abc",
        canonical_url="https://example.test/p/abc",
        query="q",
        query_matches=["q"],
        engagement={"likes": 1},
    )
    frame = records_to_frame([record])
    assert frame.loc[0, "native_id"] == "abc"
    assert frame.loc[0, "tweet_id"] == "abc"
    assert json.loads(frame.loc[0, "query_matches"]) == ["q"]


def test_new_records_advertise_the_current_collector_version():
    record = PostRecord(platform="x", native_id="abc", canonical_url="u", query="q")
    assert record.collector_version == f"sugar-core-{__version__}"


def test_csv_and_xlsx_loaders_preserve_numeric_looking_native_ids(tmp_path):
    record = PostRecord(
        platform="x",
        native_id="000123",
        canonical_url="https://example.test/p/000123",
        query="q",
    )
    save_records([record], tmp_path / "posts.csv")
    metadata = json.loads((tmp_path / "posts.metadata.json").read_text(encoding="utf-8"))
    assert metadata["sugar_version"] == __version__

    for path in (tmp_path / "posts.csv", tmp_path / "posts.xlsx"):
        loaded = load_results(path)
        assert loaded.loc[0, "native_id"] == "000123"
        assert isinstance(loaded.loc[0, "native_id"], str)


def test_analysis_counts_legacy_mastodon_metrics():
    df = pd.DataFrame(
        [
            {
                "platform": "mastodon",
                "tweet_id": "1",
                "date_iso": "2026-09-10T10:00:00Z",
                "detected_language": "en",
                "inferred_location": "",
                "raw_stats": json.dumps({"favourite_count": 4, "reply_count": 1, "reblog_count": 2}),
            }
        ]
    )
    work, metrics = _prepare(df)
    assert int(work.loc[0, "engagement_total"]) == 7
    assert metrics["engagement"] == 7
