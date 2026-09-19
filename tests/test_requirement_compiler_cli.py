from __future__ import annotations

import json
from pathlib import Path

import pytest

from sugar_core.cli import build_parser, main
from sugar_core.requirement_compiler import load_research_strategy
from sugar_core.research_requirements import load_search_plan


def test_strategy_cli_parser_exposes_compile_update_approve_and_strategy_plan():
    parser = build_parser()
    compiled = parser.parse_args(
        [
            "strategy",
            "compile",
            "requirement.json",
            "--output",
            "strategy.json",
        ]
    )
    assert compiled.command == "strategy"
    assert compiled.strategy_command == "compile"

    updated = parser.parse_args(
        [
            "strategy",
            "update",
            "strategy.json",
            "--edits",
            "edits.json",
        ]
    )
    assert updated.strategy_command == "update"

    approved = parser.parse_args(
        [
            "strategy",
            "approve",
            "strategy.json",
            "--reviewer",
            "Analyst One",
        ]
    )
    assert approved.strategy_command == "approve"

    plan = parser.parse_args(
        [
            "plan",
            "requirement.json",
            "--strategy",
            "strategy.json",
        ]
    )
    assert plan.strategy == "strategy.json"


def test_strategy_cli_round_trip_and_plan_approval_gate(tmp_path: Path, capsys):
    requirement = tmp_path / "requirement.json"
    strategy = tmp_path / "strategy.json"
    plan = tmp_path / "plan.json"

    exit_code = main(
        [
            "requirement",
            "create",
            "--question",
            "How are foreign educational institutions reaching university students in Exampleland?",
            "--output",
            str(requirement),
        ]
    )
    assert exit_code == 0
    capsys.readouterr()

    exit_code = main(
        [
            "strategy",
            "compile",
            str(requirement),
            "--output",
            str(strategy),
        ]
    )
    assert exit_code == 0
    assert strategy.is_file()
    assert load_research_strategy(strategy).review_state == "draft"
    capsys.readouterr()

    with pytest.raises(ValueError, match="analyst-approved"):
        main(
            [
                "plan",
                str(requirement),
                "--strategy",
                str(strategy),
                "--output",
                str(plan),
            ]
        )

    edits = tmp_path / "edits.json"
    edits.write_text(
        json.dumps(
            {
                "add_concepts": [
                    {
                        "kind": "entity",
                        "value": "Public Engagement Center Exampleland",
                        "origin": "hypothesis",
                        "rationale": "Investigate, do not assert.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "strategy",
            "update",
            str(strategy),
            "--edits",
            str(edits),
            "--actor",
            "Analyst One",
        ]
    )
    assert exit_code == 0
    capsys.readouterr()

    exit_code = main(
        [
            "strategy",
            "approve",
            str(strategy),
            "--reviewer",
            "Analyst One",
            "--note",
            "Interpretation checked.",
        ]
    )
    assert exit_code == 0
    approved = load_research_strategy(strategy)
    assert approved.approved
    capsys.readouterr()

    exit_code = main(
        [
            "plan",
            str(requirement),
            "--strategy",
            str(strategy),
            "--output",
            str(plan),
        ]
    )
    assert exit_code == 0
    search_plan = load_search_plan(plan)
    assert any(
        branch.query == "Public Engagement Center Exampleland"
        for branch in search_plan.branches
    )
    assert any(event["type"] == "compiled_strategy_plan" for event in search_plan.events)
