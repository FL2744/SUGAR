import json

import pytest

from sugar_core import __version__
from sugar_core.cli import build_parser, main
from sugar_core.state_cli import build_parser as build_state_parser
from sugar_core.state_cli import console_main as state_console_main
from sugar_core.state_intel_cli import build_parser as build_intel_parser
from sugar_core.state_intel_cli import console_main as intel_console_main
from sugar_core.workspace_cli import build_parser as build_workspace_parser
from sugar_core.workspace_cli import console_main as workspace_console_main


@pytest.mark.parametrize(
    "parser_factory",
    [build_parser, build_state_parser, build_intel_parser, build_workspace_parser],
)
def test_public_cli_exposes_package_version(parser_factory, capsys):
    with pytest.raises(SystemExit) as exc_info:
        parser_factory().parse_args(["--version"])
    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == __version__


def test_primary_cli_returns_structured_redacted_error(capsys):
    assert main(["map", "missing-input.csv"]) == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["event"] == "error"
    assert payload["code"] == "input_missing"
    assert payload["retryable"] is False


def test_primary_cli_returns_130_for_cancellation(monkeypatch, capsys):
    def cancel(_config):
        raise KeyboardInterrupt()

    monkeypatch.setattr("sugar_core.cli.run_map", cancel)
    assert main(["map", "input.csv"]) == 130
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == "cancelled"


@pytest.mark.parametrize(
    ("command", "expected_code"),
    [
        (lambda: state_console_main(["blank", "missing-observations.csv"]), "input_invalid"),
        (
            lambda: intel_console_main(
                ["packet", "missing-observations.csv", "missing-assessments.jsonl", "--output", "out.json"]
            ),
            "input_missing",
        ),
        (lambda: workspace_console_main(["status", "missing-workspace"]), "input_missing"),
    ],
)
def test_specialized_clis_return_structured_errors(command, expected_code, capsys):
    assert command() == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["event"] == "error"
    assert payload["code"] == expected_code


@pytest.mark.parametrize("argv", [["map", "input.csv", "--json"], ["--json", "map", "input.csv"]])
def test_primary_cli_supports_machine_readable_completion(monkeypatch, capsys, argv):
    monkeypatch.setattr("sugar_core.cli.run_map", lambda config: ["map.html"])
    assert main(argv) == 0
    assert json.loads(capsys.readouterr().out) == {"event": "complete", "outputs": ["map.html"]}


def test_diagnostics_command_is_redacted_and_can_write_a_report(tmp_path, capsys):
    output = tmp_path / "diagnostics.json"
    assert main(["diagnostics", "--output", str(output)]) == 0
    payload = json.loads(capsys.readouterr().out)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert payload["version"] == __version__
    assert payload["dependencies"]["requests"]
    assert set(payload["credentials_configured"]) == {
        "x_bearer_token",
        "llm_api_key",
        "bluesky_identifier",
        "bluesky_app_password",
        "mastodon_token",
        "weibo_cookie",
    }
    assert payload["redaction"]["credential_values"] == "never included"
    assert report["diagnostics_schema"] == 1
