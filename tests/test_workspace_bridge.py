from __future__ import annotations

import json
from pathlib import Path

import sugar_bridge


def _events(output: str) -> list[dict]:
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def test_bridge_diagnostics_advertise_workspace_protocol(capsys) -> None:
    assert sugar_bridge.main(["diagnostics"]) == 0
    events = _events(capsys.readouterr().out)
    assert len(events) == 1
    payload = events[0]
    assert payload["event"] == "diagnostics"
    assert payload["bridge_protocol"] == 3
    assert {
        "workspace-init",
        "workspace-status",
        "workspace-register",
        "workspace-research-status",
        "workspace-subproject-add",
        "workspace-listening-upsert",
        "workspace-listening-run",
        "workspace-layers-import",
        "workspace-reference-map",
        "workspace-conversation-view",
        "workspace-share-export",
        "workspace-share-verify",
        "workspace-share-import",
    } <= set(payload["operations"])


def test_bridge_workspace_init_status_and_register(tmp_path: Path, capsys) -> None:
    root = tmp_path / "project"
    init_config = tmp_path / "init.json"
    init_config.write_text(
        json.dumps({"workspace": str(root), "name": "Bridge Project"}),
        encoding="utf-8",
    )

    assert sugar_bridge.main(["workspace-init", "--config", str(init_config)]) == 0
    init_events = _events(capsys.readouterr().out)
    status = next(event for event in init_events if event["event"] == "workspace_status")
    assert status["name"] == "Bridge Project"
    assert (root / "sugar-project.json").is_file()

    artifact = root / "data" / "raw" / "fixture.txt"
    artifact.write_text("fixture", encoding="utf-8")
    register_config = tmp_path / "register.json"
    register_config.write_text(
        json.dumps(
            {
                "workspace": str(root),
                "kind": "raw",
                "artifact": "data/raw/fixture.txt",
                "label": "Fixture",
                "metadata": {"source": "test"},
            }
        ),
        encoding="utf-8",
    )

    assert sugar_bridge.main(["workspace-register", "--config", str(register_config)]) == 0
    register_events = _events(capsys.readouterr().out)
    artifact_event = next(event for event in register_events if event["event"] == "workspace_artifact")
    assert artifact_event["artifact"]["path"] == "data/raw/fixture.txt"
    assert artifact_event["artifact"]["metadata"] == {"source": "test"}

    status_config = tmp_path / "status.json"
    status_config.write_text(json.dumps({"workspace": str(root)}), encoding="utf-8")
    assert sugar_bridge.main(["workspace-status", "--config", str(status_config)]) == 0
    status_events = _events(capsys.readouterr().out)
    status = next(event for event in status_events if event["event"] == "workspace_status")
    assert status["artifact_counts"] == {"raw": 1}


def test_bridge_persistent_research_state_and_share(tmp_path: Path, capsys) -> None:
    root = tmp_path / "project"
    init_config = tmp_path / "init-project.json"
    init_config.write_text(json.dumps({"workspace": str(root), "name": "Persistent Project"}), encoding="utf-8")
    assert sugar_bridge.main(["workspace-init", "--config", str(init_config)]) == 0
    capsys.readouterr()

    subproject_config = tmp_path / "subproject.json"
    subproject_config.write_text(
        json.dumps({"workspace": str(root), "name": "Institutions", "tags": ["reference"]}),
        encoding="utf-8",
    )
    assert sugar_bridge.main(["workspace-subproject-add", "--config", str(subproject_config)]) == 0
    events = _events(capsys.readouterr().out)
    subproject = next(event for event in events if event["event"] == "workspace_subproject")["subproject"]
    assert subproject["name"] == "Institutions"

    listening_config = tmp_path / "listening.json"
    listening_config.write_text(
        json.dumps({
            "workspace": str(root),
            "name": "Institution watch",
            "query_terms": ["example institution"],
            "sources": ["bilibili"],
            "subproject_id": subproject["subproject_id"],
            "cadence": "weekly",
        }),
        encoding="utf-8",
    )
    assert sugar_bridge.main(["workspace-listening-upsert", "--config", str(listening_config)]) == 0
    events = _events(capsys.readouterr().out)
    listening = next(event for event in events if event["event"] == "workspace_listening_post")["listening_post"]
    assert listening["cadence"] == "weekly"

    references = root / "references" / "institutions.csv"
    references.write_text(
        "canonical_name,latitude,longitude,lifecycle_status\n"
        "Open Center,38.9,-77.0,active\n"
        "Former Center,40.7,-74.0,closed\n",
        encoding="utf-8",
    )
    layer_config = tmp_path / "layers.json"
    layer_config.write_text(
        json.dumps({"workspace": str(root), "sources": [str(references)], "layer_type": "institution"}),
        encoding="utf-8",
    )
    assert sugar_bridge.main(["workspace-layers-import", "--config", str(layer_config)]) == 0
    capsys.readouterr()

    map_config = tmp_path / "reference-map.json"
    map_config.write_text(json.dumps({"workspace": str(root)}), encoding="utf-8")
    assert sugar_bridge.main(["workspace-reference-map", "--config", str(map_config)]) == 0
    events = _events(capsys.readouterr().out)
    map_event = next(event for event in events if event["event"] == "workspace_reference_map")
    assert Path(map_event["output"]).is_file()

    status_config = tmp_path / "research-status.json"
    status_config.write_text(json.dumps({"workspace": str(root)}), encoding="utf-8")
    assert sugar_bridge.main(["workspace-research-status", "--config", str(status_config)]) == 0
    events = _events(capsys.readouterr().out)
    state = next(event for event in events if event["event"] == "workspace_research")
    assert state["dashboard"]["subproject_count"] == 1
    assert state["dashboard"]["listening_post_count"] == 1
    assert state["dashboard"]["reference_layer_count"] == 1

    share_config = tmp_path / "share.json"
    share_config.write_text(json.dumps({"workspace": str(root)}), encoding="utf-8")
    assert sugar_bridge.main(["workspace-share-export", "--config", str(share_config)]) == 0
    events = _events(capsys.readouterr().out)
    share = next(event for event in events if event["event"] == "workspace_share")["output"]
    assert Path(share).is_file()

    verify_config = tmp_path / "verify-share.json"
    verify_config.write_text(json.dumps({"share_file": share}), encoding="utf-8")
    assert sugar_bridge.main(["workspace-share-verify", "--config", str(verify_config)]) == 0
    events = _events(capsys.readouterr().out)
    verification = next(event for event in events if event["event"] == "workspace_share_verification")
    assert verification["valid"] is True
