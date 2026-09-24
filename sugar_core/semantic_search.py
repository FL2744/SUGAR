from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from .models import PostRecord

SEMANTIC_INDEX_SCHEMA = "1.0"
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _text(record: PostRecord) -> str:
    original = str(record.original_text or "").strip()
    translated = str(record.translated_text or "").strip()
    return (original or translated)[:12000]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _embedding_space_id(provider: str, base_url: str, model: str) -> str:
    endpoint = ""
    if base_url.strip():
        parsed = urlsplit(base_url.strip())
        endpoint = urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path.rstrip("/"), "", ""))
    return _hash(f"{provider.casefold()}|{endpoint}|{model}")[:20]


def _record_row(record: PostRecord) -> dict[str, Any]:
    text = _text(record)
    return {
        "record_key": record.record_key,
        "platform": record.platform,
        "url": record.canonical_url,
        "title": str(record.raw_stats.get("title") or "") if isinstance(record.raw_stats, dict) else "",
        "published_at": record.published_at,
        "language": record.detected_language or record.platform_language,
        "text": text,
        "text_basis": "original_text" if record.original_text else "translated_text_fallback",
        "text_sha256": _hash(text),
    }


def _record_rows(records: Iterable[PostRecord]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for record in records:
        if not record.record_key or not _text(record):
            continue
        row = _record_row(record)
        previous = unique.get(row["record_key"])
        if previous is None or len(row["text"]) > len(previous["text"]):
            unique[row["record_key"]] = row
    return [unique[key] for key in sorted(unique)]


def _embed(client, texts: list[str], model: str) -> list[list[float]]:
    vectors: list[list[float]] = []
    for offset in range(0, len(texts), 64):
        response = client.embeddings.create(model=model, input=texts[offset:offset + 64])
        vectors.extend([list(map(float, item.embedding)) for item in response.data])
    if len(vectors) != len(texts):
        raise RuntimeError("Embedding endpoint returned an unexpected number of vectors.")
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) > 1:
        raise RuntimeError("Embedding endpoint returned inconsistent vector dimensions.")
    return vectors


def build_semantic_index(
    records: Iterable[PostRecord], client, *, model: str, provider: str = "openai", base_url: str = ""
) -> dict[str, Any]:
    rows = _record_rows(records)
    vectors = _embed(client, [row["text"] for row in rows], model) if rows else []
    return {
        "schema_version": SEMANTIC_INDEX_SCHEMA,
        "model": model,
        "provider": provider,
        "embedding_space_id": _embedding_space_id(provider, base_url, model),
        "dimensions": len(vectors[0]) if vectors else 0,
        "documents": [dict(row, vector=vector) for row, vector in zip(rows, vectors)],
        "disclaimer": "Vectors support retrieval only. They are not evidence, findings, or source-independence judgments.",
    }


def refresh_semantic_index(
    index: dict[str, Any], records: Iterable[PostRecord], client, *, model: str,
    provider: str = "openai", base_url: str = "",
) -> dict[str, Any]:
    space_id = _embedding_space_id(provider, base_url, model)
    if index.get("schema_version") != SEMANTIC_INDEX_SCHEMA or index.get("embedding_space_id") != space_id:
        return build_semantic_index(records, client, model=model, provider=provider, base_url=base_url)
    old = {str(row.get("record_key")): row for row in index.get("documents") or []}
    current = _record_rows(records)
    stale = [row for row in current if row["record_key"] not in old or old[row["record_key"]].get("text_sha256") != row["text_sha256"]]
    vectors = iter(_embed(client, [row["text"] for row in stale], model)) if stale else iter(())
    stale_rows = {row["record_key"]: dict(row, vector=next(vectors)) for row in stale}
    documents = [stale_rows.get(row["record_key"], old.get(row["record_key"], {})) for row in current]
    documents = [row for row in documents if row]
    return {
        "schema_version": SEMANTIC_INDEX_SCHEMA,
        "model": model,
        "provider": provider,
        "embedding_space_id": space_id,
        "dimensions": len(documents[0].get("vector") or []) if documents else 0,
        "documents": documents,
        "disclaimer": "Vectors support retrieval only. They are not evidence, findings, or source-independence judgments.",
    }


