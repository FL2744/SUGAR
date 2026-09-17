from __future__ import annotations

import json
from pathlib import Path

from sugar_core.handoff import build_handoff_bundle, verify_handoff_bundle
from sugar_core.models import PostRecord
from sugar_core.observations import observation_from_post
from sugar_core.research_requirements import (
    ResearchRequirement,
    build_initial_search_plan,
    save_requirement,
    save_search_plan,
)
from sugar_core.storage import save_records
from sugar_core.state_workflow import blank_state_assessments, save_state_package


def _inputs(tmp_path: Path):
    requirement = ResearchRequirement(
        question="How are public programs reaching a target audience?",
        geographies=["Exampleland"],
        preferred_sources=["example", "unobserved-source"],
        known_entities=["Public Engagement Center A"],
    )
    plan = build_initial_search_plan(requirement)
    requirement_file = Path(save_requirement(requirement, tmp_path / "requirement.json"))
    plan_file = Path(save_search_plan(plan, tmp_path / "plan.json"))
    record = PostRecord(
        platform="example",
        native_id="1",
        canonical_url="https://example.test/1",
        query=plan.branches[0].query,
        query_matches=[plan.branches[0].query],
        original_text="Public source evidence",
        detected_language="en",
        published_at="2026-09-01T12:00:00Z",
    )
    records_file = tmp_path / "records.csv"
    save_records([record], records_file)
    observation = observation_from_post(record)
    observation.relevance = "relevant"
    observations_file = tmp_path / "observations.jsonl"
    observations_file.write_text(
        json.dumps(observation.export_dict(), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "brief.md"
    output.write_text("# Analytic output\n", encoding="utf-8")
    return requirement_file, plan_file, records_file, observations_file, output


def test_handoff_bundle_is_portable_self_describing_and_hash_verified(tmp_path: Path):
    requirement_file, plan_file, records_file, observations_file, output = _inputs(tmp_path)
    result = build_handoff_bundle(
        requirement_file,
        plan_file,
        records_file,
        observations_file,
        tmp_path / "handoffs",
        name="case-a",
        analytic_outputs=[output],
    )

    root = Path(result.directory)
    manifest = json.loads(Path(result.manifest).read_text(encoding="utf-8"))
    assert Path(result.archive or "").is_file()
    assert manifest["requirement_id"].startswith("rq_")
    assert manifest["portability"]["requires_virginia_tech_infrastructure"] is False
    assert manifest["counts"]["records"] == 1
    assert manifest["counts"]["observations"] == 1
    assert manifest["counts"]["analytic_outputs"] == 1
    assert (root / "evidence" / "records.jsonl").is_file()
    assert (root / "evidence" / "observations.jsonl").is_file()
    assert verify_handoff_bundle(root)["status"] == "pass"

    limitations = json.loads((root / "limitations.json").read_text(encoding="utf-8"))
    assert limitations["source_coverage"]["example"]["status"] == "success"
    assert limitations["source_coverage"]["unobserved-source"]["status"] == "not_run"
    assert limitations["search_plan"]["branch_coverage"][0]["query"]
    assert any("not evidence of zero" in line for line in limitations["limitations"])


def test_handoff_verifier_detects_tampering(tmp_path: Path):
    requirement_file, plan_file, records_file, observations_file, _ = _inputs(tmp_path)
    result = build_handoff_bundle(
        requirement_file,
        plan_file,
        records_file,
        observations_file,
        tmp_path / "handoffs",
        name="case-b",
        create_zip=False,
    )
    evidence = Path(result.directory) / "evidence" / "records.jsonl"
    evidence.write_text(evidence.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8")

    verified = verify_handoff_bundle(result.directory)
    assert verified["status"] == "fail"
    assert any(item["path"] == "evidence/records.jsonl" and item["status"] == "mismatch" for item in verified["findings"])


def test_handoff_verifier_rejects_manifest_path_escape(tmp_path: Path):
    requirement_file, plan_file, records_file, observations_file, _ = _inputs(tmp_path)
    result = build_handoff_bundle(
        requirement_file,
        plan_file,
        records_file,
        observations_file,
        tmp_path / "handoffs",
        name="case-path",
        create_zip=False,
    )
    manifest_path = Path(result.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["path"] = "../outside.txt"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    verified = verify_handoff_bundle(result.directory)
    assert verified["status"] == "fail"
    assert verified["findings"][0]["status"] == "invalid_path"


def test_existing_state_package_outputs_can_be_carried_without_reimplementation(tmp_path: Path):
    requirement_file, plan_file, records_file, observations_file, _ = _inputs(tmp_path)
    from sugar_core.observation_storage import load_observations

    observations = load_observations(observations_file)
    state_dir = tmp_path / "state-package"
    state_outputs = save_state_package(
        observations,
        blank_state_assessments(observations),
        state_dir,
        name="example_state",
    )
    assessments = next(path for path in state_outputs if path.endswith(".state.jsonl"))
    brief = next(path for path in state_outputs if path.endswith(".brief.md"))
    audit = next(path for path in state_outputs if path.endswith(".audit.json"))

    result = build_handoff_bundle(
        requirement_file,
        plan_file,
        records_file,
        observations_file,
        tmp_path / "handoffs",
        name="state-integrated",
        assessments_file=assessments,
        analytic_outputs=[brief, audit],
        create_zip=False,
    )
    manifest = json.loads(Path(result.manifest).read_text(encoding="utf-8"))
    roles = [artifact["role"] for artifact in manifest["artifacts"]]
    assert "human_review_state" in roles
    assert roles.count("analytic_output") == 2
    assert verify_handoff_bundle(result.directory)["status"] == "pass"


def test_handoff_uses_collection_coverage_to_distinguish_unavailable_from_zero(tmp_path: Path):
    requirement_file, plan_file, records_file, observations_file, _ = _inputs(tmp_path)
    coverage_file = records_file.with_suffix(".coverage.json")
    coverage_file.write_text(
        json.dumps({
            "schema_version": "1.0",
            "overall_status": "partial",
            "sources": {
                "example": {"source": "example", "status": "success", "records": 1, "attempted": True},
                "unobserved-source": {
                    "source": "unobserved-source",
                    "status": "unavailable",
                    "records": 0,
                    "attempted": True,
                    "reason": "authentication required",
                    "error_type": "AccessError",
                },
            },
        }),
        encoding="utf-8",
    )

    result = build_handoff_bundle(
        requirement_file,
        plan_file,
        records_file,
        observations_file,
        tmp_path / "handoffs",
        name="coverage-aware",
        create_zip=False,
    )
    root = Path(result.directory)
    limitations = json.loads((root / "limitations.json").read_text(encoding="utf-8"))
    source = limitations["source_coverage"]["unobserved-source"]
    assert source["status"] == "unavailable"
    assert source["reason"] == "authentication required"
    assert any("Unavailable collection surfaces" in line for line in limitations["limitations"])
    manifest = json.loads(Path(result.manifest).read_text(encoding="utf-8"))
    assert any(artifact["path"].endswith("records.coverage.json") for artifact in manifest["artifacts"])
