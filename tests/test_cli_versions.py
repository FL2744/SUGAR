import pytest

import sugar_core
from sugar_core.cli import build_parser as build_main_parser
from sugar_core.state_cli import build_parser as build_state_parser
from sugar_core.state_intel_cli import build_parser as build_intel_parser
from sugar_core.workspace_cli import build_parser as build_project_parser


@pytest.mark.parametrize(
    ("factory", "program"),
    [
        (build_main_parser, "sugar"),
        (build_project_parser, "sugar-project"),
        (build_state_parser, "sugar-state"),
        (build_intel_parser, "sugar-intel"),
    ],
)
def test_top_level_cli_reports_package_version(factory, program, capsys):
    parser = factory()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"{program} {sugar_core.__version__}"
