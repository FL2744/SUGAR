from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from sugar_core import research_service
from sugar_core.models import PostRecord
from sugar_core.observations import observation_from_post
from sugar_core.observation_storage import save_observations
from sugar_core.storage import save_records
from sugar_core.source_conflicts import SourceClaim, SourceConflict, save_source_conflicts
from sugar_core.state_schema import AnalyticClaim, StateAssessment
from sugar_core.state_workflow import save_state_assessments
from sugar_core.workspace import SugarWorkspace


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
