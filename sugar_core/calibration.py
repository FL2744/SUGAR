from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import PostRecord
from .observations import EvidenceReference, ResearchObservation
from .research_intelligence import (
    apply_next_evidence_recommendation,
    build_content_lineage,
    build_next_evidence_recommendation,
    build_robustness_report,
    build_temporal_evidence_graph,
)
from .research_requirements import ResearchRequirement, SearchBranch, SearchPlan
from .state_schema import StateAssessment


def run_calibration_suite() -> dict[str, Any]:
    """Run fixed, offline gold cases for core research-intelligence behaviors."""
    duplicate_text = "The university announced a 2026 scholarship for local engineering students."
    records = [
        PostRecord(platform=platform, native_id=f"copy-{index}", canonical_url=f"https://{host}/item", query="scholarship", original_text=duplicate_text)
        for index, (platform, host) in enumerate((("news", "wire.example"), ("weibo", "social.example"), ("blog", "local.example")), start=1)
    ]
    records.append(PostRecord(
        platform="news", native_id="irrelevant", canonical_url="https://viral.example/item", query="scholarship",
        original_text="A popular unrelated sports event drew many viewers.", engagement={"views": 900000},
    ))
    lineage = build_content_lineage(records)
    expected_pairs = {
        frozenset(("news:copy-1", "weibo:copy-2")),
        frozenset(("news:copy-1", "blog:copy-3")),
        frozenset(("weibo:copy-2", "blog:copy-3")),
    }
    actual_pairs = {
        frozenset((edge["left_record_key"], edge["right_record_key"]))
        for edge in lineage["candidate_pairs"]
    }
    true_positives = len(expected_pairs & actual_pairs)
    duplicate_precision = true_positives / len(actual_pairs) if actual_pairs else 1.0
    duplicate_recall = true_positives / len(expected_pairs)

    observation = ResearchObservation(
        observation_type="program", title="Scholarship announcement", summary=duplicate_text,
        observed_at="2026-06-01T09:00:00Z", country="Exampleland", city="Sample City",
        institution_name="Example University", program_name="Engineering Scholarship",
        evidence=[EvidenceReference(url="https://university.example/scholarship", platform="website", language="en")],
        verification_state="human_verified", reviewer="Calibration gold set",
    )
    verified_assessment = StateAssessment(
        observation_id=observation.observation_id, program_domains=["higher_education"],
        review_state="human_verified", reviewer="Calibration gold set",
    )
    unreviewed = ResearchObservation(
        observation_type="program", title="Unreviewed", summary="This must not enter the robustness baseline.",
        evidence=[EvidenceReference(url="https://unreviewed.example/item", platform="website")],
    )
    unreviewed_assessment = StateAssessment(observation_id=unreviewed.observation_id)
    graph = build_temporal_evidence_graph([observation], [verified_assessment])
    graph_refs = {ref for node in graph["nodes"] for ref in node.get("evidence_refs", [])}
    citation_complete = all(ref in graph_refs for ref in (observation.evidence[0].url,))
    robustness = build_robustness_report([observation, unreviewed], [verified_assessment, unreviewed_assessment])

    requirement = ResearchRequirement(
        question="How do programs recruit university students in Exampleland?",
        geographies=["Exampleland"], target_audiences=["university students"],
        languages=["Russian"], known_entities=["Example University"],
    )
    plan = SearchPlan(
        requirement_id=requirement.requirement_id,
        branches=[SearchBranch(query="Scholarship announcement", rationale="Initial search.")],
    )
    hypotheses = {"hypotheses": [{
        "hypothesis_id": "h_local_recruitment",
        "hypothesis": "The program uses a local student recruitment mechanism.",
        "collection_needed": ["Search Russian-language Exampleland university student scholarships"],
        "discriminators": ["Find a Russian-language call for student applications in Exampleland."],
    }]}
    recommendation = build_next_evidence_recommendation(requirement, plan, hypotheses=hypotheses)
    selected = recommendation.get("recommended_next_collection") or {}
    branch_id = apply_next_evidence_recommendation(plan, recommendation)
    paused = next((branch.status == "paused" for branch in plan.branches if branch.branch_id == branch_id), False)

    checks = [
        {"case": "duplicate_candidate_precision", "passed": duplicate_precision == 1.0, "value": duplicate_precision},
        {"case": "duplicate_candidate_recall", "passed": duplicate_recall == 1.0, "value": duplicate_recall},
        {"case": "graph_citation_completeness", "passed": citation_complete, "value": citation_complete},
        {"case": "verified_only_robustness_baseline", "passed": robustness["baseline"]["verified_observations"] == 1, "value": robustness["baseline"]["verified_observations"]},
        {"case": "hypothesis_and_scope_collection_recommendation", "passed": "Exampleland" in selected.get("query", "") and bool(selected.get("hypothesis_ids")), "value": selected.get("query", "")},
        {"case": "analyst_approval_gate", "passed": paused, "value": "paused" if paused else "not_paused"},
    ]
    return {
        "suite": "sugar-research-calibration",
        "suite_version": "1.0",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "pass" if all(item["passed"] for item in checks) else "fail",
        "checks": checks,
        "summary": {"passed": sum(bool(item["passed"]) for item in checks), "total": len(checks)},
        "limits": [
            "These synthetic fixtures test deterministic software behavior; they do not establish field accuracy or analyst performance.",
            "This suite does not yet score live collector retrieval recall, unsupported claims in LLM synthesis, or real-world entity resolution.",
            "Duplicate-text candidates are not a source-independence ground truth beyond the explicit synthetic labels.",
        ],
    }
