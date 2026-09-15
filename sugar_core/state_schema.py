from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

STATE_SCHEMA_VERSION = "1.1"

STRATEGIC_AUDIENCES = {
    "students",
    "prospective_students",
    "youth",
    "emerging_leaders",
    "entrepreneurs",
    "technical_professionals",
    "educators",
    "researchers_academics",
    "journalists_media",
    "civil_society",
    "government_officials",
    "exchange_alumni",
    "general_public",
    "other",
}

PROGRAM_DOMAINS = {
    "higher_education",
    "language_education",
    "english_language",
    "entrepreneurship",
    "stem_technology",
    "media_information_literacy",
    "civic_engagement",
    "culture_arts",
    "economic_commercial",
    "professional_skills",
    "exchange_alumni",
    "digital_connectivity",
    "other",
}

# This mapping is intentionally program/domain-based, not audience-based. It is used to keep
# direct service overlap distinct from audience overlap. A Chinese-language program aimed at
# students, for example, must not become an "english_language" service overlap merely because
# U.S. student programming may include English instruction.
_PROGRAM_DOMAIN_SERVICE_TAGS = {
    "higher_education": {"educationusa", "study_in_the_us", "higher_education"},
    "language_education": {"language_education"},
    "english_language": {"english_language", "english_learning"},
    "entrepreneurship": {"entrepreneurship", "business", "innovation"},
    "stem_technology": {"stem", "technology", "makerspace", "innovation"},
    "media_information_literacy": {"media_literacy", "information_literacy"},
    "civic_engagement": {"civic_engagement", "democracy", "community_engagement"},
    "culture_arts": {"culture", "arts"},
    "economic_commercial": {"business", "entrepreneurship", "economic"},
    "professional_skills": {"professional_skills", "career"},
    "exchange_alumni": {"alumni", "exchange", "exchange_alumni"},
    "digital_connectivity": {"digital_connectivity", "technology"},
    "other": set(),
}

NARRATIVE_TAGS = {
    "education_opportunity",
    "technology_innovation",
    "development_modernization",
    "culture_civilization",
    "economic_opportunity",
    "china_model",
    "china_us_comparison",
    "anti_us",
    "multipolarity",
    "global_south_solidarity",
    "shared_future",
    "china_russia_coordination",
    "third_party_coordination",
    "local_partnership",
    "commercial_branding",
    "other",
}

SUPPORT_LEVELS = {
    "not_assessed",
    "unsupported",
    "possible",
    "probable",
    "confirmed",
}

SUPPORT_BASES = {
    "official_prc_source",
    "official_host_source",
    "funding",
    "personnel",
    "governance",
    "branding",
    "co_sponsorship",
    "facility_or_material_support",
    "program_delivery",
    "credible_secondary_reporting",
    "other",
}

OBSERVABILITY_LEVELS = {
    "not_assessed",
    "activity_observed",
    "reach_observed",
    "engagement_observed",
    "outcome_evidence",
    "causal_influence_evidence",
}

CLAIM_TYPES = {
    "descriptive_fact",
    "support_relationship",
    "audience",
    "program_domain",
    "narrative",
    "reach",
    "coordination",
    "us_overlap",
    "influence",
    "other",
}

EPISTEMIC_STATUSES = {
    "observed_fact",
    "analytic_assessment",
    "hypothesis",
}

REVIEW_STATES = {
    "unreviewed",
    "ai_triaged",
    "human_verified",
    "rejected",
    "needs_followup",
}

NETWORK_TYPES = {
    "american_space",
    "educationusa",
    "us_embassy_or_consulate",
    "binational_center",
    "other_usg",
}

US_SERVICE_DELIVERY_MODES = {
    "physical",
    "virtual",
    "hybrid",
}

US_SERVICE_COVERAGE_SCOPES = {
    "site",
    "city",
    "country",
    "global",
}

US_LOCATION_PRECISIONS = {
    "exact",
    "site",
    "locality",
    "city",
    "region",
    "country",
    "unknown",
}

_US_LOCATION_DEFAULT_UNCERTAINTY_KM = {
    "exact": 0.10,
    "site": 0.75,
    "locality": 3.0,
    "city": 12.0,
    "region": 75.0,
    "country": 250.0,
    "unknown": 100.0,
}

