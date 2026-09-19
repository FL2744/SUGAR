from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .llm import LLMConfig, cached_chat, create_client, parse_json_object
from .research_requirements import (
    ResearchRequirement,
    SearchBranch,
    SearchPlan,
    _clean,
    _clean_list,
    policy_for_mode,
)
from .utils import JsonCache

RESEARCH_STRATEGY_SCHEMA_VERSION = "1.0"
RESEARCH_STRATEGY_WORKFLOW = "research-requirement-compiler-v1"

CONCEPT_ORIGINS = {"explicit", "interpreted", "hypothesis"}
CONCEPT_KINDS = {
    "subject",
    "actor_class",
    "entity",
    "activity",
    "target_audience",
    "geography",
    "timeframe",
    "language",
    "source",
    "out_of_scope",
    "indicator",
}
STRATEGY_REVIEW_STATES = {"draft", "approved", "rejected"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_id(prefix: str, payload: Any, length: int = 16) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:length]}"


def _bounded_confidence(value: Any, *, default: float = 1.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = default
    return max(0.0, min(1.0, result))


@dataclass
class SourceSpan:
    text: str
    start: int
    end: int

    def __post_init__(self) -> None:
        self.text = str(self.text or "")
        self.start = int(self.start)
        self.end = int(self.end)
        if not self.text:
            raise ValueError("Source span text cannot be empty.")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("Source span offsets are invalid.")

    def validate_against(self, question: str) -> None:
        if self.end > len(question) or question[self.start:self.end] != self.text:
            raise ValueError(
                f"Source span {self.start}:{self.end} does not exactly match the research question."
            )


@dataclass
class StrategyConcept:
    kind: str
    value: str
    origin: str
    source_span: SourceSpan | None = None
    confidence: float = 1.0
    rationale: str = ""
    canonical_value: str = ""
    included: bool = True
    analyst_note: str = ""
    concept_id: str = ""

    def __post_init__(self) -> None:
        self.kind = _clean(self.kind).casefold()
        self.value = _clean(self.value)
        self.origin = _clean(self.origin).casefold()
        self.rationale = _clean(self.rationale)
        self.canonical_value = _clean(self.canonical_value)
        self.included = bool(self.included)
        self.analyst_note = _clean(self.analyst_note)
        self.confidence = _bounded_confidence(self.confidence)
        if self.kind not in CONCEPT_KINDS:
            raise ValueError(f"Unsupported strategy concept kind: {self.kind}")
        if self.origin not in CONCEPT_ORIGINS:
            raise ValueError(f"Unsupported strategy concept origin: {self.origin}")
        if not self.value:
            raise ValueError("Strategy concept value cannot be empty.")
        if self.source_span is not None and not isinstance(self.source_span, SourceSpan):
            self.source_span = SourceSpan(**dict(self.source_span))
        if self.origin == "explicit" and self.source_span is None:
            raise ValueError("Explicit strategy concepts require an exact source span.")
        if self.origin == "hypothesis" and self.source_span is not None:
            raise ValueError("Search hypotheses cannot masquerade as explicit source spans.")
        if not self.concept_id:
            self.concept_id = _stable_id(
                "sc",
                {
                    "kind": self.kind,
                    "value": self.value.casefold(),
                    "origin": self.origin,
                    "span": asdict(self.source_span) if self.source_span else None,
                },
                length=14,
            )


@dataclass
class ResearchDimension:
    name: str
    question: str
    indicators: list[str] = field(default_factory=list)
    source_families: list[str] = field(default_factory=list)
    rationale: str = ""
    included: bool = True
    analyst_note: str = ""
    dimension_id: str = ""

    def __post_init__(self) -> None:
        self.name = _clean(self.name).casefold().replace(" ", "_")
        self.question = _clean(self.question)
        self.indicators = _clean_list(self.indicators)
        self.source_families = _clean_list(self.source_families)
        self.rationale = _clean(self.rationale)
        self.included = bool(self.included)
        self.analyst_note = _clean(self.analyst_note)
        if not self.name or not self.question:
            raise ValueError("Research dimensions require a name and question.")
        if not self.dimension_id:
            self.dimension_id = _stable_id(
                "rd",
                {"name": self.name, "question": self.question.casefold()},
                length=14,
            )


@dataclass
class MissingDimension:
    field: str
    reason: str
    required_for_search: bool = False

    def __post_init__(self) -> None:
        self.field = _clean(self.field).casefold().replace(" ", "_")
        self.reason = _clean(self.reason)
        self.required_for_search = bool(self.required_for_search)
        if not self.field or not self.reason:
            raise ValueError("Missing-dimension entries require field and reason.")


@dataclass
class CompiledResearchStrategy:
    requirement_id: str
    original_question: str
    analytic_task: str
    concepts: list[StrategyConcept] = field(default_factory=list)
    dimensions: list[ResearchDimension] = field(default_factory=list)
    missing_dimensions: list[MissingDimension] = field(default_factory=list)
    review_state: str = "draft"
    reviewer: str = ""
    review_note: str = ""
    reviewed_at: str = ""
    ai_provider: str = ""
    ai_model: str = ""
    ai_workflow: str = ""
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    strategy_id: str = ""
    schema_version: str = RESEARCH_STRATEGY_SCHEMA_VERSION
    events: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.requirement_id = _clean(self.requirement_id)
        self.original_question = _clean(self.original_question)
        self.analytic_task = _clean(self.analytic_task).casefold()
        self.review_state = _clean(self.review_state).casefold()
        self.reviewer = _clean(self.reviewer)
        self.review_note = _clean(self.review_note)
        self.ai_provider = _clean(self.ai_provider).casefold()
        self.ai_model = _clean(self.ai_model)
        self.ai_workflow = _clean(self.ai_workflow)
        self.concepts = [
            item if isinstance(item, StrategyConcept) else StrategyConcept(**item)
            for item in self.concepts
        ]
        self.dimensions = [
            item if isinstance(item, ResearchDimension) else ResearchDimension(**item)
            for item in self.dimensions
        ]
        self.missing_dimensions = [
            item if isinstance(item, MissingDimension) else MissingDimension(**item)
            for item in self.missing_dimensions
        ]
        if not self.requirement_id or not self.original_question:
            raise ValueError("Compiled strategy requires requirement_id and original_question.")
        if self.review_state not in STRATEGY_REVIEW_STATES:
            raise ValueError(f"Unsupported strategy review state: {self.review_state}")
        if self.schema_version != RESEARCH_STRATEGY_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported strategy schema {self.schema_version!r}; "
                f"expected {RESEARCH_STRATEGY_SCHEMA_VERSION!r}."
            )
        for concept in self.concepts:
            if concept.source_span is not None:
                concept.source_span.validate_against(self.original_question)
        ids = [item.concept_id for item in self.concepts]
        if len(ids) != len(set(ids)):
            raise ValueError("Compiled strategy contains duplicate concept IDs.")
        if self.review_state in {"approved", "rejected"} and not self.reviewer:
            raise ValueError("Approved or rejected strategies require a named reviewer.")
        if not self.strategy_id:
            self.strategy_id = _stable_id(
                "rs",
                {"requirement_id": self.requirement_id, "question": self.original_question},
            )

    @property
    def approved(self) -> bool:
        return self.review_state == "approved"

    def concepts_by(self, kind: str, *, origins: set[str] | None = None) -> list[StrategyConcept]:
        kind = _clean(kind).casefold()
        return [
            item
            for item in self.concepts
            if item.included
            and item.kind == kind
            and (origins is None or item.origin in origins)
        ]

    def concept(self, concept_id: str) -> StrategyConcept:
        concept_id = _clean(concept_id)
        for item in self.concepts:
            if item.concept_id == concept_id:
                return item
        raise KeyError(f"Unknown strategy concept_id: {concept_id}")

    def update_concept(
        self,
        concept_id: str,
        *,
        value: str | None = None,
        included: bool | None = None,
        rationale: str | None = None,
        analyst_note: str | None = None,
        actor: str = "analyst",
    ) -> None:
        item = self.concept(concept_id)
        changes: dict[str, Any] = {}
        if value is not None:
            cleaned = _clean(value)
            if not cleaned:
                raise ValueError("Strategy concept value cannot be empty.")
            if item.origin == "explicit" and cleaned != item.value:
                raise ValueError(
                    "Explicit source-span text is immutable. Exclude it and add an interpreted concept instead."
                )
            if cleaned != item.value:
                changes["value"] = {"from": item.value, "to": cleaned}
                item.value = cleaned
        if included is not None and bool(included) != item.included:
            changes["included"] = {"from": item.included, "to": bool(included)}
            item.included = bool(included)
        if rationale is not None:
            cleaned = _clean(rationale)
            if cleaned != item.rationale:
                changes["rationale"] = {"from": item.rationale, "to": cleaned}
                item.rationale = cleaned
        if analyst_note is not None:
            cleaned = _clean(analyst_note)
            if cleaned != item.analyst_note:
                changes["analyst_note"] = {"from": item.analyst_note, "to": cleaned}
                item.analyst_note = cleaned
        if not changes:
            return
        self.review_state = "draft"
        self.reviewer = ""
        self.reviewed_at = ""
        self.updated_at = _utc_now()
        self.events.append(
            {
                "type": "concept_updated",
                "at": self.updated_at,
                "actor": _clean(actor) or "analyst",
                "concept_id": item.concept_id,
                "changes": changes,
            }
        )

    def add_analyst_concept(
        self,
        *,
        kind: str,
        value: str,
        origin: str = "interpreted",
        rationale: str = "",
        actor: str = "analyst",
    ) -> StrategyConcept:
        origin = _clean(origin).casefold()
        if origin == "explicit":
            raise ValueError("Analyst-added concepts must be interpreted or hypothesis concepts.")
        concept = StrategyConcept(
            kind=kind,
            value=value,
            origin=origin,
            confidence=1.0,
            rationale=rationale or "Added during analyst review.",
            analyst_note=f"Added by {_clean(actor) or 'analyst'}.",
        )
        _add_unique_concept(self.concepts, concept)
        self.review_state = "draft"
        self.reviewer = ""
        self.reviewed_at = ""
        self.updated_at = _utc_now()
        self.events.append(
            {
                "type": "concept_added",
                "at": self.updated_at,
                "actor": _clean(actor) or "analyst",
                "concept_id": concept.concept_id,
                "origin": concept.origin,
            }
        )
        return concept

    def dimension(self, dimension_id: str) -> ResearchDimension:
        dimension_id = _clean(dimension_id)
        for item in self.dimensions:
            if item.dimension_id == dimension_id:
                return item
        raise KeyError(f"Unknown research dimension_id: {dimension_id}")

    def update_dimension(
        self,
        dimension_id: str,
        *,
        question: str | None = None,
        indicators: Iterable[Any] | None = None,
        source_families: Iterable[Any] | None = None,
        rationale: str | None = None,
        included: bool | None = None,
        analyst_note: str | None = None,
        actor: str = "analyst",
    ) -> None:
        item = self.dimension(dimension_id)
        changes: dict[str, Any] = {}
        if question is not None:
            cleaned = _clean(question)
            if not cleaned:
                raise ValueError("Research dimension question cannot be empty.")
            if cleaned != item.question:
                changes["question"] = {"from": item.question, "to": cleaned}
                item.question = cleaned
        if indicators is not None:
            cleaned = _clean_list(indicators)
            if cleaned != item.indicators:
                changes["indicators"] = {"from": item.indicators, "to": cleaned}
                item.indicators = cleaned
        if source_families is not None:
            cleaned = _clean_list(source_families)
            if cleaned != item.source_families:
                changes["source_families"] = {
                    "from": item.source_families,
                    "to": cleaned,
                }
                item.source_families = cleaned
        if rationale is not None:
            cleaned = _clean(rationale)
            if cleaned != item.rationale:
                changes["rationale"] = {"from": item.rationale, "to": cleaned}
                item.rationale = cleaned
        if included is not None and bool(included) != item.included:
            changes["included"] = {"from": item.included, "to": bool(included)}
            item.included = bool(included)
        if analyst_note is not None:
            cleaned = _clean(analyst_note)
            if cleaned != item.analyst_note:
                changes["analyst_note"] = {"from": item.analyst_note, "to": cleaned}
                item.analyst_note = cleaned
        if not changes:
            return
        self.review_state = "draft"
        self.reviewer = ""
        self.reviewed_at = ""
        self.updated_at = _utc_now()
        self.events.append(
            {
                "type": "dimension_updated",
                "at": self.updated_at,
                "actor": _clean(actor) or "analyst",
                "dimension_id": item.dimension_id,
                "changes": changes,
            }
        )

    def update_analytic_task(self, value: str, *, actor: str = "analyst") -> None:
        value = _clean(value).casefold()
        if not value:
            raise ValueError("Analytic task cannot be empty.")
        if value == self.analytic_task:
            return
        previous = self.analytic_task
        self.analytic_task = value
        self.review_state = "draft"
        self.reviewer = ""
        self.reviewed_at = ""
        self.updated_at = _utc_now()
        self.events.append(
            {
                "type": "analytic_task_updated",
                "at": self.updated_at,
                "actor": _clean(actor) or "analyst",
                "from": previous,
                "to": value,
            }
        )

    def approve(self, *, reviewer: str, note: str = "") -> None:
        reviewer = _clean(reviewer)
        if not reviewer:
            raise ValueError("Strategy approval requires a named reviewer.")
        previous = self.review_state
        self.review_state = "approved"
        self.reviewer = reviewer
        self.review_note = _clean(note)
        self.reviewed_at = _utc_now()
        self.updated_at = self.reviewed_at
        self.events.append(
            {
                "type": "strategy_approved",
                "at": self.reviewed_at,
                "actor": reviewer,
                "from": previous,
                "to": "approved",
                "note": self.review_note,
            }
        )

    def export_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CompiledResearchStrategy":
        return cls(**dict(payload))


