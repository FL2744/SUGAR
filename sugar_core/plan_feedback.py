from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import PostRecord
from .observations import ResearchObservation
from .research_requirements import BranchDecision, SearchPlan, evaluate_branch
from .search_planner import EvidenceExcerpt


@dataclass(frozen=True)
class BranchFeedback:
    branch_id: str
    decision: BranchDecision
    matched_records: int
    matched_observations: int


def _record_matches_query(record: PostRecord, query: str) -> bool:
    matches = record.query_matches or ([record.query] if record.query else [])
    return query in matches


def apply_triage_feedback(
    plan: SearchPlan,
    records: Iterable[PostRecord],
    observations: Iterable[ResearchObservation],
) -> list[BranchFeedback]:
    records = list(records)
    observations = list(observations)
    feedback: list[BranchFeedback] = []

    for branch in plan.branches:
        matching_records = [record for record in records if _record_matches_query(record, branch.query)]
        record_keys = {record.record_key for record in matching_records if record.record_key}
        matching_observations = [
            observation
            for observation in observations
            if record_keys.intersection(observation.source_record_keys)
        ]

        relevant = sum(observation.relevance == "relevant" for observation in matching_observations)
        not_relevant = sum(observation.relevance == "not_relevant" for observation in matching_observations)
        uncertain = sum(observation.relevance == "uncertain" for observation in matching_observations)

        branch.metrics.retrieved = len(matching_records)
        branch.metrics.unique = len(record_keys)
        branch.metrics.distinct_sources = len({record.platform for record in matching_records if record.platform})
        branch.metrics.relevant = relevant
        branch.metrics.uncertain = uncertain
        # Only decisive relevant/not-relevant judgments enter the denominator. An uncertain
        # triage result must not become implicit negative evidence against a search branch.
        branch.metrics.relevance_assessed = relevant + not_relevant

        decision = evaluate_branch(branch.metrics, plan.policy)
        if decision.action == "retire" and branch.status != "retired":
            plan.set_status(
                branch.branch_id,
                "retired",
                actor="controller",
                reason="; ".join(decision.reasons),
            )
        elif decision.action == "review" and branch.status != "paused":
            plan.set_status(
                branch.branch_id,
                "paused",
                actor="controller",
                reason="; ".join(decision.reasons),
            )

        plan.add_event(
            "branch_evaluation",
            branch_id=branch.branch_id,
            decision=decision.action,
            reasons=decision.reasons,
            metrics={
                "retrieved": branch.metrics.retrieved,
                "relevance_assessed": branch.metrics.relevance_assessed,
                "relevant": branch.metrics.relevant,
                "uncertain": branch.metrics.uncertain,
                "relevance_rate": branch.metrics.relevance_rate,
                "new_concepts": branch.metrics.new_concepts,
                "novelty_rate": branch.metrics.novelty_rate,
                "duplicate_rate": branch.metrics.duplicate_rate,
                "coverage_gain": branch.metrics.coverage_gain,
            },
        )
        feedback.append(
            BranchFeedback(
                branch_id=branch.branch_id,
                decision=decision,
                matched_records=len(matching_records),
                matched_observations=len(matching_observations),
            )
        )

    return feedback


def evidence_excerpts_for_branch(
    plan: SearchPlan,
    branch_id: str,
    records: Iterable[PostRecord],
    observations: Iterable[ResearchObservation],
    *,
    max_excerpts: int = 24,
    max_chars: int = 1400,
) -> list[EvidenceExcerpt]:
    branch = plan.branch(branch_id)
    records = list(records)
    matching_records = [record for record in records if _record_matches_query(record, branch.query)]
    by_key = {record.record_key: record for record in matching_records if record.record_key}
    excerpts: list[EvidenceExcerpt] = []
    seen: set[str] = set()

    for observation in observations:
        if observation.relevance not in {"relevant", "uncertain"}:
            continue
        record = next((by_key[key] for key in observation.source_record_keys if key in by_key), None)
        if record is None or observation.observation_id in seen:
            continue
        text = (record.original_text or record.translated_text).strip()
        if not text:
            continue
        excerpts.append(
            EvidenceExcerpt(
                evidence_id=observation.observation_id,
                text=text[:max_chars],
                language=record.detected_language or record.platform_language,
            )
        )
        seen.add(observation.observation_id)
        if len(excerpts) >= max(1, int(max_excerpts)):
            break
    return excerpts
