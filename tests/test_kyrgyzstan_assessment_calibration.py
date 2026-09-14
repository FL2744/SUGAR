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
