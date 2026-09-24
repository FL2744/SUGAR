import json
from pathlib import Path

from sugar_core.models import PostRecord
from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.observation_storage import save_observations
from sugar_core.research_requirements import save_requirement, save_search_plan
from sugar_core.storage import save_records
from sugar_core.desktop_ops import run_desktop_analytic_operation
from sugar_core.state_intel_cli import main as intel_main
from sugar_core.state_workflow import save_state_assessments
from sugar_core.research_intelligence import (
    apply_next_evidence_recommendation,
    build_content_lineage,
    build_next_evidence_recommendation,
    build_robustness_report,
    build_temporal_evidence_graph,
)
from sugar_core.research_requirements import (
    BranchMetrics,
    ResearchRequirement,
    ResearchTimeframe,
    SearchBranch,
    SearchPlan,
)
from sugar_core.state_schema import StateAssessment
from sugar_core.workspace import SugarWorkspace


def test_next_evidence_ranks_hypothesis_collection_needs_with_visible_components():
    requirement = ResearchRequirement(
        question="What education programs reach students in Bishkek?",
        geographies=["Bishkek"],
        target_audiences=["students"],
        languages=["Russian"],
        timeframe=ResearchTimeframe("2025-01-01", "2026-12-31"),
    )
    plan = SearchPlan(
        requirement_id=requirement.requirement_id,
        branches=[
            SearchBranch(
                query="Russian student programs Bishkek",
                rationale="Covers the in-scope city, language, and audience.",
                status="planned",
                metrics=BranchMetrics(
                    retrieved=20,
                    relevance_assessed=10,
                    relevant=8,
                    unique=18,
                    duplicates=2,
                    new_concepts=5,
                    distinct_sources=3,
                ),
            )
        ],
    )
    hypotheses = {
        "hypotheses": [
            {
                "hypothesis_id": "h_local",
                "hypothesis": "Programs are adapted locally.",
                "collection_needed": ["Find local university announcements for the 2025-2026 academic year."],
                "discriminators": ["local university announcements"],
            },
            {
                "hypothesis_id": "h_central",
                "hypothesis": "Programs follow shared central guidance.",
                "collection_needed": ["Find public program guidance from central institutions."],
            },
        ]
    }

    result = build_next_evidence_recommendation(requirement, plan, hypotheses=hypotheses)

    assert result["recommended_next_collection"]["origin"] == "search_plan"
    assert result["recommended_next_collection"]["matched_open_scope"] == [
        {"dimension": "geography", "value": "Bishkek"},
        {"dimension": "audience", "value": "students"},
        {"dimension": "language", "value": "Russian"},
    ]
    assert result["recommended_next_collection"]["components"]["observed_relevance"] == 0.8
    assert result["recommended_next_collection"]["components"]["observed_duplicate_avoidance"] == 0.9
    assert result["recommended_next_collection"]["estimated_cost"] == {"queries": 1, "records_max": 300}
    assert "No collection is started" in " ".join(result["score_method"]["guardrails"])
    assert any(item["origin"] == "hypothesis_collection_need" for item in result["recommendations"])


def test_next_evidence_apply_adds_hypothesis_query_paused_for_human_review():
    requirement = ResearchRequirement(question="Assess public scholarship programs.")
    plan = SearchPlan(requirement_id=requirement.requirement_id, branches=[])
    hypotheses = {
        "hypotheses": [{
            "hypothesis_id": "h_local",
            "hypothesis": "Local adaptation drives program variation.",
            "collection_needed": ["Search local university scholarship announcements."],
        }]
    }
    report = build_next_evidence_recommendation(requirement, plan, hypotheses=hypotheses)

    branch_id = apply_next_evidence_recommendation(plan, report)

    branch = plan.branch(branch_id)
    assert branch.status == "paused"
    assert branch.origin == "generated"
    assert branch.search_family == "hypothesis_discriminator"
    assert branch.parent_concept == "h_local"
    assert plan.events[-1]["type"] == "next_evidence_recommendation"
    assert plan.events[-1]["analyst_approval_required"] is True


