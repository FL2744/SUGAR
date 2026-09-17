import json

import pytest

from sugar_core import __version__
from sugar_core.cli import build_parser, main
from sugar_core.state_cli import build_parser as build_state_parser
from sugar_core.state_intel_cli import build_parser as build_intel_parser
from sugar_core.workspace_cli import build_parser as build_workspace_parser


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
