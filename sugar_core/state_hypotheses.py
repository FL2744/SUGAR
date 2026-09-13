from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .utils import stable_hash, utc_iso


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _load(value: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return json.loads(Path(value).read_text(encoding="utf-8-sig"))


def _hypotheses(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    final = payload.get("final") or payload
    for raw in final.get("alternatives") or []:
        if not isinstance(raw, dict):
            continue
        text = _clean(raw.get("hypothesis"))
        if not text:
            continue
        candidates.append({
            "hypothesis_id": "h_" + stable_hash(text)[:16],
            "hypothesis": text,
            "supporting_refs": sorted({_clean(x) for x in raw.get("supporting_refs") or [] if _clean(x)}),
            "contradicting_refs": sorted({_clean(x) for x in raw.get("contradicting_refs") or [] if _clean(x)}),
            "discriminators": [_clean(x) for x in raw.get("discriminators") or [] if _clean(x)],
            "collection_needed": [_clean(x) for x in raw.get("collection_needed") or [] if _clean(x)],
            "source": "final_synthesis",
        })
    # Preserve distinct alternatives raised by specialist agents even when the integrator omits them.
    seen = {row["hypothesis"].casefold() for row in candidates}
    for agent in payload.get("agents") or []:
        for raw in agent.get("alternatives") or []:
            if not isinstance(raw, dict):
                continue
            text = _clean(raw.get("hypothesis"))
            if not text or text.casefold() in seen:
                continue
            candidates.append({
                "hypothesis_id": "h_" + stable_hash(text)[:16],
                "hypothesis": text,
                "supporting_refs": sorted({_clean(x) for x in raw.get("supporting_refs") or [] if _clean(x)}),
                "contradicting_refs": sorted({_clean(x) for x in raw.get("contradicting_refs") or [] if _clean(x)}),
                "discriminators": [_clean(x) for x in raw.get("discriminators") or [] if _clean(x)],
                "collection_needed": [_clean(x) for x in raw.get("collection_needed") or [] if _clean(x)],
                "source": str(agent.get("agent") or "specialist_agent"),
            })
            seen.add(text.casefold())
    return candidates


def build_hypothesis_matrix(payload: dict[str, Any] | str | Path) -> dict[str, Any]:
    payload = _load(payload)
    hypotheses = _hypotheses(payload)
    evidence = sorted({
        ref
        for hypothesis in hypotheses
        for ref in hypothesis["supporting_refs"] + hypothesis["contradicting_refs"]
    })
    matrix: list[dict[str, Any]] = []
    for ref in evidence:
        row: dict[str, Any] = {"evidence_ref": ref}
        for hypothesis in hypotheses:
            if ref in hypothesis["supporting_refs"]:
                value = "supports"
            elif ref in hypothesis["contradicting_refs"]:
                value = "contradicts"
            else:
                value = "neutral_or_unassessed"
            row[hypothesis["hypothesis_id"]] = value
        matrix.append(row)

    # Evidence is especially useful when it pushes hypotheses in different directions.
    discriminating: list[dict[str, Any]] = []
    for row in matrix:
        values = [row[h["hypothesis_id"]] for h in hypotheses]
        if "supports" in values and "contradicts" in values:
            discriminating.append({
                "evidence_ref": row["evidence_ref"],
                "supports": [h["hypothesis_id"] for h in hypotheses if row[h["hypothesis_id"]] == "supports"],
                "contradicts": [h["hypothesis_id"] for h in hypotheses if row[h["hypothesis_id"]] == "contradicts"],
            })

    ranking: list[dict[str, Any]] = []
    for hypothesis in hypotheses:
        support_count = len(hypothesis["supporting_refs"])
        contradiction_count = len(hypothesis["contradicting_refs"])
        assessed = support_count + contradiction_count
        inconsistency_rate = contradiction_count / assessed if assessed else None
        ranking.append({
            "hypothesis_id": hypothesis["hypothesis_id"],
            "hypothesis": hypothesis["hypothesis"],
            "supporting_evidence": support_count,
            "contradicting_evidence": contradiction_count,
            "assessed_evidence": assessed,
            "inconsistency_rate": round(inconsistency_rate, 4) if inconsistency_rate is not None else None,
            "least_inconsistent_rank_basis": "contradicting evidence count, then supporting evidence count; not a probability",
        })
    ranking.sort(key=lambda row: (
        row["contradicting_evidence"],
        -row["supporting_evidence"],
        row["hypothesis"].casefold(),
    ))
    for index, row in enumerate(ranking, 1):
        row["least_inconsistent_rank"] = index

    return {
        "generated_at": utc_iso(),
        "scope": payload.get("scope"),
        "hypotheses": hypotheses,
        "evidence_matrix": matrix,
        "discriminating_evidence": discriminating,
        "least_inconsistent_ranking": ranking,
        "guardrails": [
            "The least-inconsistent ranking is a structured comparison aid, not a probability estimate.",
            "Missing evidence is not evidence against a hypothesis unless the collection design made the expected evidence observable.",
            "Hypotheses generated by AI remain analytic hypotheses until human analysts review the evidence and alternatives.",
            "A hypothesis can survive because collection is weak; discriminating collection matters more than raw support counts.",
        ],
    }


def render_hypothesis_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Competing Hypotheses Matrix", "", "## Least-Inconsistent Ordering", ""]
    for row in payload.get("least_inconsistent_ranking") or []:
        lines.append(
            f"{row['least_inconsistent_rank']}. **{row['hypothesis']}** — "
            f"supporting={row['supporting_evidence']}, contradicting={row['contradicting_evidence']}, "
            f"inconsistency_rate={row['inconsistency_rate']}."
        )
    lines.extend(["", "## Discriminating Evidence", ""])
    for row in payload.get("discriminating_evidence") or []:
        lines.append(
            f"- `{row['evidence_ref']}` supports {', '.join(row['supports'])} and contradicts {', '.join(row['contradicts'])}."
        )
    lines.extend(["", "## Collection Needed", ""])
    for hypothesis in payload.get("hypotheses") or []:
        if hypothesis.get("collection_needed"):
            lines.append(f"- **{hypothesis['hypothesis']}**: " + "; ".join(hypothesis["collection_needed"]))
    lines.extend(["", "## Guardrails", ""])
    for value in payload.get("guardrails") or []:
        lines.append(f"- {value}")
    lines.append("")
    return "\n".join(lines)


def save_hypothesis_matrix(
    synthesis: dict[str, Any] | str | Path,
    output_directory: str | Path,
    *,
    name: str = "analytic_intelligence",
) -> list[str]:
    out_dir = Path(output_directory).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "_".join(_clean(name).split()) or "analytic_intelligence"
    payload = build_hypothesis_matrix(synthesis)
    json_path = out_dir / f"{stem}.hypotheses.json"
    csv_path = out_dir / f"{stem}.hypotheses.csv"
    markdown_path = out_dir / f"{stem}.hypotheses.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    hypotheses = payload.get("hypotheses") or []
    fields = ["hypothesis_id", "hypothesis", "source", "supporting_refs", "contradicting_refs", "discriminators", "collection_needed"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in hypotheses:
            value = dict(row)
            for key in ("supporting_refs", "contradicting_refs", "discriminators", "collection_needed"):
                value[key] = json.dumps(value.get(key) or [], ensure_ascii=False)
            writer.writerow({key: value.get(key, "") for key in fields})
    markdown_path.write_text(render_hypothesis_markdown(payload), encoding="utf-8")
    return [str(json_path), str(csv_path), str(markdown_path)]
