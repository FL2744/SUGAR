"""Score independently adjudicated SUGAR outputs without collapsing quality to one number.

Input is a JSON review file with gold labels, model predictions, evidence judgments, and (when
available) resolved forecasts. See ``docs/benchmarking.md`` for the schema and review protocol.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

if __package__:
    from .benchmark_utils import atomic_write_text
else:
    from benchmark_utils import atomic_write_text

RELEVANCE = ("relevant", "uncertain", "not_relevant")
EVIDENCE_VERDICTS = ("supported", "partly_supported", "unsupported", "unverifiable")


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total <= 0:
        return None
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    radius = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total) / denominator
    return [round(max(0.0, center - radius), 4), round(min(1.0, center + radius), 4)]


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _class_metrics(gold: list[str], predicted: list[str], label: str) -> dict[str, Any]:
    true_positive = sum(1 for actual, guess in zip(gold, predicted) if actual == label and guess == label)
    predicted_positive = sum(1 for guess in predicted if guess == label)
    actual_positive = sum(1 for actual in gold if actual == label)
    precision = _ratio(true_positive, predicted_positive)
    recall = _ratio(true_positive, actual_positive)
    f1 = (2 * precision * recall / (precision + recall)) if precision is not None and recall is not None and precision + recall else 0.0
    return {
        "precision": precision,
        "precision_95_wilson_ci": _wilson(true_positive, predicted_positive),
        "recall": recall,
        "recall_95_wilson_ci": _wilson(true_positive, actual_positive),
        "f1": round(f1, 4),
        "support": actual_positive,
    }


def _label_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    true_positive = false_positive = false_negative = 0
    per_label: dict[str, dict[str, Any]] = {}
    all_labels = sorted({
        str(label).strip().casefold()
        for item in items
        for field in ("gold_labels", "predicted_labels")
        for label in item.get(field, [])
        if str(label).strip()
    })
    for label in all_labels:
        gold = [label in {str(v).strip().casefold() for v in item.get("gold_labels", [])} for item in items]
        predicted = [label in {str(v).strip().casefold() for v in item.get("predicted_labels", [])} for item in items]
        tp = sum(a and p for a, p in zip(gold, predicted))
        fp = sum((not a) and p for a, p in zip(gold, predicted))
        fn = sum(a and (not p) for a, p in zip(gold, predicted))
        precision = _ratio(tp, tp + fp)
        recall = _ratio(tp, tp + fn)
        f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else 0.0
        per_label[label] = {"precision": precision, "recall": recall, "f1": round(f1, 4), "support": tp + fn}
        true_positive += tp
        false_positive += fp
        false_negative += fn
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    micro_f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else 0.0
    return {
        "micro_precision": precision,
        "micro_recall": recall,
        "micro_f1": round(micro_f1, 4),
        "macro_f1": round(statistics.mean(row["f1"] for row in per_label.values()), 4) if per_label else None,
        "per_label": per_label,
    }


def _confidence_calibration(items: list[dict[str, Any]], bins: int = 10) -> dict[str, Any]:
    scored = []
    for item in items:
        confidence = item.get("predicted_confidence")
        if confidence is None:
            continue
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError("predicted_confidence must be a number between 0 and 1.")
        value = float(confidence)
        if not 0 <= value <= 1:
            raise ValueError("predicted_confidence must be between 0 and 1.")
        correct = item["gold_relevance"] == item["predicted_relevance"]
        scored.append((value, float(correct)))
    if not scored:
        return {"n": 0, "brier_score": None, "expected_calibration_error": None, "bins": []}

    brier = statistics.mean((confidence - correct) ** 2 for confidence, correct in scored)
    bin_rows = []
    ece = 0.0
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        rows = [
            row for row in scored
            if lower <= row[0] < upper or (index == bins - 1 and row[0] == 1.0)
        ]
        if not rows:
            continue
        mean_confidence = statistics.mean(row[0] for row in rows)
        accuracy = statistics.mean(row[1] for row in rows)
        ece += len(rows) / len(scored) * abs(mean_confidence - accuracy)
        bin_rows.append({
            "lower_bound": round(lower, 2),
            "upper_bound": round(upper, 2),
            "n": len(rows),
            "mean_confidence": round(mean_confidence, 4),
            "accuracy": round(accuracy, 4),
        })
    return {
        "n": len(scored),
        "confidence_target": "probability that the predicted relevance class is correct",
        "brier_score": round(brier, 4),
        "expected_calibration_error": round(ece, 4),
        "bins": bin_rows,
    }


def _reviewer_agreement(items: list[dict[str, Any]]) -> dict[str, Any]:
    paired = []
    for index, item in enumerate(items):
        left = str(item.get("reviewer1_relevance", "") or "").strip().casefold()
        right = str(item.get("reviewer2_relevance", "") or "").strip().casefold()
        for field, value in (("reviewer1_relevance", left), ("reviewer2_relevance", right)):
            if value and value not in RELEVANCE:
                raise ValueError(f"items[{index}].{field} must be one of {', '.join(RELEVANCE)}.")
        if left and right:
            paired.append((left, right))
    if not paired:
        return {"paired_items": 0, "agreement": None, "cohen_kappa": None}
    first_counts = Counter(left for left, _ in paired)
    second_counts = Counter(right for _, right in paired)
    agreement_count = sum(left == right for left, right in paired)
    observed = agreement_count / len(paired)
    expected = sum(first_counts[key] * second_counts[key] for key in set(first_counts) | set(second_counts)) / (len(paired) ** 2)
    kappa = 1.0 if observed == 1.0 and expected == 1.0 else ((observed - expected) / (1 - expected) if expected < 1 else None)
    return {
        "paired_items": len(paired),
        "agreement": round(observed, 4),
        "cohen_kappa": round(kappa, 4) if kappa is not None else None,
    }


def _verdict_counts(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row.get("verdict", "")).strip().casefold() for row in rows)
    total = sum(counts.get(label, 0) for label in EVIDENCE_VERDICTS)
    supported = counts.get("supported", 0)
    partial = counts.get("partly_supported", 0)
    return {
        "reviewed": total,
        "counts": {label: counts.get(label, 0) for label in EVIDENCE_VERDICTS},
        "fully_supported_rate": _ratio(supported, total),
        "supported_or_partial_rate": _ratio(supported + partial, total),
    }


def _ratings(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in fields:
        values = []
        for row in rows:
            value = row.get(field)
            if value in (None, ""):
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 5:
                raise ValueError(f"{field} ratings must be integers from 1 to 5.")
            values.append(value)
        result[field] = {
            "n": len(values),
            "mean": round(statistics.mean(values), 4) if values else None,
            "median": statistics.median(values) if values else None,
            "distribution": {str(level): values.count(level) for level in range(1, 6)},
        }
    return result


def _forecast_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = []
    for row in rows:
        probability = row.get("probability")
        outcome = row.get("outcome")
        if probability is None and outcome is None:
            continue
        if probability is None or not isinstance(outcome, bool):
            raise ValueError("Each forecast must include a numeric probability and a boolean outcome when resolved.")
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise ValueError("Forecast probabilities must be numbers between 0 and 1.")
        value = float(probability)
        if not 0 <= value <= 1:
            raise ValueError("Forecast probabilities must be between 0 and 1.")
        scored.append((value, float(outcome)))
    return {
        "resolved_forecasts": len(scored),
        "brier_score": round(statistics.mean((p - outcome) ** 2 for p, outcome in scored), 4) if scored else None,
        "log_loss": round(statistics.mean(-((outcome * math.log(max(p, 1e-15))) + ((1 - outcome) * math.log(max(1 - p, 1e-15)))) for p, outcome in scored), 4) if scored else None,
    }


def _summarize_operations(collection: dict[str, Any] | None, stress: dict[str, Any] | None) -> dict[str, Any]:
    live_summary = None
    if collection is not None:
        live_summary = {
            "operation": collection.get("operation"),
            "request_policy": collection.get("request_policy"),
            "sources": collection.get("sources", {}),
            "local_checkpoint": collection.get("local_checkpoint"),
        }
    stress_summary = None
    if stress is not None:
        if isinstance(stress.get("runs"), list):
            stress_summary = {
                "operation": stress.get("operation"),
                "network": stress.get("network"),
                "runs": [
                    {
                        "records": row.get("records"),
                        "peak_python_bytes": row.get("peak_python_bytes"),
                        "results": row.get("results", []),
                        "disk_bytes": row.get("disk_bytes"),
                        "budget_failures": row.get("budget_failures", []),
                    }
                    for row in stress["runs"]
                ],
                "budget_failures": stress.get("budget_failures", []),
            }
        else:
            stress_summary = {
                "operation": stress.get("operation"),
                "network": stress.get("network"),
                "records": stress.get("records"),
                "peak_python_bytes": stress.get("peak_python_bytes"),
                "results": stress.get("results", []),
                "disk_bytes": stress.get("disk_bytes"),
                "budget_failures": stress.get("budget_failures", []),
            }
    return {"live_collection": live_summary, "offline_scale": stress_summary}


def score_benchmark(
    payload: dict[str, Any],
    *,
    minimum_sample_size: int = 50,
    collection_report: dict[str, Any] | None = None,
    stress_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if minimum_sample_size < 1:
        raise ValueError("minimum_sample_size must be positive.")
    if payload.get("schema_version") != 1:
        raise ValueError("benchmark input schema_version must be 1.")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("benchmark input must contain an items array.")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"items[{index}] must be an object.")
        if item.get("gold_relevance") not in RELEVANCE or item.get("predicted_relevance") not in RELEVANCE:
            raise ValueError(f"items[{index}] must have valid gold_relevance and predicted_relevance labels.")
        for key in ("gold_labels", "predicted_labels", "evidence_checks", "judgments", "forecasts"):
            if key in item and not isinstance(item[key], list):
                raise ValueError(f"items[{index}].{key} must be an array.")
        for key in ("evidence_checks", "judgments"):
            for row_index, row in enumerate(item.get(key, [])):
                if not isinstance(row, dict) or row.get("verdict") not in EVIDENCE_VERDICTS:
                    raise ValueError(
                        f"items[{index}].{key}[{row_index}].verdict must be one of {', '.join(EVIDENCE_VERDICTS)}."
                    )
                if "supporting_refs_valid" in row and not isinstance(row["supporting_refs_valid"], bool):
                    raise ValueError(f"items[{index}].{key}[{row_index}].supporting_refs_valid must be boolean.")
        for row_index, row in enumerate(item.get("forecasts", [])):
            if not isinstance(row, dict):
                raise ValueError(f"items[{index}].forecasts[{row_index}] must be an object.")

    gold = [item["gold_relevance"] for item in items]
    predicted = [item["predicted_relevance"] for item in items]
    correct = sum(actual == guess for actual, guess in zip(gold, predicted))
    class_rows = {label: _class_metrics(gold, predicted, label) for label in RELEVANCE}
    macro_f1 = statistics.mean(row["f1"] for row in class_rows.values()) if items else None
    confidence = _confidence_calibration(items)
    agreement = _reviewer_agreement(items)

    reviewed_pairs = agreement["paired_items"]
    double_review_fraction = _ratio(reviewed_pairs, len(items))
    if len(items) < minimum_sample_size:
        status = "INSUFFICIENT_SAMPLE"
    elif double_review_fraction is None or double_review_fraction < 0.8:
        status = "INCOMPLETE_DOUBLE_REVIEW"
    elif agreement["cohen_kappa"] is None or agreement["cohen_kappa"] < 0.6:
        status = "REVIEWER_AGREEMENT_LOW"
    else:
        status = "SCORABLE_NOT_PASS"

    evidence_rows = [row for item in items for row in item.get("evidence_checks", []) if isinstance(row, dict)]
    judgment_rows = [row for item in items for row in item.get("judgments", []) if isinstance(row, dict)]
    forecast_rows = [row for item in items for row in item.get("forecasts", []) if isinstance(row, dict)]
    judged_claims = sum(1 for row in judgment_rows if row.get("verdict") in EVIDENCE_VERDICTS)
    supported_claims = sum(1 for row in judgment_rows if row.get("verdict") == "supported")
    return {
        "schema_version": 1,
        "operation": "sugar_intelligence_benchmark",
        "status": status,
        "status_note": "SCORABLE_NOT_PASS means the sample and reviewer agreement are sufficient to interpret metrics; project acceptance thresholds must be set separately.",
        "sample": {
            "items": len(items),
            "minimum_sample_size": minimum_sample_size,
            "double_review_fraction": double_review_fraction,
            "reviewer_agreement": agreement,
        },
        "relevance_classification": {
            "accuracy": _ratio(correct, len(items)),
            "accuracy_95_wilson_ci": _wilson(correct, len(items)),
            "macro_f1": round(macro_f1, 4) if macro_f1 is not None else None,
            "per_class": class_rows,
            "confusion_matrix": {
                actual: {guess: sum(a == actual and p == guess for a, p in zip(gold, predicted)) for guess in RELEVANCE}
                for actual in RELEVANCE
            },
            "abstention_rate": _ratio(sum(value == "uncertain" for value in predicted), len(predicted)),
            "selective_accuracy": _ratio(
                sum(actual == guess for actual, guess in zip(gold, predicted) if guess != "uncertain"),
                sum(guess != "uncertain" for guess in predicted),
            ),
            "confidence_calibration": confidence,
        },
        "controlled_labels": _label_metrics(items),
        "evidence_support": _verdict_counts(evidence_rows),
        "analytic_judgments": {
            "reviewed": judged_claims,
            "fully_supported_rate": _ratio(supported_claims, judged_claims),
            "verdict_counts": _verdict_counts(judgment_rows),
            "ratings": _ratings(judgment_rows, ("usefulness", "actionability", "novelty")),
            "with_valid_supporting_references": _ratio(
                sum(bool(row.get("supporting_refs_valid")) for row in judgment_rows if "supporting_refs_valid" in row),
                sum(1 for row in judgment_rows if "supporting_refs_valid" in row),
            ),
        },
        "resolved_forecasts": _forecast_metrics(forecast_rows),
        "operations": _summarize_operations(collection_report, stress_report),
        "composite_score": None,
        "composite_score_note": "Quality, calibration, evidence integrity, usefulness, and operational capacity remain separate so a strong dimension cannot hide a failure in another.",
        "run_metadata": payload.get("run", {}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Adjudicated benchmark JSON file.")
    parser.add_argument("--output", type=Path, required=True, help="Path for the scored JSON report.")
    parser.add_argument("--collection-report", type=Path, help="Optional sanitized live public API benchmark report.")
    parser.add_argument("--stress-report", type=Path, help="Optional offline stress or stress-matrix report.")
    parser.add_argument("--minimum-sample-size", type=int, default=50, help="Minimum independently reviewed items (default: 50).")
    args = parser.parse_args(argv)
    if args.minimum_sample_size < 1:
        parser.error("--minimum-sample-size must be positive")
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    collection = json.loads(args.collection_report.read_text(encoding="utf-8")) if args.collection_report else None
    stress = json.loads(args.stress_report.read_text(encoding="utf-8")) if args.stress_report else None
    report = score_benchmark(
        payload,
        minimum_sample_size=args.minimum_sample_size,
        collection_report=collection,
        stress_report=stress,
    )
    output = args.output.expanduser().resolve()
    atomic_write_text(output, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
