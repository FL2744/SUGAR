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
    assert {"workspace-init", "workspace-status", "workspace-register"} <= set(payload["operations"])


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
