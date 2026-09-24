from __future__ import annotations

import json
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from sugar_core.analyst_capture import capture_saved_page
from sugar_core.calibration import run_calibration_suite
from sugar_core.media_artifacts import build_media_citation, ingest_media
from sugar_core.models import PostRecord
from sugar_core.observation_storage import load_observations, save_observations
from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.reference_registry import add_relationship, upsert_entity
from sugar_core.research_intelligence import build_temporal_evidence_graph
from sugar_core.semantic_search import (
    build_semantic_index,
    load_semantic_index,
    save_semantic_index,
    search_lexical,
    search_semantic_index,
)
from sugar_core.state_intel_cli import main as state_intel_cli_main
from sugar_core.workspace import SugarWorkspace
from sugar_core.desktop_ops import run_desktop_analytic_operation
from sugar_core import desktop_ops


class _FakeEmbeddings:
    def create(self, *, model: str, input: list[str]):
        data = []
        for text in input:
            folded = text.casefold()
            vector = [1.0, 0.0] if any(term in folded for term in ("student", "students", "студент")) else [0.0, 1.0]
            data.append(SimpleNamespace(embedding=vector))
        return SimpleNamespace(data=data)


class _FakeClient:
    embeddings = _FakeEmbeddings()


def test_semantic_search_supports_local_retrieval_and_cross_lingual_index(tmp_path: Path) -> None:
    records = [
        PostRecord(platform="website", native_id="en", canonical_url="https://example.org/en", query="", original_text="University scholarships for students", detected_language="en"),
        PostRecord(platform="website", native_id="ru", canonical_url="https://example.org/ru", query="", original_text="Стипендии для студентов университета", detected_language="ru"),
        PostRecord(platform="news", native_id="other", canonical_url="https://example.org/sport", query="", original_text="A football match", detected_language="en"),
    ]
    lexical = search_lexical(records, "university students")
    assert lexical["retrieval_mode"] == "local_lexical"
    assert lexical["results"][0]["record_key"] == "website:en"

    index = build_semantic_index(records, _FakeClient(), model="fixture-multilingual")
    index_file = Path(save_semantic_index(index, tmp_path / "index.json.gz"))
    restored = load_semantic_index(index_file)
    result = search_semantic_index(restored, "students receiving education funding", _FakeClient(), model="fixture-multilingual")
    assert result["retrieval_mode"] == "cross_lingual_embedding"
    assert {row["record_key"] for row in result["results"][:2]} == {"website:en", "website:ru"}
    assert "not evidence" in restored["disclaimer"]


def test_media_ingest_keeps_hash_derivatives_and_timestamped_citation(tmp_path: Path) -> None:
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"fixture media bytes")
    transcript = tmp_path / "clip.vtt"
    transcript.write_text("WEBVTT\n\n00:01:13.000 --> 00:01:22.500\nA speaker describes the program.\n", encoding="utf-8")
    workspace = SugarWorkspace.create(tmp_path / "project", name="Media")

    result = ingest_media(media, workspace.root, source_url="https://video.example/item", parent_record_id="rec-1", language="en", transcript_file=transcript)
    manifest_path = workspace.root / "media" / f"{result['artifact_id']}.json"
    assert result["sha256"]
    assert result["derivatives"][0]["timestamped_cues"][0]["start_seconds"] == 73
    citation = build_media_citation(manifest_path, start="01:13", end="01:22.500", quote="A speaker describes the program.")
    assert citation["media_artifact_id"] == result["artifact_id"]
    assert citation["locator"]["end_seconds"] == 82.5
    assert len(workspace.list_artifacts("media_artifact")) == 1
    assert len(workspace.list_artifacts("media_derivative")) == 1


