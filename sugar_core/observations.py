from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from .models import PostRecord

OBSERVATION_SCHEMA_VERSION = "1.0"

OBSERVATION_TYPES = {
    "institution",
    "program",
    "event",
    "digital_post",
    "narrative",
    "partnership",
    "other",
}

VERIFICATION_STATES = {
    "unreviewed",
    "ai_triaged",
    "human_verified",
    "rejected",
    "needs_followup",
}

_ALLOWED_TRANSITIONS = {
    "unreviewed": {"ai_triaged", "human_verified", "rejected", "needs_followup"},
    "ai_triaged": {"human_verified", "rejected", "needs_followup"},
    "needs_followup": {"ai_triaged", "human_verified", "rejected"},
    "human_verified": {"needs_followup"},
    "rejected": {"needs_followup"},
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _clean_list(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean(value)
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _bounded_confidence(value: float | int | None, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1.")
    return number


def make_observation_id(*parts: Any) -> str:
    identity = "|".join(_clean(part).casefold() for part in parts if _clean(part))
    if not identity:
        raise ValueError("Cannot create an observation ID without stable identifying information.")
    return "obs_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


@dataclass
class EvidenceReference:
    url: str
    title: str = ""
    source_type: str = ""
    platform: str = ""
    native_id: str = ""
    published_at: str = ""
    collected_at: str = field(default_factory=_utc_now_iso)
    archived_url: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        self.url = _clean(self.url)
        self.title = _clean(self.title)
        self.source_type = _clean(self.source_type)
        self.platform = _clean(self.platform)
        self.native_id = _clean(self.native_id)
        self.published_at = _clean(self.published_at)
        self.collected_at = _clean(self.collected_at) or _utc_now_iso()
        self.archived_url = _clean(self.archived_url)
        self.note = _clean(self.note)
        if not self.url and not (self.platform and self.native_id):
            raise ValueError("Evidence requires a URL or a platform/native_id identity.")


@dataclass
class ResearchObservation:
    observation_type: str
    summary: str
    observation_id: str = ""
    title: str = ""
    observed_at: str = ""
    activity_status: str = "unknown"

    location_label: str = ""
    country: str = ""
    region: str = ""
    city: str = ""
    latitude: float | None = None
    longitude: float | None = None
    location_basis: str = "unknown"
    location_confidence: float | None = None

    institution_name: str = ""
    program_name: str = ""
    actors: list[str] = field(default_factory=list)
    audiences: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    us_overlap: list[str] = field(default_factory=list)
    overlap_note: str = ""

    evidence: list[EvidenceReference] = field(default_factory=list)
    source_record_keys: list[str] = field(default_factory=list)

    triage_labels: list[str] = field(default_factory=list)
    ai_confidence: float | None = None
    ai_model: str = ""
    ai_reason: str = ""

    verification_state: str = "unreviewed"
    reviewer: str = ""
    reviewed_at: str = ""
    verification_notes: str = ""

    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    schema_version: str = OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.observation_type = _clean(self.observation_type).casefold()
        if self.observation_type not in OBSERVATION_TYPES:
            raise ValueError(f"Unsupported observation_type: {self.observation_type}")
        self.summary = _clean(self.summary)
        if not self.summary:
            raise ValueError("Observation summary is required.")

        for attr in (
            "title", "observed_at", "activity_status", "location_label", "country", "region", "city",
            "location_basis", "institution_name", "program_name", "overlap_note", "ai_model", "ai_reason",
            "reviewer", "reviewed_at", "verification_notes", "created_at", "updated_at", "schema_version",
        ):
            setattr(self, attr, _clean(getattr(self, attr)))

        self.actors = _clean_list(self.actors)
        self.audiences = _clean_list(self.audiences)
        self.themes = _clean_list(self.themes)
        self.us_overlap = _clean_list(self.us_overlap)
        self.source_record_keys = _clean_list(self.source_record_keys)
        self.triage_labels = _clean_list(self.triage_labels)
        self.location_confidence = _bounded_confidence(self.location_confidence, "location_confidence")
        self.ai_confidence = _bounded_confidence(self.ai_confidence, "ai_confidence")

        normalized_evidence: list[EvidenceReference] = []
        for item in self.evidence:
            if isinstance(item, EvidenceReference):
                normalized_evidence.append(item)
            elif isinstance(item, dict):
                normalized_evidence.append(EvidenceReference(**item))
            else:
                raise TypeError("evidence entries must be EvidenceReference objects or dictionaries.")
        self.evidence = normalized_evidence

        self.verification_state = _clean(self.verification_state).casefold() or "unreviewed"
        if self.verification_state not in VERIFICATION_STATES:
            raise ValueError(f"Unsupported verification_state: {self.verification_state}")

        if not self.observation_id:
            primary = self.evidence[0] if self.evidence else None
            self.observation_id = make_observation_id(
                self.observation_type,
                primary.platform if primary else "",
                primary.native_id if primary else "",
                primary.url if primary else "",
                self.institution_name,
                self.program_name,
                self.observed_at,
                self.title or self.summary,
            )
        else:
            self.observation_id = _clean(self.observation_id)

        if self.verification_state in {"human_verified", "rejected"} and not self.reviewer:
            raise ValueError(f"{self.verification_state} observations require a reviewer.")

    @property
    def primary_source_url(self) -> str:
        return self.evidence[0].url if self.evidence else ""

    def add_evidence(self, evidence: EvidenceReference | dict[str, Any]) -> None:
        item = evidence if isinstance(evidence, EvidenceReference) else EvidenceReference(**evidence)
        identity = (item.url.casefold(), item.platform.casefold(), item.native_id.casefold())
        existing = {(x.url.casefold(), x.platform.casefold(), x.native_id.casefold()) for x in self.evidence}
        if identity not in existing:
            self.evidence.append(item)
            self.updated_at = _utc_now_iso()

    def set_ai_triage(
        self,
        *,
        labels: Iterable[str],
        confidence: float | int | None,
        model: str,
        reason: str = "",
    ) -> None:
        self.triage_labels = _clean_list(labels)
        self.ai_confidence = _bounded_confidence(confidence, "ai_confidence")
        self.ai_model = _clean(model)
        self.ai_reason = _clean(reason)
        if self.verification_state in {"unreviewed", "needs_followup"}:
            self.verification_state = "ai_triaged"
        self.updated_at = _utc_now_iso()

    def transition_verification(self, state: str, *, reviewer: str = "", notes: str = "") -> None:
        target = _clean(state).casefold()
        if target not in VERIFICATION_STATES:
            raise ValueError(f"Unsupported verification state: {target}")
        if target == self.verification_state:
            return
        if target not in _ALLOWED_TRANSITIONS[self.verification_state]:
            raise ValueError(f"Invalid verification transition: {self.verification_state} -> {target}")

        reviewer = _clean(reviewer)
        if target in {"human_verified", "rejected"} and not reviewer:
            raise ValueError(f"{target} requires a reviewer.")

        self.verification_state = target
        if reviewer:
            self.reviewer = reviewer
            self.reviewed_at = _utc_now_iso()
        self.verification_notes = _clean(notes)
        self.updated_at = _utc_now_iso()

    def export_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("actors", "audiences", "themes", "us_overlap", "source_record_keys", "triage_labels"):
            data[key] = json.dumps(data[key], ensure_ascii=False)
        data["evidence"] = json.dumps(data["evidence"], ensure_ascii=False, sort_keys=True)
        data["primary_source_url"] = self.primary_source_url
        return data

    @classmethod
    def from_export_dict(cls, raw: dict[str, Any]) -> "ResearchObservation":
        data = dict(raw)
        data.pop("primary_source_url", None)
        for key in ("actors", "audiences", "themes", "us_overlap", "source_record_keys", "triage_labels"):
            value = data.get(key, [])
            if isinstance(value, str):
                value = json.loads(value) if value.strip() else []
            data[key] = value
        evidence = data.get("evidence", [])
        if isinstance(evidence, str):
            evidence = json.loads(evidence) if evidence.strip() else []
        data["evidence"] = evidence
        for key in ("latitude", "longitude", "location_confidence", "ai_confidence"):
            value = data.get(key)
            if value is None or value == "" or str(value).casefold() == "nan":
                data[key] = None
        return cls(**data)


def observation_from_post(record: PostRecord, *, summary: str | None = None) -> ResearchObservation:
    source_url = record.canonical_url or record.source_url
    evidence = EvidenceReference(
        url=source_url,
        source_type="social_media",
        platform=record.platform,
        native_id=record.native_id,
        published_at=record.published_at,
        collected_at=record.collected_at,
        note=f"Collected via {record.source_mode}" if record.source_mode else "",
    )
    location_basis = "ai_inferred" if record.inferred_location else ("profile" if record.author_location else "unknown")
    location_label = record.inferred_location or record.author_location
    return ResearchObservation(
        observation_type="digital_post",
        title=f"{record.platform} post by {record.author_handle or record.author_name}".strip(),
        summary=summary or record.translated_text or record.original_text,
        observed_at=record.published_at,
        location_label=location_label,
        latitude=record.latitude,
        longitude=record.longitude,
        location_basis=location_basis,
        location_confidence=record.location_confidence if record.inferred_location else None,
        actors=[record.author_name or record.author_handle] if (record.author_name or record.author_handle) else [],
        evidence=[evidence],
        source_record_keys=[f"{record.platform}:{record.native_id}"],
    )


def observations_from_posts(records: Iterable[PostRecord]) -> list[ResearchObservation]:
    return [observation_from_post(record) for record in records]
