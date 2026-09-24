from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from sugar_core import research_service
from sugar_core.models import PostRecord
from sugar_core.observations import observation_from_post
from sugar_core.observation_storage import save_observations
from sugar_core.observation_storage import load_observations
from sugar_core.storage import save_records
from sugar_core.source_conflicts import SourceClaim, SourceConflict, save_source_conflicts
from sugar_core.state_schema import AnalyticClaim, StateAssessment
from sugar_core.state_workflow import save_state_assessments
from sugar_core.state_workflow import load_state_assessments
from sugar_core.triage_io import load_post_records
from sugar_core.workspace import SugarWorkspace
from sugar_core.workspace_runtime import latest_workspace_artifact_path


def _workspace(tmp_path: Path) -> SugarWorkspace:
    return SugarWorkspace.create(tmp_path / "project", name="North Star")


def test_requirement_and_plan_use_workspace_defaults(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    requirement_outputs = research_service.create_research_requirement(
        {
            "workspace": str(workspace.root),
            "question": "Where are public cultural programs expanding?",
            "geographies": ["Central Asia"],
            "languages": ["en", "ru"],
            "known_entities": ["Example Center"],
            "preferred_sources": ["bilibili", "weibo"],
            "collection_mode": "quick",
        }
    )
    requirement = Path(requirement_outputs[0])
    assert requirement.is_file()
    assert requirement.parent == workspace.path_for("state")

    plan_outputs = research_service.create_research_plan(
        {"workspace": str(workspace.root), "requirement_file": str(requirement)}
    )
    plan = Path(plan_outputs[0])
    payload = json.loads(plan.read_text(encoding="utf-8"))
    assert plan.parent == workspace.path_for("state")
    assert payload["requirement_id"]
    assert payload["branches"]


def test_compiled_strategy_requires_analyst_approval_before_driving_plan(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    research_service.create_research_requirement(
        {
            "workspace": str(workspace.root),
            "question": "How are foreign educational institutions reaching university students in Exampleland?",
            "collection_mode": "standard",
        }
    )
    events: list[tuple[str, dict]] = []
    research_service.compile_research_strategy(
        {"workspace": str(workspace.root), "ai_expand": False},
        progress=lambda event, values: events.append((event, values)),
    )
    review = next(values for event, values in events if event == "strategy-review")
    assert review["review_state"] == "draft"
    assert any(
        item["kind"] == "subject"
        and item["origin"] == "explicit"
        and item["value"] == "foreign educational institutions"
        for item in review["concepts"]
    )
    assert any(
        item["kind"] == "target_audience"
        and item["value"] == "university students"
        for item in review["concepts"]
    )

    with pytest.raises(ValueError, match="Review and approve"):
        research_service.create_research_plan({"workspace": str(workspace.root)})

    research_service.update_research_strategy(
        {
            "workspace": str(workspace.root),
            "add_concepts": [
                {
                    "kind": "entity",
                    "value": "Public Engagement Center Exampleland",
                    "origin": "hypothesis",
                    "rationale": "Analyst wants this investigated, not asserted.",
                }
            ],
            "decision": "approved",
            "reviewer": "Analyst One",
            "review_note": "Question interpretation checked.",
        }
    )
    outputs = research_service.create_research_plan({"workspace": str(workspace.root)})
    plan = json.loads(Path(outputs[0]).read_text(encoding="utf-8"))
    queries = {item["query"] for item in plan["branches"]}
    assert "foreign educational institutions Exampleland" in queries
    assert "foreign educational institutions university students" in queries
    assert "Public Engagement Center Exampleland" in queries
    assert any(item["type"] == "compiled_strategy_plan" for item in plan["events"])
    strategy_artifact = workspace.latest_artifact("research_strategy")
    assert strategy_artifact is not None
    assert strategy_artifact.metadata["review_state"] == "approved"


def test_changed_requirement_invalidates_old_compiled_strategy(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    research_service.create_research_requirement(
        {
            "workspace": str(workspace.root),
            "question": "How are educational institutions reaching university students in Exampleland?",
        }
    )
    research_service.compile_research_strategy({"workspace": str(workspace.root)})
    research_service.update_research_strategy(
        {
            "workspace": str(workspace.root),
            "decision": "approved",
            "reviewer": "Analyst One",
        }
    )
    research_service.create_research_requirement(
        {
            "workspace": str(workspace.root),
            "question": "How are cultural institutions reaching high school students in Sampleland?",
        }
    )
    with pytest.raises(ValueError, match="different research requirement"):
        research_service.create_research_plan({"workspace": str(workspace.root)})


def test_plan_review_and_analyst_update_round_trip(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    research_service.create_research_requirement(
        {
            "workspace": str(workspace.root),
            "question": "How is the program reaching students?",
            "known_entities": ["Example Center"],
        }
    )
    research_service.create_research_plan({"workspace": str(workspace.root)})

    events: list[tuple[str, dict]] = []
    review_outputs = research_service.review_research_plan(
        {"workspace": str(workspace.root)},
        progress=lambda event, values: events.append((event, values)),
    )
    assert review_outputs[0].endswith("search-plan.json")
    review = next(values for event, values in events if event == "plan-review")
    assert review["branches"]
    branch = review["branches"][0]

    events.clear()
    research_service.update_research_plan_branch(
        {
            "workspace": str(workspace.root),
            "branch_id": branch["branch_id"],
            "query": "Example Center student advising",
            "rationale": "Analyst narrowed the seed to the target audience.",
            "status": "approved",
            "actor": "Analyst A",
            "reason": "Reviewed before collection.",
        },
        progress=lambda event, values: events.append((event, values)),
    )
    updated = next(values for event, values in events if event == "plan-branch-updated")
    assert updated["branch"]["status"] == "approved"
    assert updated["branch"]["query"] == "Example Center student advising"
    refreshed = next(values for event, values in events if event == "plan-review")
    assert refreshed["branches"][0]["status"] == "approved"

    plan = json.loads(Path(review_outputs[0]).read_text(encoding="utf-8"))
    assert plan["branches"][0]["query"] == "Example Center student advising"
    assert any(item["type"] == "branch_edited" for item in plan["events"])
    assert any(item["type"] == "status_change" for item in plan["events"])


def test_external_import_is_first_class_research_input(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    source = tmp_path / "partner.csv"
    pd.DataFrame(
        [
            {
                "platform": "partner",
                "native_id": "p-1",
                "canonical_url": "https://example.org/post/1",
                "original_text": "External source record",
            }
        ]
    ).to_csv(source, index=False)
    outputs = research_service.import_research_dataset(
        {"workspace": str(workspace.root), "source_file": str(source), "source_system": "partner-export"}
    )
    assert any(path.endswith(".csv") for path in outputs)
    assert any(path.endswith(".import.json") for path in outputs)
    imported = latest_workspace_artifact_path(workspace, "import")
    manifest = latest_workspace_artifact_path(workspace, "import_manifest")
    assert imported is not None and imported.suffix == ".jsonl"
    assert manifest is not None and manifest.name.endswith(".import.json")


def test_external_dataset_reaches_portable_handoff_without_collector_or_llm(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    research_service.create_research_requirement(
        {
            "workspace": str(workspace.root),
            "question": "What public program activity is documented?",
            "known_entities": ["Example Center"],
        }
    )
    research_service.create_research_plan({"workspace": str(workspace.root)})

    source = tmp_path / "partner.csv"
    pd.DataFrame(
        [
            {
                "platform": "partner",
                "native_id": "partner-1",
                "canonical_url": "https://example.org/partner/1",
                "original_text": "Example Center announced a public student program.",
                "usage_restrictions": "Research use only",
            }
        ]
    ).to_csv(source, index=False)

    def unexpected(*args, **kwargs):
        raise AssertionError("external-data handoff path must not invoke collection or LLM triage")

    monkeypatch.setattr(research_service, "execute_search_plan", unexpected)
    monkeypatch.setattr(research_service, "triage_dataset", unexpected)
    research_service.import_research_dataset(
        {
            "workspace": str(workspace.root),
            "source_file": str(source),
            "source_system": "partner-export",
        }
    )

    records_path = latest_workspace_artifact_path(workspace, "import")
    assert records_path is not None and records_path.suffix == ".jsonl"
    records = load_post_records(records_path)
    assert len(records) == 1
    observation = observation_from_post(records[0])
    observations_path = workspace.path_for("state") / "partner-observations.csv"
    save_observations([observation], observations_path)
    workspace.register_artifact("observations", observations_path, label="Partner observations")

    outputs = research_service.export_research_handoff(
        {"workspace": str(workspace.root), "name": "partner-handoff"}
    )
    bundle = next(Path(path) for path in outputs if Path(path).name == "partner-handoff")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["portability"]["requires_virginia_tech_infrastructure"] is False
    assert manifest["counts"]["records"] == 1
    assert manifest["counts"]["observations"] == 1
    verification = research_service.verify_research_handoff(
        {"bundle_directory": str(bundle)}
    )
    result = json.loads(Path(verification[0]).read_text(encoding="utf-8"))
    assert result["status"] == "pass"


def test_approved_compiled_strategy_is_preserved_in_portable_handoff(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    research_service.create_research_requirement(
        {
            "workspace": str(workspace.root),
            "question": "How are foreign educational institutions reaching university students in Exampleland?",
        }
    )
    research_service.compile_research_strategy({"workspace": str(workspace.root)})
    research_service.update_research_strategy(
        {
            "workspace": str(workspace.root),
            "decision": "approved",
            "reviewer": "Analyst One",
            "review_note": "Interpretation checked.",
        }
    )
    research_service.create_research_plan({"workspace": str(workspace.root)})
    record = PostRecord(
        platform="external",
        native_id="strategy-1",
        canonical_url="https://example.org/strategy/1",
        original_text="A public program announcement.",
        query="foreign educational institutions Exampleland",
    )
    records_path = workspace.path_for("raw") / "records.csv"
    save_records([record], records_path)
    workspace.register_artifact("evidence", records_path, label="Evidence")
    observation = observation_from_post(record)
    observations_path = workspace.path_for("state") / "observations.csv"
    save_observations([observation], observations_path)
    workspace.register_artifact("observations", observations_path, label="Observations")

    outputs = research_service.export_research_handoff(
        {"workspace": str(workspace.root), "name": "strategy-handoff"}
    )
    bundle = next(Path(path) for path in outputs if Path(path).name == "strategy-handoff")
    strategy_file = bundle / "context" / "research-strategy.json"
    assert strategy_file.is_file()
    strategy = json.loads(strategy_file.read_text(encoding="utf-8"))
    assert strategy["review_state"] == "approved"
    assert strategy["reviewer"] == "Analyst One"
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["strategy_id"] == strategy["strategy_id"]
    assert manifest["schemas"]["research_strategy"] == "1.0"
    assert any(
        artifact["role"] == "compiled_research_strategy"
        for artifact in manifest["artifacts"]
    )
    verification = research_service.verify_research_handoff(
        {"bundle_directory": str(bundle)}
    )
    result = json.loads(Path(verification[0]).read_text(encoding="utf-8"))
    assert result["status"] == "pass"


def test_manual_review_preparation_from_import_is_unreviewed_and_preserves_source(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    source = tmp_path / "partner.csv"
    source.write_text(
        "platform,native_id,canonical_url,original_text\n"
        "partner,1,https://example.org/1,Public program announcement\n",
        encoding="utf-8",
    )
    research_service.import_research_dataset({
        "workspace": str(workspace.root), "source_file": str(source), "source_system": "partner-export"
    })
    outputs = research_service.prepare_manual_review({"workspace": str(workspace.root)})
    observations_path = latest_workspace_artifact_path(workspace, "observations")
    assessments_path = latest_workspace_artifact_path(workspace, "state_assessments")
    assert observations_path is not None and observations_path.suffix == ".csv"
    assert assessments_path is not None and assessments_path.suffix == ".jsonl"
    assert len(outputs) == 4
    observation = load_observations(observations_path)[0]
    assessment = load_state_assessments(assessments_path)[0]
    assert observation.summary == "Public program announcement"
    assert observation.evidence[0].url == "https://example.org/1"
    assert observation.verification_state == "unreviewed"
    assert assessment.observation_id == observation.observation_id
    assert assessment.review_state == "unreviewed"
    with pytest.raises(ValueError, match="will not overwrite"):
        research_service.prepare_manual_review({"workspace": str(workspace.root)})


def test_feedback_and_handoff_can_resolve_workspace_artifacts(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    research_service.create_research_requirement(
        {
            "workspace": str(workspace.root),
            "question": "What activity is documented?",
            "known_entities": ["Example Center"],
        }
    )
    plan_path = Path(research_service.create_research_plan({"workspace": str(workspace.root)})[0])
    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    query = plan_payload["branches"][0]["query"]
    record = PostRecord(
        platform="external",
        native_id="1",
        canonical_url="https://example.org/1",
        original_text="Example Center hosted a public event.",
        query=query,
        query_matches=[query],
    )
    records_path = workspace.path_for("raw") / "records.csv"
    save_records([record], records_path)
    workspace.register_artifact("evidence", records_path, label="Evidence")
    observation = observation_from_post(record)
    observation.relevance = "relevant"
    observations_path = workspace.path_for("state") / "observations.csv"
    save_observations([observation], observations_path)
    workspace.register_artifact("observations", observations_path, label="Observations")
    claim = AnalyticClaim(
        statement="The source documents the public event.",
        evidence_refs=[record.canonical_url],
    )
    assessments_path = workspace.path_for("state") / "assessments.jsonl"
    save_state_assessments(
        [StateAssessment(observation_id=observation.observation_id, claims=[claim])],
        assessments_path,
    )
    workspace.register_artifact("state_assessments", assessments_path, label="Assessments")
    supported = SourceClaim(
        statement="The event was public.",
        source_url=record.canonical_url,
    )
    contrary = SourceClaim(
        statement="The event was restricted.",
        source_url="https://example.org/contrary",
    )
    conflicts_path = workspace.path_for("state") / "source-conflicts.json"
    save_source_conflicts(
        [SourceConflict(topic="Event access", claims=[supported, contrary])],
        conflicts_path,
    )
    workspace.register_artifact("source_conflicts", conflicts_path, label="Source conflicts")

    feedback_outputs = research_service.apply_research_feedback({"workspace": str(workspace.root)})
    assert any(path.endswith("plan-feedback.json") for path in feedback_outputs)

    handoff_outputs = research_service.export_research_handoff(
        {"workspace": str(workspace.root), "name": "handoff-test"}
    )
    bundle = next(Path(path) for path in handoff_outputs if Path(path).name == "handoff-test")
    assert (bundle / "manifest.json").is_file()
    lineage = json.loads((bundle / "evidence" / "lineage.json").read_text(encoding="utf-8"))
    finding = next(item for item in lineage["findings"] if item["finding_id"] == claim.claim_id)
    assert finding["contradicting_evidence_ids"] == [contrary.claim_id]
    assert (bundle / "review" / "source-conflicts.json").is_file()
    verification = research_service.verify_research_handoff({"bundle_directory": str(bundle)})
    result = json.loads(Path(verification[0]).read_text(encoding="utf-8"))
    assert result["status"] == "pass"


def test_collect_plan_reuses_existing_collection_engine(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    requirement_path = research_service.create_research_requirement(
        {
            "workspace": str(workspace.root),
            "question": "What activity is documented?",
            "known_entities": ["Example Center"],
            "preferred_sources": ["bilibili"],
        }
    )[0]
    plan_path = research_service.create_research_plan({"workspace": str(workspace.root)})[0]

    class Result:
        outputs = [str(tmp_path / "records.csv")]
        executed_branch_ids = ["q1"]
        records = 3
        coverage_status = "success"

    seen = {}

    def fake_execute(requirement, plan, *, config, secrets, progress=None):
        seen.update(requirement=requirement, plan=plan, config=config, secrets=secrets)
        return Result()

    monkeypatch.setattr(research_service, "execute_search_plan", fake_execute)
    outputs = research_service.collect_research_plan(
        {
            "workspace": str(workspace.root),
            "requirement_file": requirement_path,
            "plan_file": plan_path,
            "sources": ["bilibili"],
        }
    )
    assert seen["config"]["sources"] == ["bilibili"]
    assert outputs[-1].endswith("search-plan.json")


def test_research_triage_resolves_records_and_registers_observations(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    records_path = workspace.path_for("raw") / "records.csv"
    record = PostRecord(
        platform="external",
        native_id="triage-1",
        canonical_url="https://example.org/triage-1",
        original_text="Public program activity.",
        query="example",
    )
    save_records([record], records_path)
    workspace.register_artifact("evidence", records_path, label="Evidence")
    seen = {}

    def fake_triage(source_file, output_file, **kwargs):
        seen.update(source=Path(source_file), output=Path(output_file), kwargs=kwargs)
        target = Path(output_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("observation_id,summary\nobs-1,Activity\n", encoding="utf-8")
        target.with_suffix(".xlsx").write_bytes(b"xlsx")
        target.with_suffix(".metadata.json").write_text("{}", encoding="utf-8")
        return [str(target), str(target.with_suffix(".xlsx")), str(target.with_suffix(".metadata.json"))]

    monkeypatch.setattr(research_service, "triage_dataset", fake_triage)
    outputs = research_service.triage_research_records(
        {
            "workspace": str(workspace.root),
            "llm": {"provider": "arc", "model": "gpt-oss-120b"},
        },
        {"llm_api_key": "test-key"},
    )
    assert seen["source"] == records_path.resolve()
    assert seen["kwargs"]["llm"].provider == "arc"
    assert any(path.endswith("research-observations.csv") for path in outputs)
