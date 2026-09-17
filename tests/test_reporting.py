import json
from pathlib import Path

import pandas as pd
import pytest
from docx import Document

from sugar_core.reporting import _bar, _json_dict, _prepare, _terms, create_analysis_report


def _report_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "platform": "weibo & partner",
                "native_id": "1",
                "published_at": "2026-09-01T12:00:00Z",
                "detected_language": "zh",
                "inferred_location": "Bishkek <Central>",
                "translated_text": "technology workshop students technology exchange",
                "original_text": "原文",
                "engagement": json.dumps({"likes": 5, "replies": 2, "impressions": 100}),
            },
            {
                "platform": "x",
                "native_id": "2",
                "published_at": "2026-09-03T12:00:00Z",
                "detected_language": "en",
                "inferred_location": "Blacksburg",
                "translated_text": "students discuss technology partnerships",
                "original_text": "students discuss technology partnerships",
                "engagement": json.dumps({"retweet_count": 3, "impression_count": 50}),
            },
        ]
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"likes": 1}, {"likes": 1}),
        ('{"likes": 2}', {"likes": 2}),
        ("[1, 2]", {}),
        ("not json", {}),
        (None, {}),
    ],
)
def test_json_dict_accepts_only_mapping_payloads(value, expected):
    assert _json_dict(value) == expected


def test_prepare_rejects_empty_input():
    with pytest.raises(ValueError, match="contains no records"):
        _prepare(pd.DataFrame())


def test_prepare_normalizes_aliases_invalid_values_and_defaults():
    frame = pd.DataFrame(
        [
            {
                "tweet_id": "legacy-1",
                "date_iso": "2026-09-10T10:00:00Z",
                "raw_stats": json.dumps(
                    {
                        "favourite_count": "bad",
                        "reply_count": "2",
                        "retweet_count": 3,
                        "quote_count": 1,
                        "bookmark_count": 4,
                        "impression_count": 20,
                    }
                ),
            },
            {
                "tweet_id": "",
                "date_iso": "not-a-date",
                "raw_stats": "malformed",
            },
        ]
    )

    work, metrics = _prepare(frame)

    assert work.loc[0, "likes"] == 0
    assert work.loc[0, "replies"] == 2
    assert work.loc[0, "reposts"] == 3
    assert work.loc[0, "quotes"] == 1
    assert work.loc[0, "bookmarks"] == 4
    assert work.loc[0, "engagement_total"] == 10
    assert work.loc[0, "engagement_rate"] == 0.5
    assert work.loc[0, "platform"] == "unknown"
    assert work.loc[0, "language"] == "unknown"
    assert work.loc[0, "location"] == "Unassigned"
    assert metrics == {
        "records": 2,
        "unique_ids": 1,
        "engagement": 10,
        "impressions": 20,
        "start": "2026-09-10",
        "end": "2026-09-10",
    }


def test_prepare_uses_unknown_dates_when_none_parse():
    _, metrics = _prepare(pd.DataFrame([{"native_id": "1", "published_at": "bad", "engagement": "{}"}]))
    assert metrics["start"] == "Unknown"
    assert metrics["end"] == "Unknown"


def test_terms_prefers_translation_and_falls_back_to_original_text():
    translated = pd.DataFrame(
        {"translated_text": ["Technology technology workshop and students"], "original_text": ["ignored ignored"]}
    )
    assert _terms(translated)[0] == ("technology", 2)

    original_only = pd.DataFrame({"translated_en": [""], "original_text": ["Research research partnership"]})
    assert _terms(original_only)[0] == ("research", 2)


def test_bar_writes_nonempty_png(tmp_path: Path):
    path = tmp_path / "chart.png"
    _bar(pd.Series({"a": 2, "b": 1}), "Example", path)
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert path.stat().st_size > 1000


def test_create_analysis_report_rejects_unknown_format_before_loading_source(tmp_path: Path):
    with pytest.raises(ValueError, match="docx, pdf, or both"):
        create_analysis_report(str(tmp_path / "missing.csv"), str(tmp_path / "report"), "html")


def test_create_analysis_report_writes_content_equivalent_docx_and_pdf(tmp_path: Path):
    source = tmp_path / "source & sample.csv"
    _report_frame().to_csv(source, index=False)

    outputs = create_analysis_report(str(source), str(tmp_path / "analysis"), "both")

    assert outputs == [str((tmp_path / "analysis.docx").resolve()), str((tmp_path / "analysis.pdf").resolve())]
    docx_path, pdf_path = map(Path, outputs)
    assert docx_path.is_file() and docx_path.stat().st_size > 1000
    assert pdf_path.is_file() and pdf_path.stat().st_size > 1000
    assert pdf_path.read_bytes().startswith(b"%PDF-")

    document = Document(docx_path)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "SUGAR Collection Analysis" in text
    assert "Engagement" in text
    assert "Recurring vocabulary" in text
    assert "weibo & partner: 7 recorded interactions" in text
    assert "technology (3)" in text
    assert "source & sample.csv" in text


@pytest.mark.parametrize("output_format", ["docx", "pdf"])
def test_create_analysis_report_respects_single_format(tmp_path: Path, output_format: str):
    source = tmp_path / "source.csv"
    _report_frame().to_csv(source, index=False)

    outputs = create_analysis_report(str(source), str(tmp_path / "single"), output_format)

    assert len(outputs) == 1
    assert Path(outputs[0]).suffix == f".{output_format}"
    other = ".pdf" if output_format == "docx" else ".docx"
    assert not (tmp_path / f"single{other}").exists()