def save_semantic_index(index: dict[str, Any], path: str | Path) -> str:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(target, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(index, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")
    return str(target)


def load_semantic_index(path: str | Path) -> dict[str, Any]:
    with gzip.open(Path(path).expanduser().resolve(), "rt", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict) or payload.get("schema_version") != SEMANTIC_INDEX_SCHEMA:
        raise ValueError("Unsupported SUGAR semantic index.")
    return payload


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Query embedding dimensions do not match the semantic index.")
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def search_semantic_index(
    index: dict[str, Any], query: str, client, *, model: str, top_k: int = 20,
    provider: str = "openai", base_url: str = "",
) -> dict[str, Any]:
    if model != index.get("model") or _embedding_space_id(provider, base_url, model) != index.get("embedding_space_id"):
        raise ValueError("The query embedding model must match the model used to build the index.")
    if not 1 <= int(top_k) <= 500:
        raise ValueError("top_k must be between 1 and 500.")
    vector = _embed(client, [query], model)[0]
    results = []
    for row in index.get("documents") or []:
        score = _cosine(vector, row.get("vector") or [])
        results.append({key: value for key, value in row.items() if key not in {"vector", "text_sha256", "text"}} | {
            "similarity": round(score, 6),
            "why_retrieved": "Cross-lingual embedding similarity; the vector is a retrieval aid, not evidence.",
            "excerpt": row.get("text", "")[:500],
        })
    results.sort(key=lambda row: (-row["similarity"], row["record_key"]))
    return {
        "schema_version": SEMANTIC_INDEX_SCHEMA,
        "query": query,
        "retrieval_mode": "cross_lingual_embedding",
        "embedding_model": model,
        "embedding_provider": provider,
        "index_documents": len(index.get("documents") or []),
        "results": results[:int(top_k)],
        "translation_status": "No translation was created; each result retains its source language and text basis.",
        "guardrails": [
            "Embeddings rank retrieval candidates and are never cited as evidence.",
            "Review the original source, original text, and citation before relying on a result.",
            "The configured embedding service receives the query and the records sent for indexing.",
        ],
    }


def search_lexical(records: Iterable[PostRecord], query: str, *, top_k: int = 20) -> dict[str, Any]:
    if not 1 <= int(top_k) <= 500:
        raise ValueError("top_k must be between 1 and 500.")
    query_tokens = {token.casefold() for token in _TOKEN_RE.findall(query) if len(token) > 1}
    query_compact = "".join(_TOKEN_RE.findall(query)).casefold()
    rows = []
    unique_records: dict[str, PostRecord] = {}
    for record in records:
        if not record.record_key or not _text(record):
            continue
        previous = unique_records.get(record.record_key)
        if previous is None or len(_text(record)) > len(_text(previous)):
            unique_records[record.record_key] = record
    for record_key in sorted(unique_records):
        record = unique_records[record_key]
        text = _text(record)
        tokens = {token.casefold() for token in _TOKEN_RE.findall(text) if len(token) > 1}
        overlap = query_tokens & tokens
        compact = "".join(_TOKEN_RE.findall(text)).casefold()
        substring = bool(query_compact and query_compact in compact)
        score = (len(overlap) / len(query_tokens) if query_tokens else 0.0)
        if substring:
            score = max(score, 1.0)
        if score <= 0:
            continue
        row = _record_row(record)
        rows.append({key: value for key, value in row.items() if key not in {"text_sha256", "text"}} | {
            "similarity": round(score, 6),
            "why_retrieved": {"matched_tokens": sorted(overlap), "exact_phrase": substring},
            "excerpt": text[:500],
        })
    rows.sort(key=lambda row: (-row["similarity"], row["record_key"]))
    return {
        "schema_version": SEMANTIC_INDEX_SCHEMA,
        "query": query,
        "retrieval_mode": "local_lexical",
        "index_documents": len(unique_records),
        "results": rows[:int(top_k)],
        "guardrails": ["Local lexical matching is not cross-lingual semantic retrieval."],
    }