def test_capture_sanitizes_saved_page_and_registers_evidence(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Capture")
    html = tmp_path / "saved.html"
    html.write_text(
        """<html><head><title>Public Program</title><meta property='og:site_name' content='Example'>
        <script>stealCookie()</script></head><body><h1>Student scholarship</h1>
        <p>Applications open in Bishkek. access_token=verysecretvalue</p>
        <form><input type='password' value='hidden-secret'></form>
        <img src='/poster.png'><div hidden>hidden token should not appear</div>
        <a href='/detail?session_id=private&year=2026'>Details</a></body></html>""",
        encoding="utf-8",
    )

    result = capture_saved_page(html, source_url="https://analyst:urlpassword@example.org/page?access_token=urlsecret&view=public", workspace_path=workspace.root)
    captured = Path(result["snapshot_file"]).read_text(encoding="utf-8")
    assert "stealCookie" not in captured
    assert "hidden-secret" not in captured
    assert "verysecretvalue" not in captured
    assert "urlsecret" not in captured
    assert "urlpassword" not in captured
    assert result["source_url"] == "https://example.org/page?view=public"
    assert result["media_references"] == [{"tag": "img", "url": "https://example.org/poster.png"}]
    assert len(workspace.list_artifacts("analyst_capture")) == 1
    assert len(workspace.list_artifacts("evidence")) == 1


def test_fixed_research_calibration_suite_passes() -> None:
    report = run_calibration_suite()
    assert report["status"] == "pass"
    assert report["summary"] == {"passed": 6, "total": 6}


def test_manual_aliases_and_media_citations_remain_evidence_bound() -> None:
    observations = [
        ResearchObservation(
            observation_type="program", title="AUCA activity", summary="University program activity.",
            institution_name="AUCA", evidence=[EvidenceReference(url="https://example.org/one")],
        ),
        ResearchObservation(
            observation_type="program", title="University activity", summary="Related university program activity.",
            institution_name="American University of Central Asia",
            evidence=[EvidenceReference(url="https://example.org/two", media_artifact_id="media_abc", media_locator="t=01:13-01:22")],
        ),
    ]
    graph = build_temporal_evidence_graph(
        observations,
        entity_aliases={"American University of Central Asia": ["AUCA"]},
    )
    entities = [node for node in graph["nodes"] if node["node_type"] == "entity"]
    institution = next(node for node in entities if node["label"] == "American University of Central Asia")
    assert set(institution["observed_names"]) == {"AUCA", "American University of Central Asia"}
    media_event = next(node for node in graph["nodes"] if node.get("observation_id") == observations[1].observation_id)
    assert media_event["evidence_refs"] == ["https://example.org/two", "media:media_abc#t=01:13-01:22"]


def test_workspace_graph_includes_sourced_registry_relationships_and_lifecycle(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "temporal-project", name="Temporal Project")
    source = upsert_entity(
        workspace,
        {"entity_id": "center-a", "name": "Example Center", "entity_type": "institution",
         "aliases": ["EC"], "status": "active", "opened_date": "2020-03-14"},
        evidence_refs=[{"source_url": "https://example.org/center", "source_row": 2}],
        actor="Analyst One",
        review_state="human_verified",
    )
    target = upsert_entity(
        workspace,
        {"entity_id": "program-b", "name": "Example Advising Program", "entity_type": "program"},
        evidence_refs=["https://example.org/advising"],
        actor="Analyst One",
        review_state="human_verified",
    )
    relationship = add_relationship(
        workspace,
        source_entity_id=source["entity_id"],
        target_entity_id=target["entity_id"],
        relationship_type="partner_of",
        evidence_refs=[{"source_url": "https://example.org/partnership", "document_date": "2021-01-01"}],
        actor="Analyst One",
        review_state="human_verified",
        valid_from="2021-01-01",
        valid_to="2024-12-31",
        note="The source lists the two entities as program partners.",
    )
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        add_relationship(
            workspace,
            source_entity_id=source["entity_id"],
            target_entity_id=target["entity_id"],
            relationship_type="partner_of",
            evidence_refs=["https://example.org/invalid-date"],
            valid_from="2021-1-1",
        )
    with pytest.raises(ValueError, match="on or after"):
        add_relationship(
            workspace,
            source_entity_id=source["entity_id"],
            target_entity_id=target["entity_id"],
            relationship_type="partner_of",
            evidence_refs=["https://example.org/reversed-date"],
            valid_from="2024-01-01",
            valid_to="2023-12-31",
        )

    observation = ResearchObservation(
        observation_type="program",
        title="Example Center advising activity",
        summary="The center describes an advising program.",
        institution_name="EC",
        evidence=[EvidenceReference(url="https://example.org/activity", published_at="2023-04-01T09:00:00Z")],
        verification_state="human_verified",
        reviewer="Analyst One",
    )
    observations_path = workspace.path_for("observations") / "observations.csv"
    save_observations([observation], observations_path)
    workspace.register_artifact("observations", observations_path)

    outputs = run_desktop_analytic_operation("intel-evidence-graph", {"workspace": str(workspace.root)})
    graph = json.loads(Path(outputs[0]).read_text(encoding="utf-8"))
    registry_entities = [node for node in graph["nodes"] if node.get("registry_entity_ids")]
    center = next(node for node in registry_entities if "center-a" in node["registry_entity_ids"])
    assert observation.observation_id in center["observation_ids"]
    relation_edge = next(edge for edge in graph["edges"] if edge.get("relationship_id") == relationship["relationship_id"])
    assert relation_edge["predicate"] == "partner_of"
    assert (relation_edge["valid_from"], relation_edge["valid_to"]) == ("2021-01-01", "2024-12-31")
    assert relation_edge["review_state"] == "human_verified"
    assert relation_edge["evidence_refs"][0]["source_url"] == "https://example.org/partnership"
    lifecycle = next(node for node in graph["nodes"] if node["node_type"] == "lifecycle_event")
    assert lifecycle["valid_from"] == "2020-03-14"
    assert lifecycle["evidence_refs"][0]["source_url"] == "https://example.org/center"
    assert graph["registry_summary"] == {
        "entities_included": 2,
        "relationships_included": 1,
        "lifecycle_events_included": 1,
        "unresolved_relationships": 0,
        "unresolved_lifecycle_events": 0,
    }
    pipeline = workspace.latest_artifact("intelligence").metadata["pipeline"]
    tracked_inputs = {Path(item["path"]).name for item in pipeline["inputs"]}
    assert {"relationships.jsonl", "lifecycle.jsonl"} <= tracked_inputs

    cli_output = tmp_path / "cli-temporal-graph.json"
    assert state_intel_cli_main([
        "graph", str(observations_path), "--workspace", str(workspace.root), "--output", str(cli_output),
    ]) == 0
    cli_graph = json.loads(cli_output.read_text(encoding="utf-8"))
    assert cli_graph["registry_summary"] == graph["registry_summary"]
    assert any(edge.get("relationship_id") == relationship["relationship_id"] for edge in cli_graph["edges"])


def test_capture_media_and_timestamp_attachment_desktop_workflow(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Capture and Media")
    html_file = tmp_path / "page.html"
    html_file.write_text("<html><head><title>Activity</title></head><body><p>Public activity text.</p></body></html>", encoding="utf-8")
    page_outputs = run_desktop_analytic_operation(
        "intel-capture-page",
        {"workspace": str(workspace.root), "html_file": str(html_file), "source_url": "https://example.org/activity"},
    )
    media_file = tmp_path / "clip.wav"
    with wave.open(str(media_file), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * 5)
    transcript_file = tmp_path / "transcript.srt"
    transcript_file.write_text("1\n00:00:02,000 --> 00:00:04,000\nA program title is visible.\n", encoding="utf-8")
    media_outputs = run_desktop_analytic_operation(
        "intel-media-ingest",
        {"workspace": str(workspace.root), "media_file": str(media_file), "transcript": str(transcript_file), "source_url": "https://example.org/activity"},
    )
    captured_observations = ResearchObservation(
        observation_type="event", title="Captured activity", summary="Public activity text.",
        evidence=[EvidenceReference(url="https://example.org/activity")],
    )
    observations_file = workspace.path_for("observations") / "observations.csv"
    save_observations([captured_observations], observations_file)
    workspace.register_artifact("observations", observations_file)
    attached = run_desktop_analytic_operation(
        "intel-media-attach",
        {"workspace": str(workspace.root), "observation_id": captured_observations.observation_id, "media_start": "00:02", "media_end": "00:04", "quote": "A program title is visible."},
    )
    restored = load_observations(attached[0])[0]
    assert len(restored.evidence) == 2
    assert restored.evidence[1].media_artifact_id.startswith("media_")
    assert page_outputs and media_outputs and Path(page_outputs[-1]).is_file() and Path(media_outputs[1]).is_file()
    graph_output = run_desktop_analytic_operation("intel-evidence-graph", {"workspace": str(workspace.root)})[0]
    graph = json.loads(Path(graph_output).read_text(encoding="utf-8"))
    assert any(ref.startswith("media:media_") for node in graph["nodes"] for ref in node.get("evidence_refs", []))


def test_desktop_semantic_search_requires_explicit_remote_opt_in_and_reuses_index(tmp_path: Path, monkeypatch) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Search")
    records_file = workspace.path_for("raw") / "records.csv"
    from sugar_core.storage import save_records

    save_records([PostRecord(
        platform="website", native_id="one", canonical_url="https://example.org/item",
        query="", original_text="University scholarships for students", detected_language="en",
    )], records_file)
    workspace.register_artifact("evidence", records_file)
    local = run_desktop_analytic_operation(
        "intel-semantic-search", {"workspace": str(workspace.root), "query": "university students"}
    )[0]
    assert json.loads(Path(local).read_text(encoding="utf-8"))["retrieval_mode"] == "local_lexical"

    client = _FakeClient()
    monkeypatch.setattr(desktop_ops, "create_client", lambda config: client)
    config = {
        "workspace": str(workspace.root), "query": "students", "remote_embeddings": True,
        "llm": {"provider": "openai", "model": "text-embedding-3-small"},
    }
    outputs = run_desktop_analytic_operation("intel-semantic-search", config, {"llm_api_key": "fixture"})
    report = json.loads(Path(outputs[0]).read_text(encoding="utf-8"))
    assert report["retrieval_mode"] == "cross_lingual_embedding"
    assert workspace.list_artifacts("semantic_index")
    pipeline = workspace.list_artifacts("intelligence")[0].metadata["pipeline"]
    assert "query" not in pipeline["parameters"]
