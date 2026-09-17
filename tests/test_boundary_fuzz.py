from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

import sugar_bridge
from sugar_core.bilibili import normalize_bilibili_engagement
from sugar_core.collectors import normalize_engagement
from sugar_core.observations import ResearchObservation, SpatialMatch
from sugar_core.source_conflicts import load_source_conflicts
from sugar_core.state_entities import load_entity_registry
from sugar_core.state_schema import QualifiedReachValue
from sugar_core.state_workflow import load_state_assessments
from sugar_core.triage_io import post_record_from_mapping
from sugar_core.weibo import normalize_weibo_engagement


def _jsonish(rng: random.Random, depth: int = 0) -> object:
    """Produce a stable, JSON-serializable boundary corpus without external fuzz dependencies."""
    if depth >= 7 or rng.random() < 0.42:
        return rng.choice([None, True, False, 0, 1, -1, "", "text", "\u2603"])
    if rng.random() < 0.5:
        return {f"field_{index}": _jsonish(rng, depth + 1) for index in range(rng.randrange(0, 4))}
    return [_jsonish(rng, depth + 1) for _ in range(rng.randrange(0, 4))]


@pytest.mark.parametrize("seed", range(20))
def test_bridge_seeded_json_boundary_corpus_is_deterministic(tmp_path: Path, seed: int) -> None:
    payload = {"payload": _jsonish(random.Random(seed))}
    path = tmp_path / f"config-{seed}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    assert sugar_bridge.load_config(str(path)) == payload


@pytest.mark.parametrize(
    "normalizer",
    [
        lambda raw: normalize_engagement("x", raw),
        normalize_bilibili_engagement,
        normalize_weibo_engagement,
    ],
)
def test_metric_normalizers_return_canonical_nonnegative_integers(normalizer) -> None:
    values = [None, "", "not-a-number", -1, float("nan"), float("inf"), float("-inf")]
    for value in values:
        normalized = normalizer(
            {
                "like_count": value,
                "reply_count": value,
                "retweet_count": value,
                "quote_count": value,
                "bookmark_count": value,
                "impression_count": value,
                "like": value,
                "reply": value,
                "favorite": value,
                "view": value,
                "attitudes_count": value,
                "comments_count": value,
                "reposts_count": value,
            }
        )
        assert all(isinstance(metric, int) and metric >= 0 for metric in normalized.values())


@pytest.mark.parametrize("value", ["not-a-number", float("nan"), float("inf"), float("-inf")])
def test_imported_engagement_metrics_fail_closed(value) -> None:
    record = post_record_from_mapping(
        {
            "platform": "x",
            "native_id": "123",
            "engagement": json.dumps({"likes": value}),
        }
    )
    assert record.engagement == {"likes": 0}


@pytest.mark.parametrize(
    ("loader", "filename", "contents", "message"),
    [
        (load_source_conflicts, "conflicts.json", '["not-an-object"]', "record 1 must be a JSON object"),
        (load_state_assessments, "assessments.jsonl", '["not-an-object"]\n', "records must be JSON objects"),
        (load_entity_registry, "entities.jsonl", "[]\n", "line 1 must be an object"),
    ],
)
def test_json_loaders_reject_non_object_records_with_stable_errors(
    tmp_path: Path, loader, filename: str, contents: str, message: str
) -> None:
    path = tmp_path / filename
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        loader(path)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_analytic_numeric_boundaries_are_rejected(value) -> None:
    with pytest.raises(ValueError, match="finite|between 0 and 1|cannot be negative"):
        QualifiedReachValue(value=value, qualifier="exact")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_observation_spatial_numeric_boundaries_are_rejected(value) -> None:
    with pytest.raises(ValueError, match="finite|cannot be negative"):
        ResearchObservation(
            observation_type="event",
            summary="Boundary case.",
            latitude=value,
            longitude=value,
        )
    with pytest.raises(ValueError, match="finite|cannot be negative"):
        SpatialMatch(
            reference_layer="test",
            reference_id="ref",
            reference_name="Reference",
            distance_km=value,
        )
