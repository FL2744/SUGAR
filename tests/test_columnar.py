import json
from pathlib import Path

from sugar_core.columnar import build_parquet_dataset, query_parquet_dataset


def test_columnar_build_partitions_canonical_csv_and_queries_without_pandas(tmp_path: Path):
    source = tmp_path / "records.csv"
    source.write_text(
        "platform,native_id,original_text\n"
        "x,1,English source\n"
        "weibo,2,Chinese source\n"
        "x,3,Another English source\n",
        encoding="utf-8",
    )
    dataset = tmp_path / "parquet"

    build = build_parquet_dataset(source, dataset)
    query = query_parquet_dataset(
        dataset,
        "SELECT platform, COUNT(*) AS records FROM evidence GROUP BY platform ORDER BY platform",
    )

    assert build["records"] == 3
    assert build["partitioned_by"] == "platform"
    assert len(build["parquet_files"]) == 2
    assert query["rows"] == [
        {"platform": "weibo", "records": 1},
        {"platform": "x", "records": 2},
    ]


def test_columnar_build_accepts_jsonl_and_bounds_query_interface(tmp_path: Path):
    source = tmp_path / "records.jsonl"
    source.write_text(
        json.dumps({"platform": "x", "native_id": "1", "original_text": "one"}) + "\n"
        + json.dumps({"platform": "x", "native_id": "2", "original_text": "two"}) + "\n",
        encoding="utf-8",
    )
    dataset = tmp_path / "parquet"
    assert build_parquet_dataset(source, dataset)["records"] == 2
    assert query_parquet_dataset(dataset, "SELECT COUNT(*) AS records FROM evidence")["rows"] == [{"records": 2}]
