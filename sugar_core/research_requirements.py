from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

REQUIREMENT_SCHEMA_VERSION = "1.0"
SEARCH_PLAN_SCHEMA_VERSION = "1.0"

BRANCH_STATUSES = {"planned", "approved", "active", "paused", "retired", "excluded", "completed"}
BRANCH_ORIGINS = {"requirement", "generated", "discovered", "analyst"}


def _utc_now() -> str:
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


def _validate_date(value: str, field_name: str) -> str:
    text = _clean(value)
    if not text:
        return ""
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must use ISO YYYY-MM-DD format.") from exc
    return text


def _stable_id(prefix: str, payload: Any, length: int = 16) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:length]}"


@dataclass
class ResearchTimeframe:
    start: str = ""
    end: str = ""

    def __post_init__(self) -> None:
        self.start = _validate_date(self.start, "timeframe.start")
        self.end = _validate_date(self.end, "timeframe.end")
        if self.start and self.end and self.start > self.end:
            raise ValueError("timeframe.start cannot be after timeframe.end.")


@dataclass
class ResearchRequirement:
    question: str
    geographies: list[str] = field(default_factory=list)
    timeframe: ResearchTimeframe = field(default_factory=ResearchTimeframe)
    target_audiences: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=lambda: ["auto"])
    known_entities: list[str] = field(default_factory=list)
    excluded_topics: list[str] = field(default_factory=list)
    preferred_sources: list[str] = field(default_factory=list)
    collection_mode: Literal["quick", "standard", "deep"] = "standard"
    notes: str = ""
    requirement_id: str = ""
    created_at: str = field(default_factory=_utc_now)
    schema_version: str = REQUIREMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.question = _clean(self.question)
        if not self.question:
            raise ValueError("A research requirement needs a non-empty question.")
        if not isinstance(self.timeframe, ResearchTimeframe):
            self.timeframe = ResearchTimeframe(**dict(self.timeframe))
        self.geographies = _clean_list(self.geographies)
        self.target_audiences = _clean_list(self.target_audiences)
        self.languages = _clean_list(self.languages) or ["auto"]
        self.known_entities = _clean_list(self.known_entities)
        self.excluded_topics = _clean_list(self.excluded_topics)
        self.preferred_sources = _clean_list(self.preferred_sources)
        self.notes = _clean(self.notes)
        self.collection_mode = _clean(self.collection_mode).casefold()  # type: ignore[assignment]
        if self.collection_mode not in {"quick", "standard", "deep"}:
            raise ValueError("collection_mode must be quick, standard, or deep.")
        if self.schema_version != REQUIREMENT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported requirement schema {self.schema_version!r}; expected {REQUIREMENT_SCHEMA_VERSION!r}."
            )
        if not self.requirement_id:
            self.requirement_id = _stable_id("rq", self.identity_payload())

    def identity_payload(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "geographies": self.geographies,
            "timeframe": asdict(self.timeframe),
            "target_audiences": self.target_audiences,
            "languages": self.languages,
            "known_entities": self.known_entities,
            "excluded_topics": self.excluded_topics,
            "preferred_sources": self.preferred_sources,
            "collection_mode": self.collection_mode,
        }

    def export_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ResearchRequirement":
        data = dict(payload)
        timeframe = data.get("timeframe") or {}
        if not isinstance(timeframe, dict):
            raise ValueError("requirement timeframe must be a JSON object.")
        data["timeframe"] = ResearchTimeframe(**timeframe)
        return cls(**data)


