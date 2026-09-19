from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .handoff import build_handoff_bundle, verify_handoff_bundle
from .importers import import_external_dataset
from .llm import ARC_BASE_URL, LLMConfig
from .observation_storage import load_observations
from .plan_execution import execute_search_plan
from .plan_feedback import apply_triage_feedback
from .research_requirements import (
    ResearchRequirement,
    SearchPlan,
    ResearchTimeframe,
    build_initial_search_plan,
    load_requirement,
    load_search_plan,
    save_requirement,
    save_search_plan,
)
from .requirement_compiler import (
    CompiledResearchStrategy,
    build_search_plan_from_strategy,
    compile_requirement_deterministically,
    enrich_strategy_with_llm,
    load_research_strategy,
    save_research_strategy,
)
from .search_planner import expand_initial_plan_with_llm
from .triage import DEFAULT_PROJECT_CONTEXT
from .triage_io import load_post_records, triage_dataset
from .workspace_runtime import (
    latest_workspace_artifact_path,
    optional_workspace,
    register_handoff_bundle,
    register_workspace_outputs,
)

ProgressCallback = Callable[[str, dict[str, Any]], None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _notify(progress: ProgressCallback | None, event: str, **values: Any) -> None:
    if progress is not None:
        progress(event, values)


def _branch_review_payload(branch) -> dict[str, Any]:
    return {
        "branch_id": branch.branch_id,
        "query": branch.query,
        "rationale": branch.rationale,
        "origin": branch.origin,
        "status": branch.status,
        "search_family": branch.search_family,
        "language": branch.language,
        "generator": branch.generator,
        "parent_branch_id": branch.parent_branch_id,
        "parent_concept": branch.parent_concept,
        "evidence_ids": list(branch.evidence_ids),
        "hop_depth": branch.hop_depth,
        "metrics": asdict(branch.metrics),
    }


def _plan_review_payload(plan: SearchPlan, plan_path: str | Path) -> dict[str, Any]:
    return {
        "plan_file": str(Path(plan_path).expanduser().resolve()),
        "requirement_id": plan.requirement_id,
        "policy": asdict(plan.policy),
        "event_count": len(plan.events),
        "branches": [_branch_review_payload(branch) for branch in plan.branches],
    }


def _notify_plan_review(
    progress: ProgressCallback | None,
    plan: SearchPlan,
    plan_path: str | Path,
) -> None:
    _notify(progress, "plan-review", **_plan_review_payload(plan, plan_path))


def _strategy_review_payload(
    strategy: CompiledResearchStrategy,
    strategy_path: str | Path,
) -> dict[str, Any]:
    return {
        "strategy_file": str(Path(strategy_path).expanduser().resolve()),
        "strategy_id": strategy.strategy_id,
        "requirement_id": strategy.requirement_id,
        "original_question": strategy.original_question,
        "analytic_task": strategy.analytic_task,
        "review_state": strategy.review_state,
        "reviewer": strategy.reviewer,
        "review_note": strategy.review_note,
        "reviewed_at": strategy.reviewed_at,
        "ai_provider": strategy.ai_provider,
        "ai_model": strategy.ai_model,
        "ai_workflow": strategy.ai_workflow,
        "concepts": [asdict(item) for item in strategy.concepts],
        "dimensions": [asdict(item) for item in strategy.dimensions],
        "missing_dimensions": [asdict(item) for item in strategy.missing_dimensions],
        "event_count": len(strategy.events),
    }


def _notify_strategy_review(
    progress: ProgressCallback | None,
    strategy: CompiledResearchStrategy,
    strategy_path: str | Path,
) -> None:
    _notify(progress, "strategy-review", **_strategy_review_payload(strategy, strategy_path))


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw: Iterable[Any] = value.replace("\r", "\n").split("\n") if "\n" in value or "\r" in value else value.split(",")
    elif isinstance(value, Iterable):
        raw = value
    else:
        raw = [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _path(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text).expanduser().resolve() if text else None


def _required_path(config: dict[str, Any], key: str, *, workspace, kinds: str | Iterable[str]) -> Path:
    explicit = _path(config.get(key))
    if explicit is not None:
        if not explicit.exists():
            raise FileNotFoundError(explicit)
        return explicit
    resolved = latest_workspace_artifact_path(workspace, kinds)
    if resolved is None:
        label = key.replace("_", " ")
        raise ValueError(f"No {label} was supplied and no matching workspace artifact is available.")
    return resolved


def _llm_config(config: dict[str, Any], secrets: dict[str, str]) -> LLMConfig:
    raw = config.get("llm") or {}
    provider = str(raw.get("provider") or "openai").strip().casefold()
    base_url = str(raw.get("base_url") or "").strip()
    if provider == "arc" and not base_url:
        base_url = ARC_BASE_URL
    if provider == "custom" and not base_url:
        raise ValueError("A base URL is required for a custom LLM endpoint.")
    return LLMConfig(
        provider=provider,
        model=str(raw.get("model") or "gpt-5.6-luna").strip(),
        api_key=str(secrets.get("llm_api_key") or "").strip(),
        base_url=base_url,
    )


def create_research_requirement(
    config: dict[str, Any],
    *,
    progress: ProgressCallback | None = None,
) -> list[str]:
    workspace = optional_workspace(config.get("workspace"))
    question = str(config.get("question") or "").strip()
    if not question:
        raise ValueError("Enter the research question you want SUGAR to answer.")
    target = _path(config.get("output_file")) or (
        workspace.path_for("state") / "research-requirement.json"
        if workspace is not None
        else (Path.cwd() / "research-requirement.json").resolve()
    )
    requirement = ResearchRequirement(
        question=question,
        geographies=_values(config.get("geographies")),
        timeframe=ResearchTimeframe(
            start=str(config.get("since") or "").strip(),
            end=str(config.get("until") or "").strip(),
        ),
        target_audiences=_values(config.get("target_audiences")),
        languages=_values(config.get("languages")) or ["auto"],
        known_entities=_values(config.get("known_entities")),
        excluded_topics=_values(config.get("excluded_topics")),
        preferred_sources=_values(config.get("preferred_sources")),
        collection_mode=str(config.get("collection_mode") or "standard").strip().casefold(),
        notes=str(config.get("notes") or "").strip(),
    )
    _notify(progress, "requirement-created", requirement_id=requirement.requirement_id)
    output = save_requirement(requirement, target)
    if workspace is not None:
        workspace.register_artifact(
            "research_requirement",
            output,
            label=requirement.question,
            metadata={"requirement_id": requirement.requirement_id, "schema_version": requirement.schema_version},
        )
    _notify(progress, "saved", outputs=[output])
    return [output]


def create_research_plan(
    config: dict[str, Any],
    secrets: dict[str, str] | None = None,
    *,
    progress: ProgressCallback | None = None,
) -> list[str]:
    secrets = secrets or {}
    workspace = optional_workspace(config.get("workspace"))
    requirement_path = _required_path(config, "requirement_file", workspace=workspace, kinds="research_requirement")
    requirement = load_requirement(requirement_path)
    target = _path(config.get("output_file")) or (
        workspace.path_for("state") / "search-plan.json"
        if workspace is not None
        else requirement_path.with_name("search-plan.json")
    )
    strategy_path = _path(config.get("strategy_file"))
    if strategy_path is None and workspace is not None:
        strategy_path = latest_workspace_artifact_path(workspace, "research_strategy")
    strategy: CompiledResearchStrategy | None = None
    if strategy_path is not None and strategy_path.is_file():
        strategy = load_research_strategy(strategy_path)
        if strategy.requirement_id != requirement.requirement_id:
            raise ValueError(
                "The compiled research strategy belongs to a different research requirement. Recompile the current question."
            )
        if not strategy.approved:
            raise ValueError(
                "Review and approve the compiled research strategy before building a search plan."
            )
        plan = build_search_plan_from_strategy(requirement, strategy)
    else:
        plan = build_initial_search_plan(requirement)
    _notify(progress, "plan-created", branches=len(plan.branches), requirement_id=requirement.requirement_id)
    if bool(config.get("ai_expand")):
        llm = _llm_config(config, secrets)
        cache_dir = workspace.path_for("cache") if workspace is not None else target.parent / ".sugar-cache"
        plan = expand_initial_plan_with_llm(
            requirement,
            plan,
            llm=llm,
            cache_dir=cache_dir,
            max_candidates=max(1, int(config.get("max_ai_queries") or 24)),
        )
        _notify(progress, "plan-expanded", branches=len(plan.branches), provider=llm.provider, model=llm.model)
    output = save_search_plan(plan, target)
    if workspace is not None:
        workspace.register_artifact(
            "search_plan",
            output,
            label=f"Search plan for {requirement.requirement_id}",
            metadata={
                "requirement_id": requirement.requirement_id,
                "schema_version": plan.schema_version,
                "branch_count": len(plan.branches),
                "strategy_id": strategy.strategy_id if strategy is not None else "",
            },
        )
    _notify_plan_review(progress, plan, output)
    _notify(progress, "saved", outputs=[output])
    return [output]


def compile_research_strategy(
    config: dict[str, Any],
    secrets: dict[str, str] | None = None,
    *,
    progress: ProgressCallback | None = None,
) -> list[str]:
    secrets = secrets or {}
    workspace = optional_workspace(config.get("workspace"))
    requirement_path = _required_path(
        config,
        "requirement_file",
        workspace=workspace,
        kinds="research_requirement",
    )
    requirement = load_requirement(requirement_path)
    target = _path(config.get("output_file")) or (
        workspace.path_for("state") / "research-strategy.json"
        if workspace is not None
        else requirement_path.with_name("research-strategy.json")
    )
    strategy = compile_requirement_deterministically(requirement)
    _notify(
        progress,
        "strategy-compiled",
        requirement_id=requirement.requirement_id,
        concepts=len(strategy.concepts),
        dimensions=len(strategy.dimensions),
        ai_used=False,
    )
    if bool(config.get("ai_expand")):
        llm = _llm_config(config, secrets)
        cache_dir = workspace.path_for("cache") if workspace is not None else target.parent / ".sugar-cache"
        strategy = enrich_strategy_with_llm(
            requirement,
            strategy,
            llm=llm,
            cache_dir=cache_dir,
        )
        _notify(
            progress,
            "strategy-expanded",
            concepts=len(strategy.concepts),
            dimensions=len(strategy.dimensions),
            provider=llm.provider,
            model=llm.model,
        )
    output = save_research_strategy(strategy, target)
    if workspace is not None:
        workspace.register_artifact(
            "research_strategy",
            output,
            label=f"Compiled strategy for {requirement.requirement_id}",
            metadata={
                "strategy_id": strategy.strategy_id,
                "requirement_id": requirement.requirement_id,
                "schema_version": strategy.schema_version,
                "review_state": strategy.review_state,
                "ai_provider": strategy.ai_provider,
                "ai_model": strategy.ai_model,
            },
        )
    _notify_strategy_review(progress, strategy, output)
    _notify(progress, "saved", outputs=[output])
    return [output]


def review_research_strategy(
    config: dict[str, Any],
    *,
    progress: ProgressCallback | None = None,
) -> list[str]:
    workspace = optional_workspace(config.get("workspace"))
    strategy_path = _required_path(
        config,
        "strategy_file",
        workspace=workspace,
        kinds="research_strategy",
    )
    strategy = load_research_strategy(strategy_path)
    _notify_strategy_review(progress, strategy, strategy_path)
    return [str(strategy_path)]


def update_research_strategy(
    config: dict[str, Any],
    *,
    progress: ProgressCallback | None = None,
) -> list[str]:
    workspace = optional_workspace(config.get("workspace"))
    strategy_path = _required_path(
        config,
        "strategy_file",
        workspace=workspace,
        kinds="research_strategy",
    )
    strategy = load_research_strategy(strategy_path)
    actor = str(config.get("actor") or config.get("reviewer") or "analyst").strip() or "analyst"

    updates = config.get("concept_updates") or []
    if not isinstance(updates, list):
        raise ValueError("concept_updates must be a list.")
    for raw in updates:
        if not isinstance(raw, dict):
            continue
        concept_id = str(raw.get("concept_id") or "").strip()
        if not concept_id:
            continue
        strategy.update_concept(
            concept_id,
            value=str(raw["value"]) if "value" in raw else None,
            included=bool(raw["included"]) if "included" in raw else None,
            rationale=str(raw["rationale"]) if "rationale" in raw else None,
            analyst_note=str(raw["analyst_note"]) if "analyst_note" in raw else None,
            actor=actor,
        )

    additions = config.get("add_concepts") or []
    if not isinstance(additions, list):
        raise ValueError("add_concepts must be a list.")
    for raw in additions:
        if not isinstance(raw, dict):
            continue
        strategy.add_analyst_concept(
            kind=str(raw.get("kind") or ""),
            value=str(raw.get("value") or ""),
            origin=str(raw.get("origin") or "interpreted"),
            rationale=str(raw.get("rationale") or ""),
            actor=actor,
        )

    dimension_updates = config.get("dimension_updates") or []
    if not isinstance(dimension_updates, list):
        raise ValueError("dimension_updates must be a list.")
    for raw in dimension_updates:
        if not isinstance(raw, dict):
            continue
        dimension_id = str(raw.get("dimension_id") or "").strip()
        if not dimension_id:
            continue
        strategy.update_dimension(
            dimension_id,
            question=str(raw["question"]) if "question" in raw else None,
            indicators=raw.get("indicators") if "indicators" in raw else None,
            source_families=raw.get("source_families") if "source_families" in raw else None,
            rationale=str(raw["rationale"]) if "rationale" in raw else None,
            included=bool(raw["included"]) if "included" in raw else None,
            analyst_note=str(raw["analyst_note"]) if "analyst_note" in raw else None,
            actor=actor,
        )

    analytic_task = str(config.get("analytic_task") or "").strip()
    if analytic_task:
        strategy.update_analytic_task(analytic_task, actor=actor)

    decision = str(config.get("decision") or "").strip().casefold()
    reviewer = str(config.get("reviewer") or "").strip()
    review_note = str(config.get("review_note") or "").strip()
    if decision == "approved":
        strategy.approve(reviewer=reviewer, note=review_note)
    elif decision == "rejected":
        if not reviewer:
            raise ValueError("Strategy rejection requires a named reviewer.")
        strategy.review_state = "rejected"
        strategy.reviewer = reviewer
        strategy.review_note = review_note
        strategy.reviewed_at = _utc_now()
        strategy.updated_at = strategy.reviewed_at
        strategy.events.append(
            {
                "type": "strategy_rejected",
                "at": strategy.reviewed_at,
                "actor": reviewer,
                "note": review_note,
            }
        )
    elif decision and decision != "draft":
        raise ValueError("strategy decision must be approved, rejected, or draft.")

    output = save_research_strategy(strategy, strategy_path)
    if workspace is not None:
        workspace.register_artifact(
            "research_strategy",
            output,
            label=f"Reviewed strategy for {strategy.requirement_id}",
            metadata={
                "strategy_id": strategy.strategy_id,
                "requirement_id": strategy.requirement_id,
                "review_state": strategy.review_state,
                "reviewer": strategy.reviewer,
            },
        )
    _notify(progress, "strategy-updated", review_state=strategy.review_state, reviewer=strategy.reviewer)
    _notify_strategy_review(progress, strategy, output)
    return [output]


def review_research_plan(
    config: dict[str, Any],
    *,
    progress: ProgressCallback | None = None,
) -> list[str]:
    workspace = optional_workspace(config.get("workspace"))
    plan_path = _required_path(
        config,
        "plan_file",
        workspace=workspace,
        kinds="search_plan",
    )
    plan = load_search_plan(plan_path)
    _notify_plan_review(progress, plan, plan_path)
    return [str(plan_path)]


def update_research_plan_branch(
    config: dict[str, Any],
    *,
    progress: ProgressCallback | None = None,
) -> list[str]:
    workspace = optional_workspace(config.get("workspace"))
    plan_path = _required_path(
        config,
        "plan_file",
        workspace=workspace,
        kinds="search_plan",
    )
    plan = load_search_plan(plan_path)
    branch_id = str(config.get("branch_id") or "").strip()
    if not branch_id:
        raise ValueError("Choose a search-plan branch to update.")
    branch = plan.branch(branch_id)
    actor = str(config.get("actor") or "analyst").strip() or "analyst"
    reason = str(config.get("reason") or "").strip()

    has_query = "query" in config and config.get("query") is not None
    has_rationale = "rationale" in config and config.get("rationale") is not None
    status = str(config.get("status") or "").strip().casefold()
    if not has_query and not has_rationale and not status:
        raise ValueError("No branch edit or status change was supplied.")

    if has_query or has_rationale:
        plan.edit_branch(
            branch_id,
            query=str(config.get("query") or "") if has_query else None,
            rationale=(
                str(config.get("rationale") or "")
                if has_rationale
                else None
            ),
            actor=actor,
            reason=reason,
        )
    if status:
        plan.set_status(
            branch_id,
            status,
            actor=actor,
            reason=reason,
        )

    saved_plan = save_search_plan(plan, plan_path)
    if workspace is not None:
        workspace.register_artifact(
            "search_plan",
            saved_plan,
            label=f"Analyst-reviewed search plan for {plan.requirement_id}",
            metadata={
                "requirement_id": plan.requirement_id,
                "branch_count": len(plan.branches),
                "event_count": len(plan.events),
            },
        )
    branch = plan.branch(branch_id)
    _notify(
        progress,
        "plan-branch-updated",
        branch=_branch_review_payload(branch),
        event_count=len(plan.events),
    )
    _notify_plan_review(progress, plan, saved_plan)
    return [str(Path(saved_plan).resolve())]


def import_research_dataset(
    config: dict[str, Any],
    *,
    progress: ProgressCallback | None = None,
) -> list[str]:
    workspace = optional_workspace(config.get("workspace"))
    source = _required_path(config, "source_file", workspace=None, kinds=())
    target = _path(config.get("output_file")) or (
        workspace.path_for("raw") / f"{source.stem}.import"
        if workspace is not None
        else source.with_name(source.stem + ".sugar-import")
    )
    field_map = config.get("field_map") or {}
    if not isinstance(field_map, dict):
        raise ValueError("field_map must be a JSON object mapping canonical fields to source columns.")
    _notify(progress, "importing", source_file=str(source))
    outputs = import_external_dataset(
        source,
        target,
        source_system=str(config.get("source_system") or "external"),
        platform=str(config.get("platform") or ""),
        field_map={str(key): str(value) for key, value in field_map.items()},
        strict=bool(config.get("strict")),
        preserve_unmapped_fields=not bool(config.get("drop_unmapped")),
    )
    register_workspace_outputs(workspace, outputs, operation="external-import")
    _notify(progress, "saved", outputs=outputs)
    return outputs


def collect_research_plan(
    config: dict[str, Any],
    secrets: dict[str, str] | None = None,
    *,
    progress: ProgressCallback | None = None,
) -> list[str]:
    secrets = secrets or {}
    workspace = optional_workspace(config.get("workspace"))
    requirement_path = _required_path(config, "requirement_file", workspace=workspace, kinds="research_requirement")
    plan_path = _required_path(config, "plan_file", workspace=workspace, kinds="search_plan")
    requirement = load_requirement(requirement_path)
    plan = load_search_plan(plan_path)
    sources = _values(config.get("sources")) or requirement.preferred_sources
    if not sources:
        raise ValueError("Choose at least one collection source or set preferred sources in the research requirement.")
    _notify(progress, "plan-collection-started", branches=sum(branch.status in {"planned", "approved"} for branch in plan.branches), sources=sources)
    result = execute_search_plan(
        requirement,
        plan,
        config={
            "sources": sources,
            "max_posts_per_query": max(1, int(config.get("max_posts_per_query") or 20)),
            "max_pages_per_query": max(1, int(config.get("max_pages_per_query") or 1)),
            "output_directory": config.get("output_directory"),
            "workspace": config.get("workspace"),
            "translate_posts": bool(config.get("translate_posts", False)),
            "infer_locations": bool(config.get("infer_locations", False)),
            "include_retweets": bool(config.get("include_retweets", False)),
            "x_search_mode": str(config.get("x_search_mode") or "recent"),
            "mastodon_url": str(config.get("mastodon_url") or "https://mastodon.social"),
            "continue_on_source_error": bool(config.get("continue_on_source_error", True)),
        },
        secrets=secrets,
        progress=progress,
    )
    saved_plan = save_search_plan(plan, plan_path)
    if workspace is not None:
        workspace.register_artifact(
            "search_plan",
            saved_plan,
            label=f"Executed search plan for {requirement.requirement_id}",
            metadata={
                "requirement_id": requirement.requirement_id,
                "executed_branches": len(result.executed_branch_ids),
                "records": result.records,
                "coverage_status": result.coverage_status,
            },
        )
    outputs = [*result.outputs, str(Path(saved_plan).resolve())]
    _notify_plan_review(progress, plan, saved_plan)
    _notify(progress, "plan-collection-complete", records=result.records, coverage_status=result.coverage_status, outputs=outputs)
    return outputs


def triage_research_records(
    config: dict[str, Any],
    secrets: dict[str, str] | None = None,
    *,
    progress: ProgressCallback | None = None,
) -> list[str]:
    secrets = secrets or {}
    workspace = optional_workspace(config.get("workspace"))
    records_path = _required_path(
        config,
        "records_file",
        workspace=workspace,
        kinds=("evidence", "raw_collection", "import"),
    )
    target = _path(config.get("output_file")) or (
        workspace.path_for("state") / "research-observations.csv"
        if workspace is not None
        else records_path.with_name(records_path.stem + ".observations.csv")
    )
    llm = _llm_config(config, secrets)
    cache_dir = workspace.path_for("cache") if workspace is not None else target.parent / ".sugar-cache"
    project_context = str(config.get("project_context") or DEFAULT_PROJECT_CONTEXT).strip()
    _notify(progress, "triage-started", source_file=str(records_path), provider=llm.provider, model=llm.model)
    outputs = triage_dataset(
        records_path,
        target,
        llm=llm,
        cache_dir=cache_dir,
        project_context=project_context,
        progress=progress,
        continue_on_error=bool(config.get("continue_on_error", True)),
    )
    register_workspace_outputs(workspace, outputs, operation="research-triage", kind="observations")
    _notify(progress, "triage-complete", outputs=outputs)
    return outputs


def apply_research_feedback(
    config: dict[str, Any],
    *,
    progress: ProgressCallback | None = None,
) -> list[str]:
    workspace = optional_workspace(config.get("workspace"))
    plan_path = _required_path(config, "plan_file", workspace=workspace, kinds="search_plan")
    records_path = _required_path(config, "records_file", workspace=workspace, kinds=("evidence", "raw_collection", "import"))
    observations_path = _required_path(config, "observations_file", workspace=workspace, kinds="observations")
    plan = load_search_plan(plan_path)
    feedback = apply_triage_feedback(plan, load_post_records(records_path), load_observations(observations_path))
    saved_plan = save_search_plan(plan, plan_path)
    summary = {
        "plan": str(Path(saved_plan).resolve()),
        "branches": [
            {
                "branch_id": item.branch_id,
                "decision": item.decision.action,
                "reasons": item.decision.reasons,
                "matched_records": item.matched_records,
                "matched_observations": item.matched_observations,
            }
            for item in feedback
        ],
    }
    summary_path = _path(config.get("output_file")) or (
        workspace.path_for("state") / "plan-feedback.json"
        if workspace is not None
        else plan_path.with_name("plan-feedback.json")
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if workspace is not None:
        workspace.register_artifact("search_plan", saved_plan, label="Search plan with analyst feedback")
        workspace.register_artifact("plan_feedback", summary_path, label="Search-plan feedback decisions")
    outputs = [str(Path(saved_plan).resolve()), str(summary_path.resolve())]
    _notify(progress, "feedback-applied", branches=len(feedback), outputs=outputs)
    _notify_plan_review(progress, plan, saved_plan)
    return outputs


def export_research_handoff(
    config: dict[str, Any],
    *,
    progress: ProgressCallback | None = None,
) -> list[str]:
    workspace = optional_workspace(config.get("workspace"))
    requirement_path = _required_path(config, "requirement_file", workspace=workspace, kinds="research_requirement")
    plan_path = _required_path(config, "plan_file", workspace=workspace, kinds="search_plan")
    strategy_path = _path(config.get("strategy_file"))
    if strategy_path is None:
        strategy_path = latest_workspace_artifact_path(workspace, "research_strategy")
    records_path = _required_path(config, "records_file", workspace=workspace, kinds=("evidence", "raw_collection", "import"))
    observations_path = _required_path(config, "observations_file", workspace=workspace, kinds="observations")
    output_directory = _path(config.get("output_directory")) or (
        workspace.path_for("exports") if workspace is not None else (Path.cwd() / "handoffs").resolve()
    )
    assessments = _path(config.get("assessments_file"))
    if assessments is None:
        assessments = latest_workspace_artifact_path(workspace, "state_assessments")
    source_conflicts = _path(config.get("source_conflicts_file"))
    if source_conflicts is None:
        source_conflicts = latest_workspace_artifact_path(workspace, "source_conflicts")
    limitations = _path(config.get("limitations_file"))
    analytic_outputs = [_path(value) for value in (config.get("analytic_outputs") or [])]
    provenance_files = [_path(value) for value in (config.get("provenance_files") or [])]
    _notify(progress, "handoff-started", output_directory=str(output_directory))
    result = build_handoff_bundle(
        requirement_path,
        plan_path,
        records_path,
        observations_path,
        output_directory,
        name=str(config.get("name") or "sugar-handoff"),
        strategy_file=strategy_path,
        assessments_file=assessments,
        source_conflicts_file=source_conflicts,
        limitations_file=limitations,
        analytic_outputs=[path for path in analytic_outputs if path is not None],
        provenance_files=[path for path in provenance_files if path is not None],
        create_zip=bool(config.get("create_zip", True)),
    )
    if workspace is not None:
        register_handoff_bundle(workspace, result.manifest, archive_file=result.archive)
    outputs = [result.directory, result.manifest]
    if result.archive:
        outputs.append(result.archive)
    _notify(progress, "handoff-complete", artifacts=result.artifacts, outputs=outputs)
    return outputs


def verify_research_handoff(
    config: dict[str, Any],
    *,
    progress: ProgressCallback | None = None,
) -> list[str]:
    bundle = _path(config.get("bundle_directory"))
    if bundle is None:
        raise ValueError("Choose a handoff bundle directory to verify.")
    result = verify_handoff_bundle(bundle)
    report = _path(config.get("output_file")) or (bundle / "verification.json")
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _notify(progress, "handoff-verified", status=result.get("status"), artifacts=result.get("artifacts"), outputs=[str(report)])
    return [str(report)]