_ACTIVITY_PATTERNS: list[tuple[str, str]] = [
    (r"\breach(?:ing|es|ed)?\b", "audience_outreach"),
    (r"\bengag(?:e|es|ed|ing)\b", "audience_engagement"),
    (r"\binfluenc(?:e|es|ed|ing)\b", "influence"),
    (r"\bexpand(?:s|ed|ing)?\b", "expansion"),
    (r"\boperate(?:s|d|ing)?\b", "operations"),
    (r"\bpartner(?:s|ed|ing)?\b", "partnership"),
    (r"\btarget(?:s|ed|ing)?\b", "targeting"),
]


def _span(question: str, start: int, end: int) -> SourceSpan:
    return SourceSpan(text=question[start:end], start=start, end=end)


def _add_unique_concept(target: list[StrategyConcept], concept: StrategyConcept) -> None:
    key = (concept.kind, concept.value.casefold(), concept.origin)
    if any((item.kind, item.value.casefold(), item.origin) == key for item in target):
        return
    target.append(concept)


def _find_exact(question: str, value: str) -> SourceSpan | None:
    if not value:
        return None
    match = re.search(re.escape(value), question, flags=re.I)
    if not match:
        return None
    return _span(question, match.start(), match.end())


def _deterministic_sentence_concepts(requirement: ResearchRequirement) -> tuple[list[StrategyConcept], str]:
    question = requirement.question
    concepts: list[StrategyConcept] = []

    structured = [
        ("geography", requirement.geographies),
        ("target_audience", requirement.target_audiences),
        ("entity", requirement.known_entities),
        ("language", [item for item in requirement.languages if item.casefold() != "auto"]),
        ("source", requirement.preferred_sources),
        ("out_of_scope", requirement.excluded_topics),
    ]
    for kind, values in structured:
        for value in values:
            span = _find_exact(question, value)
            if span is not None:
                _add_unique_concept(
                    concepts,
                    StrategyConcept(
                        kind=kind,
                        value=value,
                        origin="explicit",
                        source_span=span,
                        rationale="Analyst-supplied structured field is explicitly present in the question.",
                    ),
                )
            else:
                _add_unique_concept(
                    concepts,
                    StrategyConcept(
                        kind=kind,
                        value=value,
                        origin="interpreted",
                        confidence=1.0,
                        rationale="Analyst supplied this structured constraint alongside the question.",
                    ),
                )

    for pattern, canonical in _ACTIVITY_PATTERNS:
        match = re.search(pattern, question, flags=re.I)
        if match:
            _add_unique_concept(
                concepts,
                StrategyConcept(
                    kind="activity",
                    value=match.group(0),
                    canonical_value=canonical,
                    origin="explicit",
                    source_span=_span(question, match.start(), match.end()),
                    rationale="Activity verb appears explicitly in the research question.",
                ),
            )

    # Common "How are/is SUBJECT VERB AUDIENCE in GEOGRAPHY?" structure.
    activity = next((item for item in concepts if item.kind == "activity" and item.source_span), None)
    if activity and activity.source_span:
        prefix = question[: activity.source_span.start]
        subject_match = re.search(r"(?i)^\s*(?:how|what|which|where|who|why)\s+(?:are|is|do|does|did|have|has|can|could|will|would)\s+(.+?)\s*$", prefix)
        if subject_match:
            raw = subject_match.group(1)
            start = subject_match.start(1)
            end = subject_match.end(1)
            _add_unique_concept(
                concepts,
                StrategyConcept(
                    kind="subject",
                    value=raw,
                    origin="explicit",
                    source_span=_span(question, start, end),
                    rationale="Subject phrase is grammatically positioned before the explicit activity verb.",
                ),
            )

        suffix_start = activity.source_span.end
        suffix = question[suffix_start:]
        audience_match = re.match(r"\s+(.+?)(?=\s+(?:in|across|within|throughout|among)\s+|[?.!]?$)", suffix, flags=re.I)
        if audience_match:
            raw = _clean(audience_match.group(1))
            if raw:
                start = suffix_start + audience_match.start(1)
                end = suffix_start + audience_match.end(1)
                _add_unique_concept(
                    concepts,
                    StrategyConcept(
                        kind="target_audience",
                        value=raw,
                        origin="explicit",
                        source_span=_span(question, start, end),
                        rationale="Audience phrase follows the explicit activity verb.",
                        confidence=0.85,
                    ),
                )

    geography_match = re.search(
        r"(?i)\b(?:in|across|within|throughout)\s+([A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*){0,4})(?=[?.!,]|$)",
        question,
    )
    if geography_match:
        _add_unique_concept(
            concepts,
            StrategyConcept(
                kind="geography",
                value=geography_match.group(1),
                origin="explicit",
                source_span=_span(question, geography_match.start(1), geography_match.end(1)),
                rationale="Geographic phrase follows an explicit location preposition.",
                confidence=0.9,
            ),
        )

    folded = question.casefold()
    if folded.startswith("how ") or folded.startswith("how are ") or folded.startswith("how is "):
        analytic_task = "mechanism_assessment"
    elif folded.startswith("where "):
        analytic_task = "geographic_mapping"
    elif folded.startswith("who "):
        analytic_task = "actor_identification"
    elif folded.startswith(("what ", "which ")):
        analytic_task = "inventory_assessment"
    elif "compare" in folded or " versus " in folded or " vs " in folded:
        analytic_task = "comparative_assessment"
    else:
        analytic_task = "descriptive_assessment"
    return concepts, analytic_task