@dataclass
class SearchPolicy:
    max_hops: int = 2
    max_branches: int = 64
    min_sample: int = 12
    min_relevance_rate: float = 0.15
    min_novelty_rate: float = 0.05
    max_duplicate_rate: float = 0.85

    def __post_init__(self) -> None:
        if not 0 <= self.max_hops <= 5:
            raise ValueError("max_hops must be between 0 and 5.")
        if not 1 <= self.max_branches <= 1000:
            raise ValueError("max_branches must be between 1 and 1000.")
        if self.min_sample < 1:
            raise ValueError("min_sample must be positive.")
        for name in ("min_relevance_rate", "min_novelty_rate", "max_duplicate_rate"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1.")


@dataclass
class BranchMetrics:
    retrieved: int = 0
    relevance_assessed: int = 0
    relevant: int = 0
    uncertain: int = 0
    unique: int = 0
    duplicates: int = 0
    new_concepts: int = 0
    distinct_sources: int = 0
    coverage_gain: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "retrieved", "relevance_assessed", "relevant", "uncertain", "unique", "duplicates", "new_concepts",
            "distinct_sources"
        ):
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} cannot be negative.")
            setattr(self, name, value)
        self.coverage_gain = float(self.coverage_gain)
        if not 0.0 <= self.coverage_gain <= 1.0:
            raise ValueError("coverage_gain must be between 0 and 1.")

    @property
    def relevance_rate(self) -> float:
        return self.relevant / self.relevance_assessed if self.relevance_assessed else 0.0

    @property
    def novelty_rate(self) -> float:
        return self.new_concepts / self.relevant if self.relevant else 0.0

    @property
    def duplicate_rate(self) -> float:
        denominator = self.unique + self.duplicates
        return self.duplicates / denominator if denominator else 0.0


@dataclass
class SearchBranch:
    query: str
    rationale: str
    origin: str = "generated"
    status: str = "planned"
    search_family: str = ""
    language: str = ""
    generator: str = ""
    parent_branch_id: str = ""
    parent_concept: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    hop_depth: int = 0
    branch_id: str = ""
    metrics: BranchMetrics = field(default_factory=BranchMetrics)

    def __post_init__(self) -> None:
        self.query = _clean(self.query)
        self.rationale = _clean(self.rationale)
        self.origin = _clean(self.origin).casefold()
        self.status = _clean(self.status).casefold()
        self.search_family = _clean(self.search_family).casefold()
        self.language = _clean(self.language)
        self.generator = _clean(self.generator)
        self.parent_branch_id = _clean(self.parent_branch_id)
        self.parent_concept = _clean(self.parent_concept)
        self.evidence_ids = _clean_list(self.evidence_ids)
        self.hop_depth = int(self.hop_depth)
        if not self.query:
            raise ValueError("Search branch query cannot be empty.")
        if not self.rationale:
            raise ValueError("Search branch rationale cannot be empty.")
        if self.origin not in BRANCH_ORIGINS:
            raise ValueError(f"Unsupported branch origin: {self.origin}")
        if self.status not in BRANCH_STATUSES:
            raise ValueError(f"Unsupported branch status: {self.status}")
        if self.hop_depth < 0:
            raise ValueError("hop_depth cannot be negative.")
        if not isinstance(self.metrics, BranchMetrics):
            self.metrics = BranchMetrics(**dict(self.metrics))
        if not self.branch_id:
            self.branch_id = _stable_id(
                "q",
                {"query": self.query.casefold(), "parent": self.parent_branch_id, "origin": self.origin},
                length=14,
            )


@dataclass
class BranchDecision:
    action: Literal["continue", "retire", "review"]
    reasons: list[str]


