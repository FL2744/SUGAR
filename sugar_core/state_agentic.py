from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .llm import LLMConfig, create_client
from .observations import ResearchObservation
from .state_intelligence import build_intelligence_packet
from .state_schema import StateAssessment
from .state_synthesis import (
    SYNTHESIS_VERSION,
    AgentTask,
    _call_integrator,
    _parallel_agents,
    _red_team,
    _role_question,
    _scope_label,
    render_synthesis_markdown,
)
from .state_tradecraft import build_tradecraft_audit
from .utils import JsonCache, MemoryCache, atomic_path, atomic_write_text, safe_artifact_stem, utc_iso

AGENTIC_ORCHESTRATION_VERSION = "1.4"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _referenced_ids(output: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for judgment in output.get("judgments") or []:
        refs.update(str(x) for x in judgment.get("supporting_refs") or [])
        refs.update(str(x) for x in judgment.get("contrary_refs") or [])
    for finding in output.get("findings") or []:
        refs.update(str(x) for x in finding.get("refs") or [])
    for alternative in output.get("alternatives") or []:
        refs.update(str(x) for x in alternative.get("supporting_refs") or [])
        refs.update(str(x) for x in alternative.get("contradicting_refs") or [])
    return {_clean(ref) for ref in refs if _clean(ref)}


def _case_index(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for case in packet.get("representative_cases") or []:
        observation_id = _clean(case.get("observation_id"))
        assessment_id = _clean(case.get("assessment_id"))
        if observation_id:
            result[observation_id] = case
        if assessment_id:
            result[assessment_id] = case
        for ref in case.get("source_refs") or []:
            if _clean(ref):
                result[_clean(ref)] = case
        for claim in case.get("high_consequence_claims") or []:
            claim_id = _clean(claim.get("claim_id"))
            if claim_id:
                result[claim_id] = case
            for ref in claim.get("evidence_refs") or []:
                if _clean(ref):
                    result[_clean(ref)] = case
    return result


def _evidence_neighborhood(packet: dict[str, Any], output: dict[str, Any], *, limit: int = 18) -> dict[str, Any] | None:
    index = _case_index(packet)
    selected: dict[str, dict[str, Any]] = {}
    for ref in _referenced_ids(output):
        case = index.get(ref)
        if not case:
            continue
        selected[case["observation_id"]] = case
        for comparable in case.get("comparables") or []:
            neighbor = index.get(_clean(comparable.get("observation_id")))
            if neighbor:
                selected[neighbor["observation_id"]] = neighbor
        if len(selected) >= limit:
            break
    if not selected:
        return None
    return {
        "scope": packet.get("scope"),
        "guardrails": packet.get("guardrails"),
        "corpus": packet.get("corpus"),
        "macro_structure": packet.get("macro_structure"),
        "comparative_diagnostics": packet.get("comparative_diagnostics"),
        "network_patterns": packet.get("network_patterns"),
        "collection_questions": packet.get("collection_questions"),
        "tradecraft_audit": packet.get("tradecraft_audit"),
        "representative_cases": list(selected.values())[:limit],
        "first_pass": output,
        "retrieval_note": "Cases were selected because the first-pass agent cited them or their deterministic comparable-case neighbors.",
    }


def _refine_agents(
    client,
    llm: LLMConfig,
    cache: JsonCache | None,
    base_packet: dict[str, Any],
    tasks: list[AgentTask],
    first_pass: list[dict[str, Any]],
    *,
    max_workers: int,
) -> list[dict[str, Any]]:
    by_name = {row.get("agent"): row for row in first_pass}
    refine_tasks: list[AgentTask] = []
    passthrough: dict[str, dict[str, Any]] = {}
    for task in tasks:
        first = by_name.get(task.name) or {}
        neighborhood = _evidence_neighborhood(task.packet if task.role == "country_analyst" else base_packet, first)
        if not neighborhood:
            passthrough[task.name] = first
            continue
        refine_tasks.append(
            AgentTask(
                name=f"{task.name}:refined",
                role=task.role,
                question=(
                    task.question
                    + " Reassess your first-pass conclusions against the retrieved evidence neighborhood. "
                    "Actively look for cases that weaken your original explanation, revise confidence when warranted, "
                    "and keep only judgments that survive the additional evidence."
                ),
                packet=neighborhood,
            )
        )
    refined_outputs = _parallel_agents(client, llm, cache, refine_tasks, max_workers=max_workers)
    for refined in refined_outputs:
        base_name = str(refined.get("agent") or "").removesuffix(":refined")
        refined["agent"] = base_name
        refined["refined_from_first_pass"] = True
        passthrough[base_name] = refined
    return [passthrough.get(task.name, by_name.get(task.name, {})) for task in tasks]


def _roles(country: str, observation_id: str, depth: str) -> list[str]:
    if observation_id:
        return (
            ["case_analyst", "methodologist"]
            if depth == "quick"
            else ["case_analyst", "network_mechanism_analyst", "public_diplomacy_analyst", "methodologist"]
        )
    if country:
        return (
            ["system_pattern_analyst", "methodologist"]
            if depth == "quick"
            else [
                "system_pattern_analyst",
                "network_mechanism_analyst",
                "public_diplomacy_analyst",
                "trajectory_indicators_analyst",
                "methodologist",
            ]
        )
    return (
        ["system_pattern_analyst", "methodologist"]
        if depth == "quick"
        else [
            "system_pattern_analyst",
            "network_mechanism_analyst",
            "comparative_analyst",
            "public_diplomacy_analyst",
            "trajectory_indicators_analyst",
            "methodologist",
        ]
    )


def _scoped_rows(
    observations: list[ResearchObservation],
    assessments: list[StateAssessment],
    *,
    country: str = "",
    observation_id: str = "",
) -> tuple[list[ResearchObservation], list[StateAssessment]]:
    selected = observations
    if country:
        selected = [row for row in selected if row.country.casefold() == country.casefold()]
    if observation_id:
        selected = [row for row in selected if row.observation_id == observation_id]
    ids = {row.observation_id for row in selected}
    return selected, [row for row in assessments if row.observation_id in ids]


def _packet_with_tradecraft(
    observations: list[ResearchObservation],
    assessments: list[StateAssessment],
    *,
    country: str = "",
    observation_id: str = "",
    representative_case_limit: int = 500,
) -> dict[str, Any]:
    packet = build_intelligence_packet(
        observations,
        assessments,
        country=country,
        observation_id=observation_id,
        representative_case_limit=representative_case_limit,
    )
    scoped_observations, scoped_assessments = _scoped_rows(
        observations, assessments, country=country, observation_id=observation_id
    )
    packet["tradecraft_audit"] = build_tradecraft_audit(scoped_observations, scoped_assessments)
    return packet


def _integration_packet(
    base_packet: dict[str, Any],
    tasks: list[AgentTask],
    agent_outputs: list[dict[str, Any]],
    *,
    baseline_cases: int = 24,
    max_cases: int = 80,
) -> dict[str, Any]:
    """Build a bounded integration context containing baseline, cited cases, and hard tradecraft warnings."""
    selected: dict[str, dict[str, Any]] = {}
    for case in list(base_packet.get("representative_cases") or [])[:baseline_cases]:
        observation_id = _clean(case.get("observation_id"))
        if observation_id:
            selected[observation_id] = case

    indices = [_case_index(base_packet)]
    indices.extend(_case_index(task.packet) for task in tasks if task.packet is not base_packet)
    refs = set()
    for output in agent_outputs:
        refs.update(_referenced_ids(output))
    for ref in refs:
        for index in indices:
            case = index.get(ref)
            if case:
                observation_id = _clean(case.get("observation_id"))
                if observation_id:
                    selected[observation_id] = case
                break
        if len(selected) >= max_cases:
            break

    packet = dict(base_packet)
    packet["representative_cases"] = list(selected.values())[:max_cases]

    audit = base_packet.get("tradecraft_audit") or {}
    tensions = list(audit.get("high_severity_tensions") or [])
    questions = list(base_packet.get("collection_questions") or [])
    for tension in tensions[:20]:
        questions.append(
            {
                "question": f"Resolve high-severity analytic tension `{_clean(tension.get('type'))}`: {_clean(tension.get('explanation'))}",
                "priority": "high",
                "affected_observation_ids": [_clean(tension.get("observation_id"))]
                if _clean(tension.get("observation_id"))
                else [],
                "next_step": _clean(tension.get("next_step")),
            }
        )
    packet["collection_questions"] = questions

    guardrails = list(base_packet.get("guardrails") or [])
    if tensions:
        guardrails.append(
            f"The deterministic tradecraft audit found {len(tensions)} high-severity analytic tension(s). "
            "The final synthesis must either carry these limitations explicitly or explain how the cited evidence resolves them."
        )
    packet["guardrails"] = guardrails
    packet["integration_context"] = {
        "baseline_cases": min(baseline_cases, len(base_packet.get("representative_cases") or [])),
        "specialist_refs_considered": len(refs),
        "cases_in_integrator_context": len(packet["representative_cases"]),
        "high_severity_tensions_injected": len(tensions),
        "strategy": "high-priority baseline plus specialist-cited cases plus deterministic tradecraft tensions",
        "guardrail": "Cases absent from the bounded integration context cannot be cited by the final synthesis even if they exist elsewhere in the corpus.",
    }
    return packet


def run_iterative_agentic_synthesis(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    *,
    llm: LLMConfig,
    country: str = "",
    observation_id: str = "",
    depth: str = "standard",
    cache_dir: str | Path | None = None,
    max_workers: int = 4,
    max_country_agents: int = 6,
) -> dict[str, Any]:
    observations, assessments = list(observations), list(assessments)
    if depth not in {"quick", "standard", "deep"}:
        raise ValueError("depth must be quick, standard, or deep")

    # The large case index exists for specialist validation/retrieval. Agent prompts are trimmed by
    # state_synthesis._call_agent, and the final integrator receives a separately bounded context.
    base_packet = _packet_with_tradecraft(
        observations,
        assessments,
        country=country,
        observation_id=observation_id,
        representative_case_limit=500,
    )
    scope = _scope_label(country, observation_id)
    tasks = [
        AgentTask(name=role, role=role, question=_role_question(role, scope), packet=base_packet)
        for role in _roles(country, observation_id, depth)
    ]

    if depth == "deep" and not country and not observation_id:
        countries = [
            row["value"]
            for row in (base_packet.get("macro_structure") or {}).get("countries") or []
            if row.get("value") and row.get("value") != "Unspecified"
        ]
        for candidate in countries[:max_country_agents]:
            country_packet = _packet_with_tradecraft(
                observations, assessments, country=candidate, representative_case_limit=100
            )
            tasks.append(
                AgentTask(
                    name=f"country:{candidate}",
                    role="country_analyst",
                    question=_role_question("country_analyst", f"country assessment: {candidate}"),
                    packet=country_packet,
                )
            )

    client = create_client(llm)
    # Agent prompts include source-derived observations; keep cache process-local.
    cache = MemoryCache() if cache_dir else None
    first_pass = _parallel_agents(client, llm, cache, tasks, max_workers=max_workers)
    analysis_pass = first_pass
    if depth == "deep":
        analysis_pass = _refine_agents(client, llm, cache, base_packet, tasks, first_pass, max_workers=max_workers)

    integration_packet = _integration_packet(base_packet, tasks, analysis_pass)
    draft = _call_integrator(client, llm, cache, integration_packet, analysis_pass, stage="iterative-draft")
    critique = None
    final = draft
    if depth != "quick":
        critique = _red_team(client, llm, cache, integration_packet, draft)
        final = _call_integrator(
            client,
            llm,
            cache,
            integration_packet,
            analysis_pass,
            stage="iterative-revised",
            critique=critique,
        )

    audit = base_packet.get("tradecraft_audit") or {}
    return {
        "synthesis_version": SYNTHESIS_VERSION,
        "agentic_orchestration_version": AGENTIC_ORCHESTRATION_VERSION,
        "generated_at": utc_iso(),
        "scope": base_packet.get("scope"),
        "depth": depth,
        "llm": {"provider": llm.provider, "model": llm.model},
        "method": {
            "architecture": "deterministic full evidence index + tradecraft audit -> parallel specialists -> optional evidence-neighborhood refinement -> retrieved integration context -> integrator -> red team -> revised integrator",
            "specialist_prompt_window_is_bounded": True,
            "integrator_prompt_window_is_bounded": True,
            "deep_mode_iterative_retrieval": depth == "deep",
            "probability_confidence_separated": True,
            "source_adequacy_and_tensions_exposed_to_agents": True,
            "high_severity_tensions_forced_into_integration_context": True,
            "evidence_allowlist_enforced": True,
            "human_verification_mutated": False,
        },
        "packet_summary": {
            "corpus": base_packet.get("corpus"),
            "macro_structure": base_packet.get("macro_structure"),
            "comparative_diagnostics": base_packet.get("comparative_diagnostics"),
            "tradecraft": {
                "epistemic_debt": audit.get("epistemic_debt"),
                "high_severity_tensions": audit.get("high_severity_tensions"),
                "source_environment": audit.get("source_environment"),
            },
            "integration_context": integration_packet.get("integration_context"),
        },
        "first_pass_agents": first_pass,
        "agents": analysis_pass,
        "draft": draft,
        "red_team": critique,
        "final": final,
    }


def save_iterative_agentic_synthesis(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    output_directory: str | Path,
    *,
    llm: LLMConfig,
    country: str = "",
    observation_id: str = "",
    depth: str = "standard",
    cache_dir: str | Path | None = None,
    max_workers: int = 4,
    name: str = "analytic_intelligence",
) -> list[str]:
    out_dir = Path(output_directory).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_artifact_stem(name, "analytic_intelligence")
    payload = run_iterative_agentic_synthesis(
        observations,
        assessments,
        llm=llm,
        country=country,
        observation_id=observation_id,
        depth=depth,
        cache_dir=cache_dir,
        max_workers=max_workers,
    )
    json_path = out_dir / f"{stem}.synthesis.json"
    markdown_path = out_dir / f"{stem}.synthesis.md"
    agents_path = out_dir / f"{stem}.agents.jsonl"
    manifest_path = out_dir / f"{stem}.manifest.json"
    atomic_write_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    atomic_write_text(markdown_path, render_synthesis_markdown(payload))
    with atomic_path(agents_path) as temporary:
        with temporary.open("w", encoding="utf-8") as stream:
            for phase, key in (("first_pass", "first_pass_agents"), ("analysis_pass", "agents")):
                for agent in payload.get(key) or []:
                    stream.write(json.dumps({"phase": phase, **agent}, ensure_ascii=False, sort_keys=True) + "\n")
            if payload.get("red_team"):
                stream.write(
                    json.dumps({"phase": "red_team", **payload["red_team"]}, ensure_ascii=False, sort_keys=True) + "\n"
                )
    atomic_write_text(
        manifest_path,
        json.dumps(
            {
                "generated_at": payload.get("generated_at"),
                "synthesis_version": SYNTHESIS_VERSION,
                "agentic_orchestration_version": AGENTIC_ORCHESTRATION_VERSION,
                "scope": payload.get("scope"),
                "depth": depth,
                "provider": llm.provider,
                "model": llm.model,
                "outputs": [json_path.name, markdown_path.name, agents_path.name],
                "human_verification_mutated": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
    )
    return [str(json_path), str(markdown_path), str(agents_path), str(manifest_path)]
