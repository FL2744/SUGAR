from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .observations import ResearchObservation
from .state_schema import StateAssessment
from .utils import utc_iso


def _parse_time(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text[:10])
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_freshness_report(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    *,
    now: datetime | None = None,
    current_activity_start: str = "2024-01-01",
    collection_stale_days: int = 90,
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = _parse_time(current_activity_start) or datetime(2024, 1, 1, tzinfo=timezone.utc)
    assessment_map = {row.observation_id: row for row in assessments}
    rows: list[dict[str, Any]] = []
    current_verified = 0
    stale_collection = 0
    undated = 0
    pre_period = 0

    for observation in observations:
        assessment = assessment_map.get(observation.observation_id)
        observed_at = _parse_time(observation.observed_at)
        evidence_collected = [_parse_time(item.collected_at) for item in observation.evidence]
        evidence_collected = [value for value in evidence_collected if value is not None]
        latest_collection = max(evidence_collected, default=None)
        age_days = (now - latest_collection).total_seconds() / 86400 if latest_collection else None
        in_current_period = observed_at is not None and observed_at >= start
        if observed_at is None:
            undated += 1
        elif not in_current_period:
            pre_period += 1
        if age_days is not None and age_days > collection_stale_days:
            stale_collection += 1
        verified = bool(assessment and assessment.brief_eligible and observation.verification_state == "human_verified")
        if verified and in_current_period:
            current_verified += 1
        rows.append(
            {
                "observation_id": observation.observation_id,
                "title": observation.title,
                "country": observation.country,
                "city": observation.city,
                "observed_at": observation.observed_at,
                "in_current_activity_period": in_current_period,
                "latest_evidence_collected_at": latest_collection.replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
                if latest_collection
                else "",
                "collection_age_days": round(age_days, 1) if age_days is not None else None,
                "collection_stale": bool(age_days is not None and age_days > collection_stale_days),
                "brief_eligible": verified,
                "verification_state": assessment.review_state if assessment else "not_assessed",
            }
        )

    return {
        "generated_at": utc_iso(),
        "current_activity_start": start.date().isoformat(),
        "collection_stale_days": collection_stale_days,
        "observations": len(rows),
        "current_period_verified": current_verified,
        "undated_observations": undated,
        "pre_period_observations": pre_period,
        "stale_collection_observations": stale_collection,
        "guardrail": "Pre-period evidence may remain valuable for background or relationship history. Freshness flags identify monitoring gaps; they do not invalidate older evidence automatically.",
        "records": rows,
    }


def save_freshness_report(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    path: str | Path,
    **kwargs,
) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            build_freshness_report(observations, assessments, **kwargs), ensure_ascii=False, indent=2, sort_keys=True
        ),
        encoding="utf-8",
    )
    return str(target.resolve())