def test_next_evidence_uses_comparable_completed_branch_history_and_explains_rank():
    requirement = ResearchRequirement(
        question="Find Russian scholarships for students in Bishkek.",
        geographies=["Bishkek"],
        target_audiences=["students"],
        languages=["Russian"],
    )
    plan = SearchPlan(
        requirement_id=requirement.requirement_id,
        branches=[
            SearchBranch(
                query="Russian university scholarship Bishkek students",
                rationale="Targets the remaining local gap.",
                search_family="local_programs",
                language="Russian",
                status="planned",
            ),
            SearchBranch(
                query="Completed local program search in Russian",
                rationale="Completed comparison branch.",
                search_family="local_programs",
                language="Russian",
                status="completed",
                metrics=BranchMetrics(
                    retrieved=10,
                    relevance_assessed=4,
                    relevant=3,
                    unique=8,
                    duplicates=2,
                    new_concepts=2,
                    distinct_sources=2,
                ),
            ),
            SearchBranch(
                query="Completed zero-result local program search in Russian",
                rationale="A successful zero-result attempt remains part of yield history.",
                search_family="local_programs",
                language="Russian",
                status="completed",
                metrics=BranchMetrics(retrieved=0),
            ),
            SearchBranch(
                query="Completed unrelated English search",
                rationale="Must not override the more specific cohort.",
                search_family="general_discovery",
                language="English",
                status="completed",
                metrics=BranchMetrics(
                    retrieved=100,
                    relevance_assessed=1,
                    relevant=0,
                    unique=100,
                    distinct_sources=4,
                ),
            ),
        ],
    )

    report = build_next_evidence_recommendation(requirement, plan)
    selected = next(
        item for item in report["recommendations"]
        if item["query"] == "Russian university scholarship Bishkek students"
    )

    assert selected["historical_outcomes"]["basis"] == "same_search_family_and_language"
    assert selected["historical_outcomes"]["completed_branch_count"] == 2
    assert selected["historical_outcomes"]["observed_retrieved_records"] == {
        "median": 5, "minimum": 0, "maximum": 10,
    }
    assert selected["historical_outcomes"]["planning_estimate"]["expected_retrieved_records"] == 5
    assert selected["historical_outcomes"]["planning_estimate"]["human_triage_relevance_rate"] == 0.7
    assert selected["component_evidence_basis"]["observed_relevance"] == (
        "historical_completed_branches:same_search_family_and_language"
    )
    assert any("geography=Bishkek" in reason for reason in selected["why_recommended"])
    assert "guarantee" in " ".join(selected["historical_outcomes"]["limits"])


def test_next_evidence_accepts_string_collection_need_as_one_proposal():
    requirement = ResearchRequirement(question="Assess scholarship announcements.")
    plan = SearchPlan(requirement_id=requirement.requirement_id, branches=[])
    report = build_next_evidence_recommendation(requirement, plan, hypotheses={
        "hypotheses": [{
            "hypothesis_id": "h_local",
            "hypothesis": "Local adaptation matters.",
            "collection_needed": "Search local university scholarship announcements.",
        }],
    })

    assert [item["query"] for item in report["recommendations"]] == [
        "Search local university scholarship announcements."
    ]


def test_next_evidence_does_not_treat_default_zero_quality_counters_as_measured():
    requirement = ResearchRequirement(question="Assess scholarship announcements.")
    plan = SearchPlan(requirement_id=requirement.requirement_id, branches=[SearchBranch(
        query="scholarship announcements",
        rationale="Existing bounded candidate.",
        status="planned",
        metrics=BranchMetrics(
            retrieved=20,
            relevance_assessed=10,
            relevant=5,
            unique=20,
            distinct_sources=1,
        ),
    )])

    selected = build_next_evidence_recommendation(requirement, plan)["recommended_next_collection"]

    assert selected["component_evidence_basis"]["observed_relevance"] == "candidate_branch_metrics"
    assert selected["component_evidence_basis"]["observed_novelty"] == "unmeasured"
    assert selected["component_evidence_basis"]["observed_duplicate_avoidance"] == "unmeasured"


def test_next_evidence_cli_saves_report_and_paused_plan_proposal(tmp_path: Path, capsys):
    requirement = ResearchRequirement(question="Assess local public scholarship programs.")
    requirement_path = Path(save_requirement(requirement, tmp_path / "requirement.json"))
    plan_path = Path(save_search_plan(
        SearchPlan(requirement_id=requirement.requirement_id, branches=[]),
        tmp_path / "plan.json",
    ))
    hypotheses_path = tmp_path / "hypotheses.json"
    hypotheses_path.write_text(json.dumps({
        "hypotheses": [{
            "hypothesis_id": "h_local",
            "hypothesis": "Universities locally adapt the programs.",
            "collection_needed": ["Search local university scholarship announcements."],
        }]
    }), encoding="utf-8")
    output = tmp_path / "recommendation.json"

    result = intel_main([
        "next-evidence", str(requirement_path), str(plan_path),
        "--hypotheses", str(hypotheses_path),
        "--output", str(output),
    ])

    assert result == 0
    assert json.loads(output.read_text(encoding="utf-8"))["recommended_next_collection"]["query"] == (
        "Search local university scholarship announcements."
    )
    saved_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert saved_plan["branches"][0]["status"] == "paused"
    assert saved_plan["events"][-1]["analyst_approval_required"] is True
    assert json.loads(capsys.readouterr().out)["proposed_branch_id"] == saved_plan["branches"][0]["branch_id"]


