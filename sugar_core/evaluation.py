"""Measuring how well SUGAR's suggestions match a person's judgment.

A reviewer labels a random sample of items (relevant or not, audiences, programs). ``score_labels`` compares those labels
with what the relevance scorer and the activity coder propose, and reports precision, recall and F1 with the counts behind
them, so the tool's accuracy is a measured number a team can track over time and re-check after changing a model.
"""
from __future__ import annotations

import csv
import io
import random
from collections import defaultdict
from typing import Any

from . import analysis
from .activity_coding import propose_by_pattern
from .research_items import ResearchItem

SAMPLE_COLUMNS = ["item_id", "run_id", "platform", "url", "language", "text", "gold_relevance", "gold_audiences", "gold_programs"]


def sample_items(items: list[ResearchItem], n: int = 60, seed: int = 7) -> list[ResearchItem]:
    pool = sorted((i for i in items if i.status in {"collected", "processed"}), key=lambda i: i.item_id)
    rng = random.Random(seed)
    return rng.sample(pool, min(n, len(pool)))


def sample_csv(items: list[ResearchItem], n: int = 60, seed: int = 7) -> str:
    """A labeling sheet. Predictions are left out on purpose so they cannot influence the labeler."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(SAMPLE_COLUMNS)
    for i in sample_items(items, n, seed):
        text = i.original_text if not (isinstance(i.translation, dict) and i.translation.get("status") == "done") else f"{i.original_text}\n[translation] {i.translation.get('text', '')}"
        writer.writerow([i.item_id, i.run_id, i.platform, i.url, i.language, " ".join(text.split())[:1500], "", "", ""])
    return out.getvalue()


def _split(value: str) -> set[str]:
    return {p.strip().casefold().replace(" ", "_") for p in str(value or "").replace(",", ";").split(";") if p.strip()}


def _prf(tp: int, fp: int, fn: int) -> dict[str, Any]:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"precision": None if p is None else round(p, 3), "recall": None if r is None else round(r, 3), "f1": None if f is None else round(f, 3), "tp": tp, "fp": fp, "fn": fn}


def score_labels(labels_csv: str, items: list[ResearchItem], plan: Any, settings: dict[str, Any] | None = None, *, relevant_at: float = 0.3) -> dict[str, Any]:
    rows = [r for r in csv.DictReader(io.StringIO(labels_csv)) if r.get("item_id")]
    by_id = {i.item_id: i for i in items}
    terms = analysis.plan_terms(plan, settings)
    rel = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    sweep: dict[float, dict[str, int]] = {t: {"tp": 0, "fp": 0, "fn": 0} for t in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7)}
    per: dict[str, dict[str, dict[str, int]]] = {"audience": defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0}), "program": defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})}
    labeled_rel = labeled_code = missing = 0
    for row in rows:
        item = by_id.get(row["item_id"])
        if item is None:
            missing += 1
            continue
        gold_rel = str(row.get("gold_relevance") or "").strip().casefold()
        if gold_rel in {"relevant", "not_relevant", "not relevant", "yes", "no", "1", "0"}:
            labeled_rel += 1
            truth = gold_rel in {"relevant", "yes", "1"}
            score = analysis.score_item(item, terms)["score"]
            pred = score >= relevant_at
            rel["tp" if truth and pred else "fp" if pred else "fn" if truth else "tn"] += 1
            for t, c in sweep.items():
                p = score >= t
                if truth and p:
                    c["tp"] += 1
                elif p and not truth:
                    c["fp"] += 1
                elif truth and not p:
                    c["fn"] += 1
        if str(row.get("gold_audiences") or "").strip() or str(row.get("gold_programs") or "").strip():
            labeled_code += 1
            predicted = propose_by_pattern(item, (settings or {}).get("coding_terms"))
            for kind, column in (("audience", "gold_audiences"), ("program", "gold_programs")):
                gold, pred = _split(row.get(column, "")), {p["label"] for p in predicted if p["field"] == kind}
                for label in gold | pred:
                    key = per[kind][label]
                    key["tp" if label in gold and label in pred else "fp" if label in pred else "fn"] += 1
    def micro(kind: str) -> dict[str, Any]:
        tp, fp, fn = (sum(c[k] for c in per[kind].values()) for k in ("tp", "fp", "fn"))
        return _prf(tp, fp, fn)
    return {
        "labeled_relevance": labeled_rel, "labeled_coding": labeled_code, "unknown_item_ids": missing,
        "relevance": {**_prf(rel["tp"], rel["fp"], rel["fn"]), "threshold": relevant_at, "true_negatives": rel["tn"],
                      "by_threshold": {str(t): _prf(c["tp"], c["fp"], c["fn"]) for t, c in sweep.items()}},
        "audience": {"overall": micro("audience"), "by_label": {k: _prf(**v) for k, v in sorted(per["audience"].items())}},
        "program": {"overall": micro("program"), "by_label": {k: _prf(**v) for k, v in sorted(per["program"].items())}},
        "note": "These numbers describe agreement with the labels you supplied on this sample. A small sample gives a rough estimate; label at least 60 items "
                "and re-check after changing models, vocabulary or sources.",
    }
