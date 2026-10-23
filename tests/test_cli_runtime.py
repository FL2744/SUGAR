from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sugar_core import __version__
from sugar_core.cli import main
from sugar_core.cli_runtime import run_cli
from sugar_core.research_requirements import load_requirement, load_search_plan
from sugar_core.requirement_compiler import load_research_strategy


ROOT = Path(__file__).resolve().parents[1]
MODULES = [
    ("sugar_core", "sugar"),
    ("sugar_core.cli", "sugar"),
    ("sugar_core.workspace_cli", "sugar-project"),
    ("sugar_core.state_cli", "sugar-state"),
    ("sugar_core.state_intel_cli", "sugar-intel"),
    ("sugar_api", "sugar-api"),
]


def _run(module, args, cwd, extra_env=None):
    env = {key: value for key, value in os.environ.items() if not key.startswith("SUGAR_")}
    env.update(PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, "-m", module, *args], cwd=cwd, env=env,
        input="", capture_output=True, text=True, encoding="utf-8", timeout=20,
    )


@pytest.mark.parametrize(("module", "program"), MODULES)
def test_module_entrypoints_report_help_and_version(module, program, tmp_path):
    help_result = _run(module, ["--help"], tmp_path)
    assert help_result.returncode == 0, help_result.stderr
    assert f"usage: {program}" in help_result.stdout
    version_result = _run(module, ["--version"], tmp_path)
    assert version_result.returncode == 0, version_result.stderr
    assert version_result.stdout.strip() == f"{program} {__version__}"


@pytest.mark.parametrize(("module", "args"), [
    ("sugar_core", ["import", "missing.csv"]),
    ("sugar_core.workspace_cli", ["status", "missing-project"]),
    ("sugar_core.state_cli", ["blank", "missing.csv", "--output", "blank.jsonl"]),
    ("sugar_core.state_intel_cli", ["media-cite", "missing.json", "--start", "0", "--end", "1"]),
])
def test_missing_files_are_actionable_console_errors(module, args, tmp_path):
    result = _run(module, args, tmp_path)
    assert result.returncode == 2
    assert ": error:" in result.stderr
    assert "missing" in result.stderr.lower()
    assert "Traceback" not in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(("args", "message"), [
    (["search", "test", "--sources", ""], "at least one collection source"),
    (["search", "test", "--sources", "unknown"], "Unsupported collection source"),
    (["search", "test", "--since", "not-a-date"], "valid date"),
    (["search", "test", "--since", "2026-09-02", "--until", "2026-09-01"], "on or before"),
    (["search", "test", "--posts", "0"], "positive integer"),
    (["harvest", "--sources", "x"], "at least one search term"),
    (["search", "test", "--sources", "X", "--no-translate", "--no-location"], "SUGAR_X_BEARER_TOKEN"),
    (["search", "test", "--sources", "bluesky"], "SUGAR_LLM_API_KEY"),
])
def test_collection_rejects_invalid_inputs_before_prompting_or_network(args, message, tmp_path):
    result = _run("sugar_core", args, tmp_path)
    assert result.returncode == 2
    assert message in result.stderr
    assert "Traceback" not in result.stderr
    assert "GetPassWarning" not in result.stderr


def test_api_help_survives_invalid_environment_port_and_rejects_invalid_ports(tmp_path):
    env = {"SUGAR_API_PORT": "invalid"}
    assert _run("sugar_api", ["--help"], tmp_path, env).returncode == 0
    result = _run("sugar_api", [], tmp_path, env)
    assert result.returncode == 2
    assert "--port" in result.stderr
    assert "Traceback" not in result.stderr
    result = _run("sugar_api", ["--port", "65536"], tmp_path)
    assert result.returncode == 2
    assert "between 0 and 65535" in result.stderr
    assert not (tmp_path / "sugar-project.json").exists()


def test_console_boundary_retains_debug_tracebacks_and_programming_errors(monkeypatch, capsys):
    def invalid_input(argv):
        raise ValueError("input needs attention")

    monkeypatch.delenv("SUGAR_DEBUG", raising=False)
    assert run_cli(invalid_input, prog="sugar") == 2
    assert "input needs attention" in capsys.readouterr().err
    monkeypatch.setenv("SUGAR_DEBUG", "1")
    with pytest.raises(ValueError, match="input needs attention"):
        run_cli(invalid_input, prog="sugar")

    def programming_error(argv):
        raise TypeError("unexpected internal type")

    monkeypatch.delenv("SUGAR_DEBUG")
    with pytest.raises(TypeError, match="unexpected internal type"):
        run_cli(programming_error, prog="sugar")


def test_windows_bom_research_files_round_trip_through_cli(tmp_path, capsys):
    requirement, strategy, plan, edits = [tmp_path / name for name in ("requirement.json", "strategy.json", "plan.json", "edits.json")]
    assert main(["requirement", "create", "--question", "Which public education programs are documented?", "--output", str(requirement)]) == 0
    requirement.write_text(requirement.read_text(encoding="utf-8"), encoding="utf-8-sig")
    assert main(["requirement", "validate", str(requirement)]) == 0
    assert main(["strategy", "compile", str(requirement), "--output", str(strategy)]) == 0
    strategy.write_text(strategy.read_text(encoding="utf-8"), encoding="utf-8-sig")
    edits.write_text(json.dumps({"analytic_task": "Review documented public education programs"}), encoding="utf-8-sig")
    assert main(["strategy", "update", str(strategy), "--edits", str(edits)]) == 0
    assert main(["strategy", "approve", str(strategy), "--reviewer", "Test analyst"]) == 0
    assert main(["plan", str(requirement), "--strategy", str(strategy), "--output", str(plan)]) == 0
    plan.write_text(plan.read_text(encoding="utf-8"), encoding="utf-8-sig")
    assert load_requirement(requirement).question
    assert load_research_strategy(strategy).review_state == "approved"
    assert load_search_plan(plan).branches
    capsys.readouterr()
