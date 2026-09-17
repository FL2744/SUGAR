from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .utils import utc_iso

LIKELIHOOD_ORDER = {
    "very_unlikely": 1,
    "unlikely": 2,
    "roughly_even_chance": 3,
    "likely": 4,
    "very_likely": 5,
    "almost_certain": 6,
    "not_estimative": 0,
}
CONFIDENCE_ORDER = {"low": 1, "moderate": 2, "high": 3}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _load(path_or_payload: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(path_or_payload, dict):
        return path_or_payload
    path = Path(path_or_payload)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _judgments(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    final = payload.get("final") or payload
    result: dict[str, dict[str, Any]] = {}
    for row in final.get("key_judgments") or []:
        if not isinstance(row, dict):
            continue
        judgment_id = _clean(row.get("judgment_id"))
        if judgment_id:
            result[judgment_id] = row
    return result


def _direction(old: int, new: int) -> str:
    if new > old:
        return "strengthened"
    if new < old:
        return "weakened"
    return "unchanged"


def compare_syntheses(
    previous: dict[str, Any] | str | Path,
    current: dict[str, Any] | str | Path,
) -> dict[str, Any]:
    previous = _load(previous)
    current = _load(current)
    old = _judgments(previous)
    new = _judgments(current)
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed: list[dict[str, Any]] = []
    for judgment_id in sorted(set(old) & set(new)):
        left, right = old[judgment_id], new[judgment_id]
        fields: dict[str, Any] = {}
        for key in ("statement", "status", "likelihood", "confidence", "basis", "implication"):
            if left.get(key) != right.get(key):
                fields[key] = {"previous": left.get(key), "current": right.get(key)}
        left_refs = set(left.get("supporting_refs") or [])
        right_refs = set(right.get("supporting_refs") or [])
        if left_refs != right_refs:
            fields["supporting_refs"] = {
                "added": sorted(right_refs - left_refs),
                "removed": sorted(left_refs - right_refs),
            }
        left_contrary = set(left.get("contrary_refs") or [])
        right_contrary = set(right.get("contrary_refs") or [])
        if left_contrary != right_contrary:
            fields["contrary_refs"] = {
                "added": sorted(right_contrary - left_contrary),
                "removed": sorted(left_contrary - right_contrary),
            }
        if fields:
            likelihood_change = _direction(
                LIKELIHOOD_ORDER.get(str(left.get("likelihood")), 0),
                LIKELIHOOD_ORDER.get(str(right.get("likelihood")), 0),
            )
            confidence_change = _direction(
                CONFIDENCE_ORDER.get(str(left.get("confidence")), 0),
                CONFIDENCE_ORDER.get(str(right.get("confidence")), 0),
            )
            changed.append({
                "judgment_id": judgment_id,
                "statement": right.get("statement") or left.get("statement"),
                "likelihood_change": likelihood_change,
                "confidence_change": confidence_change,
                "changed_fields": fields,
            })
    return {
        "generated_at": utc_iso(),
        "previous_generated_at": previous.get("generated_at"),
        "current_generated_at": current.get("generated_at"),
        "scope_previous": previous.get("scope"),
        "scope_current": current.get("scope"),
        "added_judgments": [{"judgment_id": key, **new[key]} for key in added],
        "removed_judgments": [{"judgment_id": key, **old[key]} for key in removed],
        "changed_judgments": changed,
        "unchanged_judgments": len(set(old) & set(new)) - len(changed),
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "strengthened_likelihood": sum(x["likelihood_change"] == "strengthened" for x in changed),
            "weakened_likelihood": sum(x["likelihood_change"] == "weakened" for x in changed),
            "strengthened_confidence": sum(x["confidence_change"] == "strengthened" for x in changed),
            "weakened_confidence": sum(x["confidence_change"] == "weakened" for x in changed),
        },
        "guardrail": "A changed synthesis can reflect new evidence, changed collection coverage, model variation, or revised analyst framing. Review the evidence-reference deltas before treating a shift as a real-world change.",
    }


def _distribution_map(rows: list[dict[str, Any]]) -> dict[str, float]:
    return {str(row.get("value")): float(row.get("share") or 0.0) for row in rows if row.get("value")}


def _distribution_delta(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    left, right = _distribution_map(previous), _distribution_map(current)
    rows = []
    for key in sorted(set(left) | set(right)):
        delta = right.get(key, 0.0) - left.get(key, 0.0)
        if abs(delta) >= 0.01:
            rows.append({
                "value": key,
                "previous_share": round(left.get(key, 0.0), 4),
                "current_share": round(right.get(key, 0.0), 4),
                "share_delta": round(delta, 4),
            })
    return sorted(rows, key=lambda row: -abs(row["share_delta"]))


def compare_intelligence_packets(
    previous: dict[str, Any] | str | Path,
    current: dict[str, Any] | str | Path,
) -> dict[str, Any]:
    previous = _load(previous)
    current = _load(current)
    old_corpus, new_corpus = previous.get("corpus") or {}, current.get("corpus") or {}
    old_macro, new_macro = previous.get("macro_structure") or {}, current.get("macro_structure") or {}
    count_fields = (
        "observations", "assessments", "verified_brief_eligible", "verified_multi_source_cases",
        "unresolved_country", "material_us_overlap_verified",
    )
    corpus_delta = {
        field: {
            "previous": old_corpus.get(field),
            "current": new_corpus.get(field),
            "delta": (new_corpus.get(field) or 0) - (old_corpus.get(field) or 0),
        }
        for field in count_fields
        if old_corpus.get(field) is not None or new_corpus.get(field) is not None
    }
    distribution_fields = (
        "countries", "observation_types", "program_domains", "strategic_audiences",
        "narrative_tags", "delivery_modes", "sponsor_support", "source_types_all_records",
    )
    distribution_deltas = {
        field: _distribution_delta(old_macro.get(field) or [], new_macro.get(field) or [])
        for field in distribution_fields
    }
    old_signals = Counter(x.get("signal") for x in (previous.get("temporal") or {}).get("signals") or [] if x.get("signal"))
    new_signals = Counter(x.get("signal") for x in (current.get("temporal") or {}).get("signals") or [] if x.get("signal"))
    return {
        "generated_at": utc_iso(),
        "corpus_delta": corpus_delta,
        "distribution_deltas": distribution_deltas,
        "new_temporal_signals": sorted((new_signals - old_signals).elements()),
        "signals_no_longer_present": sorted((old_signals - new_signals).elements()),
        "guardrails": [
            "Distribution-share movement is descriptive of the corpus and is not coverage-adjusted.",
            "Source-mix and verification changes can alter apparent country, domain, audience, and narrative shares without a corresponding real-world change.",
        ],
    }


def save_longitudinal_comparison(
    previous: str | Path,
    current: str | Path,
    output_file: str | Path,
    *,
    kind: str = "synthesis",
) -> str:
    target = Path(output_file).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if kind == "synthesis":
        payload = compare_syntheses(previous, current)
    elif kind == "packet":
        payload = compare_intelligence_packets(previous, current)
    else:
        raise ValueError("kind must be synthesis or packet")
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return str(target)
