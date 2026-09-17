import zipfile
from pathlib import Path

import pandas as pd
import pytest

import sugar_core.reporting as reporting
import sugar_core.state_review as state_review
from sugar_core import __version__
from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_schema import StateAssessment


def _results_source(path: Path) -> Path:
    pd.DataFrame(
        [
            {
                "platform": "x",
                "native_id": "000123",
                "published_at": "2026-09-10T10:00:00Z",
                "engagement": '{"likes": 3, "impressions": 12}',
                "detected_language": "ar",
                "inferred_location": "Bishkek",
                "original_text": "مرحبا 世界 👋",
            },
            {
                "platform": "bluesky",
                "native_id": "abc-2",
                "published_at": "2026-09-11T10:00:00Z",
                "engagement": '{"replies": 2}',
                "detected_language": "en",
                "inferred_location": "",
                "original_text": "A very long field " + ("x" * 400),
            },
        ]
    ).to_csv(path, index=False)
    return path


def test_analysis_reports_are_valid_and_publish_complete_files(tmp_path: Path):
    outputs = reporting.create_analysis_report(
        str(_results_source(tmp_path / "results.csv")),
        str(tmp_path / "analysis"),
        output_format="both",
    )

    docx, pdf = (Path(path) for path in outputs)
    assert docx.is_file()
    assert pdf.is_file()
    with zipfile.ZipFile(docx) as archive:
        assert archive.testzip() is None
        assert __version__.encode() in archive.read("word/document.xml")
    assert pdf.read_bytes().startswith(b"%PDF-")
    assert pdf.read_bytes().rstrip().endswith(b"%%EOF")


def test_analysis_report_keeps_previous_file_when_generation_is_interrupted(tmp_path: Path, monkeypatch):
    source = _results_source(tmp_path / "results.csv")
    target = tmp_path / "analysis.docx"
    target.write_bytes(b"previous complete report")

    def interrupted(*args, **kwargs):
        Path(kwargs.get("output", args[-1])).write_bytes(b"partial report")
        raise RuntimeError("simulated report interruption")

    monkeypatch.setattr(reporting, "_docx", interrupted)
    with pytest.raises(RuntimeError, match="simulated report interruption"):
        reporting.create_analysis_report(str(source), str(tmp_path / "analysis"), output_format="docx")

    assert target.read_bytes() == b"previous complete report"
    assert not list(tmp_path.glob(".analysis.docx.*"))


def test_review_workbook_keeps_previous_file_when_formatting_is_interrupted(tmp_path: Path, monkeypatch):
    observation = ResearchObservation(
        observation_type="program",
        title="Reviewed program",
        summary="Evidence summary",
        evidence=[EvidenceReference(url="https://example.org/evidence")],
    )
    assessment = StateAssessment(observation_id=observation.observation_id)
    target = tmp_path / "review.xlsx"
    target.write_bytes(b"previous complete workbook")

    def interrupted(*args, **kwargs):
        raise RuntimeError("simulated workbook interruption")

    monkeypatch.setattr(state_review, "load_workbook", interrupted)
    with pytest.raises(RuntimeError, match="simulated workbook interruption"):
        state_review.export_review_workbook([observation], [assessment], target)

    assert target.read_bytes() == b"previous complete workbook"
    assert not list(tmp_path.glob(".review.xlsx.*"))
