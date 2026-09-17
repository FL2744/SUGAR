from __future__ import annotations

import json
from pathlib import Path

from sugar_core.cli import build_parser, main
from sugar_core.lineage import load_lineage_index, validate_lineage_index
from sugar_core.models import PostRecord
from sugar_core.observation_storage import save_observations
from sugar_core.observations import observation_from_post
from sugar_core.state_schema import AnalyticClaim, StateAssessment
from sugar_core.state_workflow import save_state_assessments
from sugar_core.storage import save_records


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    record = PostRecord(
        platform="example",
        native_id="cli-1",
        canonical_url="https://example.test/cli-1",
        query="example",
        original_text="CLI lineage source evidence.",
    )
    records = tmp_path / "records.csv"
    save_records([record], records)
    observation = observation_from_post(record)
    observations = tmp_path / "observations.csv"
    save_observations([observation], observations)
    claim = AnalyticClaim(
        statement="The record documents the activity.",
        evidence_refs=[record.canonical_url],
    )
    assessments = tmp_path / "assessments.jsonl"
    save_state_assessments(
        [StateAssessment(observation_id=observation.observation_id, claims=[claim])],
        assessments,
    )
    return records, observations, assessments


def test_lineage_cli_parser_exposes_generation_and_verification():
    parser = build_parser()
    args = parser.parse_args(
        [
            "lineage",
            "observations.csv",
            "--assessments",
            "assessments.jsonl",
            "--records",
            "records.csv",
            "--output",
            "lineage.json",
        ]
    )
    assert args.command == "lineage"
    assert args.records == "records.csv"

    verify = parser.parse_args(["verify-lineage", "lineage.json"])
    assert verify.command == "verify-lineage"


def test_lineage_cli_round_trip(tmp_path: Path, capsys):
    records, observations, assessments = _inputs(tmp_path)
    output = tmp_path / "case.lineage.json"

    exit_code = main(
        [
            "lineage",
            str(observations),
            "--assessments",
            str(assessments),
            "--records",
            str(records),
            "--output",
            str(output),
        ]
    )
    assert exit_code == 0
    assert output.is_file()
    assert validate_lineage_index(load_lineage_index(output))["status"] == "pass"
    capsys.readouterr()

    exit_code = main(["verify-lineage", str(output)])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "pass"
    assert payload["counts"]["findings"] == 1
