from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from sugar_core.state_conflict_package import save_state_package_with_conflicts

CASE_DIR = Path(__file__).resolve().parents[1] / "examples" / "cases" / "kyrgyzstan_2026"
if str(CASE_DIR) not in sys.path:
    sys.path.insert(0, str(CASE_DIR))

from case_data import build_assessments, build_observations, build_us_presence_sites
from location_enrichment import (
    apply_observation_location_enrichment,
    apply_us_site_location_enrichment,
)
from source_conflicts import build_source_conflicts


def test_real_kyrgyzstan_package_carries_educationusa_conflict(tmp_path):
    observations = build_observations()
    sites = build_us_presence_sites()
    apply_observation_location_enrichment(observations)
    apply_us_site_location_enrichment(sites)
    assessments = build_assessments(observations)
    conflicts = build_source_conflicts()

    outputs = save_state_package_with_conflicts(
        observations,
        assessments,
        tmp_path,
        name="kyrgyzstan_conflict_regression",
        us_sites=sites,
        title="Kyrgyzstan 2026 Public Diplomacy Research Update",
        source_conflicts=conflicts,
    )

    conflict_path = tmp_path / "kyrgyzstan_conflict_regression.source_conflicts.json"
    assert str(conflict_path.resolve()) in outputs

    audit = json.loads((tmp_path / "kyrgyzstan_conflict_regression.audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "conditional"
    assert audit["errors"] == 0
    assert audit["source_conflicts"] == {
        "conflicts": 1,
        "open": 0,
        "provisional_treatment": 1,
        "human_adjudicated": 0,
        "resolved_by_source_update": 0,
        "requiring_human_review": 1,
        "distinct_sources": 2,
    }

    queue = pd.read_csv(tmp_path / "kyrgyzstan_conflict_regression.review_queue.csv")
    affected = queue[queue["source_conflicts_requiring_human_review"] == 1]
    assert len(affected) == 2
    assert set(affected["source_conflict_topics"]) == {"EducationUSA Kyrgyzstan service topology"}
    assert all("higher_education" in value for value in affected["program_domains"])

    with pd.ExcelFile(tmp_path / "kyrgyzstan_conflict_regression.state.xlsx") as workbook:
        assert "source_conflicts" in workbook.sheet_names
    conflicts_sheet = pd.read_excel(
        tmp_path / "kyrgyzstan_conflict_regression.state.xlsx",
        sheet_name="source_conflicts",
    )
    assert conflicts_sheet.loc[0, "status"] == "provisional_treatment"
    assert bool(conflicts_sheet.loc[0, "requires_human_review"]) is True

    brief = (tmp_path / "kyrgyzstan_conflict_regression.brief.md").read_text(encoding="utf-8")
    assert "EducationUSA Kyrgyzstan service topology" in brief
    assert "not a human adjudication" in brief