def _default_dimensions(
    requirement: ResearchRequirement,
    concepts: Iterable[StrategyConcept],
    analytic_task: str,
) -> list[ResearchDimension]:
    subjects = [item.value for item in concepts if item.kind in {"subject", "actor_class", "entity"}]
    subject = subjects[0] if subjects else "in-scope actors or institutions"
    audiences = [item.value for item in concepts if item.kind == "target_audience"]
    audience = audiences[0] if audiences else "the target audience"
    geographies = [item.value for item in concepts if item.kind == "geography"]
    geography = geographies[0] if geographies else "the target geography"
    dimensions = [
        ResearchDimension(
            name="presence",
            question=f"Which {subject} are present or active in {geography}?",
            indicators=["institution", "office", "center", "program", "partnership"],
            source_families=["official institutions", "partner institutions", "local media"],
            rationale="Establish the actor/institution baseline before assessing activity.",
        ),
        ResearchDimension(
            name="program_activity",
            question=f"What public-facing programs or activities are {subject} conducting?",
            indicators=["event", "course", "scholarship", "exchange", "competition", "lecture", "partnership"],
            source_families=["official institutions", "universities", "event pages", "local media"],
            rationale="Observe concrete activity rather than infer intent from presence alone.",
        ),
        ResearchDimension(
            name="audience_reach",
            question=f"What evidence shows contact with or participation by {audience}?",
            indicators=["attendance", "participation", "applications", "student organization", "registration", "testimonial"],
            source_families=["universities", "student organizations", "public social platforms", "event pages"],
            rationale="Separate activity from evidence that the target audience was actually reached.",
        ),
    ]
    if analytic_task == "mechanism_assessment":
        dimensions.append(
            ResearchDimension(
                name="engagement_mechanism",
                question=f"Through which mechanisms do {subject} engage {audience}?",
                indicators=["scholarship", "event", "social media", "language education", "exchange", "partnership"],
                source_families=["official institutions", "universities", "public social platforms"],
                rationale="The wording of the question asks how engagement occurs.",
            )
        )
    if analytic_task == "comparative_assessment":
        dimensions.append(
            ResearchDimension(
                name="comparison",
                question="Which observable differences matter across the compared cases?",
                indicators=["presence", "activity", "reach", "engagement", "time"],
                source_families=["comparable official sources", "local media", "public social platforms"],
                rationale="The research question requests a comparative judgment.",
            )
        )
    return dimensions


