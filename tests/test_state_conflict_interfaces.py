from __future__ import annotations

import json
from pathlib import Path

from sugar_core.desktop_ops import run_desktop_analytic_operation
from sugar_core.observation_storage import save_observations
from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.source_conflicts import SourceClaim, SourceConflict, save_source_conflicts
from sugar_core.state_cli import build_parser
from sugar_core.state_schema import StateAssessment
from sugar_core.state_workflow import save_state_assessments


STATE_URL = "https://educationusa.state.gov/node/421"
OPERATOR_URL = "https://kyrgyzstan.americancouncils.org/edusa"


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    observation = ResearchObservation(
        observation_type="program",
        title="Education advising context",
        summary="A public-source record uses the current State EducationUSA directory.",
        observed_at="2026-09-14",
        country="Kyrgyzstan",
        city="Bishkek",
        evidence=[
            EvidenceReference(
                url=STATE_URL,
                source_type="official_usg_source",
                collected_at="2026-09-14T00:00:00Z",
            )
        ],
    )
    observations_path = tmp_path / "observations.csv"
    save_observations([observation], observations_path)

    assessments_path = tmp_path / "assessments.jsonl"
    save_state_assessments(
        [
            StateAssessment(
                observation_id=observation.observation_id,
                strategic_audiences=["students"],
                program_domains=["higher_education"],
            )
        ],
        assessments_path,
    )

    state_claim = SourceClaim(
        statement="EducationUSA Kyrgyzstan is fully online beginning April 1, 2026.",
        source_url=STATE_URL,
        publisher="U.S. Department of State EducationUSA",
        authority_type="official_authority",
        freshness="current",
        effective_date="2026-04-01",
    )
    operator_claim = SourceClaim(
        statement="EducationUSA Kyrgyzstan provides in-person advising in Bishkek.",
        source_url=OPERATOR_URL,
        publisher="American Councils Kyrgyzstan",
        authority_type="official_operator",
        freshness="unknown",
    )
    conflict = SourceConflict(
        topic="EducationUSA Kyrgyzstan service topology",
        conflict_type="service_topology",
        status="provisional_treatment",
        claims=[state_claim, operator_claim],
        preferred_claim_id=state_claim.claim_id,
        treatment="Use the current State directory topology provisionally.",
        preference_rationale="The State directory supplies an explicit effective date.",
    )
    conflicts_path = Path(
        save_source_conflicts([conflict], tmp_path / "source-conflicts.json")
    )
    return observations_path, assessments_path, conflicts_path


def test_state_package_cli_accepts_source_conflicts_argument():
    parser = build_parser()
    args = parser.parse_args(
        [
            "package",
            "observations.csv",
            "--assessments",
            "assessments.jsonl",
            "--source-conflicts",
            "source-conflicts.json",
            "--output",
            "out",
        ]
    )

    assert args.command == "package"
    assert args.source_conflicts == "source-conflicts.json"


def test_desktop_state_package_carries_explicit_source_conflicts(tmp_path):
    observations_path, assessments_path, conflicts_path = _inputs(tmp_path)
    out_dir = tmp_path / "state-output"

    outputs = run_desktop_analytic_operation(
        "state-package",
        {
            "observations": str(observations_path),
            "assessments": str(assessments_path),
            "source_conflicts": str(conflicts_path),
            "output_directory": str(out_dir),
            "name": "desktop_case",
        },
    )

    conflict_output = out_dir / "desktop_case.source_conflicts.json"
    assert str(conflict_output.resolve()) in outputs
    assert conflict_output.is_file()

    audit = json.loads((out_dir / "desktop_case.audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "conditional"
    assert audit["source_conflicts"]["requiring_human_review"] == 1

    snapshot = json.loads(
        (out_dir / "desktop_case.snapshot.json").read_text(encoding="utf-8")
    )
    assert snapshot["source_conflicts"]["conflicts"] == 1

    brief = (out_dir / "desktop_case.brief.md").read_text(encoding="utf-8")
    assert "## Source Conflicts" in brief
    assert "EducationUSA Kyrgyzstan service topology" in brief
