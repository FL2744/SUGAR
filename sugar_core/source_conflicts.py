from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from .utils import atomic_write_text

SOURCE_AUTHORITY_TYPES = {
    "official_authority",
    "official_operator",
    "official_host",
    "primary_source",
    "credible_secondary",
    "other",
}

SOURCE_FRESHNESS_STATES = {
    "current",
    "potentially_stale",
    "historical",
    "unknown",
}

SOURCE_CONFLICT_TYPES = {
    "service_topology",
    "location",
    "operational_status",
    "date",
    "identity",
    "quantitative",
    "other",
}

SOURCE_CONFLICT_STATUSES = {
    "open",
    "provisional_treatment",
    "human_adjudicated",
    "resolved_by_source_update",
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _choice(value: Any, allowed: set[str], field_name: str, default: str) -> str:
    text = _clean(value).casefold() or default
    if text not in allowed:
        raise ValueError(f"Unsupported {field_name}: {text}")
    return text


def _date_like(value: Any, field_name: str) -> str:
    text = _clean(value)
    if not text:
        return ""
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date or datetime.") from exc
    return text


def _source_url(value: Any) -> str:
    text = _clean(value)
    if not text:
        raise ValueError("Source claims require a source_url.")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_url must be an absolute HTTP(S) URL.")
    return text


def _stable_id(prefix: str, *parts: Any) -> str:
    identity = "|".join(_clean(part).casefold() for part in parts if _clean(part))
    if not identity:
        raise ValueError("Stable source-conflict IDs require identifying information.")
    return f"{prefix}_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


@dataclass
class SourceClaim:
    statement: str
    source_url: str
    source_label: str = ""
    publisher: str = ""
    authority_type: str = "other"
    authority_scope: str = ""
    freshness: str = "unknown"
    published_at: str = ""
    updated_at: str = ""
    retrieved_at: str = ""
    effective_date: str = ""
    note: str = ""
    claim_id: str = ""

    def __post_init__(self) -> None:
        self.statement = _clean(self.statement)
        if not self.statement:
            raise ValueError("Source claims require a statement.")
        self.source_url = _source_url(self.source_url)
        self.source_label = _clean(self.source_label)
        self.publisher = _clean(self.publisher)
        self.authority_type = _choice(self.authority_type, SOURCE_AUTHORITY_TYPES, "source authority type", "other")
        self.authority_scope = _clean(self.authority_scope)
        self.freshness = _choice(self.freshness, SOURCE_FRESHNESS_STATES, "source freshness", "unknown")
        self.published_at = _date_like(self.published_at, "published_at")
        self.updated_at = _date_like(self.updated_at, "updated_at")
        self.retrieved_at = _date_like(self.retrieved_at, "retrieved_at")
        self.effective_date = _date_like(self.effective_date, "effective_date")
        self.note = _clean(self.note)
        if not self.claim_id:
            self.claim_id = _stable_id("srcclaim", self.source_url, self.statement)
        else:
            self.claim_id = _clean(self.claim_id)


@dataclass
class SourceConflict:
    topic: str
    claims: list[SourceClaim | dict[str, Any]]
    conflict_type: str = "other"
    status: str = "open"
    preferred_claim_id: str = ""
    treatment: str = ""
    preference_rationale: str = ""
    reviewer: str = ""
    review_note: str = ""
    conflict_id: str = ""

    def __post_init__(self) -> None:
        self.topic = _clean(self.topic)
        if not self.topic:
            raise ValueError("Source conflicts require a topic.")
        normalized: list[SourceClaim] = []
        for raw in self.claims or []:
            normalized.append(raw if isinstance(raw, SourceClaim) else SourceClaim(**dict(raw)))
        self.claims = normalized
        if len(self.claims) < 2:
            raise ValueError("Source conflicts require at least two contradictory source claims.")
        if len({claim.claim_id for claim in self.claims}) != len(self.claims):
            raise ValueError("Source conflicts cannot contain duplicate claims.")
        if len({claim.source_url for claim in self.claims}) < 2:
            raise ValueError("Source conflicts require at least two distinct source URLs.")

        self.conflict_type = _choice(self.conflict_type, SOURCE_CONFLICT_TYPES, "source conflict type", "other")
        self.status = _choice(self.status, SOURCE_CONFLICT_STATUSES, "source conflict status", "open")
        self.preferred_claim_id = _clean(self.preferred_claim_id)
        self.treatment = _clean(self.treatment)
        self.preference_rationale = _clean(self.preference_rationale)
        self.reviewer = _clean(self.reviewer)
        self.review_note = _clean(self.review_note)

        claim_ids = {claim.claim_id for claim in self.claims}
        if self.preferred_claim_id and self.preferred_claim_id not in claim_ids:
            raise ValueError("preferred_claim_id must reference a claim in this conflict.")
        if self.status == "open" and self.preferred_claim_id:
            raise ValueError("Open source conflicts cannot silently prefer one claim; use provisional_treatment.")
        if self.status in {"provisional_treatment", "human_adjudicated", "resolved_by_source_update"}:
            if not self.preferred_claim_id:
                raise ValueError(f"{self.status} source conflicts require a preferred_claim_id.")
            if not self.treatment:
                raise ValueError(f"{self.status} source conflicts require an explicit treatment.")
            if not self.preference_rationale:
                raise ValueError(f"{self.status} source conflicts require a preference rationale.")
        if self.status == "human_adjudicated" and not self.reviewer:
            raise ValueError("Human-adjudicated source conflicts require a named reviewer.")

        if not self.conflict_id:
            self.conflict_id = _stable_id("srcconflict", self.conflict_type, self.topic, *sorted(claim_ids))
        else:
            self.conflict_id = _clean(self.conflict_id)

    @property
    def preferred_claim(self) -> SourceClaim | None:
        if not self.preferred_claim_id:
            return None
        return next(
            (claim for claim in self.claims if claim.claim_id == self.preferred_claim_id),
            None,
        )

    @property
    def requires_human_review(self) -> bool:
        return self.status in {"open", "provisional_treatment"}

    @property
    def is_human_adjudicated(self) -> bool:
        return self.status == "human_adjudicated"

    @property
    def is_resolved(self) -> bool:
        return self.status in {"human_adjudicated", "resolved_by_source_update"}


def source_conflict_to_dict(conflict: SourceConflict) -> dict[str, Any]:
    return asdict(conflict)


def source_conflicts_to_dicts(conflicts: Iterable[SourceConflict]) -> list[dict[str, Any]]:
    return [source_conflict_to_dict(conflict) for conflict in conflicts]


def save_source_conflicts(conflicts: Iterable[SourceConflict], path: str | Path) -> str:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = source_conflicts_to_dicts(conflicts)
    atomic_write_text(target, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return str(target)


def load_source_conflicts(path: str | Path) -> list[SourceConflict]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    raw = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list):
        raise ValueError("Source conflict files must contain a JSON list.")
    return [SourceConflict(**dict(item)) for item in raw]


def source_conflict_summary(conflicts: Iterable[SourceConflict]) -> dict[str, Any]:
    rows = list(conflicts)
    return {
        "conflicts": len(rows),
        "open": sum(row.status == "open" for row in rows),
        "provisional_treatment": sum(row.status == "provisional_treatment" for row in rows),
        "human_adjudicated": sum(row.status == "human_adjudicated" for row in rows),
        "resolved_by_source_update": sum(row.status == "resolved_by_source_update" for row in rows),
        "requiring_human_review": sum(row.requires_human_review for row in rows),
        "distinct_sources": len({claim.source_url for row in rows for claim in row.claims}),
    }
