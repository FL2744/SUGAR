from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parents[1] / "examples" / "cases" / "kyrgyzstan_2026"
SPEC = importlib.util.spec_from_file_location("kyrgyzstan_case_data", CASE_DIR / "case_data.py")
assert SPEC is not None and SPEC.loader is not None
CASE_DATA = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CASE_DATA
SPEC.loader.exec_module(CASE_DATA)


def test_kyrgyzstan_case_has_real_evidence_and_remains_unverified():
    observations = CASE_DATA.build_observations()
    assessments = CASE_DATA.build_assessments(observations)

    assert len(observations) == 11
    assert len(assessments) == 11
    assert all(row.country == "Kyrgyzstan" for row in observations)
    assert all(row.verification_state == "ai_triaged" for row in observations)
    assert all(row.review_state == "ai_triaged" for row in assessments)
    assert all(not row.brief_eligible for row in assessments)
    assert all(row.evidence and row.primary_source_url.startswith("https://") for row in observations)
    assert all(row.prc_support.level == "probable" for row in assessments)
    assert all(row.prc_support.review_state == "ai_triaged" for row in assessments)


def test_kyrgyzstan_case_exposes_language_taxonomy_gap_without_losing_concept():
    observations = CASE_DATA.build_observations()
    assessments = CASE_DATA.build_assessments(observations)
    assessment_by_id = {row.observation_id: row for row in assessments}

    language_records = [row for row in observations if "language_education" in row.triage_labels]
    assert len(language_records) >= 4
    assert all("other" in assessment_by_id[row.observation_id].program_domains for row in language_records)
    assert all(
        any("Chinese-language education" in value for value in assessment_by_id[row.observation_id].policy_relevance)
        for row in language_records
    )


def test_kyrgyzstan_us_layer_keeps_virtual_educationusa_nonspatial():
    sites = CASE_DATA.build_us_presence_sites()
    physical = [site for site in sites if site.latitude is not None and site.longitude is not None]
    virtual = [site for site in sites if site.latitude is None or site.longitude is None]

    assert len(physical) == 8
    assert len(virtual) == 1
    assert virtual[0].network == "educationusa"
    assert virtual[0].city == ""
    assert "educationusa" in virtual[0].service_tags
    assert all(site.source_url.startswith("https://") for site in sites)