@dataclass
class SearchPlan:
    requirement_id: str
    branches: list[SearchBranch]
    policy: SearchPolicy = field(default_factory=SearchPolicy)
    created_at: str = field(default_factory=_utc_now)
    schema_version: str = SEARCH_PLAN_SCHEMA_VERSION
    events: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.requirement_id = _clean(self.requirement_id)
        if not self.requirement_id:
            raise ValueError("Search plan requires a requirement_id.")
        if not isinstance(self.policy, SearchPolicy):
            self.policy = SearchPolicy(**dict(self.policy))
        self.branches = [branch if isinstance(branch, SearchBranch) else SearchBranch(**branch) for branch in self.branches]
        if len(self.branches) > self.policy.max_branches:
            raise ValueError("Search plan exceeds max_branches policy.")
        ids = [branch.branch_id for branch in self.branches]
        if len(ids) != len(set(ids)):
            raise ValueError("Search plan contains duplicate branch IDs.")
        if self.schema_version != SEARCH_PLAN_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported search plan schema {self.schema_version!r}; expected {SEARCH_PLAN_SCHEMA_VERSION!r}."
            )

    def export_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SearchPlan":
        data = dict(payload)
        data["policy"] = SearchPolicy(**dict(data.get("policy") or {}))
        data["branches"] = [SearchBranch(**dict(branch)) for branch in data.get("branches") or []]
        return cls(**data)

    def branch(self, branch_id: str) -> SearchBranch:
        for branch in self.branches:
            if branch.branch_id == branch_id:
                return branch
        raise KeyError(branch_id)

    def add_event(self, event_type: str, **payload: Any) -> None:
        event = {"at": _utc_now(), "type": _clean(event_type)}
        event.update(payload)
        self.events.append(event)

    def set_status(self, branch_id: str, status: str, *, actor: str = "analyst", reason: str = "") -> None:
        normalized = _clean(status).casefold()
        if normalized not in BRANCH_STATUSES:
            raise ValueError(f"Unsupported branch status: {status}")
        branch = self.branch(branch_id)
        previous = branch.status
        branch.status = normalized
        self.add_event(
            "status_change",
            branch_id=branch_id,
            **{
                "from": previous,
                "to": normalized,
                "actor": _clean(actor) or "analyst",
                "reason": _clean(reason),
            },
        )

    def edit_branch(
        self,
        branch_id: str,
        *,
        query: str | None = None,
        rationale: str | None = None,
        actor: str = "analyst",
        reason: str = "",
    ) -> None:
        branch = self.branch(branch_id)
        changes: dict[str, dict[str, str]] = {}

        if query is not None:
            cleaned_query = _clean(query)
            if not cleaned_query:
                raise ValueError("Search branch query cannot be empty.")
            duplicate = next(
                (
                    item
                    for item in self.branches
                    if item.branch_id != branch.branch_id
                    and item.query.casefold() == cleaned_query.casefold()
                ),
                None,
            )
            if duplicate is not None:
                raise ValueError(
                    f"Search branch query duplicates existing branch {duplicate.branch_id}."
                )
            if cleaned_query != branch.query:
                changes["query"] = {"from": branch.query, "to": cleaned_query}
                branch.query = cleaned_query

        if rationale is not None:
            cleaned_rationale = _clean(rationale)
            if not cleaned_rationale:
                raise ValueError("Search branch rationale cannot be empty.")
            if cleaned_rationale != branch.rationale:
                changes["rationale"] = {
                    "from": branch.rationale,
                    "to": cleaned_rationale,
                }
                branch.rationale = cleaned_rationale

        if not changes:
            return
        self.add_event(
            "branch_edited",
            branch_id=branch.branch_id,
            actor=_clean(actor) or "analyst",
            reason=_clean(reason),
            changes=changes,
        )

    def add_discovered_branch(
        self,
        *,
        query: str,
        rationale: str,
        parent_branch_id: str,
        evidence_ids: Iterable[str],
        parent_concept: str = "",
        search_family: str = "",
        language: str = "",
        generator: str = "",
    ) -> SearchBranch:
        if len(self.branches) >= self.policy.max_branches:
            raise ValueError("Search plan branch budget is exhausted.")
        parent = self.branch(parent_branch_id)
        evidence = _clean_list(evidence_ids)
        if not evidence:
            raise ValueError("Discovered branches require at least one evidence ID.")
        depth = parent.hop_depth + 1
        if depth > self.policy.max_hops:
            raise ValueError(
                f"Discovered branch would exceed max_hops={self.policy.max_hops}; analyst approval/new root required."
            )
        branch = SearchBranch(
            query=query,
            rationale=rationale,
            origin="discovered",
            search_family=search_family,
            language=language,
            generator=generator,
            parent_branch_id=parent.branch_id,
            parent_concept=parent_concept,
            evidence_ids=evidence,
            hop_depth=depth,
        )
        if any(existing.branch_id == branch.branch_id or existing.query.casefold() == branch.query.casefold() for existing in self.branches):
            raise ValueError("Search branch duplicates an existing query.")
        self.branches.append(branch)
        self.add_event(
            "branch_added",
            branch_id=branch.branch_id,
            parent_branch_id=parent.branch_id,
            evidence_ids=evidence,
        )
        return branch


