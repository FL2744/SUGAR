from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


CASE_DIR = Path(__file__).resolve().parents[1] / "examples" / "cases" / "kyrgyzstan_2026"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, CASE_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CASE_DATA = _load("kyrgyzstan_case_data_calibration_test", "case_data.py")
CALIBRATION = _load("kyrgyzstan_assessment_calibration_test", "assessment_calibration.py")


def test_support_calibration_distinguishes_direct_and_weaker_support_evidence():
    observations = CASE_DATA.build_observations()
    assessments = CASE_DATA.build_assessments(observations)
    summary = CALIBRATION.calibrate_support_assessments(observations, assessments)
    by_title = {
        observation.title: assessment
        for observation, assessment in zip(observations, assessments, strict=True)
    }

    assert summary == {"probable": 9, "possible": 2}
    assert by_title["Chinese painting exhibition at the National Historical Museum"].prc_support.level == "probable"
    assert by_title["Chinese Bridge school competition Kyrgyzstan qualifier"].prc_support.level == "probable"
    assert by_title["Kyrgyz and Chinese writers organizations sign cooperation agreement"].prc_support.level == "possible"
    assert by_title["Presentation of Xi Jinping's The Governance of China in Bishkek"].prc_support.level == "possible"
    assert all(assessment.prc_support.level != "confirmed" for assessment in assessments)
    assert all(assessment.prc_support.review_state == "ai_triaged" for assessment in assessments)

    language_titles = {
        observation.title
        for observation in observations
        if "language_education" in observation.triage_labels
    }
    assert len(language_titles) == 4
    for title in language_titles:
        assessment = by_title[title]
        assert "language_education" in assessment.program_domains
        assert "other" not in assessment.program_domains


def test_real_case_preserves_qualified_reach_without_false_exact_counts():
    observations = CASE_DATA.build_observations()
    assessments = CASE_DATA.build_assessments(observations)
    CALIBRATION.calibrate_support_assessments(observations, assessments)
    by_title = {
        observation.title: assessment
        for observation, assessment in zip(observations, assessments, strict=True)
    }

    governance = by_title["Presentation of Xi Jinping's The Governance of China in Bishkek"]
    governance_attendance = governance.reach.metric("attendance")
    assert governance_attendance is not None
    assert governance_attendance.qualifier == "approximate"
    assert governance_attendance.value == 300
    assert governance.reach.attendance is None
    assert governance.reach.observed_total == 0
    assert governance_attendance.source_ref
    assert "roughly 300" in governance_attendance.source_note

    sco = by_title["SCO Civilizations Dialogue at the National Historical Museum"]
    sco_attendance = sco.reach.metric("attendance")
    assert sco_attendance is not None
    assert sco_attendance.qualifier == "approximate"
    assert sco_attendance.value == 200
    assert sco.reach.attendance is None
    assert "roughly 200" in sco_attendance.source_note

    manas = by_title["Chinese-produced Manas dance drama premieres in Kyrgyzstan"]
    manas_attendance = manas.reach.metric("attendance")
    assert manas_attendance is not None
    assert manas_attendance.qualifier == "minimum"
    assert manas_attendance.value == 1000
    assert manas_attendance.lower_bound == 1000
    assert manas_attendance.upper_bound is None
    assert manas.reach.attendance is None
    assert manas.reach.observed_total == 0
    assert "more than 1,000" in manas_attendance.source_note

    for assessment in (governance, sco, manas):
        assert assessment.observability_level == "reach_observed"
        reach_claims = [claim for claim in assessment.claims if claim.claim_type == "reach"]
        assert len(reach_claims) == 1
        assert reach_claims[0].review_state == "ai_triaged"
        assert reach_claims[0].evidence_refs