REACH_METRIC_NAMES = {
    "attendance",
    "views",
    "likes",
    "comments",
    "shares_reposts",
    "followers",
}

REACH_QUALIFIERS = {
    "exact",
    "approximate",
    "minimum",
    "maximum",
    "range",
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _clean_list(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = _clean(value)
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _choice(value: Any, allowed: set[str], field_name: str, default: str) -> str:
    text = _clean(value).casefold() or default
    if text not in allowed:
        raise ValueError(f"Unsupported {field_name}: {text}")
    return text


def _confidence(value: Any, field_name: str = "confidence") -> float | None:
    if value is None or value == "":
        return None
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1.")
    return number


def _nonnegative_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    number = int(value)
    if number < 0:
        raise ValueError("Reach metrics cannot be negative.")
    return number


def _nonnegative_float(value: Any, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    number = float(value)
    if number < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return number


def stable_state_id(prefix: str, *parts: Any) -> str:
    identity = "|".join(_clean(part).casefold() for part in parts if _clean(part))
    if not identity:
        raise ValueError("Stable State research IDs require identifying information.")
    return f"{prefix}_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


@dataclass
class QualifiedReachValue:
    value: int | None = None
    qualifier: str = "exact"
    minimum: int | None = None
    maximum: int | None = None
    source_note: str = ""
    source_ref: str = ""

    def __post_init__(self) -> None:
        self.qualifier = _choice(self.qualifier, REACH_QUALIFIERS, "reach qualifier", "exact")
        self.value = _nonnegative_int(self.value)
        self.minimum = _nonnegative_int(self.minimum)
        self.maximum = _nonnegative_int(self.maximum)
        self.source_note = _clean(self.source_note)
        self.source_ref = _clean(self.source_ref)

        if self.qualifier == "range":
            if self.minimum is None or self.maximum is None:
                raise ValueError("Range reach values require minimum and maximum bounds.")
            if self.minimum > self.maximum:
                raise ValueError("Reach minimum cannot exceed maximum.")
            if self.value is not None and not self.minimum <= self.value <= self.maximum:
                raise ValueError("Reach range representative value must fall within its bounds.")
        else:
            if self.value is None:
                raise ValueError(f"{self.qualifier} reach values require a value.")
            if self.qualifier == "exact":
                if self.minimum not in (None, self.value) or self.maximum not in (None, self.value):
                    raise ValueError("Exact reach bounds must equal the exact value.")
                self.minimum = self.value
                self.maximum = self.value
            elif self.qualifier == "minimum":
                if self.maximum is not None:
                    raise ValueError("Minimum reach values cannot also set a maximum bound.")
                self.minimum = self.value
            elif self.qualifier == "maximum":
                if self.minimum is not None:
                    raise ValueError("Maximum reach values cannot also set a minimum bound.")
                self.maximum = self.value
            elif self.qualifier == "approximate" and (self.minimum is not None or self.maximum is not None):
                raise ValueError("Approximate reach should not invent numeric bounds; use range when bounds are reported.")

        if self.qualifier != "exact" and not (self.source_note or self.source_ref):
            raise ValueError("Non-exact reach values require a source note or source reference preserving the qualifier.")

    @property
    def is_exact(self) -> bool:
        return self.qualifier == "exact"

    @property
    def lower_bound(self) -> int | None:
        if self.qualifier in {"exact", "minimum", "range"}:
            return self.minimum
        return None

    @property
    def upper_bound(self) -> int | None:
        if self.qualifier in {"exact", "maximum", "range"}:
            return self.maximum
        return None


@dataclass
class ReachMetrics:
    attendance: int | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares_reposts: int | None = None
    followers: int | None = None
    qualified: dict[str, QualifiedReachValue | dict[str, Any]] = field(default_factory=dict)
    source_note: str = ""

    def __post_init__(self) -> None:
        for field_name in REACH_METRIC_NAMES:
            setattr(self, field_name, _nonnegative_int(getattr(self, field_name)))

        normalized: dict[str, QualifiedReachValue] = {}
        for metric_name, raw_value in (self.qualified or {}).items():
            metric = _choice(metric_name, REACH_METRIC_NAMES, "reach metric name", "attendance")
            qualified = raw_value if isinstance(raw_value, QualifiedReachValue) else QualifiedReachValue(**dict(raw_value))
            exact_value = getattr(self, metric)
            if qualified.is_exact:
                if exact_value is None:
                    setattr(self, metric, qualified.value)
                elif exact_value != qualified.value:
                    raise ValueError(f"Exact qualified {metric} conflicts with the legacy exact value.")
            elif exact_value is not None:
                raise ValueError(
                    f"Non-exact qualified {metric} cannot also be stored as a bare exact integer."
                )
            normalized[metric] = qualified
        self.qualified = normalized
        self.source_note = _clean(self.source_note)

    def metric(self, metric_name: str) -> QualifiedReachValue | None:
        metric = _choice(metric_name, REACH_METRIC_NAMES, "reach metric name", "attendance")
        if metric in self.qualified:
            return self.qualified[metric]
        exact_value = getattr(self, metric)
        if exact_value is None:
            return None
        return QualifiedReachValue(value=exact_value, qualifier="exact")

    @property
    def has_nonexact_values(self) -> bool:
        return any(not value.is_exact for value in self.qualified.values())

    @property
    def observed_total(self) -> int:
        # Preserve backward compatibility for exact integer data while deliberately excluding
        # approximate/bounded observations from a falsely precise aggregate.
        return sum(
            value or 0
            for value in (self.attendance, self.views, self.likes, self.comments, self.shares_reposts)
        )


@dataclass
class AnalyticClaim:
    statement: str
    claim_type: str = "descriptive_fact"
    epistemic_status: str = "observed_fact"
    confidence: float | None = None
    evidence_refs: list[str] = field(default_factory=list)
    review_state: str = "unreviewed"
    reviewer: str = ""
    review_note: str = ""
    claim_id: str = ""

    def __post_init__(self) -> None:
        self.statement = _clean(self.statement)
        if not self.statement:
            raise ValueError("Analytic claims require a statement.")
        self.claim_type = _choice(self.claim_type, CLAIM_TYPES, "claim_type", "descriptive_fact")
        self.epistemic_status = _choice(
            self.epistemic_status, EPISTEMIC_STATUSES, "epistemic_status", "observed_fact"
        )
        self.review_state = _choice(self.review_state, REVIEW_STATES, "review_state", "unreviewed")
        self.confidence = _confidence(self.confidence)
        self.evidence_refs = _clean_list(self.evidence_refs)
        self.reviewer = _clean(self.reviewer)
        self.review_note = _clean(self.review_note)
        if self.claim_type in {"support_relationship", "coordination", "influence"} and not self.evidence_refs:
            raise ValueError(f"{self.claim_type} claims require explicit evidence references.")
        if self.claim_type == "influence" and self.epistemic_status == "observed_fact":
            raise ValueError("Influence cannot be encoded as a simple observed fact; use an analytic assessment.")
        if self.review_state in {"human_verified", "rejected"} and not self.reviewer:
            raise ValueError(f"{self.review_state} claims require a named reviewer.")
        if not self.claim_id:
            self.claim_id = stable_state_id("claim", self.claim_type, self.statement, *self.evidence_refs)
        else:
            self.claim_id = _clean(self.claim_id)


@dataclass
class SupportAssessment:
    level: str = "not_assessed"
    bases: list[str] = field(default_factory=list)
    rationale: str = ""
    confidence: float | None = None
    evidence_refs: list[str] = field(default_factory=list)
    review_state: str = "unreviewed"
    reviewer: str = ""

    def __post_init__(self) -> None:
        self.level = _choice(self.level, SUPPORT_LEVELS, "support level", "not_assessed")
        self.bases = [_choice(value, SUPPORT_BASES, "support basis", "other") for value in _clean_list(self.bases)]
        self.rationale = _clean(self.rationale)
        self.confidence = _confidence(self.confidence)
        self.evidence_refs = _clean_list(self.evidence_refs)
        self.review_state = _choice(self.review_state, REVIEW_STATES, "review_state", "unreviewed")
        self.reviewer = _clean(self.reviewer)
        if self.level in {"probable", "confirmed"} and not self.evidence_refs:
            raise ValueError(f"{self.level} PRC-support assessments require explicit evidence references.")
        if self.level == "confirmed" and self.review_state != "human_verified":
            raise ValueError("Confirmed PRC support requires human verification.")
        if self.review_state in {"human_verified", "rejected"} and not self.reviewer:
            raise ValueError(f"{self.review_state} support assessments require a reviewer.")


@dataclass
class USPresenceSite:
    name: str
    network: str
    country: str
    city: str = ""
    subtype: str = ""
    latitude: float | None = None
    longitude: float | None = None
    service_tags: list[str] = field(default_factory=list)
    source_url: str = ""
    status: str = "active"
    site_id: str = ""
    delivery_mode: str = "physical"
    coverage_scope: str = "site"
    location_precision: str = "unknown"
    location_confidence: float | None = None
    location_uncertainty_km: float | None = None
    location_basis: str = ""

    def __post_init__(self) -> None:
        self.name = _clean(self.name)
        self.network = _choice(self.network, NETWORK_TYPES, "network", "other_usg")
        self.country = _clean(self.country)
        self.city = _clean(self.city)
        self.subtype = _clean(self.subtype)
        self.service_tags = _clean_list(self.service_tags)
        self.source_url = _clean(self.source_url)
        self.status = _clean(self.status).casefold() or "active"
        self.delivery_mode = _choice(
            self.delivery_mode, US_SERVICE_DELIVERY_MODES, "U.S. service delivery mode", "physical"
        )
        self.coverage_scope = _choice(
            self.coverage_scope, US_SERVICE_COVERAGE_SCOPES, "U.S. service coverage scope", "site"
        )
        self.location_precision = _choice(
            self.location_precision, US_LOCATION_PRECISIONS, "U.S. site location precision", "unknown"
        )
        self.location_confidence = _confidence(self.location_confidence, "location_confidence")
        self.location_uncertainty_km = _nonnegative_float(
            self.location_uncertainty_km, "location_uncertainty_km"
        )
        self.location_basis = _clean(self.location_basis)
        if not self.name or not self.country:
            raise ValueError("U.S. presence sites require name and country.")
        if self.latitude not in (None, ""):
            self.latitude = float(self.latitude)
        else:
            self.latitude = None
        if self.longitude not in (None, ""):
            self.longitude = float(self.longitude)
        else:
            self.longitude = None
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("U.S. presence coordinates require both latitude and longitude.")
        if self.latitude is not None and not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if self.longitude is not None and not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")
        if not self.site_id:
            self.site_id = stable_state_id("us", self.network, self.name, self.country, self.city)
        else:
            self.site_id = _clean(self.site_id)

    @property
    def is_spatial(self) -> bool:
        return bool(
            self.delivery_mode in {"physical", "hybrid"}
            and self.latitude is not None
            and self.longitude is not None
        )

    def effective_location_uncertainty_km(self, default: float = 0.75) -> float:
        if self.location_uncertainty_km is not None:
            return float(self.location_uncertainty_km)
        if self.location_precision != "unknown":
            return float(_US_LOCATION_DEFAULT_UNCERTAINTY_KM[self.location_precision])
        return max(0.0, float(default))


@dataclass
class USOverlapAssessment:
    same_country: bool = False
    same_city: bool = False
    nearest_site_id: str = ""
    nearest_site_name: str = ""
    nearest_network: str = ""
    distance_km: float | None = None
    audience_overlap: list[str] = field(default_factory=list)
    thematic_overlap: list[str] = field(default_factory=list)
    service_overlap: list[str] = field(default_factory=list)
    note: str = ""

    def __post_init__(self) -> None:
        self.nearest_site_id = _clean(self.nearest_site_id)
        self.nearest_site_name = _clean(self.nearest_site_name)
        self.nearest_network = _clean(self.nearest_network)
        self.audience_overlap = _clean_list(self.audience_overlap)
        self.thematic_overlap = _clean_list(self.thematic_overlap)
        raw_service_overlap = _clean_list(self.service_overlap)
        allowed_service_tags: set[str] = set()
        for domain in self.thematic_overlap:
            allowed_service_tags.update(_PROGRAM_DOMAIN_SERVICE_TAGS.get(domain.casefold(), set()))
        # Keep service overlap program-semantic. Audience similarity is already represented by
        # audience_overlap and must not manufacture a direct service/program equivalence.
        self.service_overlap = [
            value for value in raw_service_overlap if value.casefold() in allowed_service_tags
        ]
        self.note = _clean(self.note)
        if self.distance_km not in (None, ""):
            self.distance_km = max(0.0, float(self.distance_km))
        else:
            self.distance_km = None

    @property
    def material(self) -> bool:
        return bool(
            self.same_city
            or (self.distance_km is not None and self.distance_km <= 50)
            or self.audience_overlap
            or self.thematic_overlap
            or self.service_overlap
        )


@dataclass
class StateAssessment:
    observation_id: str
    assessment_id: str = ""
    strategic_audiences: list[str] = field(default_factory=list)
    program_domains: list[str] = field(default_factory=list)
    narrative_tags: list[str] = field(default_factory=list)
    sponsor_entities: list[str] = field(default_factory=list)
    host_entities: list[str] = field(default_factory=list)
    partner_entities: list[str] = field(default_factory=list)
    delivery_modes: list[str] = field(default_factory=list)
    policy_relevance: list[str] = field(default_factory=list)
    prc_support: SupportAssessment = field(default_factory=SupportAssessment)
    observability_level: str = "not_assessed"
    reach: ReachMetrics = field(default_factory=ReachMetrics)
    us_overlap: USOverlapAssessment = field(default_factory=USOverlapAssessment)
    claims: list[AnalyticClaim] = field(default_factory=list)
    review_state: str = "unreviewed"
    reviewer: str = ""
    review_note: str = ""
    analytic_priority: str = "normal"
    schema_version: str = STATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.observation_id = _clean(self.observation_id)
        if not self.observation_id:
            raise ValueError("State assessments require an observation_id.")
        self.strategic_audiences = [
            _choice(value, STRATEGIC_AUDIENCES, "strategic audience", "other")
            for value in _clean_list(self.strategic_audiences)
        ]
        self.program_domains = [
            _choice(value, PROGRAM_DOMAINS, "program domain", "other")
            for value in _clean_list(self.program_domains)
        ]
        self.narrative_tags = [
            _choice(value, NARRATIVE_TAGS, "narrative tag", "other")
            for value in _clean_list(self.narrative_tags)
        ]
        self.sponsor_entities = _clean_list(self.sponsor_entities)
        self.host_entities = _clean_list(self.host_entities)
        self.partner_entities = _clean_list(self.partner_entities)
        self.delivery_modes = _clean_list(self.delivery_modes)
        self.policy_relevance = _clean_list(self.policy_relevance)
        if isinstance(self.prc_support, dict):
            self.prc_support = SupportAssessment(**self.prc_support)
        if isinstance(self.reach, dict):
            self.reach = ReachMetrics(**self.reach)
        if isinstance(self.us_overlap, dict):
            self.us_overlap = USOverlapAssessment(**self.us_overlap)
        self.claims = [claim if isinstance(claim, AnalyticClaim) else AnalyticClaim(**claim) for claim in self.claims]
        self.observability_level = _choice(
            self.observability_level, OBSERVABILITY_LEVELS, "observability_level", "not_assessed"
        )
        self.review_state = _choice(self.review_state, REVIEW_STATES, "review_state", "unreviewed")
        self.reviewer = _clean(self.reviewer)
        self.review_note = _clean(self.review_note)
        self.analytic_priority = _clean(self.analytic_priority).casefold() or "normal"
        if self.analytic_priority not in {"low", "normal", "high", "urgent"}:
            raise ValueError("analytic_priority must be low, normal, high, or urgent")
        if self.review_state in {"human_verified", "rejected"} and not self.reviewer:
            raise ValueError(f"{self.review_state} assessments require a reviewer.")
        if not self.assessment_id:
            self.assessment_id = stable_state_id("state", self.observation_id)
        else:
            self.assessment_id = _clean(self.assessment_id)

    @property
    def brief_eligible(self) -> bool:
        if self.review_state != "human_verified":
            return False
        if self.prc_support.level == "confirmed" and self.prc_support.review_state != "human_verified":
            return False
        return all(claim.review_state == "human_verified" for claim in self.claims if claim.claim_type in {"support_relationship", "coordination", "influence"})

    def export_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "StateAssessment":
        return cls(**dict(raw))

    def fingerprint(self) -> str:
        payload = asdict(self)
        payload.pop("assessment_id", None)
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