def _missing_dimensions(requirement: ResearchRequirement, concepts: Iterable[StrategyConcept]) -> list[MissingDimension]:
    concepts = list(concepts)
    result: list[MissingDimension] = []
    if not requirement.timeframe.start and not requirement.timeframe.end:
        result.append(
            MissingDimension(
                field="timeframe",
                reason="No explicit research timeframe was supplied.",
                required_for_search=False,
            )
        )
    if requirement.languages == ["auto"]:
        result.append(
            MissingDimension(
                field="languages",
                reason="Search languages are set to auto and should be confirmed for multilingual coverage.",
                required_for_search=False,
            )
        )
    if not any(item.kind == "geography" for item in concepts):
        result.append(
            MissingDimension(
                field="geography",
                reason="No geography could be safely extracted or supplied.",
                required_for_search=False,
            )
        )
    if not any(item.kind == "target_audience" for item in concepts):
        result.append(
            MissingDimension(
                field="target_audience",
                reason="No target audience could be safely extracted or supplied.",
                required_for_search=False,
            )
        )
    return result


def compile_requirement_deterministically(requirement: ResearchRequirement) -> CompiledResearchStrategy:
    concepts, analytic_task = _deterministic_sentence_concepts(requirement)
    strategy = CompiledResearchStrategy(
        requirement_id=requirement.requirement_id,
        original_question=requirement.question,
        analytic_task=analytic_task,
        concepts=concepts,
        dimensions=_default_dimensions(requirement, concepts, analytic_task),
        missing_dimensions=_missing_dimensions(requirement, concepts),
    )
    strategy.events.append(
        {
            "type": "deterministic_compile",
            "at": _utc_now(),
            "workflow": RESEARCH_STRATEGY_WORKFLOW,
            "concept_count": len(strategy.concepts),
            "dimension_count": len(strategy.dimensions),
        }
    )
    return strategy


