from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_EXTERNAL_SQL = re.compile(
    r"\b(?:read_[a-z0-9_]*|[a-z0-9_]*_scan|glob|http_[a-z0-9_]*)\s*\(|"
    r"\b(?:copy|install|load|attach|detach|pragma|export|import|checkpoint|force_checkpoint|shell|system)\b|"
    r"\bfrom\s+['\"]",
    re.IGNORECASE,
)


def _duckdb():
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError(
            "The columnar analytical engine is optional. Install it with `python -m pip install 'sugar-osint[analytics]'`."
        ) from exc
    return duckdb


def _sql_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def build_parquet_dataset(source_file: str | Path, output_directory: str | Path) -> dict[str, Any]:
    """Stream CSV or JSONL records into a DuckDB-written, optionally platform-partitioned Parquet dataset."""
    source = Path(source_file).expanduser().resolve(strict=True)
    output = Path(output_directory).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(f"Parquet output path already exists: {output}")
    if source.suffix.casefold() in {".jsonl", ".ndjson"}:
        relation = f"read_json_auto({_sql_literal(source)}, format='newline_delimited', union_by_name=true)"
        source_format = "jsonl"
    elif source.suffix.casefold() == ".csv":
        relation = f"read_csv_auto({_sql_literal(source)}, union_by_name=true, sample_size=-1)"
        source_format = "csv"
    else:
        raise ValueError("Columnar build accepts canonical CSV or JSONL/NDJSON files.")

    output.parent.mkdir(parents=True, exist_ok=True)
    connection = _duckdb().connect(":memory:")
    try:
        columns = [row[0] for row in connection.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()]
        partition = " (platform)" if "platform" in columns else ""
        connection.execute(
            f"COPY (SELECT * FROM {relation}) TO {_sql_literal(output)} "
            f"(FORMAT PARQUET, COMPRESSION ZSTD{', PARTITION_BY' + partition if partition else ''})"
        )
        parquet_glob = output.as_posix().rstrip("/") + "/**/*.parquet"
        count = int(connection.execute(
            f"SELECT COUNT(*) FROM read_parquet({_sql_literal(parquet_glob)}, hive_partitioning=true)"
        ).fetchone()[0])
        files = sorted(path.relative_to(output).as_posix() for path in output.rglob("*.parquet"))
    finally:
        connection.close()
    return {
        "status": "pass",
        "source_file": str(source),
        "source_format": source_format,
        "output_directory": str(output),
        "records": count,
        "columns": columns,
        "partitioned_by": "platform" if "platform" in columns else None,
        "parquet_files": files,
        "engine": "DuckDB",
        "compression": "ZSTD",
    }


def query_parquet_dataset(
    dataset_directory: str | Path,
    sql: str,
    *,
    max_rows: int = 1000,
) -> dict[str, Any]:
    """Run one analyst-supplied SELECT/WITH query against the `evidence` view."""
    dataset = Path(dataset_directory).expanduser().resolve(strict=True)
    if not dataset.is_dir() or not any(dataset.rglob("*.parquet")):
        raise ValueError(f"No Parquet dataset exists in {dataset}.")
    if not 1 <= int(max_rows) <= 100000:
        raise ValueError("max_rows must be between 1 and 100000.")
    query = str(sql or "").strip().rstrip(";").strip()
    if not query or query.casefold().split(maxsplit=1)[0] not in {"select", "with"}:
        raise ValueError("Only a single SELECT or WITH query is accepted.")
    if ";" in query:
        raise ValueError("Provide one SQL statement without embedded semicolons.")
    if _EXTERNAL_SQL.search(query):
        raise ValueError("Query functions that read external files, attach databases, or load extensions are disabled.")

    parquet_glob = dataset.as_posix().rstrip("/") + "/**/*.parquet"
    connection = _duckdb().connect(":memory:")
    try:
        connection.execute(
            f"CREATE VIEW evidence AS SELECT * FROM read_parquet({_sql_literal(parquet_glob)}, hive_partitioning=true)"
        )
        cursor = connection.execute(
            f"SELECT * FROM ({query}) AS sugar_query_result LIMIT {int(max_rows)}"
        )
        columns = [item[0] for item in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        connection.close()
    return {
        "dataset_directory": str(dataset),
        "query": query,
        "row_limit": int(max_rows),
        "returned_rows": len(rows),
        "columns": columns,
        "rows": rows,
    }


def save_query_result(payload: dict[str, Any], output_file: str | Path) -> str:
    target = Path(output_file).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return str(target)
