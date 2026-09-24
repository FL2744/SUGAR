from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from .models import PostRecord

OBSERVATION_SCHEMA_VERSION = "1.4"

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

RELEVANCE_STATES = {"unknown", "relevant", "uncertain", "not_relevant"}

OBSERVATION_LOCATION_PRECISIONS = {
    "exact",
    "site",
    "locality",
    "city",
    "region",
    "country",
    "unknown",
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


def _optional_float(value: Any) -> float | None:
    if value is None or value == "" or str(value).strip().casefold() in {"nan", "none", "<na>"}:
        return None
    return float(value)


def _nonnegative_float(value: Any, field_name: str) -> float | None:
    number = _optional_float(value)
    if number is not None and number < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return number


def make_observation_id(*parts: Any) -> str:
    identity = "|".join(_clean(part).casefold() for part in parts if _clean(part))
    if not identity:
        raise ValueError("Cannot create an observation ID without stable identifying information.")
    return "obs_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def make_location_id(*parts: Any) -> str:
    identity = "|".join(_clean(part).casefold() for part in parts if _clean(part))
    if not identity:
        raise ValueError("Cannot create a location ID without stable identifying information.")
    return "loc_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


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
    language: str = ""
    media_artifact_id: str = ""
    media_locator: str = ""

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
        self.language = _clean(self.language).casefold()
        self.media_artifact_id = _clean(self.media_artifact_id)
        self.media_locator = _clean(self.media_locator)
        if not self.url and not (self.platform and self.native_id):
            raise ValueError("Evidence requires a URL or a platform/native_id identity.")


@dataclass
class ObservationLocation:
    """One evidenced or explicitly qualified location for a single research activity.

    Multiple entries describe multiple venues/locations for the same observation; they do not
    create multiple activities. Precision and provenance remain location-specific so a named
    institution with an unresolved campus can coexist with a site-level venue without inventing
    a precise point.
    """

    label: str
    country: str = ""
    region: str = ""
    city: str = ""
    latitude: float | None = None
    longitude: float | None = None
    precision: str = "unknown"
    confidence: float | None = None
    uncertainty_km: float | None = None
    basis: str = "unknown"
    source_ref: str = ""
    note: str = ""
    location_id: str = ""

    def __post_init__(self) -> None:
        for attr in ("label", "country", "region", "city", "precision", "basis", "source_ref", "note"):
            setattr(self, attr, _clean(getattr(self, attr)))
        self.precision = self.precision.casefold() or "unknown"
        if self.precision not in OBSERVATION_LOCATION_PRECISIONS:
            raise ValueError(f"Unsupported observation location precision: {self.precision}")
        self.latitude = _optional_float(self.latitude)
        self.longitude = _optional_float(self.longitude)
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Observation locations require both latitude and longitude when coordinates are supplied.")
        if self.latitude is not None and not -90.0 <= self.latitude <= 90.0:
            raise ValueError("Observation location latitude must be between -90 and 90.")
        if self.longitude is not None and not -180.0 <= self.longitude <= 180.0:
            raise ValueError("Observation location longitude must be between -180 and 180.")
        self.confidence = _bounded_confidence(self.confidence, "observation location confidence")
        self.uncertainty_km = _nonnegative_float(self.uncertainty_km, "observation location uncertainty_km")
        if not any((self.label, self.city, self.region, self.country, self.latitude is not None)):
            raise ValueError("Observation locations require a label, geographic name, or coordinate pair.")
        if not self.location_id:
            self.location_id = make_location_id(
                self.label,
                self.country,
                self.region,
                self.city,
                self.latitude,
                self.longitude,
                self.source_ref,
            )
        else:
            self.location_id = _clean(self.location_id)


@dataclass
class SpatialMatch:
    """A derived geographic relationship to a reference point.

    This structure records proximity only. It must not be treated as evidence of influence,
    coordination, competition, strategic overlap, or causation.
    """

    reference_layer: str
    reference_id: str
    reference_name: str
    distance_km: float
    reference_category: str = "reference"
    distance_band: str = ""
    same_city: bool = False
    same_country: bool = False
    latitude: float | None = None
    longitude: float | None = None
    source_url: str = ""

    def __post_init__(self) -> None:
        self.reference_layer = _clean(self.reference_layer) or "Reference"
        self.reference_id = _clean(self.reference_id)
        self.reference_name = _clean(self.reference_name) or self.reference_id or "Reference point"
        self.reference_category = _clean(self.reference_category) or "reference"
        self.distance_band = _clean(self.distance_band)
        self.source_url = _clean(self.source_url)
        self.distance_km = float(self.distance_km)
        if self.distance_km < 0:
            raise ValueError("Spatial match distance_km cannot be negative.")
        self.latitude = _optional_float(self.latitude)
        self.longitude = _optional_float(self.longitude)
        if self.latitude is not None and not -90.0 <= self.latitude <= 90.0:
            raise ValueError("Spatial match latitude must be between -90 and 90.")
        if self.longitude is not None and not -180.0 <= self.longitude <= 180.0:
            raise ValueError("Spatial match longitude must be between -180 and 180.")
        self.same_city = bool(self.same_city)
        self.same_country = bool(self.same_country)


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
    locations: list[ObservationLocation] = field(default_factory=list)

    institution_name: str = ""
    program_name: str = ""
    actors: list[str] = field(default_factory=list)
    audiences: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    us_overlap: list[str] = field(default_factory=list)
    overlap_note: str = ""
    spatial_matches: list[SpatialMatch] = field(default_factory=list)

    evidence: list[EvidenceReference] = field(default_factory=list)
    source_record_keys: list[str] = field(default_factory=list)

    relevance: str = "unknown"
    relevance_confidence: float | None = None
    triage_labels: list[str] = field(default_factory=list)
    triage_evidence: list[str] = field(default_factory=list)
    ai_confidence: float | None = None
    ai_provider: str = ""
    ai_model: str = ""
    ai_workflow: str = ""
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
            "location_basis", "institution_name", "program_name", "overlap_note", "ai_provider", "ai_model",
            "ai_workflow", "ai_reason",
            "reviewer", "reviewed_at", "verification_notes", "created_at", "updated_at", "schema_version",
        ):
            setattr(self, attr, _clean(getattr(self, attr)))

        # Keep legacy scalar coordinates backward-compatible: incomplete pairs can still be loaded
        # and are rejected as unresolved by the location resolver. New structured locations are
        # stricter because each entry is an explicit venue/location claim.
        self.latitude = _optional_float(self.latitude)
        self.longitude = _optional_float(self.longitude)
        self.actors = _clean_list(self.actors)
        self.audiences = _clean_list(self.audiences)
        self.themes = _clean_list(self.themes)
        self.us_overlap = _clean_list(self.us_overlap)
        self.source_record_keys = _clean_list(self.source_record_keys)
        self.triage_labels = _clean_list(self.triage_labels)
        self.triage_evidence = _clean_list(self.triage_evidence)
        self.location_confidence = _bounded_confidence(self.location_confidence, "location_confidence")
        self.relevance_confidence = _bounded_confidence(self.relevance_confidence, "relevance_confidence")
        self.ai_confidence = _bounded_confidence(self.ai_confidence, "ai_confidence")

        normalized_locations: list[ObservationLocation] = []
        seen_location_ids: set[str] = set()
        for item in self.locations:
            if isinstance(item, ObservationLocation):
                location = item
            elif isinstance(item, dict):
                location = ObservationLocation(**item)
            else:
                raise TypeError("locations entries must be ObservationLocation objects or dictionaries.")
            if location.location_id not in seen_location_ids:
                normalized_locations.append(location)
                seen_location_ids.add(location.location_id)
        self.locations = normalized_locations

        self.relevance = _clean(self.relevance).casefold() or "unknown"
        if self.relevance not in RELEVANCE_STATES:
            raise ValueError(f"Unsupported relevance: {self.relevance}")

        normalized_matches: list[SpatialMatch] = []
        for item in self.spatial_matches:
            if isinstance(item, SpatialMatch):
                normalized_matches.append(item)
            elif isinstance(item, dict):
                normalized_matches.append(SpatialMatch(**item))
            else:
                raise TypeError("spatial_matches entries must be SpatialMatch objects or dictionaries.")
        self.spatial_matches = sorted(
            normalized_matches,
            key=lambda item: (item.distance_km, item.reference_layer.casefold(), item.reference_id.casefold()),
        )

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

    @property
    def nearest_spatial_match(self) -> SpatialMatch | None:
        return self.spatial_matches[0] if self.spatial_matches else None

    @property
    def has_multiple_locations(self) -> bool:
        return len(self.locations) > 1

    def touch(self) -> None:
        self.updated_at = _utc_now_iso()
        self.schema_version = OBSERVATION_SCHEMA_VERSION

    def add_evidence(self, evidence: EvidenceReference | dict[str, Any]) -> None:
        item = evidence if isinstance(evidence, EvidenceReference) else EvidenceReference(**evidence)
        identity = (item.url.casefold(), item.platform.casefold(), item.native_id.casefold())
        existing = {(x.url.casefold(), x.platform.casefold(), x.native_id.casefold()) for x in self.evidence}
        if identity not in existing:
            self.evidence.append(item)
            self.touch()

    def set_ai_triage(
        self,
        *,
        labels: Iterable[str],
        confidence: float | int | None,
        provider: str = "",
        model: str,
        workflow: str = "",
        reason: str = "",
        relevance: str = "unknown",
        relevance_confidence: float | int | None = None,
        evidence_spans: Iterable[str] = (),
    ) -> None:
        normalized_relevance = _clean(relevance).casefold() or "unknown"
        if normalized_relevance not in RELEVANCE_STATES:
            raise ValueError(f"Unsupported relevance: {normalized_relevance}")
        self.relevance = normalized_relevance
        self.relevance_confidence = _bounded_confidence(relevance_confidence, "relevance_confidence")
        self.triage_labels = _clean_list(labels)
        self.triage_evidence = _clean_list(evidence_spans)
        self.ai_confidence = _bounded_confidence(confidence, "ai_confidence")
        self.ai_provider = _clean(provider).casefold()
        self.ai_model = _clean(model)
        self.ai_workflow = _clean(workflow)
        self.ai_reason = _clean(reason)
        if self.verification_state in {"unreviewed", "needs_followup"}:
            self.verification_state = "ai_triaged"
        self.touch()

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
        self.touch()

    def export_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in (
            "actors", "audiences", "themes", "us_overlap", "source_record_keys", "triage_labels", "triage_evidence"
        ):
            data[key] = json.dumps(data[key], ensure_ascii=False)
        data["locations"] = json.dumps(data["locations"], ensure_ascii=False, sort_keys=True)
        data["spatial_matches"] = json.dumps(data["spatial_matches"], ensure_ascii=False, sort_keys=True)
        data["evidence"] = json.dumps(data["evidence"], ensure_ascii=False, sort_keys=True)
        data["primary_source_url"] = self.primary_source_url
        return data

    @classmethod
    def from_export_dict(cls, raw: dict[str, Any]) -> "ResearchObservation":
        data = dict(raw)
        data.pop("primary_source_url", None)
        for key in (
            "actors", "audiences", "themes", "us_overlap", "source_record_keys", "triage_labels", "triage_evidence"
        ):
            value = data.get(key, [])
            if isinstance(value, str):
                value = json.loads(value) if value.strip() else []
            data[key] = value
        for key in ("evidence", "spatial_matches", "locations"):
            value = data.get(key, [])
            if isinstance(value, str):
                value = json.loads(value) if value.strip() else []
            data[key] = value
        for key in (
            "latitude", "longitude", "location_confidence", "relevance_confidence", "ai_confidence"
        ):
            data[key] = _optional_float(data.get(key))
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
        language=record.detected_language or record.platform_language,
    )
    location_basis = "ai_inferred" if record.inferred_location else ("profile" if record.author_location else "unknown")
    location_label = record.inferred_location or record.author_location
    return ResearchObservation(
        observation_type="digital_post",
        title=f"{record.platform} public post".strip(),
        summary=summary or record.translated_text or record.original_text,
        observed_at=record.published_at,
        location_label=location_label,
        latitude=record.latitude,
        longitude=record.longitude,
        location_basis=location_basis,
        location_confidence=record.location_confidence if record.inferred_location else None,
        # Keep account identity in the canonical source record/evidence chain rather
        # than automatically promoting every post author into an analytic actor.
        # Triage may add an actor when the source content makes that entity relevant
        # to the research requirement.
        actors=[],
        evidence=[evidence],
        source_record_keys=[record.record_key],
    )


def observations_from_posts(records: Iterable[PostRecord]) -> list[ResearchObservation]:
    return [observation_from_post(record) for record in records]