def build_search_plan_from_strategy(
    requirement: ResearchRequirement,
    strategy: CompiledResearchStrategy,
) -> SearchPlan:
    if strategy.requirement_id != requirement.requirement_id:
        raise ValueError("Compiled strategy and research requirement IDs do not match.")
    if not strategy.approved:
        raise ValueError("Compiled research strategy must be analyst-approved before planning.")

    policy = policy_for_mode(requirement.collection_mode)
    branches: list[SearchBranch] = []
    seen: set[str] = set()

    def add(
        query: str,
        rationale: str,
        *,
        family: str = "discovery",
        concept: str = "",
        origin: str = "analyst",
    ) -> None:
        text = _clean(query)
        key = text.casefold()
        if not text or key in seen or len(branches) >= policy.max_branches:
            return
        if any(topic.casefold() in key for topic in requirement.excluded_topics if topic.strip()):
            return
        seen.add(key)
        branches.append(
            SearchBranch(
                query=text,
                rationale=rationale,
                origin=origin,
                search_family=family,
                parent_concept=concept,
                generator=f"compiled-strategy:{strategy.strategy_id}",
                hop_depth=0,
            )
        )

    subjects = [
        item.value
        for item in strategy.concepts
        if item.included and item.kind in {"subject", "actor_class", "entity"} and item.origin != "hypothesis"
    ]
    entities = [
        item.value
        for item in strategy.concepts
        if item.included and item.kind == "entity" and item.origin != "hypothesis"
    ]
    geographies = [
        item.value
        for item in strategy.concepts
        if item.included and item.kind == "geography" and item.origin != "hypothesis"
    ]
    audiences = [
        item.value
        for item in strategy.concepts
        if item.included and item.kind == "target_audience" and item.origin != "hypothesis"
    ]
    activities = [
        item.canonical_value or item.value
        for item in strategy.concepts
        if item.included and item.kind == "activity" and item.origin != "hypothesis"
    ]
    hypotheses = [
        item
        for item in strategy.concepts
        if item.included and item.origin == "hypothesis"
    ]

    # Preserve analyst-supplied known entities even when they did not occur literally in the sentence.
    for entity in requirement.known_entities:
        if entity.casefold() not in {value.casefold() for value in entities}:
            entities.append(entity)
    if not subjects:
        subjects = list(entities)
    if not geographies:
        geographies = list(requirement.geographies)
    if not audiences:
        audiences = list(requirement.target_audiences)

    for entity in entities:
        add(
            entity,
            "Approved entity from the compiled research strategy.",
            family="entity",
            concept=entity,
        )
        for geography in geographies:
            add(
                f"{entity} {geography}",
                "Approved entity combined with the in-scope geography.",
                family="entity",
                concept=entity,
            )

    for subject in subjects:
        for geography in geographies[:3]:
            add(
                f"{subject} {geography}",
                "Approved subject class combined with the in-scope geography.",
                family="discovery",
                concept=subject,
            )
        for audience in audiences[:3]:
            add(
                f"{subject} {audience}",
                "Approved subject class combined with the target audience.",
                family="audience",
                concept=audience,
            )
        for activity in activities[:3]:
            for geography in geographies[:2] or [""]:
                add(
                    " ".join(part for part in (subject, activity, geography) if part),
                    "Approved subject, activity, and geography compiled from the research requirement.",
                    family="relationship",
                    concept=activity,
                )

    # Operationalize approved research dimensions as observable-indicator searches.
    dimension_budget = 2 if requirement.collection_mode == "quick" else 4 if requirement.collection_mode == "standard" else 7
    for dimension in strategy.dimensions:
        if not dimension.included:
            continue
        for indicator in dimension.indicators[:dimension_budget]:
            if subjects:
                base = subjects[0]
                query = " ".join(
                    part
                    for part in (base, indicator, geographies[0] if geographies else "")
                    if part
                )
            else:
                query = " ".join(
                    part
                    for part in (indicator, geographies[0] if geographies else "")
                    if part
                )
            add(
                query,
                f"Observable indicator for approved research dimension '{dimension.name}': {dimension.question}",
                family="discovery",
                concept=dimension.name,
            )

    for hypothesis in hypotheses:
        add(
            hypothesis.value,
            f"Analyst-approved search hypothesis, not an asserted fact: {hypothesis.rationale}",
            family="discovery",
            concept=hypothesis.value,
            origin="analyst",
        )

    if not branches:
        add(
            requirement.question,
            "Fallback seed because the approved compiled strategy produced no narrower executable branch.",
            family="discovery",
            concept=requirement.question,
        )

    plan = SearchPlan(
        requirement_id=requirement.requirement_id,
        branches=branches,
        policy=policy,
    )
    plan.add_event(
        "compiled_strategy_plan",
        strategy_id=strategy.strategy_id,
        reviewer=strategy.reviewer,
        analytic_task=strategy.analytic_task,
        included_concepts=len([item for item in strategy.concepts if item.included]),
        branch_count=len(branches),
    )
    return plan


