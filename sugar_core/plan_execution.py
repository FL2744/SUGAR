from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .research_requirements import ResearchRequirement, SearchPlan
from .service import ProgressCallback, run_search
from .triage_io import load_post_records

RUNNABLE_BRANCH_STATUSES = {"planned", "approved", "active"}


@dataclass(frozen=True)
class PlanExecutionResult:
    outputs: list[str]
    executed_branch_ids: list[str]
    records: int
    coverage_status: str = "unrecorded"


def execute_search_plan(
    requirement: ResearchRequirement,
    plan: SearchPlan,
    *,
    config: dict[str, Any],
    secrets: dict[str, str] | None = None,
    progress: ProgressCallback | None = None,
) -> PlanExecutionResult:
    """Run current plan branches through the ordinary collector service.

    This deliberately reuses `run_search`: a plan is orchestration state, not a second
    collection engine. Collection updates only observable yield/source metrics. Relevance
    and novelty remain unassessed until a triage/review stage supplies that evidence.
    """
    if plan.requirement_id != requirement.requirement_id:
        raise ValueError("Search plan and research requirement IDs do not match.")

    branches = [branch for branch in plan.branches if branch.status in RUNNABLE_BRANCH_STATUSES]
    if not branches:
        raise ValueError("Search plan has no runnable branches.")

    sources = [str(value).strip().casefold() for value in (config.get("sources") or requirement.preferred_sources) if str(value).strip()]
    if not sources:
        raise ValueError("Plan execution requires at least one source.")

    for branch in branches:
        if branch.status != "active":
            plan.set_status(branch.branch_id, "active", actor="controller", reason="Collection run started.")

    effective = dict(config)
    effective.update({
        "sources": sources,
        "terms": [branch.query for branch in branches],
        "since": config.get("since") or requirement.timeframe.start or None,
        "until": config.get("until") or requirement.timeframe.end or None,
        "continue_on_source_error": bool(config.get("continue_on_source_error", True)),
        "translate_posts": bool(config.get("translate_posts", False)),
        "infer_locations": bool(config.get("infer_locations", False)),
        "subproject_id": str(config.get("subproject_id") or ""),
        "research_requirement_id": requirement.requirement_id,
        "plan_branch_ids": [branch.branch_id for branch in branches],
    })
    outputs = run_search(effective, secrets or {}, progress=progress)
    csv_path = next((Path(path) for path in outputs if Path(path).suffix.casefold() == ".csv"), None)
    if csv_path is None:
        raise RuntimeError("Plan collection completed without a canonical CSV output.")
    records = load_post_records(csv_path)
    coverage_path = next((Path(path) for path in outputs if path.endswith(".coverage.json")), None)
    coverage_status = "legacy_unrecorded"
    source_coverage: dict[str, Any] = {}
    if coverage_path is not None and coverage_path.is_file():
        raw_coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
        if isinstance(raw_coverage, dict):
            coverage_status = str(raw_coverage.get("overall_status") or "unrecorded")
            raw_sources = raw_coverage.get("sources") or {}
            if isinstance(raw_sources, dict):
                source_coverage = raw_sources
    usable_source = not source_coverage or any(
        isinstance(value, dict) and str(value.get("status") or "") in {"success", "zero_result", "partial"}
        for value in source_coverage.values()
    )

    for branch in branches:
        matching = [
            record
            for record in records
            if branch.query in (record.query_matches or ([record.query] if record.query else []))
        ]
        branch.metrics.retrieved = len(matching)
        branch.metrics.unique = len({record.record_key for record in matching})
        branch.metrics.distinct_sources = len({record.platform for record in matching if record.platform})
        if usable_source:
            plan.set_status(
                branch.branch_id,
                "completed",
                actor="controller",
                reason=f"Collection completed with {branch.metrics.unique} unique matching records.",
            )
        else:
            plan.set_status(
                branch.branch_id,
                "paused",
                actor="controller",
                reason="All requested collection surfaces failed or were unavailable; zero retrieved records are not treated as evidence of absence.",
            )

    plan.add_event(
        "collection_run",
        sources=sources,
        branch_ids=[branch.branch_id for branch in branches],
        record_count=len(records),
        outputs=[Path(path).name for path in outputs],
        coverage_status=coverage_status,
        source_coverage=source_coverage,
        relevance_assessed=False,
    )
    return PlanExecutionResult(
        outputs=outputs,
        executed_branch_ids=[branch.branch_id for branch in branches],
        records=len(records),
        coverage_status=coverage_status,
    )