def policy_for_mode(mode: str) -> SearchPolicy:
    normalized = _clean(mode).casefold()
    if normalized == "quick":
        return SearchPolicy(max_hops=1, max_branches=24, min_sample=8)
    if normalized == "deep":
        return SearchPolicy(max_hops=3, max_branches=160, min_sample=15)
    return SearchPolicy(max_hops=2, max_branches=64, min_sample=12)


def build_initial_search_plan(requirement: ResearchRequirement) -> SearchPlan:
    policy = policy_for_mode(requirement.collection_mode)
    branches: list[SearchBranch] = []
    seen: set[str] = set()

    def add(query: str, rationale: str, concept: str = "") -> None:
        text = _clean(query)
        key = text.casefold()
        if not text or key in seen or len(branches) >= policy.max_branches:
            return
        seen.add(key)
        branches.append(SearchBranch(
            query=text,
            rationale=rationale,
            origin="requirement",
            search_family="entity" if concept and concept != requirement.question else "discovery",
            parent_concept=concept,
            hop_depth=0,
        ))

    for entity in requirement.known_entities:
        add(entity, "Known entity supplied by the research requirement.", entity)
        for geography in requirement.geographies:
            add(
                f"{entity} {geography}",
                "Known entity combined with an in-scope geography to improve local precision.",
                entity,
            )

    if not branches:
        for geography in requirement.geographies:
            add(
                f"{requirement.question} {geography}",
                "Fallback discovery seed from the analyst's question and geography; refine before high-volume collection.",
                requirement.question,
            )
    if not branches:
        add(
            requirement.question,
            "Fallback discovery seed from the analyst's question; refine before high-volume collection.",
            requirement.question,
        )
    return SearchPlan(requirement_id=requirement.requirement_id, branches=branches, policy=policy)


def evaluate_branch(metrics: BranchMetrics, policy: SearchPolicy) -> BranchDecision:
    if metrics.retrieved < policy.min_sample:
        return BranchDecision("continue", [f"Only {metrics.retrieved} items retrieved; below min_sample={policy.min_sample}."])
    if metrics.relevance_assessed < policy.min_sample:
        return BranchDecision(
            "continue",
            [
                f"Only {metrics.relevance_assessed} items have relevance assessments; "
                f"below min_sample={policy.min_sample}. Collection volume alone cannot retire a branch."
            ],
        )

    reasons: list[str] = []
    if metrics.duplicate_rate >= policy.max_duplicate_rate and metrics.coverage_gain <= 0.0:
        reasons.append(
            f"Duplicate rate {metrics.duplicate_rate:.2f} exceeds {policy.max_duplicate_rate:.2f} with no coverage gain."
        )
    if metrics.relevance_rate < policy.min_relevance_rate and metrics.novelty_rate < policy.min_novelty_rate:
        reasons.append(
            f"Relevance ({metrics.relevance_rate:.2f}) and novelty ({metrics.novelty_rate:.2f}) are both below policy floors."
        )
    if reasons:
        return BranchDecision("retire", reasons)
    if metrics.relevance_rate < policy.min_relevance_rate and metrics.coverage_gain > 0:
        return BranchDecision(
            "review",
            [f"Low relevance ({metrics.relevance_rate:.2f}) but positive coverage gain ({metrics.coverage_gain:.2f}); inspect before pivoting."],
        )
    return BranchDecision(
        "continue",
        [
            f"Branch remains above bounded continuation criteria (relevance={metrics.relevance_rate:.2f}, "
            f"novelty={metrics.novelty_rate:.2f}, duplicate={metrics.duplicate_rate:.2f})."
        ],
    )


def save_requirement(requirement: ResearchRequirement, path: str | Path) -> str:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(requirement.export_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return str(target)


def load_requirement(path: str | Path) -> ResearchRequirement:
    source = Path(path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Research requirement file must contain a JSON object.")
    return ResearchRequirement.from_dict(payload)


def save_search_plan(plan: SearchPlan, path: str | Path) -> str:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(plan.export_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return str(target)


def load_search_plan(path: str | Path) -> SearchPlan:
    source = Path(path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Search plan file must contain a JSON object.")
    return SearchPlan.from_dict(payload)
