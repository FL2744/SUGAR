from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sugar_core import handoff
from sugar_core.handoff import build_handoff_bundle, verify_handoff_bundle
from sugar_core.models import PostRecord
from sugar_core.observations import observation_from_post
from sugar_core.research_requirements import (
    ResearchRequirement,
    build_initial_search_plan,
    save_requirement,
    save_search_plan,
)
from sugar_core.requirement_compiler import (
    build_search_plan_from_strategy,
    compile_requirement_deterministically,
    save_research_strategy,
)
from sugar_core.storage import save_records
from sugar_core.state_workflow import blank_state_assessments, save_state_package
from sugar_core.source_conflicts import SourceClaim, SourceConflict, save_source_conflicts
from sugar_core.state_schema import AnalyticClaim, StateAssessment
from sugar_core.state_workflow import save_state_assessments


def test_bundle_publish_retries_a_transient_file_lock(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "staged"
    target = tmp_path / "published"
    source.mkdir()
    original = Path.replace
    attempts = 0

    def temporarily_locked(path, destination):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("Temporary indexer lock")
        return original(path, destination)

    monkeypatch.setattr(Path, "replace", temporarily_locked)
    handoff._publish_staged_path(source, target)
    assert attempts == 2
    assert target.is_dir()


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
    assert (root / "evidence" / "lineage.json").is_file()
    assert manifest["schemas"]["lineage"] == "1.0"
    verification = verify_handoff_bundle(root)
    assert verification["status"] == "pass"
    assert all(item["status"] == "ok" for item in verification["semantic_lineage"])

    limitations = json.loads((root / "limitations.json").read_text(encoding="utf-8"))
    assert limitations["source_coverage"]["example"]["status"] == "success"
    assert limitations["source_coverage"]["unobserved-source"]["status"] == "not_run"
    assert limitations["search_plan"]["branch_coverage"][0]["query"]
    assert any("not evidence of zero" in line for line in limitations["limitations"])


def test_handoff_semantically_verifies_compiled_strategy_linkage(tmp_path: Path):
    requirement = ResearchRequirement(
        question="How are foreign educational institutions reaching university students in Exampleland?"
    )
    strategy = compile_requirement_deterministically(requirement)
    strategy.approve(reviewer="Analyst One", note="Interpretation checked.")
    plan = build_search_plan_from_strategy(requirement, strategy)
    requirement_file = Path(save_requirement(requirement, tmp_path / "requirement.json"))
    strategy_file = Path(save_research_strategy(strategy, tmp_path / "strategy.json"))
    plan_file = Path(save_search_plan(plan, tmp_path / "plan.json"))
    record = PostRecord(
        platform="example",
        native_id="strategy-1",
        canonical_url="https://example.test/strategy-1",
        query=plan.branches[0].query,
        original_text="Public source evidence",
    )
    records_file = tmp_path / "records.csv"
    save_records([record], records_file)
    observation = observation_from_post(record)
    observations_file = tmp_path / "observations.jsonl"
    observations_file.write_text(
        json.dumps(observation.export_dict(), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    result = build_handoff_bundle(
        requirement_file,
        plan_file,
        records_file,
        observations_file,
        tmp_path / "handoffs",
        name="compiled-strategy",
        strategy_file=strategy_file,
        create_zip=False,
    )
    root = Path(result.directory)
    verification = verify_handoff_bundle(root)
    assert verification["status"] == "pass"
    assert verification["semantic_strategy"][0]["status"] == "ok"
    assert verification["semantic_strategy"][0]["strategy_id"] == strategy.strategy_id

    strategy_path = root / "context" / "research-strategy.json"
    tampered = json.loads(strategy_path.read_text(encoding="utf-8"))
    tampered["review_state"] = "draft"
    tampered["reviewer"] = ""
    strategy_path.write_text(
        json.dumps(tampered, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = next(
        item
        for item in manifest["artifacts"]
        if item["role"] == "compiled_research_strategy"
    )
    artifact["sha256"] = hashlib.sha256(strategy_path.read_bytes()).hexdigest()
    artifact["bytes"] = strategy_path.stat().st_size
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    verification = verify_handoff_bundle(root)
    assert verification["status"] == "fail"
    assert verification["semantic_strategy"][0]["status"] == "fail"
    assert "strategy_not_human_approved" in verification["semantic_strategy"][0]["issues"]


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


def test_handoff_verifier_rejects_semantically_broken_lineage_even_when_hash_is_updated(tmp_path: Path):
    requirement_file, plan_file, records_file, observations_file, _ = _inputs(tmp_path)
    from sugar_core.observation_storage import load_observations

    observation = load_observations(observations_file)[0]
    claim = AnalyticClaim(
        statement="The source documents the program.",
        evidence_refs=["https://example.test/1"],
    )
    assessments_file = Path(
        save_state_assessments(
            [StateAssessment(observation_id=observation.observation_id, claims=[claim])],
            tmp_path / "assessments.jsonl",
        )
    )
    result = build_handoff_bundle(
        requirement_file,
        plan_file,
        records_file,
        observations_file,
        tmp_path / "handoffs",
        name="case-semantic-lineage",
        assessments_file=assessments_file,
        create_zip=False,
    )
    root = Path(result.directory)
    lineage_path = root / "evidence" / "lineage.json"
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    lineage["findings"][0]["observation_id"] = "obs_missing"
    lineage_path.write_text(
        json.dumps(lineage, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = next(
        item for item in manifest["artifacts"] if item["role"] == "evidence_lineage"
    )
    artifact["sha256"] = hashlib.sha256(lineage_path.read_bytes()).hexdigest()
    artifact["bytes"] = lineage_path.stat().st_size
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    verified = verify_handoff_bundle(root)
    assert verified["status"] == "fail"
    semantic = verified["semantic_lineage"][0]
    assert semantic["status"] == "fail"
    codes = {item["code"] for item in semantic["issues"]}
    assert "finding_observation_missing" in codes
    assert "finding_assessment_observation_mismatch" in codes


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
    assert "evidence_lineage" in roles
    assert roles.count("analytic_output") == 2
    assert verify_handoff_bundle(result.directory)["status"] == "pass"


def test_handoff_lineage_preserves_support_and_exact_contradiction_links(tmp_path: Path):
    requirement_file, plan_file, records_file, observations_file, _ = _inputs(tmp_path)
    source_url = "https://example.test/1"
    contrary_url = "https://example.test/contrary"
    from sugar_core.observation_storage import load_observations

    observation = load_observations(observations_file)[0]
    claim = AnalyticClaim(
        statement="The documented service uses model A.",
        claim_type="descriptive_fact",
        evidence_refs=[source_url],
    )
    assessment = StateAssessment(observation_id=observation.observation_id, claims=[claim])
    assessments_file = Path(save_state_assessments([assessment], tmp_path / "assessments.jsonl"))
    supported = SourceClaim(statement="The service uses model A.", source_url=source_url)
    contrary = SourceClaim(statement="The service uses model B.", source_url=contrary_url)
    conflicts_file = Path(save_source_conflicts([
        SourceConflict(topic="Service model", claims=[supported, contrary])
    ], tmp_path / "source-conflicts.json"))

    result = build_handoff_bundle(
        requirement_file,
        plan_file,
        records_file,
        observations_file,
        tmp_path / "handoffs",
        name="lineage-conflict",
        assessments_file=assessments_file,
        source_conflicts_file=conflicts_file,
        create_zip=False,
    )
    root = Path(result.directory)
    lineage = json.loads((root / "evidence" / "lineage.json").read_text(encoding="utf-8"))
    finding = next(item for item in lineage["findings"] if item["finding_id"] == claim.claim_id)
    assert finding["supporting_evidence_ids"] == [source_url]
    assert finding["contradicting_evidence_ids"] == [contrary.claim_id]
    assert finding["supporting_evidence"][0]["source_record_keys"] == ["example:1"]
    manifest = json.loads(Path(result.manifest).read_text(encoding="utf-8"))
    roles = {artifact["role"] for artifact in manifest["artifacts"]}
    assert "source_conflicts" in roles
    assert "evidence_lineage" in roles
    verification = verify_handoff_bundle(root)
    assert verification["status"] == "pass"
    assert all(item["status"] == "ok" for item in verification["semantic_lineage"])


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