def test_content_lineage_surfaces_exact_and_near_duplicate_candidates():
    text = "The public university announced a new Russian language scholarship program for students."
    records = [
        PostRecord("weibo", "1", "https://news.example.org/a", "q", original_text=text),
        PostRecord("x", "2", "https://social.example.net/b", "q", original_text=text),
        PostRecord("blog", "3", "https://blog.example.net/c", "q", original_text=text + " Applications open today."),
        PostRecord("x", "4", "https://unrelated.example/a", "q", original_text="A local sports team won its weekend match."),
    ]

    result = build_content_lineage(records, similarity_threshold=0.75)

    assert result["candidate_pair_count"] >= 2
    assert {row["match_type"] for row in result["candidate_pairs"]} >= {
        "exact_normalized_text",
        "near_duplicate_candidate",
    }
    cluster = next(row for row in result["clusters"] if row["record_count"] == 3)
    assert len(cluster["distinct_hosts"]) == 3
    assert "do not establish independent information origins" in cluster["interpretation"]


def test_temporal_graph_keeps_entity_to_observation_provenance_without_direct_ties():
    observation = ResearchObservation(
        observation_type="partnership",
        title="University exchange announcement",
        summary="Two institutions announced an exchange.",
        observed_at="2026-08-14T10:00:00Z",
        institution_name="Example University",
        program_name="Student Exchange",
        actors=["Example Foundation"],
        evidence=[EvidenceReference(
            url="https://example.org/exchange",
            platform="website",
            published_at="2026-08-14T10:00:00Z",
        )],
        verification_state="human_verified",
        reviewer="Analyst",
    )
    assessment = StateAssessment(
        observation_id=observation.observation_id,
        partner_entities=["Partner Institute"],
        review_state="human_verified",
        reviewer="Analyst",
    )

    graph = build_temporal_evidence_graph([observation], [assessment])

    event = next(node for node in graph["nodes"] if node["node_type"] == "event")
    assert event["observed_at"] == "2026-08-14T10:00:00Z"
    assert event["evidence_refs"] == ["https://example.org/exchange"]
    assert {edge["role"] for edge in graph["edges"]} == {"institution", "program", "actor", "partner"}
    assert all(edge["target"] == event["node_id"] for edge in graph["edges"])
    assert all("valid-time interval" in edge["time_basis"] for edge in graph["edges"])


def test_registry_graph_keeps_duplicate_names_unmerged_and_invalid_dates_visible():
    observation = ResearchObservation(
        observation_type="program",
        title="Shared organization activity",
        summary="A record names an organization with a non-unique registry name.",
        institution_name="Shared Organization",
        evidence=[EvidenceReference(url="https://example.org/activity")],
    )
    graph = build_temporal_evidence_graph(
        [observation],
        registry_entities=[
            {"entity_id": "org-a", "name": "Shared Organization", "entity_type": "organization"},
            {"entity_id": "org-b", "name": "Shared Organization", "entity_type": "organization"},
            {"entity_id": "org-c", "name": "Partner Organization", "entity_type": "organization"},
        ],
        registry_relationships=[{
            "relationship_id": "rel-a-c",
            "source_entity_id": "org-a",
            "target_entity_id": "org-c",
            "relationship_type": "partner_of",
            "valid_from": "2024-99-01",
            "valid_to": "2023-01-01",
            "evidence_refs": [{"source_url": "https://example.org/relationship"}],
        }],
    )
    shared_registry_nodes = [
        node for node in graph["nodes"]
        if node.get("node_type") == "entity" and node.get("registry_entity_ids")
        and node.get("label") == "Shared Organization"
    ]
    assert len(shared_registry_nodes) == 2
    observed_shared = next(
        node for node in graph["nodes"]
        if node.get("node_type") == "entity" and observation.observation_id in node.get("observation_ids", [])
    )
    assert not observed_shared.get("registry_entity_ids")
    assert "shared organization" in graph["ambiguous_alias_keys_not_merged"]
    edge = next(item for item in graph["edges"] if item.get("relationship_id") == "rel-a-c")
    assert edge["valid_time_state"] == "invalid_source_dates"
    assert edge["valid_from"] == edge["valid_to"] == ""
    assert edge["valid_from_raw"] == "2024-99-01"


