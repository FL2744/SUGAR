from __future__ import annotations

import json
from pathlib import Path

from sugar_core.models import PostRecord
from sugar_core.research_workspace import (
    ResearchWorkspaceManager,
    build_conversation_threads,
    import_project_bundle,
)
from sugar_core.storage import save_records
from sugar_core.workspace import SugarWorkspace


def _workspace(tmp_path: Path) -> ResearchWorkspaceManager:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Research Project")
    return ResearchWorkspaceManager(workspace)


def test_research_workspace_persists_subprojects_history_and_entities(tmp_path: Path) -> None:
    manager = _workspace(tmp_path)
    subproject = manager.add_subproject("Kyrgyzstan", description="Country track", tags=["Central Asia"])

    source = tmp_path / "institutions.csv"
    source.write_text(
        "name,country,city,latitude,longitude,status,closed_at,aliases,source_url\n"
        "Example Confucius Institute,Kyrgyzstan,Bishkek,42.8746,74.5698,closed,2022-06-01,Example CI,https://example.test/source\n",
        encoding="utf-8",
    )
    result = manager.import_institutions(source, subproject_id=subproject.subproject_id)
    manager.record_search(
        operation="search",
        terms=["Example Confucius Institute", "Example CI"],
        sources=["weibo", "bilibili"],
        result_count=7,
        subproject_id=subproject.subproject_id,
    )

    reopened = ResearchWorkspaceManager.open(manager.workspace.root)
    status = reopened.status()
    assert status["subprojects"] == 1
    assert status["entities"] == 1
    assert status["closed_entities"] == 1
    assert result["accepted"] == 1
    history = reopened.search_history("Example CI", subproject_id=subproject.subproject_id)
    assert len(history) == 1
    assert history[0]["result_count"] == 7


def test_reference_layers_are_copied_and_map_closed_institutions(tmp_path: Path) -> None:
    manager = _workspace(tmp_path)
    institutions = tmp_path / "institutions.csv"
    institutions.write_text(
        "canonical_name,country,city,lat,lon,status\n"
        "Closed Center,Exampleland,Capital,10,20,closed\n",
        encoding="utf-8",
    )
    manager.import_institutions(institutions)

    points = tmp_path / "american_spaces.csv"
    points.write_text(
        "name,latitude,longitude\nAmerican Space,10.1,20.2\n",
        encoding="utf-8",
    )
    layer = manager.add_reference_layer(points, name="American Spaces")
    layer_path = manager._resolve_layer_path(layer.__dict__)
    assert layer_path.is_file()
    assert manager.workspace.root in layer_path.parents

    outputs = manager.create_map()
    rendered = Path(outputs[0]).read_text(encoding="utf-8")
    metadata = json.loads(Path(outputs[1]).read_text(encoding="utf-8"))
    assert "Closed Center" in rendered
    assert "☠" in rendered
    assert metadata["mapped_institutions"] == 1
    assert metadata["mapped_reference_points"] == 1


def test_conversation_threads_keep_speakers_and_reply_depth(tmp_path: Path) -> None:
    first = PostRecord(
        platform="x",
        native_id="1",
        canonical_url="https://example.test/1",
        query="test",
        conversation_id="conv-1",
        author_handle="@alpha",
        author_name="Alpha",
        original_text="Opening message",
        published_at="2026-01-01T00:00:00Z",
    )
    second = PostRecord(
        platform="x",
        native_id="2",
        canonical_url="https://example.test/2",
        query="test",
        conversation_id="conv-1",
        parent_record_key=first.record_key,
        author_handle="@beta",
        author_name="Beta",
        original_text="Reply",
        published_at="2026-01-01T00:01:00Z",
    )
    threads = build_conversation_threads([second, first])
    assert len(threads) == 1
    assert threads[0]["speakers"] == ["Alpha (@alpha)", "Beta (@beta)"]
    assert threads[0]["turns"][0]["depth"] == 0
    assert threads[0]["turns"][1]["depth"] == 1

    manager = _workspace(tmp_path)
    dataset = tmp_path / "thread.csv"
    save_records([first, second], dataset)
    outputs = manager.build_conversation_view(dataset)
    html = Path(outputs[0]).read_text(encoding="utf-8")
    assert "Alpha (@alpha)" in html
    assert "Beta (@beta)" in html
    assert "Opening message" in html


def test_listening_post_resolves_entity_aliases_and_handles(tmp_path: Path) -> None:
    manager = _workspace(tmp_path)
    source = tmp_path / "institutions.csv"
    source.write_text(
        "name,country,city,status,aliases,social_handles\n"
        "Institution A,Exampleland,Capital,active,Institute A; IA,@institutionA\n",
        encoding="utf-8",
    )
    manager.import_institutions(source)
    entity_id = manager.state["entities"][0]["entity_id"]
    post = manager.add_listening_post(
        "Institution monitor",
        entity_ids=[entity_id],
        query_terms=["cultural program"],
        handles=["@extra"],
        sources=["bilibili", "weibo"],
        cadence="weekly",
    )
    terms = manager.listening_post_terms(post.listening_post_id)
    assert "Institution A" in terms
    assert "Institute A" in terms
    assert "@institutionA" in terms
    assert "@extra" in terms
    assert "cultural program" in terms


def test_project_share_round_trip_preserves_portable_research_state(tmp_path: Path) -> None:
    manager = _workspace(tmp_path)
    manager.add_subproject("Track One")
    layer_source = tmp_path / "layer.csv"
    layer_source.write_text("name,lat,lon\nPoint,1,2\n", encoding="utf-8")
    manager.add_reference_layer(layer_source, name="Reference")

    bundle = Path(manager.export_share_bundle())
    assert bundle.is_file()

    imported_root = tmp_path / "imported"
    workspace = import_project_bundle(bundle, imported_root)
    imported = ResearchWorkspaceManager(workspace)
    assert imported.status()["subprojects"] == 1
    assert imported.status()["reference_layers"] == 1
    assert (imported_root / "sugar-project.json").is_file()
    assert (imported_root / "sugar-research.json").is_file()
