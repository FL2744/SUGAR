import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import sugar_bridge
from sugar_core.errors import error_payload


def _events(output: str) -> list[dict]:
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def test_bridge_rejects_oversized_config(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    path.write_text("{" + '"payload":"' + ("x" * sugar_bridge.MAX_CONFIG_BYTES) + '"}', encoding="utf-8")

    with pytest.raises(ValueError, match="exceeds"):
        sugar_bridge.load_config(str(path))


def test_bridge_rejects_deep_config(tmp_path: Path) -> None:
    value: object = "leaf"
    for _ in range(sugar_bridge.MAX_CONFIG_DEPTH + 1):
        value = {"nested": value}
    path = tmp_path / "deep.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="nesting"):
        sugar_bridge.load_config(str(path))


def test_bridge_error_event_is_structured_and_redacted(tmp_path: Path, capsys) -> None:
    config = tmp_path / "invalid.json"
    config.write_text("{not-json", encoding="utf-8")

    assert sugar_bridge.main(["analysis", "--config", str(config)]) == 1
    event = _events(capsys.readouterr().out)[-1]
    assert event["event"] == "error"
    assert event["code"] == "config_invalid"
    assert event["retryable"] is False
    assert "remediation" in event


def test_error_payload_redacts_bearer_and_known_secret() -> None:
    payload = error_payload(
        RuntimeError("Bearer abc123 cookie=session-value"),
        secrets={"token": "session-value"},
    )
    assert payload["message"] == "Bearer [REDACTED] cookie=[REDACTED]"
    assert "abc123" not in payload["message"]
    assert "session-value" not in payload["message"]


@pytest.mark.parametrize("command, function_name", [("search", "run_search"), ("harvest", "run_harvest")])
def test_bridge_routes_collection_commands(monkeypatch, tmp_path: Path, capsys, command, function_name):
    monkeypatch.setattr(sugar_bridge, function_name, lambda *args, **kwargs: ["output.txt"])
    config = tmp_path / f"{command}.json"
    config.write_text("{}", encoding="utf-8")

    assert sugar_bridge.main([command, "--config", str(config)]) == 0
    assert _events(capsys.readouterr().out)[-1] == {"event": "complete", "outputs": ["output.txt"]}


@pytest.mark.parametrize(
    "command, function_name", [("map", "run_map"), ("overlap", "run_overlap"), ("analysis", "run_analysis")]
)
def test_bridge_routes_analytic_commands(monkeypatch, tmp_path: Path, capsys, command, function_name):
    monkeypatch.setattr(sugar_bridge, function_name, lambda *args, **kwargs: ["output.txt"])
    config = tmp_path / f"{command}.json"
    config.write_text("{}", encoding="utf-8")

    assert sugar_bridge.main([command, "--config", str(config)]) == 0
    assert _events(capsys.readouterr().out)[-1]["event"] == "complete"


def test_bridge_routes_typed_desktop_operation(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setattr(sugar_bridge, "run_desktop_analytic_operation", lambda *args, **kwargs: ["output.txt"])
    config = tmp_path / "desktop.json"
    config.write_text("{}", encoding="utf-8")

    assert sugar_bridge.main(["state-template-us-sites", "--config", str(config)]) == 0
    assert _events(capsys.readouterr().out)[-1]["outputs"] == ["output.txt"]


def test_bridge_routes_weibo_operations_without_network(monkeypatch, tmp_path: Path, capsys):
    result = SimpleNamespace(
        seed=SimpleNamespace(record_key="weibo:1"),
        comments=[],
        reposts=[],
        author_posts=[],
        surface_status={},
    )
    monkeypatch.setattr(sugar_bridge, "investigate_weibo_seed", lambda *args, **kwargs: result)
    monkeypatch.setattr(sugar_bridge, "save_weibo_investigation", lambda *args, **kwargs: ["investigation.json"])
    monkeypatch.setattr(sugar_bridge, "run_weibo_seed_harvest", lambda *args, **kwargs: ["seed.jsonl"])
    monkeypatch.setattr(sugar_bridge, "run_weibo_qualification", lambda *args, **kwargs: ["qualification.json"])

    investigation = tmp_path / "investigation.json"
    investigation.write_text(
        json.dumps({"seed": "1", "output_directory": str(tmp_path)}),
        encoding="utf-8",
    )
    assert sugar_bridge.main(["weibo-investigate", "--config", str(investigation)]) == 0
    assert _events(capsys.readouterr().out)[-1]["event"] == "complete"

    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"seeds": ["1"]}), encoding="utf-8")
    assert sugar_bridge.main(["weibo-seed-harvest", "--config", str(seed)]) == 0
    assert _events(capsys.readouterr().out)[-1]["outputs"] == ["seed.jsonl"]

    qualify = tmp_path / "qualify.json"
    qualify.write_text("{}", encoding="utf-8")
    assert sugar_bridge.main(["weibo-qualify", "--config", str(qualify)]) == 0
    assert _events(capsys.readouterr().out)[-1]["outputs"] == ["qualification.json"]


def test_bridge_reports_usage_error_without_config():
    with pytest.raises(SystemExit) as exc_info:
        sugar_bridge.main(["analysis"])
    assert exc_info.value.code == 2


def test_bridge_workspace_register_validates_required_fields(tmp_path: Path):
    workspace = tmp_path / "workspace"
    from sugar_core.workspace import SugarWorkspace

    SugarWorkspace.create(workspace, name="Bridge test")
    with pytest.raises(ValueError, match="artifact is required"):
        sugar_bridge._run_workspace_operation("workspace-register", {"workspace": str(workspace)})
    with pytest.raises(ValueError, match="metadata must be a JSON object"):
        sugar_bridge._run_workspace_operation(
            "workspace-register",
            {"workspace": str(workspace), "kind": "raw", "artifact": "missing.txt", "metadata": [1]},
        )