def test_robustness_is_verified_only_and_reports_leave_one_factor_out_changes():
    verified = ResearchObservation(
        observation_type="program",
        title="Verified program",
        summary="Public program description.",
        country="Country A",
        city="City A",
        actors=["Shared Institution"],
        evidence=[
            EvidenceReference(url="https://one.example.org/program", platform="weibo", language="zh"),
            EvidenceReference(url="https://two.example.net/program", platform="website", language="en"),
        ],
        verification_state="human_verified",
        reviewer="Analyst",
    )
    unreviewed = ResearchObservation(
        observation_type="program",
        title="Unreviewed program",
        summary="Not verified.",
        evidence=[EvidenceReference(url="https://unreviewed.example.org/program", platform="x")],
    )
    assessments = [
        StateAssessment(
            observation_id=verified.observation_id,
            program_domains=["higher_education"],
            review_state="human_verified",
            reviewer="Analyst",
        ),
        StateAssessment(observation_id=unreviewed.observation_id),
    ]

    report = build_robustness_report([verified, unreviewed], assessments)

    assert report["baseline"]["verified_observations"] == 1
    assert report["status"] == "ready"
    language_removal = next(
        item for item in report["leave_one_factor_out"]
        if item["removed_factor"] == {"type": "language", "value": "zh"}
    )
    assert language_removal["retained_observations"] == 1
    assert language_removal["sensitivity"] == "unchanged"
    actor_removal = next(
        item for item in report["leave_one_factor_out"]
        if item["removed_factor"] == {"type": "actor", "value": "shared institution"}
    )
    assert actor_removal["retained_observations"] == 0
    assert report["baseline"]["program_domains"] == 1


def test_desktop_intelligence_operations_run_from_registered_project_artifacts(tmp_path: Path):
    workspace = SugarWorkspace.create(tmp_path / "project", name="Research Project")
    requirement = ResearchRequirement(
        question="What programs serve students in Bishkek?",
        geographies=["Bishkek"],
        target_audiences=["students"],
    )
    requirement_path = workspace.path_for("state") / "research-requirement.json"
    save_requirement(requirement, requirement_path)
    plan = SearchPlan(
        requirement_id=requirement.requirement_id,
        branches=[SearchBranch(query="Bishkek student programs", rationale="Requirement seed.")],
    )
    plan_path = workspace.path_for("state") / "search-plan.json"
    save_search_plan(plan, plan_path)
    observation = ResearchObservation(
        observation_type="program",
        title="Student scholarship program",
        summary="Example University announced a scholarship for students.",
        observed_at="2026-08-12T10:00:00Z",
        country="Exampleland",
        city="Sample City",
        institution_name="Example University",
        program_name="Scholarship Program",
        evidence=[EvidenceReference(
            url="https://example.org/scholarship",
            platform="website",
            source_type="official_host_source",
            language="en",
        )],
        verification_state="human_verified",
        reviewer="Analyst",
    )
    observation_path = workspace.path_for("observations") / "observations.csv"
    save_observations([observation], observation_path)
    assessment_path = workspace.path_for("state") / "assessments.jsonl"
    save_state_assessments([
        StateAssessment(
            observation_id=observation.observation_id,
            program_domains=["higher_education"],
            review_state="human_verified",
            reviewer="Analyst",
        )
    ], assessment_path)
    records_path = workspace.path_for("raw") / "records.csv"
    save_records([
        PostRecord(
            platform="website",
            native_id="one",
            canonical_url="https://example.org/scholarship",
            query="Bishkek student programs",
            original_text="Example University announced a scholarship program for students.",
            detected_language="en",
        ),
        PostRecord(
            platform="news",
            native_id="two",
            canonical_url="https://news.example.net/scholarship",
            query="Bishkek student programs",
            original_text="Example University announced a scholarship program for students.",
            detected_language="en",
        ),
    ], records_path)
    workspace.register_artifact("research_requirement", requirement_path)
    workspace.register_artifact("search_plan", plan_path)
    workspace.register_artifact("observations", observation_path)
    workspace.register_artifact("state_assessments", assessment_path)
    workspace.register_artifact("evidence", records_path)

    outputs = []
    for operation in (
        "intel-next-evidence",
        "intel-content-lineage",
        "intel-evidence-graph",
        "intel-robustness",
    ):
        outputs.extend(run_desktop_analytic_operation(operation, {"workspace": str(workspace.root)}))

    assert all(Path(path).is_file() for path in outputs)
    recommendation = json.loads(Path(outputs[0]).read_text(encoding="utf-8"))
    assert recommendation["recommended_next_collection"]["query"] == "Bishkek student programs"
    updated_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert updated_plan["events"][-1]["type"] == "next_evidence_recommendation"
    lineage = json.loads(Path(outputs[1]).read_text(encoding="utf-8"))
    assert lineage["candidate_pair_count"] == 1
    graph = json.loads(Path(outputs[2]).read_text(encoding="utf-8"))
    assert len([node for node in graph["nodes"] if node["node_type"] == "event"]) == 1
    robustness = json.loads(Path(outputs[3]).read_text(encoding="utf-8"))
    assert robustness["baseline"]["verified_observations"] == 1
