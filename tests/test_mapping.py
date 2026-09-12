from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from sugar_core.mapping import (
    MapOptions,
    _normalize_rows,
    create_map,
    detect_dataset_type,
    load_map_frame,
)
from sugar_core.service import run_map


def _observation_frame() -> pd.DataFrame:
    now = pd.Timestamp.now(tz="UTC").floor("s").isoformat()
    return pd.DataFrame(
        [
            {
                "observation_id": "obs_verified",
                "observation_type": "program",
                "title": "Public technology workshop",
                "summary": "A public workshop for university students.",
                "observed_at": now,
                "activity_status": "active",
                "location_label": "Bishkek, Kyrgyzstan",
                "country": "Kyrgyzstan",
                "city": "Bishkek",
                "latitude": 42.8746,
                "longitude": 74.5698,
                "location_basis": "source_stated",
                "location_confidence": 0.98,
                "institution_name": "Example Center",
                "program_name": "Technology Workshop",
                "actors": '["Example Center", "Partner University"]',
                "audiences": '["students", "emerging leaders"]',
                "themes": '["technology", "education"]',
                "us_overlap": '["American Space nearby"]',
                "overlap_note": "Same city as an American Space.",
                "verification_state": "human_verified",
                "triage_labels": '["prc_public_diplomacy"]',
                "ai_confidence": 0.91,
                "primary_source_url": "https://example.test/source",
            },
            {
                "observation_id": "obs_followup",
                "observation_type": "institution",
                "title": "Institution record",
                "summary": "Needs additional verification.",
                "observed_at": now,
                "location_label": "Osh, Kyrgyzstan",
                "country": "Kyrgyzstan",
                "city": "Osh",
                "latitude": 40.5139,
                "longitude": 72.8161,
                "location_basis": "geocoded_city",
                "location_confidence": 0.72,
                "verification_state": "needs_followup",
                "primary_source_url": "javascript:alert(1)",
            },
            {
                "observation_id": "obs_unmapped",
                "observation_type": "event",
                "title": "No coordinates",
                "summary": "Should count as unmapped.",
                "country": "Kyrgyzstan",
                "latitude": None,
                "longitude": None,
                "verification_state": "unreviewed",
            },
        ]
    )


def test_detects_observation_and_source_record_datasets():
    assert detect_dataset_type(_observation_frame()) == "research_observations"
    assert detect_dataset_type(pd.DataFrame([{"platform": "weibo", "latitude": 1, "longitude": 2}])) == "source_records"


def test_normalization_filters_invalid_coordinates_and_parses_lists():
    frame = _observation_frame()
    frame.loc[len(frame)] = {
        "observation_id": "bad",
        "observation_type": "event",
        "title": "Invalid coordinate",
        "latitude": 190,
        "longitude": 500,
    }

    normalized, dataset_type = _normalize_rows(frame)

    assert dataset_type == "research_observations"
    assert set(normalized["_record_id"]) == {"obs_verified", "obs_followup"}
    verified = normalized.loc[normalized["_record_id"].eq("obs_verified")].iloc[0]
    assert verified["_audiences"] == ["students", "emerging leaders"]
    assert verified["_us_overlap"] == ["American Space nearby"]


def test_observation_workbook_is_loaded_from_observations_sheet(tmp_path: Path):
    path = tmp_path / "observations.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _observation_frame().to_excel(writer, sheet_name="observations", index=False)
        pd.DataFrame([{"ignore": True}]).to_excel(writer, sheet_name="other", index=False)

    loaded = load_map_frame(path)

    assert "observation_id" in loaded.columns
    assert loaded.iloc[0]["observation_id"] == "obs_verified"


def test_source_record_workbook_falls_back_to_posts_sheet(tmp_path: Path):
    path = tmp_path / "posts.xlsx"
    expected = pd.DataFrame(
        [
            {
                "platform": "bilibili",
                "native_id": "BV1",
                "content_type": "video",
                "original_text": "Example",
                "latitude": 39.9,
                "longitude": 116.4,
            }
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        expected.to_excel(writer, sheet_name="posts", index=False)

    loaded = load_map_frame(path)

    assert loaded.iloc[0]["platform"] == "bilibili"


def test_create_map_contains_analytical_layers_and_escapes_content(tmp_path: Path):
    frame = _observation_frame()
    frame.loc[0, "title"] = "<script>alert('x')</script>"
    path = tmp_path / "research_map.html"

    result = create_map(
        frame,
        path,
        options=MapOptions(title="Diplomacy Lab Map", heat_windows=(30, 90), default_heat_window=90),
    )

    assert result == str(path.resolve())
    text = path.read_text(encoding="utf-8")
    assert "Diplomacy Lab Map" in text
    assert "Type — Program" in text
    assert "Verification — Human Verified" in text
    assert "U.S. overlap tagged" in text
    assert "Density — human-verified only" in text
    assert "Density — location-confidence weighted" in text
    assert "not influence" in text
    assert "Open source evidence" in text
    assert "javascript:alert(1)" not in text
    assert "<script>alert('x')</script>" not in text


def test_create_map_supports_raw_source_records(tmp_path: Path):
    now = pd.Timestamp.now(tz="UTC").floor("s").isoformat()
    frame = pd.DataFrame(
        [
            {
                "platform": "weibo",
                "native_id": "123",
                "content_type": "post",
                "published_at": now,
                "author_name": "Example account",
                "translated_text": "Public post",
                "inferred_location": "Beijing, China",
                "location_confidence": 0.8,
                "latitude": 39.9042,
                "longitude": 116.4074,
                "canonical_url": "https://m.weibo.cn/detail/123",
                "source_mode": "weibo_public_status_anonymous",
            }
        ]
    )
    path = tmp_path / "posts_map.html"

    create_map(frame, path)
    text = path.read_text(encoding="utf-8")

    assert "Source records" in text
    assert "Weibo Post" in text
    assert "weibo_public_status_anonymous" in text


def test_run_map_accepts_observation_xlsx_and_custom_title(tmp_path: Path):
    source = tmp_path / "observations.xlsx"
    output = tmp_path / "map.html"
    with pd.ExcelWriter(source, engine="openpyxl") as writer:
        _observation_frame().to_excel(writer, sheet_name="observations", index=False)

    outputs = run_map(
        {
            "source_file": str(source),
            "output_file": str(output),
            "map": {
                "title": "Americanspaces / PRC Activity",
                "heat_windows": [30, 180],
                "default_heat_window": 180,
            },
        }
    )

    assert outputs == [str(output.resolve())]
    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert "Americanspaces / PRC Activity" in text
    assert "Density — activity in last 180d" in text


def test_create_map_rejects_dataset_without_coordinates(tmp_path: Path):
    with pytest.raises(ValueError, match="No valid coordinates"):
        create_map(pd.DataFrame([{"title": "unmapped"}]), tmp_path / "map.html")
