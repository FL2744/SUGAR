from __future__ import annotations

import pytest

from tools.intelligence_benchmark import score_benchmark


def test_benchmark_scores_accuracy_calibration_evidence_and_usefulness_separately() -> None:
    payload = {
        "schema_version": 1,
        "run": {"provider": "test", "model": "test-model"},
        "items": [
            {
                "gold_relevance": "relevant", "predicted_relevance": "relevant", "predicted_confidence": 0.9,
                "gold_labels": ["education"], "predicted_labels": ["education"],
                "reviewer1_relevance": "relevant", "reviewer2_relevance": "relevant",
                "evidence_checks": [{"verdict": "supported"}],
                "judgments": [{"verdict": "supported", "usefulness": 5, "actionability": 4, "novelty": 3, "supporting_refs_valid": True}],
                "forecasts": [{"probability": 0.8, "outcome": True}],
            },
            {
                "gold_relevance": "not_relevant", "predicted_relevance": "not_relevant", "predicted_confidence": 0.8,
                "gold_labels": [], "predicted_labels": [],
                "reviewer1_relevance": "not_relevant", "reviewer2_relevance": "not_relevant",
                "evidence_checks": [{"verdict": "unsupported"}],
                "judgments": [{"verdict": "unsupported", "usefulness": 1, "actionability": 2, "novelty": 1, "supporting_refs_valid": False}],
                "forecasts": [{"probability": 0.3, "outcome": False}],
            },
            {
                "gold_relevance": "uncertain", "predicted_relevance": "relevant", "predicted_confidence": 0.7,
                "gold_labels": ["needs_context"], "predicted_labels": ["education"],
                "reviewer1_relevance": "uncertain", "reviewer2_relevance": "uncertain",
            },
            {
                "gold_relevance": "relevant", "predicted_relevance": "not_relevant", "predicted_confidence": 0.6,
                "gold_labels": ["education"], "predicted_labels": [],
                "reviewer1_relevance": "relevant", "reviewer2_relevance": "not_relevant",
            },
        ],
    }

    report = score_benchmark(payload, minimum_sample_size=5)

    assert report["status"] == "INSUFFICIENT_SAMPLE"
    assert report["relevance_classification"]["accuracy"] == 0.5
    assert report["relevance_classification"]["accuracy_95_wilson_ci"] is not None
    assert report["relevance_classification"]["confidence_calibration"]["brier_score"] == 0.225
    assert report["controlled_labels"]["micro_f1"] == 0.4
    assert report["evidence_support"]["fully_supported_rate"] == 0.5
    assert report["analytic_judgments"]["ratings"]["usefulness"]["mean"] == 3
    assert report["resolved_forecasts"]["brier_score"] == 0.065
    assert report["composite_score"] is None


def test_benchmark_requires_valid_schema_and_does_not_score_missing_labels() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        score_benchmark({"items": []})

    empty = score_benchmark({"schema_version": 1, "items": []})
    assert empty["status"] == "INSUFFICIENT_SAMPLE"
    assert empty["relevance_classification"]["accuracy"] is None
    assert empty["relevance_classification"]["confidence_calibration"]["brier_score"] is None


def test_benchmark_requires_double_review_and_reports_interrater_agreement() -> None:
    items = []
    for _ in range(50):
        items.append({
            "gold_relevance": "relevant", "predicted_relevance": "relevant", "predicted_confidence": 0.8,
            "reviewer1_relevance": "relevant", "reviewer2_relevance": "relevant",
        })
    report = score_benchmark({"schema_version": 1, "items": items})
    assert report["status"] == "SCORABLE_NOT_PASS"
    assert report["sample"]["reviewer_agreement"]["agreement"] == 1.0
    assert report["sample"]["reviewer_agreement"]["cohen_kappa"] == 1.0


def test_benchmark_rejects_invalid_reviewer_labels_instead_of_counting_them_as_agreement() -> None:
    payload = {
        "schema_version": 1,
        "items": [{
            "gold_relevance": "relevant", "predicted_relevance": "relevant",
            "reviewer1_relevance": "relevant", "reviewer2_relevance": "not-a-label",
        }],
    }

    with pytest.raises(ValueError, match="reviewer2_relevance"):
        score_benchmark(payload)


@pytest.mark.parametrize("rating", [True, 3.5, "4"])
def test_benchmark_requires_integer_human_ratings(rating: object) -> None:
    payload = {
        "schema_version": 1,
        "items": [{
            "gold_relevance": "relevant", "predicted_relevance": "relevant",
            "judgments": [{"verdict": "supported", "usefulness": rating}],
        }],
    }

    with pytest.raises(ValueError, match="usefulness ratings must be integers"):
        score_benchmark(payload)


def test_benchmark_rejects_malformed_evidence_and_forecast_rows() -> None:
    payload = {
        "schema_version": 1,
        "items": [{
            "gold_relevance": "relevant", "predicted_relevance": "relevant",
            "evidence_checks": [{"verdict": "probably-supported"}],
        }],
    }

    with pytest.raises(ValueError, match=r"evidence_checks\[0\].verdict"):
        score_benchmark(payload)

    payload["items"][0]["evidence_checks"] = []
    payload["items"][0]["forecasts"] = [{"probability": 0.7, "outcome": "yes"}]
    with pytest.raises(ValueError, match="boolean outcome"):
        score_benchmark(payload)
