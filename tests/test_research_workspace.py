from __future__ import annotations

import json
from pathlib import Path

import pytest

from sugar_core.research_workspace import (
    CollaborationMember,
    ListeningPost,
    ReferenceLayer,
    ResearchWorkspaceState,
    SearchHistoryEntry,
    Subproject,
    build_conversations,
)
from sugar_core.workspace import SugarWorkspace


def test_research_workspace_state_round_trip(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    state = ResearchWorkspaceState.open(workspace.root, project_id=workspace.manifest.project_id)

    parent = state.add_subproject(Subproject(name="Institutions", tags=["reference"]))
    child = state.add_subproject(
        Subproject(name="Kyrgyzstan", parent_subproject_id=parent.subproject_id)
    )
    state.record_search(
        SearchHistoryEntry(
            query_terms=["Confucius Institute", "孔子学院"],
            sources=["bilibili", "weibo"],
            subproject_id=child.subproject_id,
            research_question="Where are relevant institutions active?",
            result_count=12,
        )
    )
    post = state.upsert_listening_post(
        ListeningPost(
            name="CI watch",
            query_terms=["Confucius Institute"],
            sources=["weibo"],
            subproject_id=child.subproject_id,
            cadence="weekly",
        )
    )
    layer = state.upsert_reference_layer(
        ReferenceLayer(
            name="Institutions",
            source="references/institutions.csv",
            layer_type="institution",
            subproject_id=parent.subproject_id,
        )
    )
    member = state.upsert_collaborator(
        CollaborationMember(display_name="Analyst One", role="reviewer")
    )

    reopened = ResearchWorkspaceState.open(
        workspace.root,
        project_id=workspace.manifest.project_id,
    )
    assert reopened.subprojects[child.subproject_id].parent_subproject_id == parent.subproject_id
    assert reopened.search_history[0].result_count == 12
    assert reopened.listening_posts[post.listening_post_id].cadence == "weekly"
    assert reopened.reference_layers[layer.layer_id].source == "references/institutions.csv"
    assert reopened.collaborators[member.member_id].role == "reviewer"
    assert reopened.dashboard() == {
        "project_id": workspace.manifest.project_id,
        "subproject_count": 2,
        "active_subproject_count": 2,
        "search_count": 1,
        "listening_post_count": 1,
        "active_listening_post_count": 1,
        "reference_layer_count": 1,
        "collaborator_count": 1,
        "updated_at": reopened.updated_at,
    }


def test_research_workspace_rejects_unknown_subproject_links(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    state = ResearchWorkspaceState.open(workspace.root, project_id=workspace.manifest.project_id)

    with pytest.raises(ValueError, match="Unknown parent subproject"):
        state.add_subproject(Subproject(name="Child", parent_subproject_id="missing"))

    with pytest.raises(ValueError, match="Unknown subproject"):
        state.upsert_listening_post(
            ListeningPost(
                name="Bad",
                query_terms=["term"],
                sources=["x"],
                subproject_id="missing",
            )
        )


def test_workspace_status_exposes_research_dashboard(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    status = workspace.status()

    assert Path(status["research_state"]).name == "sugar-research.json"
    assert status["research"]["project_id"] == workspace.manifest.project_id
    assert status["research"]["search_count"] == 0


def test_build_conversations_preserves_speakers_and_reply_order() -> None:
    rows = [
        {
            "record_key": "root",
            "author_name": "Alice",
            "author_handle": "@alice",
            "text": "Opening",
            "conversation_id": "thread-1",
            "published_at": "2026-09-24T10:00:00Z",
        },
        {
            "record_key": "reply",
            "author_name": "Bob",
            "author_handle": "@bob",
            "text": "Reply",
            "conversation_id": "thread-1",
            "parent_record_key": "root",
            "published_at": "2026-09-24T10:01:00Z",
        },
    ]

    conversations = build_conversations(rows)

    assert len(conversations) == 1
    assert [item.record_key for item in conversations[0]] == ["root", "reply"]
    assert conversations[0][0].author == "Alice (@alice)"
    assert conversations[0][1].author == "Bob (@bob)"


def test_research_state_file_is_portable_json(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    payload = json.loads((workspace.root / "sugar-research.json").read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.0"
    assert payload["project_id"] == workspace.manifest.project_id
    assert payload["subprojects"] == []
    assert payload["search_history"] == []