def _validated_ai_span(question: str, raw: dict[str, Any]) -> SourceSpan | None:
    try:
        span = SourceSpan(
            text=str(raw.get("source_text") or ""),
            start=int(raw.get("start")),
            end=int(raw.get("end")),
        )
        span.validate_against(question)
        return span
    except (TypeError, ValueError):
        return None


def enrich_strategy_with_llm(
    requirement: ResearchRequirement,
    strategy: CompiledResearchStrategy,
    *,
    llm: LLMConfig,
    cache_dir: str | Path | None = None,
    client: Any | None = None,
) -> CompiledResearchStrategy:
    if strategy.requirement_id != requirement.requirement_id:
        raise ValueError("Compiled strategy and research requirement IDs do not match.")
    system = (
        "You compile a research QUESTION into a research STRATEGY. Do not answer the question. "
        "Do not invent evidence or factual findings. Keep three epistemic classes separate: "
        "(1) explicit concepts quoted from the exact question with exact Python string offsets; "
        "(2) interpreted concepts that explain the semantics but are not literal facts; "
        "(3) search hypotheses that may be worth investigating but are not stated by the analyst. "
        "Never classify a hypothesis as explicit. Avoid private-person targeting or dossier construction. "
        "Return only JSON with keys analytic_task, explicit_concepts, interpreted_concepts, "
        "search_hypotheses, and research_dimensions. Concept kinds must be one of subject, actor_class, "
        "entity, activity, target_audience, geography, timeframe, language, source, out_of_scope, indicator. "
        "Each explicit concept must include kind, value, source_text, start, end, confidence, rationale. "
        "Each interpreted/hypothesis concept must include kind, value, confidence, rationale. "
        "Each research dimension must include name, question, indicators, source_families, rationale."
    )
    user = json.dumps(
        {
            "original_question": requirement.question,
            "analyst_supplied_requirement": requirement.export_dict(),
            "deterministic_compile": strategy.export_dict(),
            "instruction": "Improve semantic coverage while preserving the analyst's meaning and the explicit/interpreted/hypothesis boundary.",
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    client = client or create_client(llm)
    cache = JsonCache(Path(cache_dir).expanduser().resolve() / "requirement-compiler-cache.json") if cache_dir else None
    response = cached_chat(
        client,
        llm,
        cache,
        RESEARCH_STRATEGY_WORKFLOW,
        system,
        user,
        max_tokens=6000,
    )
    payload = parse_json_object(response)
    analytic_task = _clean(payload.get("analytic_task")).casefold()
    if analytic_task:
        strategy.analytic_task = analytic_task

    for raw in payload.get("explicit_concepts") or []:
        if not isinstance(raw, dict):
            continue
        span = _validated_ai_span(requirement.question, raw)
        if span is None:
            continue
        try:
            concept = StrategyConcept(
                kind=raw.get("kind"),
                value=span.text,
                canonical_value=(
                    _clean(raw.get("value"))
                    if _clean(raw.get("value")).casefold() != span.text.casefold()
                    else ""
                ),
                origin="explicit",
                source_span=span,
                confidence=raw.get("confidence"),
                rationale=raw.get("rationale"),
            )
        except ValueError:
            continue
        _add_unique_concept(strategy.concepts, concept)

    for origin, field_name in (
        ("interpreted", "interpreted_concepts"),
        ("hypothesis", "search_hypotheses"),
    ):
        for raw in payload.get(field_name) or []:
            if not isinstance(raw, dict):
                continue
            try:
                concept = StrategyConcept(
                    kind=raw.get("kind"),
                    value=raw.get("value"),
                    origin=origin,
                    confidence=raw.get("confidence"),
                    rationale=raw.get("rationale"),
                )
            except ValueError:
                continue
            _add_unique_concept(strategy.concepts, concept)

    dimensions: list[ResearchDimension] = []
    for raw in payload.get("research_dimensions") or []:
        if not isinstance(raw, dict):
            continue
        try:
            dimensions.append(
                ResearchDimension(
                    name=raw.get("name"),
                    question=raw.get("question"),
                    indicators=raw.get("indicators") or [],
                    source_families=raw.get("source_families") or [],
                    rationale=raw.get("rationale"),
                )
            )
        except ValueError:
            continue
    if dimensions:
        strategy.dimensions = dimensions
    strategy.missing_dimensions = _missing_dimensions(requirement, strategy.concepts)
    strategy.ai_provider = llm.provider
    strategy.ai_model = llm.model
    strategy.ai_workflow = RESEARCH_STRATEGY_WORKFLOW
    strategy.updated_at = _utc_now()
    strategy.events.append(
        {
            "type": "ai_semantic_compile",
            "at": strategy.updated_at,
            "provider": llm.provider,
            "model": llm.model,
            "workflow": RESEARCH_STRATEGY_WORKFLOW,
        }
    )
    # Re-run full semantic validation, especially exact explicit spans.
    strategy.__post_init__()
    return strategy


def save_research_strategy(strategy: CompiledResearchStrategy, path: str | Path) -> str:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(strategy.export_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return str(target)


def load_research_strategy(path: str | Path) -> CompiledResearchStrategy:
    source = Path(path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Compiled research strategy must contain a JSON object.")
    return CompiledResearchStrategy.from_dict(payload)
